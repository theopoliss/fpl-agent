import pulp
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
import numpy as np

from src.data.models import Player, Squad
from src.utils.constants import FPLConstants, Position, FormationValidator
from src.utils.logging import app_logger, log_decision
from src.utils.config import config


@dataclass
class OptimizationObjective:
    """Defines objectives for squad optimization"""
    points_weight: float = 1.0
    form_weight: float = 0.3
    fixture_weight: float = 0.2
    value_weight: float = 0.1
    
    def calculate_score(
        self,
        player: Player,
        fixture_difficulty: float = 3.0,
        next_n_fixtures: int = 5
    ) -> float:
        """Calculate weighted score for a player"""
        # Normalize metrics
        points_score = player.total_points / 38  # Normalize by gameweeks
        form_score = float(player.form) if player.form else 0
        fixture_score = (5 - fixture_difficulty) / 4  # Invert and normalize
        value_score = player.value_score
        
        return (
            self.points_weight * points_score +
            self.form_weight * form_score +
            self.fixture_weight * fixture_score +
            self.value_weight * value_score
        )


class SquadOptimizer:
    """Optimizes squad selection using linear programming"""
    
    def __init__(self):
        self.objective = OptimizationObjective(
            points_weight=config.optimization.points_weight,
            form_weight=config.optimization.form_weight,
            fixture_weight=config.optimization.fixture_weight,
            value_weight=config.optimization.value_weight
        )
        
    def optimize_initial_squad(
        self,
        players: List[Player],
        budget: float = FPLConstants.INITIAL_BUDGET,
        fixture_difficulties: Optional[Dict[int, float]] = None
    ) -> Squad:
        """
        Select optimal initial squad within budget constraints
        """
        app_logger.info(f"Optimizing initial squad with budget £{budget}m")
        
        # Create LP problem
        prob = pulp.LpProblem("FPL_Squad_Selection", pulp.LpMaximize)
        
        # Decision variables - binary for each player
        player_vars = {}
        for p in players:
            player_vars[p.id] = pulp.LpVariable(
                f"player_{p.id}", cat="Binary"
            )
        
        # Calculate scores for objective function
        scores = {}
        for p in players:
            fixture_diff = fixture_difficulties.get(p.team, 3.0) if fixture_difficulties else 3.0
            scores[p.id] = self.objective.calculate_score(p, fixture_diff)
        
        # Objective: maximize total score
        prob += pulp.lpSum([
            player_vars[p.id] * scores[p.id] for p in players
        ])
        
        # Constraints
        
        # 1. Squad size constraint
        prob += pulp.lpSum([player_vars[p.id] for p in players]) == FPLConstants.SQUAD_SIZE
        
        # 2. Budget constraint
        prob += pulp.lpSum([
            player_vars[p.id] * (p.now_cost / 10) for p in players
        ]) <= budget
        
        # 3. Position constraints
        for position in Position:
            position_players = [p for p in players if p.element_type == position.value]
            required = FPLConstants.SQUAD_REQUIREMENTS[position]
            
            prob += pulp.lpSum([
                player_vars[p.id] for p in position_players
            ]) == required
        
        # 4. Team constraints (max 3 per team)
        teams = set(p.team for p in players)
        for team in teams:
            team_players = [p for p in players if p.team == team]
            prob += pulp.lpSum([
                player_vars[p.id] for p in team_players
            ]) <= FPLConstants.MAX_PLAYERS_PER_TEAM
        
        # 5. Ensure minimum quality players (optional)
        # At least 3 players above average price in starting positions
        avg_prices = {
            Position.GOALKEEPER: 50,  # £5.0m
            Position.DEFENDER: 55,    # £5.5m
            Position.MIDFIELDER: 75,  # £7.5m
            Position.FORWARD: 75,     # £7.5m
        }
        
        for position in [Position.DEFENDER, Position.MIDFIELDER, Position.FORWARD]:
            quality_players = [
                p for p in players 
                if p.element_type == position.value and p.now_cost >= avg_prices[position]
            ]
            prob += pulp.lpSum([
                player_vars[p.id] for p in quality_players
            ]) >= 2
        
        # Solve the problem
        solver = pulp.PULP_CBC_CMD(
            timeLimit=config.optimization.time_limit,
            msg=1 if config.debug else 0
        )
        prob.solve(solver)
        
        # Extract solution
        if prob.status != pulp.LpStatusOptimal:
            app_logger.warning(f"Optimization status: {pulp.LpStatus[prob.status]}")
        
        selected_players = []
        for p in players:
            if player_vars[p.id].varValue == 1:
                selected_players.append(p)
        
        # Create squad with optimal formation
        squad = Squad(
            players=selected_players,
            budget=budget,
            formation=self._suggest_formation(selected_players)
        )
        
        app_logger.info(
            f"Selected {len(selected_players)} players, "
            f"Total cost: £{squad.value:.1f}m, "
            f"Remaining: £{squad.remaining_budget:.1f}m"
        )
        
        log_decision(
            "initial_squad",
            players_selected=len(selected_players),
            total_cost=squad.value,
            formation=squad.formation
        )
        
        return squad
    
    def optimize_starting_xi(
        self,
        squad: Squad,
        gameweek_predictions: Optional[Dict[int, float]] = None
    ) -> Tuple[List[Player], List[Player]]:
        """
        Select optimal starting XI and bench order
        """
        app_logger.info(f"Optimizing starting XI for formation {squad.formation}")
        
        # If no predictions, use total points
        if not gameweek_predictions:
            gameweek_predictions = {p.id: p.total_points for p in squad.players}
        
        # Create LP problem
        prob = pulp.LpProblem("Starting_XI_Selection", pulp.LpMaximize)
        
        # Decision variables
        starting_vars = {}
        for p in squad.players:
            starting_vars[p.id] = pulp.LpVariable(
                f"start_{p.id}", cat="Binary"
            )
        
        # Objective: maximize predicted points
        prob += pulp.lpSum([
            starting_vars[p.id] * gameweek_predictions.get(p.id, 0)
            for p in squad.players
        ])
        
        # Constraints
        
        # 1. Exactly 11 players
        prob += pulp.lpSum([
            starting_vars[p.id] for p in squad.players
        ]) == FPLConstants.STARTING_XI_SIZE
        
        # 2. Formation constraints
        gk, def_, mid, fwd = squad.formation
        
        # Goalkeepers
        gk_players = [p for p in squad.players if p.element_type == Position.GOALKEEPER.value]
        prob += pulp.lpSum([starting_vars[p.id] for p in gk_players]) == gk
        
        # Defenders
        def_players = [p for p in squad.players if p.element_type == Position.DEFENDER.value]
        prob += pulp.lpSum([starting_vars[p.id] for p in def_players]) == def_
        
        # Midfielders
        mid_players = [p for p in squad.players if p.element_type == Position.MIDFIELDER.value]
        prob += pulp.lpSum([starting_vars[p.id] for p in mid_players]) == mid
        
        # Forwards
        fwd_players = [p for p in squad.players if p.element_type == Position.FORWARD.value]
        prob += pulp.lpSum([starting_vars[p.id] for p in fwd_players]) == fwd
        
        # Solve
        solver = pulp.PULP_CBC_CMD(msg=0)
        prob.solve(solver)
        
        # Extract solution
        starting_xi = []
        bench = []
        
        for p in squad.players:
            if starting_vars[p.id].varValue == 1:
                starting_xi.append(p)
            else:
                bench.append(p)
        
        # Order bench by priority (GK first, then by predicted points)
        bench = self._order_bench(bench, gameweek_predictions)
        
        app_logger.info(f"Selected starting XI with total predicted points: {pulp.value(prob.objective):.1f}")
        
        return starting_xi, bench
    
    def optimize_transfers(
        self,
        current_squad: Squad,
        all_players: List[Player],
        free_transfers: int,
        max_hits: int = 2,
        gameweek_predictions: Optional[Dict[int, float]] = None
    ) -> List[Tuple[Player, Player]]:
        """
        Optimize transfers for maximum gain
        Returns list of (player_out, player_in) tuples
        """
        app_logger.info(f"Optimizing transfers (FT: {free_transfers}, max hits: {max_hits})")
        
        if not gameweek_predictions:
            gameweek_predictions = {p.id: p.total_points for p in all_players}
        
        # Create LP problem
        prob = pulp.LpProblem("Transfer_Optimization", pulp.LpMaximize)
        
        # Current squad IDs
        current_ids = {p.id for p in current_squad.players}
        
        # Decision variables
        # Binary variable for each player (in squad or not)
        in_squad = {}
        for p in all_players:
            in_squad[p.id] = pulp.LpVariable(f"squad_{p.id}", cat="Binary")
            # Set initial values for current squad
            if p.id in current_ids:
                in_squad[p.id].setInitialValue(1)
        
        # Transfer variables
        transfers_in = {}
        transfers_out = {}
        for p in all_players:
            if p.id not in current_ids:
                transfers_in[p.id] = pulp.LpVariable(f"in_{p.id}", cat="Binary")
            if p.id in current_ids:
                transfers_out[p.id] = pulp.LpVariable(f"out_{p.id}", cat="Binary")
        
        # Calculate net gain for objective
        # Gain from new players minus cost of hits
        max_transfers = free_transfers + max_hits
        hit_cost = FPLConstants.TRANSFER_COST_POINTS
        
        # Objective: maximize squad value minus transfer costs
        prob += pulp.lpSum([
            in_squad[p.id] * gameweek_predictions.get(p.id, 0)
            for p in all_players
        ]) - pulp.lpSum([
            transfers_in.get(p.id, 0) * hit_cost
            for p in all_players if p.id not in current_ids
        ]) * pulp.LpVariable("hits_taken", 0, max_hits, cat="Integer")
        
        # Constraints
        
        # 1. Squad size
        prob += pulp.lpSum([in_squad[p.id] for p in all_players]) == FPLConstants.SQUAD_SIZE
        
        # 2. Budget constraint
        current_value = sum(p.now_cost for p in current_squad.players) / 10
        remaining_budget = current_squad.remaining_budget
        
        prob += pulp.lpSum([
            in_squad[p.id] * (p.now_cost / 10) for p in all_players
        ]) <= current_value + remaining_budget
        
        # 3. Position constraints
        for position in Position:
            position_players = [p for p in all_players if p.element_type == position.value]
            required = FPLConstants.SQUAD_REQUIREMENTS[position]
            prob += pulp.lpSum([
                in_squad[p.id] for p in position_players
            ]) == required
        
        # 4. Team constraints
        teams = set(p.team for p in all_players)
        for team in teams:
            team_players = [p for p in all_players if p.team == team]
            prob += pulp.lpSum([
                in_squad[p.id] for p in team_players
            ]) <= FPLConstants.MAX_PLAYERS_PER_TEAM
        
        # 5. Transfer constraints
        prob += pulp.lpSum([
            transfers_in.get(p.id, 0) for p in all_players if p.id not in current_ids
        ]) <= max_transfers
        
        prob += pulp.lpSum([
            transfers_out.get(p.id, 0) for p in all_players if p.id in current_ids
        ]) <= max_transfers
        
        # Transfer balance
        prob += pulp.lpSum([
            transfers_in.get(p.id, 0) for p in all_players if p.id not in current_ids
        ]) == pulp.lpSum([
            transfers_out.get(p.id, 0) for p in all_players if p.id in current_ids
        ])
        
        # Solve
        solver = pulp.PULP_CBC_CMD(
            timeLimit=config.optimization.time_limit,
            msg=1 if config.debug else 0
        )
        prob.solve(solver)
        
        # Extract transfers
        transfers = []
        
        players_out = []
        players_in = []
        
        for p in all_players:
            if p.id in current_ids and transfers_out.get(p.id, 0).varValue == 1:
                players_out.append(p)
            elif p.id not in current_ids and transfers_in.get(p.id, 0).varValue == 1:
                players_in.append(p)
        
        # Match transfers (simple pairing for now)
        for p_out, p_in in zip(players_out, players_in):
            transfers.append((p_out, p_in))
        
        if transfers:
            app_logger.info(f"Recommended {len(transfers)} transfer(s)")
            for p_out, p_in in transfers:
                log_decision(
                    "transfer_recommendation",
                    player_out=p_out.web_name,
                    player_in=p_in.web_name,
                    cost_diff=(p_in.now_cost - p_out.now_cost) / 10,
                    points_gain=gameweek_predictions.get(p_in.id, 0) - gameweek_predictions.get(p_out.id, 0)
                )
        
        return transfers
    
    def _suggest_formation(self, players: List[Player]) -> Tuple[int, int, int, int]:
        """Suggest optimal formation based on player strengths"""
        # Count players by position
        position_counts = {
            Position.GOALKEEPER: 0,
            Position.DEFENDER: 0,
            Position.MIDFIELDER: 0,
            Position.FORWARD: 0,
        }
        
        for p in players:
            pos = Position(p.element_type)
            position_counts[pos] += 1
        
        # Get average points by position
        position_avg_points = {}
        for pos in Position:
            pos_players = [p for p in players if p.element_type == pos.value]
            if pos_players:
                # Sort by total points and take top players that might start
                pos_players.sort(key=lambda x: x.total_points, reverse=True)
                
                if pos == Position.GOALKEEPER:
                    avg = pos_players[0].total_points if pos_players else 0
                elif pos == Position.DEFENDER:
                    avg = np.mean([p.total_points for p in pos_players[:5]])
                elif pos == Position.MIDFIELDER:
                    avg = np.mean([p.total_points for p in pos_players[:5]])
                else:  # Forward
                    avg = np.mean([p.total_points for p in pos_players[:3]])
                
                position_avg_points[pos] = avg
        
        # Suggest formation based on strength
        # Prefer more players in stronger positions
        best_formation = (1, 4, 4, 2)  # Default
        best_score = 0
        
        for formation in FPLConstants.VALID_FORMATIONS:
            gk, def_, mid, fwd = formation
            
            # Calculate expected points for this formation
            score = (
                position_avg_points.get(Position.GOALKEEPER, 0) * gk +
                position_avg_points.get(Position.DEFENDER, 0) * def_ +
                position_avg_points.get(Position.MIDFIELDER, 0) * mid +
                position_avg_points.get(Position.FORWARD, 0) * fwd
            )
            
            if score > best_score:
                best_score = score
                best_formation = formation
        
        return best_formation
    
    def _order_bench(
        self,
        bench_players: List[Player],
        predictions: Dict[int, float]
    ) -> List[Player]:
        """Order bench players by priority"""
        # Goalkeeper must be first if on bench
        gk = [p for p in bench_players if p.element_type == Position.GOALKEEPER.value]
        others = [p for p in bench_players if p.element_type != Position.GOALKEEPER.value]
        
        # Sort others by predicted points
        others.sort(key=lambda p: predictions.get(p.id, 0), reverse=True)
        
        return gk + others