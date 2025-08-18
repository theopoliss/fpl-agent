from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
import numpy as np

from src.data.models import Player, Squad, Fixture
from src.utils.constants import Position
from src.utils.logging import app_logger, log_decision
from src.utils.config import config


@dataclass
class CaptainChoice:
    """Represents a captaincy choice with reasoning"""
    player: Player
    expected_points: float
    confidence: float
    reasoning: List[str]
    is_differential: bool = False
    ownership: float = 0.0
    
    @property
    def effective_ownership(self) -> float:
        """Effective ownership considering captaincy"""
        return self.ownership * 2  # Rough estimate


class CaptainSelector:
    """Selects captain and vice-captain for each gameweek"""
    
    def __init__(self):
        self.captain_threshold = config.fpl.captain_threshold_multiplier
        self.vice_threshold = config.fpl.vice_captain_threshold_multiplier
        
    def select_captain_and_vice(
        self,
        squad: Squad,
        gameweek_predictions: Dict[int, float],
        fixtures: List[Fixture],
        ownership_data: Optional[Dict[int, float]] = None,
        triple_captain_active: bool = False
    ) -> Tuple[CaptainChoice, CaptainChoice]:
        """
        Select captain and vice-captain for the gameweek
        """
        app_logger.info(f"Selecting captain and vice-captain (TC: {triple_captain_active})")
        
        # Get starting XI
        starting_xi = squad.get_starting_xi()
        
        # Evaluate all players
        captain_choices = []
        
        for player in starting_xi:
            choice = self._evaluate_captain_choice(
                player,
                gameweek_predictions.get(player.id, 0),
                fixtures,
                ownership_data.get(player.id, 0) if ownership_data else 0
            )
            captain_choices.append(choice)
        
        # Sort by expected points
        captain_choices.sort(key=lambda c: c.expected_points, reverse=True)
        
        # Select captain
        captain = self._select_best_captain(captain_choices, triple_captain_active)
        
        # Select vice-captain (different from captain)
        vice_choices = [c for c in captain_choices if c.player.id != captain.player.id]
        vice_captain = vice_choices[0] if vice_choices else captain_choices[1]
        
        # Log decision
        log_decision(
            "captain_selection",
            captain=captain.player.web_name,
            captain_points=captain.expected_points,
            vice_captain=vice_captain.player.web_name,
            vice_points=vice_captain.expected_points,
            triple_captain=triple_captain_active
        )
        
        return captain, vice_captain
    
    def evaluate_triple_captain(
        self,
        captain_choice: CaptainChoice,
        gameweek: int,
        chips_used: List[str]
    ) -> bool:
        """
        Determine if triple captain should be used
        """
        # Check if already used in this half
        phase = "first_half" if gameweek <= 19 else "second_half"
        tc_used = f"triple_captain_{phase}" in chips_used
        
        if tc_used:
            return False
            
        # Check threshold
        tc_threshold = config.fpl.triple_captain_min_points
        
        if captain_choice.expected_points < tc_threshold:
            return False
            
        # Additional checks
        reasons_for = []
        reasons_against = []
        
        # Check for premium captain with great fixture
        if captain_choice.player.now_cost >= 120:  # £12m+
            reasons_for.append("Premium player")
            
        # Check confidence
        if captain_choice.confidence > 0.8:
            reasons_for.append(f"High confidence ({captain_choice.confidence:.0%})")
            
        # Check if differential
        if captain_choice.is_differential and captain_choice.expected_points > tc_threshold * 1.2:
            reasons_for.append("High-scoring differential")
            
        # Consider saving for better opportunity
        if gameweek < 10 or (gameweek > 19 and gameweek < 29):
            reasons_against.append("Early in phase - better opportunities may come")
            
        # Make decision
        use_tc = len(reasons_for) >= 2 and len(reasons_against) == 0
        
        if use_tc:
            log_decision(
                "triple_captain",
                player=captain_choice.player.web_name,
                expected_points=captain_choice.expected_points,
                reasons=reasons_for
            )
            
        return use_tc
    
    def find_differential_captains(
        self,
        squad: Squad,
        gameweek_predictions: Dict[int, float],
        ownership_data: Dict[int, float],
        threshold: float = 10.0
    ) -> List[CaptainChoice]:
        """
        Find differential captain options (low ownership, high potential)
        """
        app_logger.info("Finding differential captain options")
        
        differentials = []
        
        for player in squad.get_starting_xi():
            ownership = ownership_data.get(player.id, 0)
            expected = gameweek_predictions.get(player.id, 0)
            
            # Low ownership but high expected points
            if ownership < threshold and expected > 6.0:
                choice = CaptainChoice(
                    player=player,
                    expected_points=expected,
                    confidence=0.6,  # Lower confidence for differentials
                    reasoning=[
                        f"Low ownership ({ownership:.1f}%)",
                        f"High upside ({expected:.1f} pts)"
                    ],
                    is_differential=True,
                    ownership=ownership
                )
                differentials.append(choice)
        
        differentials.sort(key=lambda c: c.expected_points, reverse=True)
        
        return differentials
    
    def _evaluate_captain_choice(
        self,
        player: Player,
        predicted_points: float,
        fixtures: List[Fixture],
        ownership: float
    ) -> CaptainChoice:
        """Evaluate a player as captain choice"""
        
        reasons = []
        confidence_factors = []
        
        # Base confidence from predicted points
        base_confidence = min(predicted_points / 15.0, 1.0)
        confidence_factors.append(base_confidence)
        
        # Form factor
        if player.form > 6.0:
            reasons.append(f"Excellent form ({player.form:.1f})")
            confidence_factors.append(0.9)
        elif player.form > 4.0:
            reasons.append(f"Good form ({player.form:.1f})")
            confidence_factors.append(0.7)
            
        # Position bonus for attackers
        if player.element_type == Position.FORWARD.value:
            reasons.append("Forward position")
            confidence_factors.append(0.8)
        elif player.element_type == Position.MIDFIELDER.value:
            reasons.append("Attacking midfielder")
            confidence_factors.append(0.75)
            
        # Home/away consideration
        player_fixtures = [f for f in fixtures if 
                          f.team_h == player.team or f.team_a == player.team]
        
        if player_fixtures:
            fixture = player_fixtures[0]
            if fixture.team_h == player.team:
                reasons.append("Home fixture")
                confidence_factors.append(0.8)
                
            # Fixture difficulty
            difficulty = fixture.team_h_difficulty if fixture.team_h == player.team else fixture.team_a_difficulty
            if difficulty <= 2:
                reasons.append(f"Easy fixture (FDR {difficulty})")
                confidence_factors.append(0.9)
            elif difficulty >= 4:
                reasons.append(f"Difficult fixture (FDR {difficulty})")
                confidence_factors.append(0.5)
                
        # Premium player factor
        if player.now_cost >= 120:  # £12m+
            reasons.append("Premium asset")
            confidence_factors.append(0.85)
            
        # Historical captain performance
        if player.selected_by_percent > 30:
            reasons.append(f"Highly selected ({player.selected_by_percent:.1f}%)")
            
        # Calculate overall confidence
        confidence = np.mean(confidence_factors) if confidence_factors else 0.5
        
        # Check if differential
        is_differential = ownership < 10.0 and predicted_points > 7.0
        
        return CaptainChoice(
            player=player,
            expected_points=predicted_points,
            confidence=confidence,
            reasoning=reasons,
            is_differential=is_differential,
            ownership=ownership
        )
    
    def _select_best_captain(
        self,
        choices: List[CaptainChoice],
        triple_captain: bool
    ) -> CaptainChoice:
        """Select the best captain from choices"""
        
        if not choices:
            raise ValueError("No captain choices available")
            
        # For triple captain, be more selective
        if triple_captain:
            # Filter to high confidence only
            high_confidence = [c for c in choices if c.confidence > 0.75]
            if high_confidence:
                return high_confidence[0]
                
        # Standard selection
        best = choices[0]
        
        # Consider differential if close in points
        if len(choices) > 1:
            second = choices[1]
            
            # If differential is close in points but much lower ownership
            if (second.is_differential and 
                second.expected_points > best.expected_points * 0.85 and
                second.ownership < best.ownership * 0.3):
                
                log_decision(
                    "differential_captain",
                    selected=second.player.web_name,
                    over=best.player.web_name,
                    ownership_diff=best.ownership - second.ownership
                )
                return second
                
        return best
    
    def analyze_captaincy_trends(
        self,
        historical_choices: List[Dict],
        gameweek: int
    ) -> Dict:
        """Analyze historical captaincy performance"""
        
        if not historical_choices:
            return {}
            
        analysis = {
            "total_captain_points": 0,
            "average_captain_points": 0,
            "best_captain_week": None,
            "worst_captain_week": None,
            "differential_success_rate": 0,
        }
        
        captain_points = []
        differential_attempts = 0
        differential_successes = 0
        
        for choice in historical_choices:
            points = choice.get("actual_points", 0) * choice.get("multiplier", 2)
            captain_points.append(points)
            
            if choice.get("is_differential", False):
                differential_attempts += 1
                if points > 20:  # Successful differential
                    differential_successes += 1
                    
        if captain_points:
            analysis["total_captain_points"] = sum(captain_points)
            analysis["average_captain_points"] = np.mean(captain_points)
            analysis["best_captain_week"] = max(captain_points)
            analysis["worst_captain_week"] = min(captain_points)
            
        if differential_attempts > 0:
            analysis["differential_success_rate"] = differential_successes / differential_attempts
            
        return analysis