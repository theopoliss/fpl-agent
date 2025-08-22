"""
Squad optimizer that actually fetches and uses historical player data
"""
import pulp
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
import asyncio
from datetime import datetime

from src.data.models import Player, Squad
from src.api.fpl_client import FPLClient
from src.utils.constants import FPLConstants, Position, FormationValidator
from src.utils.logging import app_logger, log_decision
from src.utils.config import config
from src.utils.set_piece_takers import SetPieceTakers


@dataclass
class PlayerScore:
    """Enhanced player scoring metrics"""
    player_id: int
    historical_score: float  # ACTUAL last season performance
    form_score: float  # Recent form
    fixture_score: float  # Next 5 fixtures
    value_score: float  # Points per million
    ownership_score: float  # Differential potential
    expected_score: float  # xG, xA based
    set_piece_score: float  # Bonus for penalty/FK takers
    total_score: float  # Weighted combination


class SquadOptimizerWithHistory:
    """Squad optimizer using real historical data from element-summary API"""
    
    def __init__(self):
        self.weights = {
            'historical': 0.50,   # Real last season data
            'form': 0.05,         # Recent form
            'fixtures': 0.15,     # Fixture difficulty
            'value': 0.10,        # Value for money
            'ownership': 0.0,     # Differential 
            'expected': 0.10,     # Expected stats
            'set_pieces': 0.10    # Set piece taker bonus
        }
        self.player_histories = {}  # Cache for player history data
        
    async def optimize_initial_squad(
        self,
        budget: float = FPLConstants.INITIAL_BUDGET
    ) -> Squad:
        """
        Select optimal initial squad using REAL historical data
        """
        app_logger.info(f"Squad optimization with REAL historical data, budget £{budget}m")
        
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
            
            # Filter to reasonable candidates to avoid fetching 700+ histories
            # Only consider players who:
            # - Have played minutes OR are regular starters from last season
            # - Are not injured
            # - Cost less than £15m (unless premium)
            candidates = []
            for i, p in enumerate(all_players):
                player_data = all_players_data[i]
                if (p.minutes > 0 or p.selected_by_percent > 1.0) and \
                   p.status == 'a' and \
                   (p.price <= 15.0 or p.price >= 10.0):
                    candidates.append((p, player_data))
            
            app_logger.info(f"Fetching historical data for {len(candidates)} candidate players...")
            
            # Fetch historical data for candidates (in batches to avoid overwhelming API)
            batch_size = 20
            for i in range(0, len(candidates), batch_size):
                batch = candidates[i:i+batch_size]
                tasks = []
                for player, _ in batch:
                    tasks.append(self._fetch_player_history(client, player.id))
                
                histories = await asyncio.gather(*tasks)
                for j, history in enumerate(histories):
                    if history:
                        self.player_histories[batch[j][0].id] = history
                
                # Small delay between batches
                if i + batch_size < len(candidates):
                    await asyncio.sleep(0.5)
                    
                app_logger.info(f"  Fetched {min(i+batch_size, len(candidates))}/{len(candidates)} player histories...")
            
            app_logger.info("Calculating player scores with historical data...")
            
            # Calculate scores using real historical data
            player_scores = await self._calculate_player_scores(
                [c[0] for c in candidates],
                [c[1] for c in candidates],
                fixtures_data,
                teams_data
            )
            
            # Run optimization with scores
            app_logger.info("Running optimization algorithm...")
            squad = self._optimize_with_scores(
                [c[0] for c in candidates],
                player_scores,
                budget
            )
            
            app_logger.info(
                f"Optimization complete: {len(squad.players)} players, "
                f"£{squad.value:.1f}m spent"
            )
            
            return squad
    
    async def _fetch_player_history(self, client: FPLClient, player_id: int) -> Optional[Dict]:
        """Fetch historical data for a single player"""
        try:
            return await client.get_player_summary(player_id)
        except Exception as e:
            app_logger.debug(f"Failed to fetch history for player {player_id}: {e}")
            return None
    
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
            history = self.player_histories.get(player.id, {})
            
            # 1. REAL Historical score from past seasons
            historical_score = self._calculate_historical_score(player, history)
            
            # 2. Form score (recent games if available)
            form_score = self._calculate_form_score(player, player_data)
            
            # 3. Fixture score (next 5 gameweeks)
            fixture_score = self._calculate_fixture_score(
                player, fixtures, teams
            )
            
            # 4. Value score (expected points per million)
            value_score = self._calculate_value_score(player, history)
            
            # 5. Ownership/differential score
            ownership_score = self._calculate_ownership_score(player)
            
            # 6. Expected stats score (xG, xA, xGI)
            expected_score = self._calculate_expected_score(player, player_data)
            
            # 7. Set piece taker bonus
            set_piece_score = self._calculate_set_piece_score(player, history)
            
            # Calculate weighted total
            total_score = (
                self.weights['historical'] * historical_score +
                self.weights['form'] * form_score +
                self.weights['fixtures'] * fixture_score +
                self.weights['value'] * value_score +
                self.weights['ownership'] * ownership_score +
                self.weights['expected'] * expected_score +
                self.weights['set_pieces'] * set_piece_score
            )
            
            scores[player.id] = PlayerScore(
                player_id=player.id,
                historical_score=historical_score,
                form_score=form_score,
                fixture_score=fixture_score,
                value_score=value_score,
                ownership_score=ownership_score,
                expected_score=expected_score,
                set_piece_score=set_piece_score,
                total_score=total_score
            )
        
        return scores
    
    def _calculate_historical_score(self, player: Player, history: Dict) -> float:
        """
        Calculate score from ACTUAL historical performance
        Uses points per 90 minutes with intelligent weighting to handle injuries
        """
        
        if not history or 'history_past' not in history:
            # No history available - new player or promoted team
            # Heavy penalty for unknown players when focusing on historical data
            # Only use 10% of current form as we have no historical basis
            return min(player.total_points * 0.5, 10)  # Max score of 10 for unknowns
        
        past_seasons = history.get('history_past', [])
        
        if not past_seasons:
            # No past seasons - heavily penalize
            return min(player.total_points * 0.5, 10)
        
        # Calculate weighted points per 90 for all available seasons
        weighted_pts_per_90 = 0
        total_weight = 0
        recent_injury_prone = False
        total_minutes_analyzed = 0  # Track total minutes across all seasons
        
        # Look at up to 3 seasons of data
        seasons_to_consider = past_seasons[-3:] if len(past_seasons) >= 3 else past_seasons
        num_seasons = len(seasons_to_consider)
        
        for i, season in enumerate(seasons_to_consider):
            season_points = season.get('total_points', 0)
            season_minutes = season.get('minutes', 0)
            
            # Skip seasons with virtually no data
            if season_minutes < 180:  # Less than 2 full games
                continue
            
            total_minutes_analyzed += season_minutes
            
            # Calculate points per 90 for this season
            pts_per_90 = (season_points / season_minutes) * 90 if season_minutes > 0 else 0
            
            # Weight by minutes played (more minutes = more reliable data)
            # Full season is ~3420 minutes (38 games * 90 mins)
            minutes_weight = min(season_minutes / 3420, 1.0)
            
            # Recency weight (more recent seasons matter more)
            # Most recent gets 1.2x, oldest gets 0.8x
            recency_multiplier = 1.2 - (0.4 * i / max(num_seasons - 1, 1))
            
            # Combined weight
            season_weight = minutes_weight * recency_multiplier
            
            # Add to weighted average
            weighted_pts_per_90 += pts_per_90 * season_weight
            total_weight += season_weight
            
            # Check if recently injury prone (most recent season)
            if i == 0 and season_minutes < 2000:
                recent_injury_prone = True
        
        # Calculate final points per 90
        if total_weight > 0:
            final_pts_per_90 = weighted_pts_per_90 / total_weight
        else:
            # Fallback if no valid historical data
            return player.total_points * 2.5
        
        # If player has very limited total minutes across all seasons, heavily penalize
        # This prevents overvaluing players with small sample sizes
        if total_minutes_analyzed < 900:  # Less than 10 full games total
            # Scale down based on how little data we have
            sample_size_multiplier = total_minutes_analyzed / 900
            final_pts_per_90 *= sample_size_multiplier
        
        # Project to full season (38 games * 90 minutes * pts_per_90)
        # But assume realistic 34 games played for projection
        projected_season_points = final_pts_per_90 * 34
        
        # Apply small penalty if recently injury prone
        if recent_injury_prone:
            projected_season_points *= 0.9  # 10% discount for injury risk
        
        # Also consider best historical season total as a reality check
        # This prevents overvaluing mediocre players with decent pts/90
        best_season_total = 0
        for season in seasons_to_consider:
            if season.get('minutes', 0) > 1800:  # Only consider substantial seasons
                best_season_total = max(best_season_total, season.get('total_points', 0))
        
        # If projected points are way higher than best historical season,
        # take weighted average to be more conservative
        if best_season_total > 0 and projected_season_points > best_season_total * 1.2:
            # Weight: 60% best historical, 40% projected
            projected_season_points = (best_season_total * 0.6 + projected_season_points * 0.4)
        
        # Normalize to 0-100 scale - STRICTER to differentiate elite from good
        # 250+ points = exceptional (100)
        # 200-250 points = excellent (75-90)
        # 170-200 points = very good (60-75)
        # 140-170 points = good (45-60)
        # 110-140 points = decent (30-45)
        # 80-110 points = squad player (15-30)
        # <80 points = bench fodder (0-15)
        if projected_season_points >= 250:
            base_score = 100
        elif projected_season_points >= 200:
            base_score = 75 + (projected_season_points - 200) * 0.3  # 75-90
        elif projected_season_points >= 170:
            base_score = 60 + (projected_season_points - 170) * 0.5  # 60-75
        elif projected_season_points >= 140:
            base_score = 45 + (projected_season_points - 140) * 0.5  # 45-60
        elif projected_season_points >= 110:
            base_score = 30 + (projected_season_points - 110) * 0.5  # 30-45
        elif projected_season_points >= 80:
            base_score = 15 + (projected_season_points - 80) * 0.5   # 15-30
        else:
            base_score = projected_season_points * 0.1875  # 0-15
        
        # Cap at 100
        return min(base_score, 100)
    
    def _calculate_form_score(self, player: Player, data: Dict) -> float:
        """Calculate form score from recent performances"""
        
        # Use the 'form' field which is last 5 games average
        form = float(player.form) if player.form else 0
        
        # Points per game if they've played
        ppg = player.points_per_game if player.points_per_game > 0 else form
        
        # Recent transfers in/out momentum
        transfers_balance = data.get('transfers_in_event', 0) - data.get('transfers_out_event', 0)
        transfer_momentum = min(max(transfers_balance / 100000, -1), 1)  # Normalize
        
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
    
    def _calculate_value_score(self, player: Player, history: Dict) -> float:
        """Calculate value for money score using historical data"""
        
        price = player.price
        
        # Get last season points if available
        last_season_points = 0
        if history and 'history_past' in history:
            past_seasons = history.get('history_past', [])
            if past_seasons:
                last_season_points = past_seasons[-1].get('total_points', 0)
        
        # Expected points based on historical data
        if last_season_points > 0:
            # Weight historical performance heavily
            expected_points = last_season_points * 0.8 + player.total_points * 20 * 0.2
        else:
            # New player - project current form
            expected_points = player.total_points * 20
        
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
            return 60
        elif ownership < 10 and player.form > 4:
            return 40
        elif ownership < 20:
            return 30
        elif ownership > 40:
            return 10  # Template player
        else:
            return 20
    
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
    
    def _calculate_set_piece_score(self, player: Player, history: Dict) -> float:
        """
        Calculate bonus score for set piece takers
        
        Primary penalty takers get huge bonus
        Free kick specialists get moderate bonus  
        Corner takers get small bonus
        """
        
        # Start with known set piece takers
        base_score = SetPieceTakers.get_set_piece_score(player.web_name)
        
        # Enhance with historical data if available
        if history:
            historical_analysis = SetPieceTakers.analyze_historical_set_pieces(history)
            
            # Add bonus for historical penalty success
            penalties_taken = (
                historical_analysis.get('penalties_scored', 0) + 
                historical_analysis.get('penalties_missed', 0)
            )
            
            if penalties_taken >= 5:
                # Confirmed penalty taker from history
                base_score = max(base_score, 20)
            elif penalties_taken >= 2:
                # Occasional penalty taker
                base_score = max(base_score, 10)
        
        # Position-based adjustments
        position = Position(player.element_type)
        
        if position == Position.GOALKEEPER:
            # GKs don't take set pieces (except rare penalties)
            base_score = 0
        elif position == Position.DEFENDER:
            # Defenders who take set pieces are extra valuable
            if base_score > 0:
                base_score *= 1.2
        elif position == Position.MIDFIELDER:
            # Expected for mids, normal scoring
            pass
        else:  # Forward
            # Forwards on penalties are very valuable
            if SetPieceTakers.is_penalty_taker(player.web_name, primary_only=True):
                base_score *= 1.3
        
        # Cap at 100
        return min(base_score * 4, 100)  # Scale up to 0-100 range
    
    def _optimize_with_scores(
        self,
        players: List[Player],
        scores: Dict[int, PlayerScore],
        budget: float
    ) -> Squad:
        """Run optimization with calculated scores"""
        
        # Create LP problem
        prob = pulp.LpProblem("FPL_Squad_Historical", pulp.LpMaximize)
        
        # Decision variables
        player_vars = {}
        for p in players:
            player_vars[p.id] = pulp.LpVariable(f"player_{p.id}", cat="Binary")
        
        # Separate goalkeepers by price for starter/bench strategy
        goalkeepers = [p for p in players if p.element_type == Position.GOALKEEPER.value]
        premium_gks = [p for p in goalkeepers if p.now_cost >= 45]  # £4.5m+
        fodder_gks = [p for p in goalkeepers if p.now_cost <= 40]  # £4.0m
        
        # Objective: maximize total score but penalize expensive bench GKs
        # We want 1 good GK and 1 cheap GK
        obj_expression = []
        for p in players:
            if p.element_type == Position.GOALKEEPER.value:
                # Reduce score for expensive backup GKs
                if p.now_cost <= 40:
                    # Fodder GK - small bonus for being cheap
                    obj_expression.append(player_vars[p.id] * (scores[p.id].total_score + 5))
                else:
                    # Regular GK - normal score
                    obj_expression.append(player_vars[p.id] * scores[p.id].total_score)
            else:
                obj_expression.append(player_vars[p.id] * scores[p.id].total_score)
        
        prob += pulp.lpSum(obj_expression)
        
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
        if len(regular_starters) >= 11:
            prob += pulp.lpSum([
                player_vars[p.id] for p in regular_starters
            ]) >= 11  # At least 11 regular starters
        
        # 6. Ensure some premium players
        premiums = [p for p in players if p.now_cost >= 100]  # £10m+
        if len(premiums) >= 2:
            prob += pulp.lpSum([
                player_vars[p.id] for p in premiums
            ]) >= 2  # At least 2 premium players
        
        # 7. Limit bench fodder
        cheap_players = [p for p in players if p.now_cost <= 45]  # £4.5m or less
        prob += pulp.lpSum([
            player_vars[p.id] for p in cheap_players
        ]) <= 4  # Max 4 bench fodder players (including £4.0m GK)
        
        # 8. Goalkeeper strategy: 1 premium + 1 fodder
        if len(premium_gks) >= 1 and len(fodder_gks) >= 1:
            # Ensure we pick exactly 1 goalkeeper >= £4.5m
            prob += pulp.lpSum([
                player_vars[p.id] for p in premium_gks
            ]) >= 1
            
            # Ensure we pick exactly 1 goalkeeper <= £4.0m  
            prob += pulp.lpSum([
                player_vars[p.id] for p in fodder_gks
            ]) >= 1
        
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
                history = self.player_histories.get(p.id, {})
                last_season_pts = 0
                if history and 'history_past' in history:
                    past = history.get('history_past', [])
                    if past:
                        last_season_pts = past[-1].get('total_points', 0)
                
                app_logger.debug(
                    f"Selected {p.web_name} (£{p.price}m): "
                    f"Total score={score.total_score:.1f}, "
                    f"Historical={score.historical_score:.1f} (Last season: {last_season_pts}pts), "
                    f"Form={score.form_score:.1f}, "
                    f"Fixtures={score.fixture_score:.1f}, "
                    f"Set pieces={score.set_piece_score:.1f}"
                )
        
        # Create squad with starting 11 selection
        squad = Squad(
            players=selected_players,
            budget=budget,
            formation=(1, 4, 4, 2)  # Default formation, will be updated
        )
        
        # Select starting 11 and bench (this also determines the actual formation)
        starting_11, bench, actual_formation = self.select_starting_eleven(selected_players, scores)
        squad.starting_11 = starting_11
        squad.bench = bench
        squad.formation = actual_formation  # Use the formation from starting 11 selection
        
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
    
    def select_starting_eleven(
        self, 
        players: List[Player], 
        scores: Dict[int, PlayerScore]
    ) -> Tuple[List[Player], List[Player], Tuple[int, int, int, int]]:
        """
        Select the best starting 11 and order the bench
        
        Returns:
            Tuple of (starting_11, bench_ordered, formation)
        """
        
        # Separate players by position
        positions = {
            Position.GOALKEEPER: [],
            Position.DEFENDER: [],
            Position.MIDFIELDER: [],
            Position.FORWARD: []
        }
        
        for p in players:
            pos = Position(p.element_type)
            positions[pos].append(p)
        
        # Sort each position by total score (not just points)
        for pos in positions:
            positions[pos].sort(
                key=lambda x: scores[x.id].total_score if x.id in scores else x.total_points, 
                reverse=True
            )
        
        # Select starting 11
        starting_11 = []
        bench = []
        
        # 1. Goalkeepers: Best one starts, cheapest benched
        if len(positions[Position.GOALKEEPER]) >= 2:
            # Start the higher-scoring GK
            starting_11.append(positions[Position.GOALKEEPER][0])
            # Bench the cheaper one (should be £4.0m fodder)
            bench.append(positions[Position.GOALKEEPER][1])
        
        # 2. Find optimal formation for outfield players
        best_formation = None
        best_score = 0
        best_lineup = None
        
        for formation in FPLConstants.VALID_FORMATIONS:
            gk, df, md, fw = formation
            
            # Skip if we don't have enough players
            if (len(positions[Position.DEFENDER]) < df or 
                len(positions[Position.MIDFIELDER]) < md or 
                len(positions[Position.FORWARD]) < fw):
                continue
            
            # Calculate total score for this formation
            formation_score = 0
            temp_lineup = []
            
            # Add best defenders
            for i in range(df):
                p = positions[Position.DEFENDER][i]
                formation_score += scores[p.id].total_score if p.id in scores else p.total_points
                temp_lineup.append(p)
            
            # Add best midfielders
            for i in range(md):
                p = positions[Position.MIDFIELDER][i]
                formation_score += scores[p.id].total_score if p.id in scores else p.total_points
                temp_lineup.append(p)
            
            # Add best forwards
            for i in range(fw):
                p = positions[Position.FORWARD][i]
                formation_score += scores[p.id].total_score if p.id in scores else p.total_points
                temp_lineup.append(p)
            
            if formation_score > best_score:
                best_score = formation_score
                best_formation = formation
                best_lineup = temp_lineup
        
        # Add the best lineup to starting 11
        if best_lineup:
            starting_11.extend(best_lineup)
            
            # Add remaining players to bench (excluding selected GK)
            gk, df, md, fw = best_formation
            
            # Bench remaining defenders
            for i in range(df, len(positions[Position.DEFENDER])):
                bench.append(positions[Position.DEFENDER][i])
            
            # Bench remaining midfielders
            for i in range(md, len(positions[Position.MIDFIELDER])):
                bench.append(positions[Position.MIDFIELDER][i])
            
            # Bench remaining forwards
            for i in range(fw, len(positions[Position.FORWARD])):
                bench.append(positions[Position.FORWARD][i])
        
        # Order bench by priority (best scoring first, but respecting positions)
        # Typically: Best outfield player, then coverage for each position
        outfield_bench = [p for p in bench if p.element_type != Position.GOALKEEPER.value]
        outfield_bench.sort(
            key=lambda x: scores[x.id].total_score if x.id in scores else x.total_points,
            reverse=True
        )
        
        # Reorder bench: best 3 outfield players + GK
        gk_bench = [p for p in bench if p.element_type == Position.GOALKEEPER.value]
        bench_ordered = outfield_bench[:3] + gk_bench
        
        app_logger.info(f"Optimal formation for starting XI: {best_formation}")
        app_logger.info(f"Starting 11: {len(starting_11)} players")
        app_logger.info(f"Bench: {len(bench_ordered)} players")
        
        return starting_11, bench_ordered, best_formation