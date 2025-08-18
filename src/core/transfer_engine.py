from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime

from src.data.models import Player, Squad, Transfer, TransferType
from src.utils.constants import FPLConstants, Position
from src.utils.logging import app_logger, log_transfer, log_decision
from src.utils.config import config


@dataclass
class TransferCandidate:
    """Represents a potential transfer"""
    player_out: Player
    player_in: Player
    expected_gain: float
    cost_difference: float
    reasoning: str
    
    @property
    def is_affordable(self) -> bool:
        return self.cost_difference <= 0
        
    @property
    def net_gain_after_hit(self) -> float:
        """Expected gain after accounting for transfer cost"""
        return self.expected_gain - FPLConstants.TRANSFER_COST_POINTS


class TransferEngine:
    """Manages transfer decisions and execution"""
    
    def __init__(self):
        self.min_transfer_gain = config.fpl.min_transfer_gain
        self.max_hit_cost = config.fpl.max_hit_cost
        
    def evaluate_transfers(
        self,
        current_squad: Squad,
        all_players: List[Player],
        gameweek_predictions: Dict[int, float],
        free_transfers: int,
        wildcard_active: bool = False,
        free_hit_active: bool = False
    ) -> List[TransferCandidate]:
        """
        Evaluate all possible transfers and return ranked candidates
        """
        app_logger.info(
            f"Evaluating transfers (FT: {free_transfers}, "
            f"WC: {wildcard_active}, FH: {free_hit_active})"
        )
        
        candidates = []
        current_player_ids = {p.id for p in current_squad.players}
        
        # Group players by position for like-for-like comparisons
        position_groups = self._group_by_position(all_players)
        squad_position_groups = self._group_by_position(current_squad.players)
        
        for position, available_players in position_groups.items():
            squad_players = squad_position_groups.get(position, [])
            
            # Skip if no players in this position in squad
            if not squad_players:
                continue
                
            # Sort available players by predicted points
            available_players.sort(
                key=lambda p: gameweek_predictions.get(p.id, 0),
                reverse=True
            )
            
            # Consider top players as potential transfers in
            for player_in in available_players[:20]:  # Top 20 per position
                if player_in.id in current_player_ids:
                    continue
                    
                # Find best player to transfer out
                for player_out in squad_players:
                    candidate = self._evaluate_single_transfer(
                        player_out,
                        player_in,
                        gameweek_predictions,
                        current_squad.remaining_budget
                    )
                    
                    if candidate and self._is_valid_transfer(
                        candidate,
                        current_squad,
                        wildcard_active,
                        free_hit_active
                    ):
                        candidates.append(candidate)
        
        # Sort by expected gain
        candidates.sort(key=lambda c: c.expected_gain, reverse=True)
        
        # Filter based on strategy
        filtered = self._filter_transfers(
            candidates,
            free_transfers,
            wildcard_active,
            free_hit_active
        )
        
        app_logger.info(f"Found {len(filtered)} viable transfer candidates")
        
        return filtered
    
    def execute_transfers(
        self,
        candidates: List[TransferCandidate],
        current_squad: Squad,
        free_transfers: int,
        gameweek: int,
        dry_run: bool = True
    ) -> Tuple[Squad, List[Transfer]]:
        """
        Execute the recommended transfers
        """
        if not candidates:
            app_logger.info("No transfers to execute")
            return current_squad, []
            
        transfers_to_make = self._select_transfers_to_make(
            candidates,
            free_transfers
        )
        
        if dry_run:
            app_logger.info(f"DRY RUN: Would make {len(transfers_to_make)} transfer(s)")
            for t in transfers_to_make:
                log_transfer(
                    t.player_in.web_name,
                    t.player_out.web_name,
                    expected_gain=t.expected_gain,
                    cost=t.cost_difference,
                    dry_run=True
                )
        
        # Create new squad
        new_players = current_squad.players.copy()
        executed_transfers = []
        
        for transfer in transfers_to_make:
            # Remove player out
            new_players = [p for p in new_players if p.id != transfer.player_out.id]
            # Add player in
            new_players.append(transfer.player_in)
            
            # Record transfer
            transfer_type = TransferType.FREE if len(executed_transfers) < free_transfers else TransferType.HIT
            
            executed_transfers.append(Transfer(
                gameweek=gameweek,
                player_in_id=transfer.player_in.id,
                player_out_id=transfer.player_out.id,
                player_in_cost=transfer.player_in.price,
                player_out_cost=transfer.player_out.price,
                transfer_type=transfer_type
            ))
            
            if not dry_run:
                log_transfer(
                    transfer.player_in.web_name,
                    transfer.player_out.web_name,
                    expected_gain=transfer.expected_gain,
                    cost=transfer.cost_difference,
                    transfer_type=transfer_type.value
                )
        
        new_squad = Squad(
            players=new_players,
            formation=current_squad.formation,
            captain_id=current_squad.captain_id,
            vice_captain_id=current_squad.vice_captain_id,
            budget=current_squad.budget,
            free_transfers=self._calculate_new_free_transfers(
                free_transfers,
                len(transfers_to_make)
            )
        )
        
        return new_squad, executed_transfers
    
    def handle_price_changes(
        self,
        current_squad: Squad,
        price_predictions: Dict[int, float]
    ) -> List[TransferCandidate]:
        """
        Handle players about to rise/fall in price
        """
        app_logger.info("Evaluating price change transfers")
        
        candidates = []
        
        for player in current_squad.players:
            predicted_change = price_predictions.get(player.id, 0)
            
            # Consider transferring out if about to fall
            if predicted_change < -0.1:
                log_decision(
                    "price_fall_risk",
                    player=player.web_name,
                    predicted_fall=predicted_change
                )
                # Find replacement before price fall
                # (Implementation would need price rise predictions)
        
        return candidates
    
    def handle_injuries(
        self,
        current_squad: Squad,
        all_players: List[Player],
        gameweek_predictions: Dict[int, float]
    ) -> List[TransferCandidate]:
        """
        Handle injured/suspended players
        """
        app_logger.info("Checking for injured/suspended players")
        
        injured_players = [
            p for p in current_squad.players
            if p.status != "a" or (
                p.chance_of_playing_this_round is not None and
                p.chance_of_playing_this_round < 75
            )
        ]
        
        if not injured_players:
            return []
            
        app_logger.warning(f"Found {len(injured_players)} injured/doubtful players")
        
        candidates = []
        position_groups = self._group_by_position(all_players)
        
        for injured in injured_players:
            position = Position(injured.element_type)
            replacements = position_groups.get(position, [])
            
            # Filter available players
            available = [
                p for p in replacements
                if p.status == "a" and
                p.id not in {pl.id for pl in current_squad.players} and
                p.price <= injured.price + current_squad.remaining_budget
            ]
            
            # Sort by predicted points
            available.sort(
                key=lambda p: gameweek_predictions.get(p.id, 0),
                reverse=True
            )
            
            if available:
                best_replacement = available[0]
                candidate = TransferCandidate(
                    player_out=injured,
                    player_in=best_replacement,
                    expected_gain=gameweek_predictions.get(best_replacement.id, 0) - 
                                 gameweek_predictions.get(injured.id, 0),
                    cost_difference=best_replacement.price - injured.price,
                    reasoning=f"Injury replacement: {injured.news}"
                )
                candidates.append(candidate)
                
                log_decision(
                    "injury_transfer",
                    player_out=injured.web_name,
                    player_in=best_replacement.web_name,
                    injury_status=injured.status,
                    news=injured.news
                )
        
        return candidates
    
    def calculate_wildcard_squad(
        self,
        all_players: List[Player],
        gameweek_predictions: Dict[int, float],
        budget: float = FPLConstants.INITIAL_BUDGET
    ) -> Squad:
        """
        Calculate optimal squad for wildcard
        """
        app_logger.info("Calculating optimal wildcard squad")
        
        # Use squad optimizer to build from scratch
        from src.core.squad_optimizer import SquadOptimizer
        
        optimizer = SquadOptimizer()
        
        # Filter to available players only
        available_players = [
            p for p in all_players
            if p.status == "a"
        ]
        
        # Build optimal squad
        squad = optimizer.optimize_initial_squad(
            available_players,
            budget=budget,
            fixture_difficulties=None  # Would need fixture data
        )
        
        log_decision(
            "wildcard_squad",
            total_players=len(squad.players),
            total_value=squad.value,
            formation=squad.formation
        )
        
        return squad
    
    def _evaluate_single_transfer(
        self,
        player_out: Player,
        player_in: Player,
        predictions: Dict[int, float],
        budget: float
    ) -> Optional[TransferCandidate]:
        """Evaluate a single transfer"""
        
        # Check affordability
        cost_diff = player_in.price - player_out.price
        if cost_diff > budget:
            return None
            
        # Calculate expected gain
        expected_out = predictions.get(player_out.id, player_out.points_per_game * 3)
        expected_in = predictions.get(player_in.id, player_in.points_per_game * 3)
        expected_gain = expected_in - expected_out
        
        # Build reasoning
        reasons = []
        if player_in.form > player_out.form:
            reasons.append(f"Better form ({player_in.form:.1f} vs {player_out.form:.1f})")
        if expected_gain > 0:
            reasons.append(f"Higher expected points (+{expected_gain:.1f})")
        if cost_diff < 0:
            reasons.append(f"Frees up £{-cost_diff:.1f}m")
            
        reasoning = ", ".join(reasons) if reasons else "Strategic transfer"
        
        return TransferCandidate(
            player_out=player_out,
            player_in=player_in,
            expected_gain=expected_gain,
            cost_difference=cost_diff,
            reasoning=reasoning
        )
    
    def _is_valid_transfer(
        self,
        candidate: TransferCandidate,
        squad: Squad,
        wildcard: bool,
        free_hit: bool
    ) -> bool:
        """Check if transfer maintains squad validity"""
        
        # Always valid on wildcard/free hit
        if wildcard or free_hit:
            return True
            
        # Check if maintains team limits
        new_team_count = sum(
            1 for p in squad.players
            if p.team == candidate.player_in.team and p.id != candidate.player_out.id
        )
        
        if new_team_count >= FPLConstants.MAX_PLAYERS_PER_TEAM:
            return False
            
        # Check minimum expected gain
        if candidate.expected_gain < self.min_transfer_gain:
            return False
            
        return True
    
    def _filter_transfers(
        self,
        candidates: List[TransferCandidate],
        free_transfers: int,
        wildcard: bool,
        free_hit: bool
    ) -> List[TransferCandidate]:
        """Filter transfers based on strategy"""
        
        if wildcard or free_hit:
            # Return all positive transfers
            return [c for c in candidates if c.expected_gain > 0]
            
        filtered = []
        
        for i, candidate in enumerate(candidates):
            # First N transfers should have positive gain
            if i < free_transfers:
                if candidate.expected_gain >= self.min_transfer_gain:
                    filtered.append(candidate)
            else:
                # Hits must overcome the -4 cost
                if candidate.net_gain_after_hit >= self.min_transfer_gain:
                    filtered.append(candidate)
                    
            # Limit total hits
            if len(filtered) >= free_transfers + (self.max_hit_cost // 4):
                break
                
        return filtered
    
    def _select_transfers_to_make(
        self,
        candidates: List[TransferCandidate],
        free_transfers: int
    ) -> List[TransferCandidate]:
        """Select which transfers to actually make"""
        
        selected = []
        used_out_ids = set()
        used_in_ids = set()
        
        for candidate in candidates:
            # Avoid duplicate transfers
            if (candidate.player_out.id in used_out_ids or
                candidate.player_in.id in used_in_ids):
                continue
                
            # Check if worth a hit
            if len(selected) >= free_transfers:
                if candidate.net_gain_after_hit < self.min_transfer_gain:
                    break
                    
            selected.append(candidate)
            used_out_ids.add(candidate.player_out.id)
            used_in_ids.add(candidate.player_in.id)
            
        return selected
    
    def _calculate_new_free_transfers(
        self,
        current_ft: int,
        transfers_made: int
    ) -> int:
        """Calculate free transfers for next week"""
        
        if transfers_made == 0:
            # Bank a transfer (max 5)
            return min(current_ft + 1, FPLConstants.MAX_BANKED_TRANSFERS)
        else:
            # Used transfers, get 1 next week
            return 1
    
    def _group_by_position(
        self,
        players: List[Player]
    ) -> Dict[Position, List[Player]]:
        """Group players by position"""
        
        groups = {pos: [] for pos in Position}
        
        for player in players:
            position = Position(player.element_type)
            groups[position].append(player)
            
        return groups