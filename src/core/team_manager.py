import asyncio
from typing import List, Dict, Optional, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass

from src.api.fpl_client import FPLClient, FPLDataProcessor
from src.core.squad_optimizer import SquadOptimizer
from src.core.transfer_engine import TransferEngine, TransferCandidate
from src.strategies.captain_selector import CaptainSelector
from src.strategies.chips import ChipStrategy
from src.analysis.player_analyzer import PlayerAnalyzer
from src.data.models import (
    Squad, Player, Fixture, GameWeek, Transfer,
    ChipUsage, ChipType, ManagerHistory
)
from src.utils.constants import FPLConstants, Chip
from src.utils.logging import app_logger, LogContext, log_decision
from src.utils.config import config


@dataclass
class GameWeekDecision:
    """Complete decision for a gameweek"""
    gameweek: int
    transfers: List[TransferCandidate]
    captain_id: int
    vice_captain_id: int
    chip: Optional[Chip] = None
    formation: Tuple[int, int, int, int] = (1, 4, 4, 2)
    bench_order: List[int] = None


class TeamManager:
    """Main orchestrator for FPL team management"""
    
    def __init__(self):
        self.api_client = FPLClient()
        self.squad_optimizer = SquadOptimizer()
        self.transfer_engine = TransferEngine()
        self.captain_selector = CaptainSelector()
        self.chip_strategy = ChipStrategy()
        self.player_analyzer = PlayerAnalyzer()
        self.data_processor = FPLDataProcessor()
        
        self.current_squad: Optional[Squad] = None
        self.chips_used: List[ChipUsage] = []
        self.transfer_history: List[Transfer] = []
        self.manager_history: List[ManagerHistory] = []
        
    async def initialize(self, manager_id: Optional[int] = None):
        """Initialize the team manager"""
        
        async with self.api_client:
            if manager_id:
                # Load existing team
                app_logger.info(f"Loading team for manager {manager_id}")
                await self._load_existing_team(manager_id)
            else:
                # Create new team
                app_logger.info("Creating new team")
                await self._create_initial_team()
                
    async def run_gameweek(
        self,
        gameweek: Optional[int] = None,
        dry_run: bool = True
    ) -> GameWeekDecision:
        """
        Run complete gameweek analysis and make decisions
        """
        
        async with self.api_client:
            with LogContext("gameweek_run", dry_run=dry_run):
                # Get current gameweek if not specified
                if not gameweek:
                    gameweek = await self.api_client.get_current_gameweek()
                    
                app_logger.info(f"Running gameweek {gameweek} analysis")
                
                # Fetch all required data
                data = await self._fetch_gameweek_data(gameweek)
                
                # Analyze squad health
                team_issues = self._analyze_squad_health(data["players"])
                
                # Make chip decision
                chip_decision = self._decide_chip_usage(
                    gameweek,
                    data["fixtures"],
                    data["predictions"],
                    team_issues
                )
                
                # Make transfer decisions
                transfer_decisions = await self._make_transfer_decisions(
                    data["players"],
                    data["predictions"],
                    chip_decision
                )
                
                # Execute transfers
                if transfer_decisions and not dry_run:
                    await self._execute_transfers(transfer_decisions, gameweek)
                    
                # Select captain and vice-captain
                captain, vice = await self._select_captains(
                    data["predictions"],
                    data["fixtures"],
                    chip_decision
                )
                
                # Optimize formation and bench
                formation, bench = await self._optimize_lineup(data["predictions"])
                
                # Create decision object
                decision = GameWeekDecision(
                    gameweek=gameweek,
                    transfers=transfer_decisions,
                    captain_id=captain.player.id,
                    vice_captain_id=vice.player.id,
                    chip=chip_decision.chip if chip_decision else None,
                    formation=formation,
                    bench_order=[p.id for p in bench]
                )
                
                # Log summary
                self._log_gameweek_summary(decision)
                
                return decision
                
    async def monitor_deadlines(self):
        """Monitor and act before deadlines"""
        
        app_logger.info("Starting deadline monitoring")
        
        while True:
            try:
                async with self.api_client:
                    deadline = await self.api_client.get_deadline_time()
                    
                    if deadline:
                        time_to_deadline = deadline - datetime.now()
                        warning_time = timedelta(hours=config.deadline_warning_hours)
                        
                        if time_to_deadline <= warning_time:
                            app_logger.warning(
                                f"Deadline approaching in {time_to_deadline.total_seconds() / 3600:.1f} hours"
                            )
                            
                            # Run gameweek decisions
                            gameweek = await self.api_client.get_current_gameweek()
                            await self.run_gameweek(gameweek, dry_run=config.dry_run)
                            
                            # Wait until after deadline
                            await asyncio.sleep(time_to_deadline.total_seconds() + 300)
                        else:
                            # Check again in an hour
                            await asyncio.sleep(3600)
                    else:
                        # No deadline found, wait and retry
                        await asyncio.sleep(3600)
                        
            except Exception as e:
                app_logger.error(f"Error in deadline monitoring: {e}")
                await asyncio.sleep(300)  # Wait 5 minutes on error
                
    async def _load_existing_team(self, manager_id: int):
        """Load existing team data"""
        
        # Get manager data
        manager_data = await self.api_client.get_manager_data(manager_id)
        
        # Get current gameweek
        current_gw = await self.api_client.get_current_gameweek()
        
        # Get manager's current picks
        picks_data = await self.api_client.get_manager_picks(manager_id, current_gw)
        
        # Get all players data
        all_players_data = await self.api_client.get_all_players()
        
        # Build current squad
        squad_player_ids = [p["element"] for p in picks_data.get("picks", [])]
        squad_players = []
        
        for player_data in all_players_data:
            if player_data["id"] in squad_player_ids:
                player = Player(**player_data)
                squad_players.append(player)
                
        self.current_squad = Squad(
            players=squad_players,
            budget=100.0,  # Would need to calculate from bank + team value
            free_transfers=picks_data.get("entry_history", {}).get("event_transfers", 1)
        )
        
        # Load history
        history_data = await self.api_client.get_manager_history(manager_id)
        
        for event in history_data.get("current", []):
            self.manager_history.append(ManagerHistory(**event))
            
        # Load chips used
        for chip_event in history_data.get("chips", []):
            chip_type = ChipType(chip_event["name"])
            gameweek = chip_event["event"]
            phase = "first_half" if gameweek <= 19 else "second_half"
            
            self.chips_used.append(ChipUsage(
                gameweek=gameweek,
                chip=chip_type,
                phase=phase
            ))
            
        app_logger.info(f"Loaded team with {len(squad_players)} players")
        
    async def _create_initial_team(self):
        """Create initial team from scratch"""
        
        # Get all players
        all_players_data = await self.api_client.get_all_players()
        all_players = [Player(**p) for p in all_players_data]
        
        # Get fixtures for difficulty assessment
        fixtures_data = await self.api_client.get_fixtures()
        
        # Calculate fixture difficulties
        fixture_difficulties = {}
        for team_id in range(1, 21):  # 20 teams
            team_fixtures = [f for f in fixtures_data if 
                            f["team_h"] == team_id or f["team_a"] == team_id]
            if team_fixtures:
                difficulties = []
                for f in team_fixtures[:5]:  # Next 5 fixtures
                    if f["team_h"] == team_id:
                        difficulties.append(f.get("team_h_difficulty", 3))
                    else:
                        difficulties.append(f.get("team_a_difficulty", 3))
                fixture_difficulties[team_id] = sum(difficulties) / len(difficulties)
                
        # Optimize initial squad
        self.current_squad = self.squad_optimizer.optimize_initial_squad(
            all_players,
            budget=FPLConstants.INITIAL_BUDGET,
            fixture_difficulties=fixture_difficulties
        )
        
        app_logger.info(f"Created initial squad with {len(self.current_squad.players)} players")
        
    async def _fetch_gameweek_data(self, gameweek: int) -> Dict:
        """Fetch all data needed for gameweek decisions"""
        
        app_logger.info(f"Fetching data for gameweek {gameweek}")
        
        # Fetch in parallel for efficiency
        tasks = [
            self.api_client.get_all_players(),
            self.api_client.get_fixtures(gameweek),
            self.api_client.get_gameweek_live_data(gameweek),
            self.api_client.get_bootstrap_data()
        ]
        
        results = await asyncio.gather(*tasks)
        
        players_data, fixtures_data, live_data, bootstrap_data = results
        
        # Convert to models
        players = [Player(**p) for p in players_data]
        fixtures = [Fixture(**f) for f in fixtures_data]
        
        # Generate predictions
        predictions = await self._generate_predictions(players, fixtures)
        
        return {
            "players": players,
            "fixtures": fixtures,
            "live_data": live_data,
            "bootstrap": bootstrap_data,
            "predictions": predictions
        }
        
    async def _generate_predictions(
        self,
        players: List[Player],
        fixtures: List[Fixture]
    ) -> Dict[int, float]:
        """Generate point predictions for all players"""
        
        predictions = {}
        
        for player in players:
            # Get player's fixtures
            player_fixtures = [
                f for f in fixtures
                if f.team_h == player.team or f.team_a == player.team
            ]
            
            if not player_fixtures:
                predictions[player.id] = 0
                continue
                
            fixture = player_fixtures[0]
            is_home = fixture.team_h == player.team
            
            # Simple prediction based on form and difficulty
            difficulty = fixture.team_h_difficulty if is_home else fixture.team_a_difficulty
            base_points = player.points_per_game
            
            # Adjust for difficulty
            difficulty_multiplier = {
                1: 1.3, 2: 1.15, 3: 1.0, 4: 0.85, 5: 0.7
            }.get(difficulty, 1.0)
            
            # Adjust for home/away
            venue_multiplier = 1.1 if is_home else 0.9
            
            # Adjust for form
            form_multiplier = min(player.form / 5.0, 1.5) if player.form else 1.0
            
            predicted = base_points * difficulty_multiplier * venue_multiplier * form_multiplier
            
            # Adjust for availability
            if player.status != "a":
                predicted *= 0.1
            elif player.chance_of_playing_this_round:
                predicted *= player.chance_of_playing_this_round / 100
                
            predictions[player.id] = predicted
            
        return predictions
        
    def _analyze_squad_health(self, all_players: List[Player]) -> List[str]:
        """Analyze current squad for issues"""
        
        issues = []
        
        if not self.current_squad:
            return ["No squad loaded"]
            
        # Check injuries
        for player in self.current_squad.players:
            current_player = next((p for p in all_players if p.id == player.id), None)
            if current_player:
                if current_player.status != "a":
                    issues.append(f"{current_player.web_name} injured/suspended")
                elif current_player.chance_of_playing_this_round and \
                     current_player.chance_of_playing_this_round < 75:
                    issues.append(f"{current_player.web_name} doubtful ({current_player.chance_of_playing_this_round}%)")
                    
        # Check poor form
        for player in self.current_squad.players:
            current_player = next((p for p in all_players if p.id == player.id), None)
            if current_player and current_player.form < 2.0:
                issues.append(f"{current_player.web_name} poor form ({current_player.form})")
                
        # Check value drops
        for player in self.current_squad.players:
            current_player = next((p for p in all_players if p.id == player.id), None)
            if current_player:
                value_change = current_player.cost_change_start
                if value_change < -0.3:
                    issues.append(f"{current_player.web_name} value dropped £{-value_change/10:.1f}m")
                    
        return issues
        
    def _decide_chip_usage(
        self,
        gameweek: int,
        fixtures: List[Fixture],
        predictions: Dict[int, float],
        team_issues: List[str]
    ) -> Optional:
        """Decide whether to use a chip"""
        
        if not self.current_squad:
            return None
            
        return self.chip_strategy.evaluate_chip_usage(
            self.current_squad,
            gameweek,
            self.chips_used,
            fixtures,
            predictions,
            team_issues
        )
        
    async def _make_transfer_decisions(
        self,
        all_players: List[Player],
        predictions: Dict[int, float],
        chip_decision
    ) -> List[TransferCandidate]:
        """Make transfer decisions"""
        
        if not self.current_squad:
            return []
            
        # Check if using wildcard or free hit
        wildcard_active = chip_decision and chip_decision.chip == Chip.WILDCARD
        free_hit_active = chip_decision and chip_decision.chip == Chip.FREE_HIT
        
        if wildcard_active:
            # Build new squad from scratch
            new_squad = self.transfer_engine.calculate_wildcard_squad(
                all_players,
                predictions,
                budget=100.0
            )
            # Generate transfer list
            # This would need more complex logic to map old to new
            return []
            
        # Normal transfers
        return self.transfer_engine.evaluate_transfers(
            self.current_squad,
            all_players,
            predictions,
            self.current_squad.free_transfers,
            wildcard_active,
            free_hit_active
        )
        
    async def _execute_transfers(
        self,
        transfers: List[TransferCandidate],
        gameweek: int
    ):
        """Execute the transfers"""
        
        if not self.current_squad:
            return
            
        new_squad, executed = self.transfer_engine.execute_transfers(
            transfers,
            self.current_squad,
            self.current_squad.free_transfers,
            gameweek,
            dry_run=config.dry_run
        )
        
        self.current_squad = new_squad
        self.transfer_history.extend(executed)
        
    async def _select_captains(
        self,
        predictions: Dict[int, float],
        fixtures: List[Fixture],
        chip_decision
    ):
        """Select captain and vice-captain"""
        
        if not self.current_squad:
            return None, None
            
        triple_captain = chip_decision and chip_decision.chip == Chip.TRIPLE_CAPTAIN
        
        return self.captain_selector.select_captain_and_vice(
            self.current_squad,
            predictions,
            fixtures,
            None,  # Would need ownership data
            triple_captain
        )
        
    async def _optimize_lineup(
        self,
        predictions: Dict[int, float]
    ) -> Tuple[Tuple[int, int, int, int], List[Player]]:
        """Optimize formation and bench order"""
        
        if not self.current_squad:
            return (1, 4, 4, 2), []
            
        starting, bench = self.squad_optimizer.optimize_starting_xi(
            self.current_squad,
            predictions
        )
        
        # Determine formation from starting XI
        formation = self._determine_formation(starting)
        
        return formation, bench
        
    def _determine_formation(self, starting_xi: List[Player]) -> Tuple[int, int, int, int]:
        """Determine formation from starting XI"""
        
        counts = {1: 0, 2: 0, 3: 0, 4: 0}
        
        for player in starting_xi:
            counts[player.element_type] += 1
            
        return (counts[1], counts[2], counts[3], counts[4])
        
    def _log_gameweek_summary(self, decision: GameWeekDecision):
        """Log summary of gameweek decisions"""
        
        log_decision(
            "gameweek_summary",
            gameweek=decision.gameweek,
            transfers=len(decision.transfers),
            captain_id=decision.captain_id,
            vice_captain_id=decision.vice_captain_id,
            chip=decision.chip.value if decision.chip else None,
            formation=decision.formation
        )