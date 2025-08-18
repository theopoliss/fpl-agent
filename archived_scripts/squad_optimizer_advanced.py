"""
Advanced squad optimizer that uses historical data, fixtures, and underlying stats
"""
import pulp
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
import numpy as np
from datetime import datetime

from src.data.models import Player, Squad
from src.api.fpl_client import FPLClient
from src.utils.constants import FPLConstants, Position, FormationValidator
from src.utils.logging import app_logger, log_decision
from src.utils.config import config


@dataclass
class PlayerScore:
    """Enhanced player scoring metrics"""
    player_id: int
    base_score: float  # Last season performance
    form_score: float  # Recent form
    fixture_score: float  # Next 5 fixtures
    value_score: float  # Points per million
    ownership_score: float  # Differential potential
    expected_score: float  # xG, xA based
    total_score: float  # Weighted combination


class AdvancedSquadOptimizer:
    """Enhanced squad optimizer using multiple data sources"""
    
    def __init__(self):
        self.weights = {
            'base': 0.70,      # Historical/last season - VERY HIGH
            'form': 0.05,      # Recent form - VERY LOW
            'fixtures': 0.10,  # Fixture difficulty
            'value': 0.10,     # Value for money
            'ownership': 0.03, # Differential 
            'expected': 0.02   # Expected stats
        }
        
    async def optimize_initial_squad_advanced(
        self,
        budget: float = FPLConstants.INITIAL_BUDGET
    ) -> Squad:
        """
        Select optimal initial squad using advanced metrics
        """
        app_logger.info(f"Advanced squad optimization with budget £{budget}m")
        
        async with FPLClient() as client:
            # Fetch all necessary data
            app_logger.info("Fetching player and fixture data...")
            
            # Get current player data
            bootstrap_data = await client.get_bootstrap_data()
            all_players_data = bootstrap_data.get('elements', [])
            teams_data = bootstrap_data.get('teams', [])
            
            # Get fixtures for difficulty analysis
            fixtures_data = await client.get_fixtures()
            
            # Convert to Player objects
            all_players = [Player(**p) for p in all_players_data]
            
            # Calculate advanced scores for each player
            app_logger.info("Calculating advanced player scores...")
            player_scores = await self._calculate_player_scores(
                all_players, 
                all_players_data,
                fixtures_data,
                teams_data
            )
            
            # Run optimization with advanced scores
            app_logger.info("Running optimization algorithm...")
            squad = self._optimize_with_scores(
                all_players,
                player_scores,
                budget
            )
            
            app_logger.info(
                f"Advanced optimization complete: {len(squad.players)} players, "
                f"£{squad.value:.1f}m spent"
            )
            
            return squad
    
    async def _calculate_player_scores(
        self,
        players: List[Player],
        players_data: List[Dict],
        fixtures: List[Dict],
        teams: List[Dict]
    ) -> Dict[int, PlayerScore]:
        """Calculate comprehensive scores for each player"""
        
        scores = {}
        
        for i, player in enumerate(players):
            player_data = players_data[i]
            
            # 1. Base score (last season + early season performance)
            base_score = self._calculate_base_score(player, player_data)
            
            # 2. Form score (recent games if available)
            form_score = self._calculate_form_score(player, player_data)
            
            # 3. Fixture score (next 5 gameweeks)
            fixture_score = self._calculate_fixture_score(
                player, fixtures, teams
            )
            
            # 4. Value score (expected points per million)
            value_score = self._calculate_value_score(player, player_data)
            
            # 5. Ownership/differential score
            ownership_score = self._calculate_ownership_score(player)
            
            # 6. Expected stats score (xG, xA, xGI)
            expected_score = self._calculate_expected_score(player, player_data)
            
            # Calculate weighted total
            total_score = (
                self.weights['base'] * base_score +
                self.weights['form'] * form_score +
                self.weights['fixtures'] * fixture_score +
                self.weights['value'] * value_score +
                self.weights['ownership'] * ownership_score +
                self.weights['expected'] * expected_score
            )
            
            scores[player.id] = PlayerScore(
                player_id=player.id,
                base_score=base_score,
                form_score=form_score,
                fixture_score=fixture_score,
                value_score=value_score,
                ownership_score=ownership_score,
                expected_score=expected_score,
                total_score=total_score
            )
        
        return scores
    
    def _calculate_base_score(self, player: Player, data: Dict) -> float:
        """Calculate base score from historical performance"""
        
        # If we're early in the season, weight last season heavily
        # Last season's total points (if available in data)
        last_season_total = data.get('last_season_points', 0)
        
        # Current season points (might be just GW1)
        current_points = player.total_points
        
        # Minutes played is important - regular starters are safer
        minutes_per_game = player.minutes / max(data.get('games_played', 1), 1)
        minutes_score = min(minutes_per_game / 90, 1.0)  # Normalize to 0-1
        
        # Combine factors
        if last_season_total > 0:
            # Weight last season more heavily early in season
            base = (last_season_total * 0.7 + current_points * 0.3) / 38
        else:
            # New player or promoted team player - use current form
            base = current_points * 2  # Project forward
        
        # Adjust for playing time
        base *= minutes_score
        
        # Normalize to 0-100 scale
        return min(base / 2, 100)
    
    def _calculate_form_score(self, player: Player, data: Dict) -> float:
        """Calculate form score from recent performances"""
        
        # Use the 'form' field which is last 5 games average
        form = float(player.form) if player.form else 0
        
        # Also consider:
        # - Recent transfers in/out
        transfers_balance = data.get('transfers_in_event', 0) - data.get('transfers_out_event', 0)
        transfer_momentum = min(max(transfers_balance / 100000, -1), 1)  # Normalize
        
        # Points per game if they've played
        ppg = player.points_per_game if player.points_per_game > 0 else form
        
        # Combine factors
        form_score = (
            form * 10 +  # Form is typically 0-10
            ppg * 5 +    # Points per game
            transfer_momentum * 10  # Market sentiment
        )
        
        return min(form_score, 100)
    
    def _calculate_fixture_score(
        self, 
        player: Player, 
        fixtures: List[Dict],
        teams: List[Dict]
    ) -> float:
        """Calculate fixture difficulty for next 5 games"""
        
        # Get player's team fixtures
        team_fixtures = [
            f for f in fixtures 
            if (f.get('team_h') == player.team or f.get('team_a') == player.team)
            and not f.get('finished', False)
        ][:5]  # Next 5 fixtures
        
        if not team_fixtures:
            return 50  # Neutral if no fixtures
        
        total_difficulty = 0
        for fixture in team_fixtures:
            if fixture.get('team_h') == player.team:
                # Home game
                difficulty = fixture.get('team_h_difficulty', 3)
                total_difficulty += (6 - difficulty) * 1.1  # Home advantage
            else:
                # Away game
                difficulty = fixture.get('team_a_difficulty', 3)
                total_difficulty += (6 - difficulty) * 0.9  # Away disadvantage
        
        # Average and normalize (1-5 scale to 0-100)
        avg_ease = total_difficulty / len(team_fixtures)
        return avg_ease * 20
    
    def _calculate_value_score(self, player: Player, data: Dict) -> float:
        """Calculate value for money score"""
        
        price = player.price
        
        # Expected points based on historical data
        if data.get('last_season_points', 0) > 0:
            expected_points = (
                data.get('last_season_points', 0) * 0.6 +
                player.total_points * 20 * 0.4  # Project current
            )
        else:
            expected_points = player.total_points * 20  # Project forward
        
        # Points per million
        if price > 0:
            ppm = expected_points / price
        else:
            ppm = 0
        
        # Normalize (good value is >20 ppm)
        return min(ppm * 5, 100)
    
    def _calculate_ownership_score(self, player: Player) -> float:
        """Calculate differential potential"""
        
        ownership = player.selected_by_percent
        
        # Low ownership but good stats = differential
        if ownership < 5 and player.form > 5:
            return 80
        elif ownership < 10 and player.form > 4:
            return 60
        elif ownership < 20:
            return 40
        elif ownership > 40:
            return 20  # Template player
        else:
            return 30
    
    def _calculate_expected_score(self, player: Player, data: Dict) -> float:
        """Calculate score based on underlying stats (xG, xA)"""
        
        # Expected goals and assists - convert to float
        xg = float(data.get('expected_goals', 0) or 0)
        xa = float(data.get('expected_assists', 0) or 0)
        xgi = float(data.get('expected_goal_involvements', 0) or 0)
        
        # Per 90 minutes rates
        minutes = max(player.minutes, 1)
        xg_90 = (xg / minutes) * 90 if minutes > 0 else 0
        xa_90 = (xa / minutes) * 90 if minutes > 0 else 0
        
        # Position-based weighting
        position = Position(player.element_type)
        
        if position == Position.FORWARD:
            score = xg_90 * 100 + xa_90 * 50
        elif position == Position.MIDFIELDER:
            score = xg_90 * 80 + xa_90 * 60
        elif position == Position.DEFENDER:
            score = xg_90 * 60 + xa_90 * 40
            # Add clean sheet potential
            xgc = float(data.get('expected_goals_conceded', 0) or 0)
            team_defense = max(0, 100 - xgc * 10)
            score += team_defense * 0.3
        else:  # Goalkeeper
            xgc = float(data.get('expected_goals_conceded', 0) or 0)
            score = max(0, 50 - xgc * 10)
        
        return min(score, 100)
    
    def _optimize_with_scores(
        self,
        players: List[Player],
        scores: Dict[int, PlayerScore],
        budget: float
    ) -> Squad:
        """Run optimization with calculated scores"""
        
        # Create LP problem
        prob = pulp.LpProblem("Advanced_FPL_Squad", pulp.LpMaximize)
        
        # Decision variables
        player_vars = {}
        for p in players:
            player_vars[p.id] = pulp.LpVariable(f"player_{p.id}", cat="Binary")
        
        # Objective: maximize total score
        prob += pulp.lpSum([
            player_vars[p.id] * scores[p.id].total_score 
            for p in players
        ])
        
        # Constraints
        
        # 1. Squad size
        prob += pulp.lpSum([player_vars[p.id] for p in players]) == 15
        
        # 2. Budget
        prob += pulp.lpSum([
            player_vars[p.id] * (p.now_cost / 10) for p in players
        ]) <= budget
        
        # 3. Position requirements
        for position in Position:
            position_players = [p for p in players if p.element_type == position.value]
            required = FPLConstants.SQUAD_REQUIREMENTS[position]
            
            prob += pulp.lpSum([
                player_vars[p.id] for p in position_players
            ]) == required
        
        # 4. Team limits (max 3 per team)
        teams = set(p.team for p in players)
        for team in teams:
            team_players = [p for p in players if p.team == team]
            prob += pulp.lpSum([
                player_vars[p.id] for p in team_players
            ]) <= 3
        
        # 5. Ensure minimum number of nailed starters
        regular_starters = [
            p for p in players 
            if p.minutes > 60 and p.chance_of_playing_this_round in [None, 100]
        ]
        prob += pulp.lpSum([
            player_vars[p.id] for p in regular_starters
        ]) >= 11  # At least 11 regular starters
        
        # 6. Ensure some premium players
        premiums = [p for p in players if p.now_cost >= 100]  # £10m+
        prob += pulp.lpSum([
            player_vars[p.id] for p in premiums
        ]) >= 2  # At least 2 premium players
        
        # 7. Limit bench fodder
        cheap_players = [p for p in players if p.now_cost <= 45]  # £4.5m or less
        prob += pulp.lpSum([
            player_vars[p.id] for p in cheap_players
        ]) <= 3  # Max 3 bench fodder players
        
        # Solve
        solver = pulp.PULP_CBC_CMD(
            timeLimit=config.optimization.time_limit,
            msg=1 if config.debug else 0
        )
        prob.solve(solver)
        
        # Extract solution
        selected_players = []
        for p in players:
            if player_vars[p.id].varValue == 1:
                selected_players.append(p)
                
                # Log why this player was selected
                score = scores[p.id]
                app_logger.debug(
                    f"Selected {p.web_name} (£{p.price}m): "
                    f"Total score={score.total_score:.1f}, "
                    f"Base={score.base_score:.1f}, "
                    f"Form={score.form_score:.1f}, "
                    f"Fixtures={score.fixture_score:.1f}"
                )
        
        # Create squad
        squad = Squad(
            players=selected_players,
            budget=budget,
            formation=self._suggest_formation(selected_players)
        )
        
        return squad
    
    def _suggest_formation(self, players: List[Player]) -> Tuple[int, int, int, int]:
        """Suggest optimal formation based on player strengths"""
        
        # Group by position
        positions = {
            Position.GOALKEEPER: [],
            Position.DEFENDER: [],
            Position.MIDFIELDER: [],
            Position.FORWARD: []
        }
        
        for p in players:
            pos = Position(p.element_type)
            positions[pos].append(p)
        
        # Sort each position by total points
        for pos in positions:
            positions[pos].sort(key=lambda x: x.total_points, reverse=True)
        
        # Find best formation based on top players
        best_formation = (1, 4, 4, 2)
        best_score = 0
        
        for formation in FPLConstants.VALID_FORMATIONS:
            gk, df, md, fw = formation
            
            # Calculate expected points for this formation
            score = 0
            if len(positions[Position.GOALKEEPER]) >= gk:
                score += sum(p.total_points for p in positions[Position.GOALKEEPER][:gk])
            if len(positions[Position.DEFENDER]) >= df:
                score += sum(p.total_points for p in positions[Position.DEFENDER][:df])
            if len(positions[Position.MIDFIELDER]) >= md:
                score += sum(p.total_points for p in positions[Position.MIDFIELDER][:md])
            if len(positions[Position.FORWARD]) >= fw:
                score += sum(p.total_points for p in positions[Position.FORWARD][:fw])
            
            if score > best_score:
                best_score = score
                best_formation = formation
        
        return best_formation