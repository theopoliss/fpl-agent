"""
Squad optimizer specifically tuned for pre-season (GW0) selection
Addresses issues found in backtesting:
1. Missing elite premiums like Salah
2. Overvaluing unproven "value" players  
3. Not accounting for consistency/reliability
"""

import pulp
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
import asyncio

from src.data.models import Player, Squad
from src.api.fpl_client import FPLClient
from src.utils.constants import FPLConstants, Position
from src.utils.logging import app_logger
from src.utils.config import config
from src.utils.set_piece_takers import SetPieceTakers


@dataclass
class PreseasonPlayerScore:
    """Player scoring for pre-season when no current form exists"""
    player_id: int
    historical_score: float  # Past seasons performance
    consistency_score: float  # How reliable/nailed
    elite_score: float  # Bonus for proven elite players
    fixture_score: float  # Opening fixtures
    set_piece_score: float  # Set piece taker bonus
    team_quality_score: float  # Playing for top 6 team
    total_score: float  # Weighted combination


class PreseasonSquadOptimizer:
    """Optimizer specifically for GW0/pre-season squad selection"""
    
    def __init__(self):
        # Pre-season weights - no form or current season data available
        self.weights = {
            'historical': 0.50,      # Past performance
            'consistency': 0.15,     # Reliability/minutes played
            'elite': 0.10,          # Proven premium bonus
            'fixtures': 0.10,       # Opening fixtures
            'set_pieces': 0.10,     # Set piece takers
            'team_quality': 0.05    # Top team bonus
        }
        self.player_histories = {}
        
    async def optimize_initial_squad(
        self,
        budget: float = FPLConstants.INITIAL_BUDGET
    ) -> Squad:
        """Select optimal pre-season squad"""
        
        app_logger.info(f"Pre-season squad optimization, budget £{budget}m")
        
        async with FPLClient() as client:
            # Fetch all data
            app_logger.info("Fetching player and fixture data...")
            
            bootstrap_data = await client.get_bootstrap_data()
            all_players_data = bootstrap_data.get('elements', [])
            teams_data = bootstrap_data.get('teams', [])
            fixtures_data = await client.get_fixtures()
            
            all_players = [Player(**p) for p in all_players_data]
            
            # Pre-season candidate filtering
            candidates = []
            for i, p in enumerate(all_players):
                player_data = all_players_data[i]
                
                # For pre-season, consider players who:
                # - Are not injured (status = 'a')
                # - Are from established PL teams (not newly promoted)
                # - Have reasonable ownership OR are premium players
                if p.status == 'a':
                    candidates.append((p, player_data))
            
            app_logger.info(f"Fetching historical data for {len(candidates)} candidates...")
            
            # Fetch histories
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
                
                if i + batch_size < len(candidates):
                    await asyncio.sleep(0.5)
                    
                app_logger.info(f"  Fetched {min(i+batch_size, len(candidates))}/{len(candidates)} histories...")
            
            app_logger.info("Calculating pre-season player scores...")
            
            # Calculate scores
            player_scores = await self._calculate_preseason_scores(
                [c[0] for c in candidates],
                [c[1] for c in candidates],
                fixtures_data,
                teams_data
            )
            
            # Optimize
            app_logger.info("Running optimization...")
            squad = self._optimize_with_scores(
                [c[0] for c in candidates],
                player_scores,
                budget
            )
            
            app_logger.info(f"Squad complete: {len(squad.players)} players, £{squad.value:.1f}m")
            
            return squad
    
    async def _fetch_player_history(self, client: FPLClient, player_id: int) -> Optional[Dict]:
        """Fetch player's historical data"""
        try:
            return await client.get_player_summary(player_id)
        except Exception as e:
            app_logger.debug(f"Failed to fetch history for {player_id}: {e}")
            return None
    
    async def _calculate_preseason_scores(
        self,
        players: List[Player],
        players_data: List[Dict],
        fixtures: List[Dict],
        teams: List[Dict]
    ) -> Dict[int, PreseasonPlayerScore]:
        """Calculate comprehensive pre-season scores"""
        
        scores = {}
        
        # Get top 6 teams for quality bonus
        top_teams = self._identify_top_teams(teams)
        
        for i, player in enumerate(players):
            player_data = players_data[i]
            history = self.player_histories.get(player.id, {})
            
            # 1. Historical performance score
            historical_score = self._calculate_historical_score(player, history)
            
            # Apply ownership reality check
            historical_score = self._apply_ownership_reality_check(historical_score, player)
            
            # 2. Consistency/reliability score
            consistency_score = self._calculate_consistency_score(player, history)
            consistency_score = self._apply_ownership_reality_check(consistency_score, player)
            
            # 3. Elite player bonus
            elite_score = self._calculate_elite_score(player, history)
            # Don't apply ownership check to elite score - elite players can have low ownership early
            
            # 4. Fixture difficulty
            fixture_score = self._calculate_fixture_score(player, fixtures, teams)
            
            # 5. Set piece taker bonus
            set_piece_score = self._calculate_set_piece_score(player, history)
            
            # 6. Team quality bonus
            team_quality_score = self._calculate_team_quality_score(player, top_teams)
            
            # Calculate weighted total
            total_score = (
                self.weights['historical'] * historical_score +
                self.weights['consistency'] * consistency_score +
                self.weights['elite'] * elite_score +
                self.weights['fixtures'] * fixture_score +
                self.weights['set_pieces'] * set_piece_score +
                self.weights['team_quality'] * team_quality_score
            )
            
            scores[player.id] = PreseasonPlayerScore(
                player_id=player.id,
                historical_score=historical_score,
                consistency_score=consistency_score,
                elite_score=elite_score,
                fixture_score=fixture_score,
                set_piece_score=set_piece_score,
                team_quality_score=team_quality_score,
                total_score=total_score
            )
        
        return scores
    
    def _calculate_historical_score(self, player: Player, history: Dict) -> float:
        """
        Enhanced historical scoring that better values elite players
        """
        
        if not history or 'history_past' not in history:
            return 5  # Minimal score for unknowns
        
        past_seasons = history.get('history_past', [])
        if not past_seasons:
            return 5
        
        # Get last 3 seasons
        recent_seasons = past_seasons[-3:] if len(past_seasons) >= 3 else past_seasons
        
        # Check for missing recent season (player wasn't in PL)
        season_names = [s.get('season_name', '') for s in past_seasons]
        gap_penalty = 1.0
        
        if '2024/25' not in season_names and len(past_seasons) > 0:
            # Player missed last season - major red flag (Bamford case)
            gap_penalty = 0.5
        
        # Check for declining minutes trend
        if len(recent_seasons) >= 2:
            recent_mins = recent_seasons[-1].get('minutes', 0)  # Most recent
            prev_mins = recent_seasons[-2].get('minutes', 0)  # Previous
            if prev_mins > 0 and recent_mins < prev_mins * 0.5 and recent_mins < 1800:
                # Lost >50% of minutes and playing <20 games - concerning
                gap_penalty *= 0.7
        
        # Calculate weighted average with recency bias
        total_weighted_points = 0
        total_weight = 0
        
        for i, season in enumerate(reversed(recent_seasons)):  # Most recent first
            points = season.get('total_points', 0)
            minutes = season.get('minutes', 0)
            
            if minutes < 900:  # Less than 10 games
                continue
                
            # Recency weight: most recent = 1.0, previous = 0.5, before that = 0.3
            recency_weight = [1.0, 0.5, 0.3][min(i, 2)]
            
            # Minutes weight (favor players who play regularly)
            minutes_weight = min(minutes / 3000, 1.0)  # Cap at ~33 games
            
            weight = recency_weight * minutes_weight
            total_weighted_points += points * weight
            total_weight += weight
        
        if total_weight == 0:
            return 5
            
        avg_points = (total_weighted_points / total_weight) * gap_penalty
        
        # NEW: More generous scoring for elite players
        # Recognize that 200+ point players are rare and valuable
        if avg_points >= 250:
            return 100
        elif avg_points >= 225:
            return 95
        elif avg_points >= 200:
            return 90
        elif avg_points >= 180:
            return 80
        elif avg_points >= 160:
            return 70
        elif avg_points >= 140:
            return 60
        elif avg_points >= 120:
            return 50
        elif avg_points >= 100:
            return 40
        elif avg_points >= 80:
            return 30
        else:
            return max(5, avg_points * 0.3)
    
    def _apply_ownership_reality_check(self, score: float, player: Player) -> float:
        """
        Reality check based on ownership percentage.
        If historical score is high but ownership is tiny, something's wrong.
        """
        ownership = player.selected_by_percent
        
        # High historical score but very low ownership = red flag
        if score > 60 and ownership < 1.0:
            # Major concern - good history but <1% owned (Bamford, Douglas Luiz)
            return score * 0.4
        elif score > 50 and ownership < 2.0:
            # Moderate concern
            return score * 0.6
        elif score > 40 and ownership < 3.0:
            # Minor concern  
            return score * 0.8
        else:
            # No adjustment needed
            return score
    
    def _calculate_consistency_score(self, player: Player, history: Dict) -> float:
        """
        Score based on how consistently player delivers
        Looks at minutes played and variance in returns
        """
        
        if not history or 'history_past' not in history:
            return 0
        
        past_seasons = history.get('history_past', [])[-3:]  # Last 3 seasons
        
        if not past_seasons:
            return 0
        
        # Calculate average minutes per season
        total_minutes = sum(s.get('minutes', 0) for s in past_seasons)
        avg_minutes = total_minutes / len(past_seasons)
        
        # High minutes = consistent starter
        minutes_score = min(avg_minutes / 3000, 1.0) * 50  # Max 50 points
        
        # Calculate points consistency (low variance is good)
        if len(past_seasons) >= 2:
            points_list = [s.get('total_points', 0) for s in past_seasons if s.get('minutes', 0) > 900]
            if len(points_list) >= 2:
                avg_points = sum(points_list) / len(points_list)
                variance = sum((p - avg_points) ** 2 for p in points_list) / len(points_list)
                std_dev = variance ** 0.5
                
                # Low variance relative to mean = consistent
                if avg_points > 0:
                    consistency_ratio = 1 - min(std_dev / avg_points, 1.0)
                    consistency_bonus = consistency_ratio * 50  # Max 50 points
                else:
                    consistency_bonus = 0
            else:
                consistency_bonus = 25  # Default if not enough data
        else:
            consistency_bonus = 25
        
        return minutes_score + consistency_bonus
    
    def _calculate_elite_score(self, player: Player, history: Dict) -> float:
        """
        Special bonus for proven elite players
        These are players who have delivered 200+ points multiple times
        """
        
        if not history or 'history_past' not in history:
            return 0
        
        past_seasons = history.get('history_past', [])
        
        # Count seasons with 200+ points
        elite_seasons = sum(1 for s in past_seasons if s.get('total_points', 0) >= 200)
        
        # Count seasons with 180+ points (very good)
        very_good_seasons = sum(1 for s in past_seasons if s.get('total_points', 0) >= 180)
        
        # Elite player recognition
        if elite_seasons >= 3:
            return 100  # Proven elite (Salah, KDB, etc.)
        elif elite_seasons >= 2:
            return 80
        elif elite_seasons >= 1:
            return 60
        elif very_good_seasons >= 2:
            return 40
        elif very_good_seasons >= 1:
            return 20
        else:
            return 0
    
    def _calculate_fixture_score(self, player: Player, fixtures: List[Dict], teams: List[Dict]) -> float:
        """Calculate opening fixture difficulty"""
        
        team_fixtures = [
            f for f in fixtures 
            if (f.get('team_h') == player.team or f.get('team_a') == player.team)
            and not f.get('finished', False)
        ][:5]  # First 5 fixtures
        
        if not team_fixtures:
            return 50
        
        total_difficulty = 0
        for fixture in team_fixtures:
            if fixture.get('team_h') == player.team:
                difficulty = fixture.get('team_h_difficulty', 3)
                total_difficulty += (6 - difficulty) * 1.1  # Home advantage
            else:
                difficulty = fixture.get('team_a_difficulty', 3)
                total_difficulty += (6 - difficulty) * 0.9
        
        avg_ease = total_difficulty / len(team_fixtures)
        return min(avg_ease * 20, 100)
    
    def _calculate_set_piece_score(self, player: Player, history: Dict) -> float:
        """Set piece taker bonus"""
        
        base_score = SetPieceTakers.get_set_piece_score(player.web_name)
        
        # Enhance with historical penalty data
        if history:
            historical_analysis = SetPieceTakers.analyze_historical_set_pieces(history)
            
            penalties_taken = (
                historical_analysis.get('penalties_scored', 0) + 
                historical_analysis.get('penalties_missed', 0)
            )
            
            if penalties_taken >= 5:
                base_score = max(base_score, 25)
            elif penalties_taken >= 2:
                base_score = max(base_score, 15)
        
        # Position adjustments
        position = Position(player.element_type)
        if position == Position.GOALKEEPER:
            base_score = 0
        elif position == Position.DEFENDER and base_score > 0:
            base_score *= 1.2  # Defenders on set pieces are valuable
        elif position == Position.FORWARD and SetPieceTakers.is_penalty_taker(player.web_name, primary_only=True):
            base_score *= 1.3  # Forwards on pens are gold
        
        return min(base_score * 4, 100)
    
    def _calculate_team_quality_score(self, player: Player, top_teams: List[int]) -> float:
        """Bonus for playing for a top team"""
        
        if player.team in top_teams[:3]:  # Top 3 teams
            return 100
        elif player.team in top_teams[:6]:  # Top 6 teams
            return 60
        elif player.team in top_teams[:10]:  # Top 10 teams
            return 30
        else:
            return 0
    
    def _identify_top_teams(self, teams: List[Dict]) -> List[int]:
        """Identify top teams based on various metrics"""
        
        # Sort by overall strength
        sorted_teams = sorted(
            teams,
            key=lambda t: (t.get('strength_overall_home', 0) + t.get('strength_overall_away', 0)) / 2,
            reverse=True
        )
        
        return [t['id'] for t in sorted_teams]
    
    def _optimize_with_scores(
        self,
        players: List[Player],
        scores: Dict[int, PreseasonPlayerScore],
        budget: float
    ) -> Squad:
        """Run the optimization with enhanced constraints"""
        
        # Create LP problem
        prob = pulp.LpProblem("FPL_Preseason_Squad", pulp.LpMaximize)
        
        # Decision variables
        player_vars = {}
        for p in players:
            player_vars[p.id] = pulp.LpVariable(f"player_{p.id}", cat="Binary")
        
        # Objective: maximize total score
        prob += pulp.lpSum([
            player_vars[p.id] * scores[p.id].total_score 
            for p in players if p.id in scores
        ])
        
        # CONSTRAINTS
        
        # 1. Squad size = 15
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
        
        # 4. Max 3 per team
        teams = set(p.team for p in players)
        for team in teams:
            team_players = [p for p in players if p.team == team]
            prob += pulp.lpSum([
                player_vars[p.id] for p in team_players
            ]) <= 3
        
        # 5. ENHANCED: Ensure at least 2 premium players (£10m+)
        premiums = [p for p in players if p.now_cost >= 100]
        if len(premiums) >= 3:
            prob += pulp.lpSum([
                player_vars[p.id] for p in premiums
            ]) >= 2
        
        # 6. ENHANCED: Ensure at least 1 elite premium (£12m+)
        elite_premiums = [p for p in players if p.now_cost >= 120]
        if len(elite_premiums) >= 1:
            prob += pulp.lpSum([
                player_vars[p.id] for p in elite_premiums
            ]) >= 1
        
        # 7. Limit bench fodder (£4.5m or less) to 4 players
        cheap_players = [p for p in players if p.now_cost <= 45]
        prob += pulp.lpSum([
            player_vars[p.id] for p in cheap_players
        ]) <= 4
        
        # 8. Goalkeeper strategy: 1 premium (£4.5m+) + 1 fodder (£4.0m)
        goalkeepers = [p for p in players if p.element_type == Position.GOALKEEPER.value]
        premium_gks = [p for p in goalkeepers if p.now_cost >= 45]
        fodder_gks = [p for p in goalkeepers if p.now_cost <= 40]
        
        if premium_gks and fodder_gks:
            prob += pulp.lpSum([player_vars[p.id] for p in premium_gks]) >= 1
            prob += pulp.lpSum([player_vars[p.id] for p in fodder_gks]) >= 1
        
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
                
                # Log selection reason
                if p.id in scores:
                    score = scores[p.id]
                    app_logger.debug(
                        f"Selected {p.web_name} (£{p.price}m): "
                        f"Total={score.total_score:.1f}, "
                        f"Hist={score.historical_score:.1f}, "
                        f"Elite={score.elite_score:.1f}, "
                        f"Consistent={score.consistency_score:.1f}"
                    )
        
        # Create squad with formation
        squad = Squad(
            players=selected_players,
            budget=budget,
            formation=(1, 4, 4, 2)
        )
        
        # Select starting 11 and bench
        starting_11, bench, formation = self.select_starting_eleven(selected_players, scores)
        squad.starting_11 = starting_11
        squad.bench = bench
        squad.formation = formation
        
        return squad
    
    def select_starting_eleven(
        self,
        players: List[Player],
        scores: Dict[int, PreseasonPlayerScore]
    ) -> Tuple[List[Player], List[Player], Tuple[int, int, int, int]]:
        """Select best starting 11 and order bench"""
        
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
        
        # Sort each position by score
        for pos in positions:
            positions[pos].sort(
                key=lambda x: scores[x.id].total_score if x.id in scores else 0,
                reverse=True
            )
        
        # Select starting 11
        starting_11 = []
        bench = []
        
        # 1. Best GK starts
        if positions[Position.GOALKEEPER]:
            starting_11.append(positions[Position.GOALKEEPER][0])
            if len(positions[Position.GOALKEEPER]) > 1:
                bench.append(positions[Position.GOALKEEPER][1])
        
        # 2. Find optimal formation
        best_formation = None
        best_score = 0
        best_lineup = None
        
        for formation in FPLConstants.VALID_FORMATIONS:
            gk, df, md, fw = formation
            
            if (len(positions[Position.DEFENDER]) < df or
                len(positions[Position.MIDFIELDER]) < md or
                len(positions[Position.FORWARD]) < fw):
                continue
            
            formation_score = 0
            temp_lineup = []
            
            for i in range(df):
                p = positions[Position.DEFENDER][i]
                formation_score += scores[p.id].total_score if p.id in scores else 0
                temp_lineup.append(p)
            
            for i in range(md):
                p = positions[Position.MIDFIELDER][i]
                formation_score += scores[p.id].total_score if p.id in scores else 0
                temp_lineup.append(p)
            
            for i in range(fw):
                p = positions[Position.FORWARD][i]
                formation_score += scores[p.id].total_score if p.id in scores else 0
                temp_lineup.append(p)
            
            if formation_score > best_score:
                best_score = formation_score
                best_formation = formation
                best_lineup = temp_lineup
        
        if best_lineup:
            starting_11.extend(best_lineup)
            
            # Add remaining to bench
            gk, df, md, fw = best_formation
            
            for i in range(df, len(positions[Position.DEFENDER])):
                bench.append(positions[Position.DEFENDER][i])
            for i in range(md, len(positions[Position.MIDFIELDER])):
                bench.append(positions[Position.MIDFIELDER][i])
            for i in range(fw, len(positions[Position.FORWARD])):
                bench.append(positions[Position.FORWARD][i])
        
        # Order bench
        outfield_bench = [p for p in bench if p.element_type != Position.GOALKEEPER.value]
        outfield_bench.sort(
            key=lambda x: scores[x.id].total_score if x.id in scores else 0,
            reverse=True
        )
        
        gk_bench = [p for p in bench if p.element_type == Position.GOALKEEPER.value]
        bench_ordered = outfield_bench[:3] + gk_bench
        
        app_logger.info(f"Formation: {best_formation}")
        
        return starting_11, bench_ordered, best_formation