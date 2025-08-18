from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
import numpy as np
from datetime import datetime, timedelta

from src.data.models import Player, Fixture, PredictedPoints
from src.utils.constants import Position, FPLConstants
from src.utils.logging import app_logger


@dataclass
class PlayerMetrics:
    """Comprehensive metrics for a player"""
    player_id: int
    
    # Performance metrics
    points_per_game: float
    points_per_million: float
    minutes_per_game: float
    
    # Form metrics
    form_rating: float
    form_trend: str  # "rising", "stable", "falling"
    last_5_average: float
    
    # Expected metrics
    xG_per_90: float
    xA_per_90: float
    xGI_per_90: float
    
    # Advanced metrics
    bps_per_90: float
    ict_index_per_90: float
    
    # Risk metrics
    injury_risk: float  # 0-1 scale
    rotation_risk: float  # 0-1 scale
    
    # Fixture metrics
    next_5_difficulty: float
    home_away_split: Dict[str, float]


class PlayerAnalyzer:
    """Analyzes player performance and potential"""
    
    def __init__(self):
        self.min_minutes_threshold = 60  # Minimum minutes to consider a game
        
    def analyze_player(
        self,
        player: Player,
        historical_data: List[Dict],
        fixtures: List[Fixture],
        team_data: Optional[Dict] = None
    ) -> PlayerMetrics:
        """
        Comprehensive analysis of a player
        """
        app_logger.debug(f"Analyzing player: {player.web_name}")
        
        # Calculate basic metrics
        ppg = self._calculate_points_per_game(player, historical_data)
        ppm = player.value_score
        mpg = self._calculate_minutes_per_game(player, historical_data)
        
        # Form analysis
        form_rating, form_trend = self._analyze_form(player, historical_data)
        last_5_avg = self._calculate_recent_average(historical_data, 5)
        
        # Expected stats per 90
        xg_90 = self._per_90_metric(player.expected_goals, player.minutes)
        xa_90 = self._per_90_metric(player.expected_assists, player.minutes)
        xgi_90 = self._per_90_metric(player.expected_goal_involvements, player.minutes)
        
        # Advanced metrics
        bps_90 = self._per_90_metric(player.bps, player.minutes)
        ict_90 = self._per_90_metric(player.ict_index, player.minutes)
        
        # Risk assessment
        injury_risk = self._assess_injury_risk(player, historical_data)
        rotation_risk = self._assess_rotation_risk(player, historical_data, team_data)
        
        # Fixture analysis
        next_5_diff = self._calculate_fixture_difficulty(player, fixtures, 5)
        home_away = self._analyze_home_away_split(historical_data)
        
        return PlayerMetrics(
            player_id=player.id,
            points_per_game=ppg,
            points_per_million=ppm,
            minutes_per_game=mpg,
            form_rating=form_rating,
            form_trend=form_trend,
            last_5_average=last_5_avg,
            xG_per_90=xg_90,
            xA_per_90=xa_90,
            xGI_per_90=xgi_90,
            bps_per_90=bps_90,
            ict_index_per_90=ict_90,
            injury_risk=injury_risk,
            rotation_risk=rotation_risk,
            next_5_difficulty=next_5_diff,
            home_away_split=home_away
        )
    
    def predict_points(
        self,
        player: Player,
        metrics: PlayerMetrics,
        fixture: Fixture,
        is_home: bool
    ) -> PredictedPoints:
        """
        Predict points for a specific fixture
        """
        app_logger.debug(f"Predicting points for {player.web_name}")
        
        # Base prediction from form and historical average
        base_points = metrics.last_5_average * 0.6 + metrics.points_per_game * 0.4
        
        # Adjust for fixture difficulty
        difficulty = fixture.team_h_difficulty if is_home else fixture.team_a_difficulty
        difficulty_multiplier = self._get_difficulty_multiplier(difficulty)
        
        # Home/away adjustment
        venue_adjustment = 1.1 if is_home else 0.9
        
        # Position-specific predictions
        predicted_goals = self._predict_goals(player, metrics, difficulty)
        predicted_assists = self._predict_assists(player, metrics, difficulty)
        clean_sheet_prob = self._predict_clean_sheet(player, fixture, is_home)
        predicted_bonus = self._predict_bonus(player, metrics)
        predicted_minutes = self._predict_minutes(player, metrics)
        
        # Calculate total predicted points
        total_predicted = (
            base_points * difficulty_multiplier * venue_adjustment +
            predicted_goals * FPLConstants.POINTS_SCORING["goal_scored"][Position(player.element_type)] +
            predicted_assists * FPLConstants.POINTS_SCORING["assist"] +
            clean_sheet_prob * FPLConstants.POINTS_SCORING["clean_sheet"][Position(player.element_type)] +
            predicted_bonus
        )
        
        # Confidence based on various factors
        confidence = self._calculate_confidence(
            player, metrics, predicted_minutes
        )
        
        return PredictedPoints(
            player_id=player.id,
            gameweek=fixture.event,
            predicted_points=total_predicted,
            confidence=confidence,
            predicted_goals=predicted_goals,
            predicted_assists=predicted_assists,
            predicted_clean_sheet_prob=clean_sheet_prob,
            predicted_bonus=predicted_bonus,
            predicted_minutes=predicted_minutes,
            fixture_difficulty=difficulty,
            home_away="home" if is_home else "away"
        )
    
    def find_form_players(
        self,
        players: List[Player],
        min_form: float = 5.0,
        min_minutes: int = 180
    ) -> List[Player]:
        """Find players in good form"""
        
        form_players = []
        
        for player in players:
            if (player.form >= min_form and 
                player.minutes >= min_minutes and
                player.status == "a"):
                form_players.append(player)
                
        form_players.sort(key=lambda p: p.form, reverse=True)
        
        return form_players
    
    def find_differential_players(
        self,
        players: List[Player],
        max_ownership: float = 5.0,
        min_points: int = 30
    ) -> List[Player]:
        """Find low-ownership, high-potential players"""
        
        differentials = []
        
        for player in players:
            if (player.selected_by_percent <= max_ownership and
                player.total_points >= min_points and
                player.status == "a"):
                differentials.append(player)
                
        differentials.sort(key=lambda p: p.value_score, reverse=True)
        
        return differentials
    
    def _calculate_points_per_game(
        self,
        player: Player,
        historical: List[Dict]
    ) -> float:
        """Calculate average points per game"""
        
        if not historical:
            return player.points_per_game
            
        games_played = len([g for g in historical if g.get("minutes", 0) > 0])
        
        if games_played == 0:
            return 0
            
        total_points = sum(g.get("total_points", 0) for g in historical)
        return total_points / games_played
    
    def _calculate_minutes_per_game(
        self,
        player: Player,
        historical: List[Dict]
    ) -> float:
        """Calculate average minutes per game"""
        
        if not historical:
            games = max(len([g for g in historical if g.get("minutes", 0) > 0]), 1)
            return player.minutes / games
            
        games_played = len([g for g in historical if g.get("minutes", 0) > 0])
        
        if games_played == 0:
            return 0
            
        total_minutes = sum(g.get("minutes", 0) for g in historical)
        return total_minutes / games_played
    
    def _analyze_form(
        self,
        player: Player,
        historical: List[Dict]
    ) -> Tuple[float, str]:
        """Analyze player form and trend"""
        
        if not historical or len(historical) < 3:
            return player.form, "stable"
            
        recent_games = historical[-5:]
        points = [g.get("total_points", 0) for g in recent_games]
        
        # Calculate trend
        if len(points) >= 3:
            first_half = np.mean(points[:len(points)//2])
            second_half = np.mean(points[len(points)//2:])
            
            if second_half > first_half * 1.2:
                trend = "rising"
            elif second_half < first_half * 0.8:
                trend = "falling"
            else:
                trend = "stable"
        else:
            trend = "stable"
            
        form_rating = np.mean(points) if points else player.form
        
        return form_rating, trend
    
    def _calculate_recent_average(
        self,
        historical: List[Dict],
        n_games: int
    ) -> float:
        """Calculate average over recent N games"""
        
        if not historical:
            return 0
            
        recent = historical[-n_games:]
        if not recent:
            return 0
            
        return np.mean([g.get("total_points", 0) for g in recent])
    
    def _per_90_metric(self, total: float, minutes: int) -> float:
        """Calculate per 90 minutes metric"""
        
        if minutes < 90:
            return 0
            
        return (total / minutes) * 90
    
    def _assess_injury_risk(
        self,
        player: Player,
        historical: List[Dict]
    ) -> float:
        """Assess injury risk (0-1 scale)"""
        
        risk = 0.0
        
        # Current injury status
        if player.status != "a":
            risk += 0.5
            
        # Chance of playing
        if player.chance_of_playing_this_round is not None:
            risk += (100 - player.chance_of_playing_this_round) / 200
            
        # Historical injuries (would need more data)
        # Check for gaps in playing history
        
        return min(risk, 1.0)
    
    def _assess_rotation_risk(
        self,
        player: Player,
        historical: List[Dict],
        team_data: Optional[Dict]
    ) -> float:
        """Assess rotation risk"""
        
        if not historical:
            return 0.3  # Default moderate risk
            
        # Check recent minutes patterns
        recent_games = historical[-5:]
        minutes_played = [g.get("minutes", 0) for g in recent_games]
        
        # High rotation if frequently benched
        benched_games = sum(1 for m in minutes_played if 0 < m < 60)
        
        rotation_risk = benched_games / len(minutes_played) if minutes_played else 0.3
        
        # Adjust for premium players (less likely to be rotated)
        if player.now_cost >= 100:  # £10m+
            rotation_risk *= 0.7
            
        return min(rotation_risk, 1.0)
    
    def _calculate_fixture_difficulty(
        self,
        player: Player,
        fixtures: List[Fixture],
        next_n: int
    ) -> float:
        """Calculate average difficulty of next N fixtures"""
        
        team_fixtures = [
            f for f in fixtures
            if (f.team_h == player.team or f.team_a == player.team) and
            not f.finished
        ][:next_n]
        
        if not team_fixtures:
            return 3.0  # Neutral
            
        difficulties = []
        for f in team_fixtures:
            if f.team_h == player.team:
                difficulties.append(f.team_h_difficulty)
            else:
                difficulties.append(f.team_a_difficulty)
                
        return np.mean(difficulties)
    
    def _analyze_home_away_split(
        self,
        historical: List[Dict]
    ) -> Dict[str, float]:
        """Analyze home vs away performance"""
        
        home_points = []
        away_points = []
        
        for game in historical:
            if game.get("was_home"):
                home_points.append(game.get("total_points", 0))
            else:
                away_points.append(game.get("total_points", 0))
                
        return {
            "home_avg": np.mean(home_points) if home_points else 0,
            "away_avg": np.mean(away_points) if away_points else 0,
            "home_games": len(home_points),
            "away_games": len(away_points)
        }
    
    def _get_difficulty_multiplier(self, difficulty: int) -> float:
        """Get points multiplier based on fixture difficulty"""
        
        multipliers = {
            1: 1.3,   # Very easy
            2: 1.15,  # Easy
            3: 1.0,   # Medium
            4: 0.85,  # Hard
            5: 0.7    # Very hard
        }
        
        return multipliers.get(difficulty, 1.0)
    
    def _predict_goals(
        self,
        player: Player,
        metrics: PlayerMetrics,
        difficulty: int
    ) -> float:
        """Predict expected goals"""
        
        base_xG = metrics.xG_per_90 * (metrics.predicted_minutes / 90)
        
        # Adjust for position
        position_multiplier = {
            Position.FORWARD: 1.2,
            Position.MIDFIELDER: 1.0,
            Position.DEFENDER: 0.5,
            Position.GOALKEEPER: 0.1
        }.get(Position(player.element_type), 1.0)
        
        # Adjust for difficulty
        diff_multiplier = self._get_difficulty_multiplier(difficulty)
        
        return base_xG * position_multiplier * diff_multiplier
    
    def _predict_assists(
        self,
        player: Player,
        metrics: PlayerMetrics,
        difficulty: int
    ) -> float:
        """Predict expected assists"""
        
        base_xA = metrics.xA_per_90 * (metrics.predicted_minutes / 90)
        
        # Adjust for position
        position_multiplier = {
            Position.MIDFIELDER: 1.1,
            Position.FORWARD: 0.9,
            Position.DEFENDER: 0.7,
            Position.GOALKEEPER: 0.1
        }.get(Position(player.element_type), 1.0)
        
        # Adjust for difficulty
        diff_multiplier = self._get_difficulty_multiplier(difficulty)
        
        return base_xA * position_multiplier * diff_multiplier
    
    def _predict_clean_sheet(
        self,
        player: Player,
        fixture: Fixture,
        is_home: bool
    ) -> float:
        """Predict clean sheet probability"""
        
        position = Position(player.element_type)
        
        if position not in [Position.GOALKEEPER, Position.DEFENDER]:
            return 0
            
        # Base probability by difficulty
        difficulty = fixture.team_h_difficulty if is_home else fixture.team_a_difficulty
        
        base_prob = {
            1: 0.5,
            2: 0.4,
            3: 0.3,
            4: 0.2,
            5: 0.1
        }.get(difficulty, 0.25)
        
        # Home advantage
        if is_home:
            base_prob *= 1.2
            
        return min(base_prob, 0.6)
    
    def _predict_bonus(
        self,
        player: Player,
        metrics: PlayerMetrics
    ) -> float:
        """Predict expected bonus points"""
        
        # Based on BPS per 90
        bps_expected = metrics.bps_per_90 * (metrics.predicted_minutes / 90)
        
        # Rough conversion to bonus points
        if bps_expected > 30:
            return 2.5  # Likely to get 3 bonus
        elif bps_expected > 25:
            return 1.5  # Likely to get 2 bonus
        elif bps_expected > 20:
            return 0.5  # Might get 1 bonus
        else:
            return 0
    
    def _predict_minutes(
        self,
        player: Player,
        metrics: PlayerMetrics
    ) -> float:
        """Predict minutes to be played"""
        
        # Base on recent average
        base_minutes = metrics.minutes_per_game
        
        # Adjust for injury risk
        minutes = base_minutes * (1 - metrics.injury_risk)
        
        # Adjust for rotation risk
        minutes *= (1 - metrics.rotation_risk * 0.5)
        
        return min(minutes, 90)
    
    def _calculate_confidence(
        self,
        player: Player,
        metrics: PlayerMetrics,
        predicted_minutes: float
    ) -> float:
        """Calculate prediction confidence"""
        
        confidence_factors = []
        
        # Minutes confidence
        if predicted_minutes > 75:
            confidence_factors.append(0.9)
        elif predicted_minutes > 60:
            confidence_factors.append(0.7)
        else:
            confidence_factors.append(0.5)
            
        # Form confidence
        if metrics.form_trend == "rising":
            confidence_factors.append(0.8)
        elif metrics.form_trend == "stable":
            confidence_factors.append(0.7)
        else:
            confidence_factors.append(0.6)
            
        # Injury confidence
        confidence_factors.append(1 - metrics.injury_risk)
        
        return np.mean(confidence_factors)