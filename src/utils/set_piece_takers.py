"""
Set piece taker identification and management
Maintains list of known penalty and free kick takers for bonus scoring
"""

from typing import Dict, List, Set


class SetPieceTakers:
    """Manages information about set piece takers in FPL"""
    
    # Known penalty takers for 2025/26 season
    # Based on official team penalty taker hierarchies
    PENALTY_TAKERS = {
        # Primary takers (almost guaranteed if on pitch)
        'primary': {
            'Haaland',           # Man City
            'Palmer',            # Chelsea  
            'M.Salah',           # Liverpool
            'Saka',              # Arsenal
            'Bruno Fernandes',   # Man United
            'Raúl',             # Fulham
            'Wood',             # Nott'm Forest
            'Mateta',           # Crystal Palace
            'Ndiaye',           # Everton
            'Paqueta',          # West Ham
            'Wissa',            # Brentford
            'Watkins'           # Aston Villa

        },
        # Secondary takers (take some but not all)
        'secondary': {
        }
    }
    
    # Known free kick specialists
    FREE_KICK_TAKERS = {
        'primary': {
            'Ward-Prowse',      # West Ham - FK specialist
            'Trippier',         # Newcastle - Set piece expert
            'Digne',           # Aston Villa - Left foot
            'Bruno Fernandes', # Man United
            'Ødegaard',        # Arsenal
        },
        'secondary': {
            'Saka',            # Arsenal  
            'Palmer',          # Chelsea
            'M.Salah',         # Liverpool (right side)
            'Pereira',         # Fulham
        }
    }
    
    # Players who take corners and have good heading/scoring ability
    CORNER_SPECIALISTS = {
        'Trippier',        # Newcastle - Takes corners
        'Saka',            # Arsenal - Takes corners
        'Ødegaard',        # Arsenal - Takes corners
        'Palmer',          # Chelsea - Takes corners
        'Ward-Prowse',     # West Ham - Takes everything
    }
    
    @classmethod
    def is_penalty_taker(cls, player_name: str, primary_only: bool = False) -> bool:
        """
        Check if a player is a known penalty taker
        
        Args:
            player_name: The player's web_name
            primary_only: Only return True for primary takers
        """
        if player_name in cls.PENALTY_TAKERS['primary']:
            return True
        
        if not primary_only and player_name in cls.PENALTY_TAKERS['secondary']:
            return True
            
        return False
    
    @classmethod
    def is_free_kick_taker(cls, player_name: str, primary_only: bool = False) -> bool:
        """
        Check if a player is a known free kick taker
        
        Args:
            player_name: The player's web_name
            primary_only: Only return True for primary takers
        """
        if player_name in cls.FREE_KICK_TAKERS['primary']:
            return True
        
        if not primary_only and player_name in cls.FREE_KICK_TAKERS['secondary']:
            return True
            
        return False
    
    @classmethod
    def is_corner_taker(cls, player_name: str) -> bool:
        """Check if a player takes corners"""
        return player_name in cls.CORNER_SPECIALISTS
    
    @classmethod
    def get_set_piece_score(cls, player_name: str) -> float:
        """
        Get a set piece bonus score for a player
        
        Returns:
            Score between 0-25 based on set piece responsibilities
        """
        score = 0
        
        # Penalty takers get the biggest bonus
        if player_name in cls.PENALTY_TAKERS['primary']:
            score += 20
        elif player_name in cls.PENALTY_TAKERS['secondary']:
            score += 10
        
        # Free kick takers get moderate bonus
        if player_name in cls.FREE_KICK_TAKERS['primary']:
            score += 10
        elif player_name in cls.FREE_KICK_TAKERS['secondary']:
            score += 5
        
        # Corner takers get small bonus
        if player_name in cls.CORNER_SPECIALISTS:
            score += 3
        
        return score
    
    @classmethod
    def analyze_historical_set_pieces(cls, player_history: Dict) -> Dict[str, int]:
        """
        Analyze historical data to identify set piece involvement
        
        Args:
            player_history: Player history data from FPL API
            
        Returns:
            Dict with penalties_scored, free_kicks_scored, etc.
        """
        result = {
            'penalties_scored': 0,
            'penalties_missed': 0,
            'free_kicks_scored': 0,
            'set_piece_goals': 0
        }
        
        # Analyze last season if available
        if player_history and 'history_past' in player_history:
            past_seasons = player_history.get('history_past', [])
            if past_seasons:
                last_season = past_seasons[-1]
                # These fields may not always be available
                result['penalties_scored'] = last_season.get('penalties_scored', 0)
                result['penalties_missed'] = last_season.get('penalties_missed', 0)
        
        # Check current season history for patterns
        if player_history and 'history' in player_history:
            current_season = player_history.get('history', [])
            # Could analyze game-by-game for penalty patterns
            # but that data might not explicitly show penalty goals
        
        return result