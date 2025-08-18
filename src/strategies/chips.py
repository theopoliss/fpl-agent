from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime
import numpy as np

from src.data.models import Squad, Player, Fixture, ChipUsage, ChipType
from src.utils.constants import Chip, FPLConstants, GameWeekPhase
from src.utils.logging import app_logger, log_chip_usage, log_decision
from src.utils.config import config


@dataclass
class ChipRecommendation:
    """Recommendation for chip usage"""
    chip: Chip
    gameweek: int
    expected_benefit: float
    confidence: float
    reasoning: List[str]
    alternative: Optional[str] = None


class ChipStrategy:
    """Manages chip usage strategy throughout the season"""
    
    def __init__(self):
        self.wildcard_threshold = config.fpl.wildcard_team_issues
        self.bench_boost_threshold = config.fpl.bench_boost_min_points
        self.triple_captain_threshold = config.fpl.triple_captain_min_points
        self.free_hit_threshold = config.fpl.free_hit_fixture_swing
        
    def evaluate_chip_usage(
        self,
        squad: Squad,
        gameweek: int,
        chips_used: List[ChipUsage],
        fixtures: List[Fixture],
        predictions: Dict[int, float],
        team_issues: List[str]
    ) -> Optional[ChipRecommendation]:
        """
        Evaluate whether to use a chip this gameweek
        """
        app_logger.info(f"Evaluating chip usage for GW{gameweek}")
        
        # Determine current phase
        phase = self._get_phase(gameweek)
        
        # Check available chips
        available_chips = self._get_available_chips(chips_used, phase)
        
        if not available_chips:
            app_logger.info("No chips available for use")
            return None
            
        # Evaluate each available chip
        recommendations = []
        
        if Chip.WILDCARD in available_chips:
            wc_rec = self._evaluate_wildcard(squad, team_issues, gameweek, fixtures)
            if wc_rec:
                recommendations.append(wc_rec)
                
        if Chip.FREE_HIT in available_chips:
            fh_rec = self._evaluate_free_hit(squad, fixtures, predictions, gameweek)
            if fh_rec:
                recommendations.append(fh_rec)
                
        if Chip.BENCH_BOOST in available_chips:
            bb_rec = self._evaluate_bench_boost(squad, predictions, gameweek)
            if bb_rec:
                recommendations.append(bb_rec)
                
        if Chip.TRIPLE_CAPTAIN in available_chips:
            tc_rec = self._evaluate_triple_captain(squad, predictions, gameweek)
            if tc_rec:
                recommendations.append(tc_rec)
                
        # Select best recommendation
        if recommendations:
            best = max(recommendations, key=lambda r: r.expected_benefit * r.confidence)
            
            # Only recommend if benefit is significant
            if best.expected_benefit > self._get_minimum_benefit(best.chip):
                log_chip_usage(
                    best.chip.value,
                    gameweek,
                    expected_benefit=best.expected_benefit,
                    confidence=best.confidence,
                    reasons=best.reasoning
                )
                return best
                
        return None
    
    def plan_chip_schedule(
        self,
        current_gameweek: int,
        chips_used: List[ChipUsage],
        fixtures: List[Fixture]
    ) -> Dict[int, Chip]:
        """
        Plan optimal chip usage for remainder of season
        """
        app_logger.info("Planning chip usage schedule")
        
        schedule = {}
        
        # Identify key gameweeks
        dgw_weeks = self._find_double_gameweeks(fixtures)
        bgw_weeks = self._find_blank_gameweeks(fixtures)
        easy_runs = self._find_easy_fixture_runs(fixtures)
        
        # Plan Bench Boost for DGW
        if dgw_weeks and Chip.BENCH_BOOST not in [c.chip for c in chips_used]:
            best_dgw = max(dgw_weeks, key=lambda w: w["teams_playing_twice"])
            schedule[best_dgw["gameweek"]] = Chip.BENCH_BOOST
            
        # Plan Free Hit for BGW or bad fixtures
        if bgw_weeks and Chip.FREE_HIT not in [c.chip for c in chips_used]:
            worst_bgw = min(bgw_weeks, key=lambda w: w["teams_playing"])
            schedule[worst_bgw["gameweek"]] = Chip.FREE_HIT
            
        # Plan Triple Captain for easy fixtures
        if easy_runs:
            for run in easy_runs:
                if run["gameweek"] not in schedule:
                    schedule[run["gameweek"]] = Chip.TRIPLE_CAPTAIN
                    break
                    
        # Plan Wildcards strategically
        # First wildcard around GW8-12
        if current_gameweek <= 8:
            schedule[10] = Chip.WILDCARD
        # Second wildcard around GW28-32
        if current_gameweek <= 28:
            schedule[30] = Chip.WILDCARD
            
        log_decision(
            "chip_schedule",
            schedule={f"GW{k}": v.value for k, v in schedule.items()}
        )
        
        return schedule
    
    def _evaluate_wildcard(
        self,
        squad: Squad,
        team_issues: List[str],
        gameweek: int,
        fixtures: List[Fixture]
    ) -> Optional[ChipRecommendation]:
        """Evaluate wildcard usage"""
        
        reasons = []
        confidence_factors = []
        
        # Check team issues
        issue_count = len(team_issues)
        if issue_count >= self.wildcard_threshold:
            reasons.append(f"{issue_count} squad issues identified")
            confidence_factors.append(0.9)
            
        # Check if many injuries
        injured_count = sum(1 for p in squad.players if p.status != "a")
        if injured_count >= 3:
            reasons.append(f"{injured_count} injured players")
            confidence_factors.append(0.85)
            
        # Check squad value decline
        value_decline = squad.value - squad.budget
        if value_decline < -2.0:
            reasons.append(f"Squad value declined by £{-value_decline:.1f}m")
            confidence_factors.append(0.7)
            
        # Check for fixture swing
        current_difficulty = self._calculate_squad_fixture_difficulty(squad, fixtures, 5)
        if current_difficulty > 3.5:
            reasons.append(f"Difficult fixtures ahead (avg {current_difficulty:.1f})")
            confidence_factors.append(0.75)
            
        # Strategic timing
        if gameweek in [8, 9, 10, 28, 29, 30]:
            reasons.append("Strategic wildcard window")
            confidence_factors.append(0.6)
            
        if not reasons:
            return None
            
        # Calculate expected benefit
        expected_benefit = issue_count * 2 + injured_count * 3
        confidence = np.mean(confidence_factors) if confidence_factors else 0.5
        
        return ChipRecommendation(
            chip=Chip.WILDCARD,
            gameweek=gameweek,
            expected_benefit=expected_benefit,
            confidence=confidence,
            reasoning=reasons
        )
    
    def _evaluate_free_hit(
        self,
        squad: Squad,
        fixtures: List[Fixture],
        predictions: Dict[int, float],
        gameweek: int
    ) -> Optional[ChipRecommendation]:
        """Evaluate free hit usage"""
        
        reasons = []
        confidence_factors = []
        
        # Check for blank gameweek
        playing_count = self._count_playing_players(squad, fixtures, gameweek)
        if playing_count < 8:
            reasons.append(f"Only {playing_count} players have fixtures")
            confidence_factors.append(0.95)
            
        # Check fixture difficulty swing
        current_avg = self._calculate_squad_fixture_difficulty(squad, fixtures, 1)
        best_possible_avg = self._calculate_best_possible_difficulty(fixtures, gameweek)
        
        fixture_swing = current_avg - best_possible_avg
        if fixture_swing > 1.5:
            reasons.append(f"Fixture swing of {fixture_swing:.1f} available")
            confidence_factors.append(0.8)
            
        # Check for mass rotation risk
        rotation_risk = sum(1 for p in squad.players if self._is_rotation_risk(p, gameweek))
        if rotation_risk >= 5:
            reasons.append(f"{rotation_risk} players at rotation risk")
            confidence_factors.append(0.7)
            
        if not reasons:
            return None
            
        # Calculate expected benefit
        expected_benefit = (11 - playing_count) * 3 + fixture_swing * 5
        confidence = np.mean(confidence_factors) if confidence_factors else 0.5
        
        return ChipRecommendation(
            chip=Chip.FREE_HIT,
            gameweek=gameweek,
            expected_benefit=expected_benefit,
            confidence=confidence,
            reasoning=reasons
        )
    
    def _evaluate_bench_boost(
        self,
        squad: Squad,
        predictions: Dict[int, float],
        gameweek: int
    ) -> Optional[ChipRecommendation]:
        """Evaluate bench boost usage"""
        
        reasons = []
        confidence_factors = []
        
        # Calculate bench predicted points
        bench = squad.get_bench()
        bench_points = sum(predictions.get(p.id, 0) for p in bench)
        
        if bench_points >= self.bench_boost_threshold:
            reasons.append(f"Bench predicted {bench_points:.1f} points")
            confidence_factors.append(0.85)
            
        # Check for double gameweek
        dgw_players = sum(1 for p in bench if self._has_double_gameweek(p, gameweek))
        if dgw_players >= 2:
            reasons.append(f"{dgw_players} bench players have DGW")
            confidence_factors.append(0.9)
            
        # Check bench quality
        bench_value = sum(p.price for p in bench)
        if bench_value >= 20.0:  # £20m+ bench
            reasons.append(f"High value bench (£{bench_value:.1f}m)")
            confidence_factors.append(0.7)
            
        # All bench players fit
        fit_bench = all(p.status == "a" for p in bench)
        if fit_bench:
            reasons.append("All bench players available")
            confidence_factors.append(0.8)
        else:
            return None  # Don't use BB with injured bench
            
        if not reasons:
            return None
            
        expected_benefit = bench_points
        confidence = np.mean(confidence_factors) if confidence_factors else 0.5
        
        return ChipRecommendation(
            chip=Chip.BENCH_BOOST,
            gameweek=gameweek,
            expected_benefit=expected_benefit,
            confidence=confidence,
            reasoning=reasons
        )
    
    def _evaluate_triple_captain(
        self,
        squad: Squad,
        predictions: Dict[int, float],
        gameweek: int
    ) -> Optional[ChipRecommendation]:
        """Evaluate triple captain usage"""
        
        reasons = []
        confidence_factors = []
        
        # Find best captain option
        starting = squad.get_starting_xi()
        captain_options = [(p, predictions.get(p.id, 0)) for p in starting]
        captain_options.sort(key=lambda x: x[1], reverse=True)
        
        if captain_options:
            best_player, best_points = captain_options[0]
            
            if best_points >= self.triple_captain_threshold:
                reasons.append(f"{best_player.web_name} predicted {best_points:.1f} points")
                confidence_factors.append(0.85)
                
            # Check for double gameweek
            if self._has_double_gameweek(best_player, gameweek):
                reasons.append(f"{best_player.web_name} has DGW")
                confidence_factors.append(0.95)
                
            # Check fixture
            player_fixtures = self._get_player_fixtures(best_player, gameweek)
            if player_fixtures and all(f.difficulty <= 2 for f in player_fixtures):
                reasons.append("Excellent fixture(s)")
                confidence_factors.append(0.9)
                
            # Premium player check
            if best_player.now_cost >= 130:  # £13m+
                reasons.append("Premium captain option")
                confidence_factors.append(0.75)
                
        if not reasons:
            return None
            
        expected_benefit = (best_points * 3) - (best_points * 2)  # TC vs normal captain
        confidence = np.mean(confidence_factors) if confidence_factors else 0.5
        
        return ChipRecommendation(
            chip=Chip.TRIPLE_CAPTAIN,
            gameweek=gameweek,
            expected_benefit=expected_benefit,
            confidence=confidence,
            reasoning=reasons
        )
    
    def _get_phase(self, gameweek: int) -> GameWeekPhase:
        """Get current gameweek phase"""
        if gameweek <= 19:
            return GameWeekPhase.FIRST_HALF
        else:
            return GameWeekPhase.SECOND_HALF
    
    def _get_available_chips(
        self,
        chips_used: List[ChipUsage],
        phase: GameWeekPhase
    ) -> List[Chip]:
        """Get chips still available in current phase"""
        
        available = []
        phase_str = phase.value
        
        # Count chips used in current phase
        phase_chips = [c for c in chips_used if c.phase == phase_str]
        
        for chip in Chip:
            used_count = sum(1 for c in phase_chips if c.chip == chip)
            allowed = FPLConstants.CHIPS_PER_HALF[chip]
            
            if used_count < allowed:
                available.append(chip)
                
        return available
    
    def _get_minimum_benefit(self, chip: Chip) -> float:
        """Get minimum expected benefit to use chip"""
        
        thresholds = {
            Chip.WILDCARD: 10.0,
            Chip.FREE_HIT: 15.0,
            Chip.BENCH_BOOST: 15.0,
            Chip.TRIPLE_CAPTAIN: 5.0
        }
        
        return thresholds.get(chip, 10.0)
    
    def _calculate_squad_fixture_difficulty(
        self,
        squad: Squad,
        fixtures: List[Fixture],
        next_n: int
    ) -> float:
        """Calculate average fixture difficulty for squad"""
        
        difficulties = []
        
        for player in squad.get_starting_xi():
            player_fixtures = [
                f for f in fixtures
                if (f.team_h == player.team or f.team_a == player.team) and
                not f.finished
            ][:next_n]
            
            for f in player_fixtures:
                if f.team_h == player.team:
                    difficulties.append(f.team_h_difficulty)
                else:
                    difficulties.append(f.team_a_difficulty)
                    
        return np.mean(difficulties) if difficulties else 3.0
    
    def _calculate_best_possible_difficulty(
        self,
        fixtures: List[Fixture],
        gameweek: int
    ) -> float:
        """Calculate best possible average difficulty"""
        
        gw_fixtures = [f for f in fixtures if f.event == gameweek]
        
        if not gw_fixtures:
            return 3.0
            
        # Get easiest fixtures
        difficulties = []
        for f in gw_fixtures:
            difficulties.append(min(f.team_h_difficulty, f.team_a_difficulty))
            
        # Return average of 11 easiest
        difficulties.sort()
        return np.mean(difficulties[:11])
    
    def _count_playing_players(
        self,
        squad: Squad,
        fixtures: List[Fixture],
        gameweek: int
    ) -> int:
        """Count how many squad players have fixtures"""
        
        gw_fixtures = [f for f in fixtures if f.event == gameweek]
        playing_teams = set()
        
        for f in gw_fixtures:
            playing_teams.add(f.team_h)
            playing_teams.add(f.team_a)
            
        return sum(1 for p in squad.players if p.team in playing_teams)
    
    def _is_rotation_risk(self, player: Player, gameweek: int) -> bool:
        """Check if player is at rotation risk"""
        
        # Would need more context (e.g., European fixtures)
        # Simplified check
        return player.minutes < 180 and player.now_cost >= 80
    
    def _has_double_gameweek(self, player: Player, gameweek: int) -> bool:
        """Check if player has double gameweek"""
        
        # Would need fixture data
        # This is a placeholder
        return False
    
    def _get_player_fixtures(
        self,
        player: Player,
        gameweek: int
    ) -> List[Dict]:
        """Get player's fixtures for gameweek"""
        
        # Would need fixture data
        # This is a placeholder
        return []
    
    def _find_double_gameweeks(self, fixtures: List[Fixture]) -> List[Dict]:
        """Find double gameweeks"""
        
        # Group fixtures by gameweek and team
        # Identify where teams play twice
        # This is a simplified version
        return []
    
    def _find_blank_gameweeks(self, fixtures: List[Fixture]) -> List[Dict]:
        """Find blank gameweeks"""
        
        # Identify gameweeks with fewer fixtures
        # This is a simplified version
        return []
    
    def _find_easy_fixture_runs(self, fixtures: List[Fixture]) -> List[Dict]:
        """Find runs of easy fixtures"""
        
        # Analyze fixture difficulty patterns
        # This is a simplified version
        return []