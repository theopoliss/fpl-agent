from enum import Enum
from typing import Dict, List


class Position(Enum):
    GOALKEEPER = 1
    DEFENDER = 2
    MIDFIELDER = 3
    FORWARD = 4


class Chip(Enum):
    WILDCARD = "wildcard"
    FREE_HIT = "freehit"
    BENCH_BOOST = "bboost"
    TRIPLE_CAPTAIN = "3xc"


class GameWeekPhase(Enum):
    FIRST_HALF = "first_half"  # GW 1-19
    SECOND_HALF = "second_half"  # GW 20-38


class FPLConstants:
    # Budget and squad
    INITIAL_BUDGET = 100.0  # £100m
    SQUAD_SIZE = 15
    MAX_PLAYERS_PER_TEAM = 3
    
    # Squad composition requirements
    SQUAD_REQUIREMENTS = {
        Position.GOALKEEPER: 2,
        Position.DEFENDER: 5,
        Position.MIDFIELDER: 5,
        Position.FORWARD: 3,
    }
    
    # Formation constraints
    MIN_FORMATION = {
        Position.GOALKEEPER: 1,
        Position.DEFENDER: 3,
        Position.MIDFIELDER: 2,
        Position.FORWARD: 1,
    }
    
    MAX_FORMATION = {
        Position.GOALKEEPER: 1,
        Position.DEFENDER: 5,
        Position.MIDFIELDER: 5,
        Position.FORWARD: 3,
    }
    
    STARTING_XI_SIZE = 11
    BENCH_SIZE = 4
    
    # Valid formations
    VALID_FORMATIONS = [
        (1, 3, 4, 3),
        (1, 3, 5, 2),
        (1, 4, 3, 3),
        (1, 4, 4, 2),
        (1, 4, 5, 1),
        (1, 5, 3, 2),
        (1, 5, 4, 1),
        (1, 5, 2, 3),  # Rare but valid
    ]
    
    # Transfer rules
    FREE_TRANSFERS_PER_WEEK = 1
    MAX_BANKED_TRANSFERS = 5
    TRANSFER_COST_POINTS = 4
    
    # Special transfer windows
    AFCON_BOOST_GAMEWEEK = 16  # Free transfers topped up to 5
    
    # Chip usage (2025/26 rules - each chip can be used twice)
    CHIPS_PER_HALF = {
        Chip.WILDCARD: 1,
        Chip.FREE_HIT: 1,
        Chip.BENCH_BOOST: 1,
        Chip.TRIPLE_CAPTAIN: 1,
    }
    
    FIRST_HALF_GAMEWEEKS = list(range(1, 20))  # GW 1-19
    SECOND_HALF_GAMEWEEKS = list(range(20, 39))  # GW 20-38
    
    # Points scoring
    POINTS_SCORING = {
        "goal_scored": {
            Position.GOALKEEPER: 6,
            Position.DEFENDER: 6,
            Position.MIDFIELDER: 5,
            Position.FORWARD: 4,
        },
        "assist": 3,
        "clean_sheet": {
            Position.GOALKEEPER: 4,
            Position.DEFENDER: 4,
            Position.MIDFIELDER: 1,
            Position.FORWARD: 0,
        },
        "penalty_save": 5,
        "penalty_miss": -2,
        "yellow_card": -1,
        "red_card": -3,
        "own_goal": -2,
        "bonus": [3, 2, 1],  # Top 3 BPS players
        "saves": 1,  # Per 3 saves
        "defensive_contribution": 2,  # 10 for DEF, 12 for MID/FWD
    }
    
    # Defensive contribution thresholds (2025/26 new rule)
    DEFENSIVE_CONTRIBUTION_THRESHOLD = {
        Position.DEFENDER: 10,  # Clearances, blocks, interceptions, tackles
        Position.MIDFIELDER: 12,  # + ball recoveries
        Position.FORWARD: 12,  # + ball recoveries
    }
    
    # Deadline rules
    DEADLINE_OFFSET_MINUTES = 90  # 90 minutes before first match
    
    # Fixture difficulty rating
    FDR_SCALE = {
        1: "Very Easy",
        2: "Easy",
        3: "Medium",
        4: "Hard",
        5: "Very Hard",
    }
    
    # Auto-sub priorities
    AUTO_SUB_PRIORITY = [
        Position.GOALKEEPER,
        Position.FORWARD,
        Position.MIDFIELDER,
        Position.DEFENDER,
    ]


class FormationValidator:
    @staticmethod
    def is_valid_formation(
        gk: int, def_: int, mid: int, fwd: int
    ) -> bool:
        """Check if a formation is valid according to FPL rules"""
        # Must have exactly 11 players
        if gk + def_ + mid + fwd != FPLConstants.STARTING_XI_SIZE:
            return False
            
        # Check position constraints
        if gk != 1:
            return False
        if def_ < 3 or def_ > 5:
            return False
        if mid < 2 or mid > 5:
            return False
        if fwd < 1 or fwd > 3:
            return False
            
        return (gk, def_, mid, fwd) in FPLConstants.VALID_FORMATIONS
        
    @staticmethod
    def get_all_valid_formations() -> List[tuple]:
        """Get all valid formations"""
        return FPLConstants.VALID_FORMATIONS
        
    @staticmethod
    def suggest_formation(
        defenders: int, midfielders: int, forwards: int
    ) -> tuple:
        """Suggest a valid formation based on available players"""
        # Start with most common formation
        best_formation = (1, 4, 4, 2)
        
        # Try to find formation that uses most valuable players
        for formation in FPLConstants.VALID_FORMATIONS:
            _, d, m, f = formation
            if d <= defenders and m <= midfielders and f <= forwards:
                # Prefer formations that use more attacking players
                if (m + f) > (best_formation[2] + best_formation[3]):
                    best_formation = formation
                    
        return best_formation


class BudgetValidator:
    @staticmethod
    def calculate_squad_value(players: List[Dict]) -> float:
        """Calculate total value of a squad"""
        return sum(p.get("now_cost", 0) for p in players) / 10
        
    @staticmethod
    def is_within_budget(players: List[Dict], budget: float) -> bool:
        """Check if squad is within budget"""
        return BudgetValidator.calculate_squad_value(players) <= budget
        
    @staticmethod
    def get_remaining_budget(players: List[Dict], budget: float) -> float:
        """Get remaining budget after selecting players"""
        return budget - BudgetValidator.calculate_squad_value(players)


class SquadValidator:
    @staticmethod
    def validate_squad(players: List[Dict]) -> Dict[str, bool]:
        """Validate a squad against FPL rules"""
        validation = {
            "valid_size": len(players) == FPLConstants.SQUAD_SIZE,
            "valid_positions": True,
            "valid_teams": True,
            "valid_budget": True,
            "errors": []
        }
        
        # Check squad size
        if not validation["valid_size"]:
            validation["errors"].append(
                f"Squad must have {FPLConstants.SQUAD_SIZE} players"
            )
            
        # Check position requirements
        position_counts = {pos: 0 for pos in Position}
        for player in players:
            pos = Position(player.get("element_type"))
            position_counts[pos] += 1
            
        for pos, required in FPLConstants.SQUAD_REQUIREMENTS.items():
            if position_counts[pos] != required:
                validation["valid_positions"] = False
                validation["errors"].append(
                    f"Must have exactly {required} {pos.name.lower()}s"
                )
                
        # Check team limits
        team_counts = {}
        for player in players:
            team = player.get("team")
            team_counts[team] = team_counts.get(team, 0) + 1
            
        for team, count in team_counts.items():
            if count > FPLConstants.MAX_PLAYERS_PER_TEAM:
                validation["valid_teams"] = False
                validation["errors"].append(
                    f"Maximum {FPLConstants.MAX_PLAYERS_PER_TEAM} players per team"
                )
                break
                
        return validation