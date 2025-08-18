"""
Simple data models without Pydantic for Python 3.13 compatibility
"""
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime
from enum import Enum


class PlayerPosition(str, Enum):
    GK = "GK"
    DEF = "DEF"
    MID = "MID"
    FWD = "FWD"


class ChipType(str, Enum):
    WILDCARD = "wildcard"
    FREE_HIT = "freehit"
    BENCH_BOOST = "bboost"
    TRIPLE_CAPTAIN = "3xc"


class TransferType(str, Enum):
    FREE = "free"
    HIT = "hit"
    WILDCARD = "wildcard"
    FREE_HIT = "freehit"


@dataclass
class Player:
    """Player data model"""
    id: int
    first_name: str
    second_name: str
    web_name: str
    team: int
    team_code: int
    element_type: int  # 1=GK, 2=DEF, 3=MID, 4=FWD
    
    # Price (in tenths)
    now_cost: int
    cost_change_start: int
    cost_change_event: int
    
    # Stats
    total_points: int
    event_points: int = 0
    points_per_game: float = 0.0
    selected_by_percent: float = 0.0
    form: float = 0.0
    
    # Performance
    minutes: int = 0
    goals_scored: int = 0
    assists: int = 0
    clean_sheets: int = 0
    goals_conceded: int = 0
    own_goals: int = 0
    penalties_saved: int = 0
    penalties_missed: int = 0
    yellow_cards: int = 0
    red_cards: int = 0
    saves: int = 0
    bonus: int = 0
    bps: int = 0
    
    # ICT
    influence: float = 0.0
    creativity: float = 0.0
    threat: float = 0.0
    ict_index: float = 0.0
    
    # Status
    status: str = "a"
    chance_of_playing_this_round: Optional[int] = None
    chance_of_playing_next_round: Optional[int] = None
    news: str = ""
    
    position: Optional[PlayerPosition] = None
    
    @property
    def price(self) -> float:
        return self.now_cost / 10
    
    @property
    def is_available(self) -> bool:
        return self.status == "a"
    
    @property
    def value_score(self) -> float:
        if self.price > 0:
            return self.total_points / self.price
        return 0
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Player':
        """Create Player from dictionary"""
        return cls(
            id=data.get('id', 0),
            first_name=data.get('first_name', ''),
            second_name=data.get('second_name', ''),
            web_name=data.get('web_name', ''),
            team=data.get('team', 0),
            team_code=data.get('team_code', 0),
            element_type=data.get('element_type', 0),
            now_cost=data.get('now_cost', 0),
            cost_change_start=data.get('cost_change_start', 0),
            cost_change_event=data.get('cost_change_event', 0),
            total_points=data.get('total_points', 0),
            event_points=data.get('event_points', 0),
            points_per_game=float(data.get('points_per_game', 0)),
            selected_by_percent=float(data.get('selected_by_percent', 0)),
            form=float(data.get('form', 0)),
            minutes=data.get('minutes', 0),
            goals_scored=data.get('goals_scored', 0),
            assists=data.get('assists', 0),
            clean_sheets=data.get('clean_sheets', 0),
            goals_conceded=data.get('goals_conceded', 0),
            own_goals=data.get('own_goals', 0),
            penalties_saved=data.get('penalties_saved', 0),
            penalties_missed=data.get('penalties_missed', 0),
            yellow_cards=data.get('yellow_cards', 0),
            red_cards=data.get('red_cards', 0),
            saves=data.get('saves', 0),
            bonus=data.get('bonus', 0),
            bps=data.get('bps', 0),
            influence=float(data.get('influence', 0)),
            creativity=float(data.get('creativity', 0)),
            threat=float(data.get('threat', 0)),
            ict_index=float(data.get('ict_index', 0)),
            status=data.get('status', 'a'),
            chance_of_playing_this_round=data.get('chance_of_playing_this_round'),
            chance_of_playing_next_round=data.get('chance_of_playing_next_round'),
            news=data.get('news', '')
        )


@dataclass
class Squad:
    """Squad data model"""
    players: List[Player]
    formation: Tuple[int, int, int, int] = (1, 4, 4, 2)
    captain_id: Optional[int] = None
    vice_captain_id: Optional[int] = None
    budget: float = 100.0
    free_transfers: int = 1
    
    @property
    def value(self) -> float:
        return sum(p.price for p in self.players)
    
    @property
    def remaining_budget(self) -> float:
        return self.budget - self.value
    
    def get_starting_xi(self) -> List[Player]:
        """Get starting XI based on formation"""
        gk, def_, mid, fwd = self.formation
        
        starting = []
        positions = {
            1: gk,  # GK
            2: def_,  # DEF
            3: mid,  # MID
            4: fwd,  # FWD
        }
        
        for pos_type, count in positions.items():
            pos_players = [p for p in self.players if p.element_type == pos_type]
            pos_players.sort(key=lambda x: x.total_points, reverse=True)
            starting.extend(pos_players[:count])
        
        return starting
    
    def get_bench(self) -> List[Player]:
        """Get bench players"""
        starting_ids = {p.id for p in self.get_starting_xi()}
        return [p for p in self.players if p.id not in starting_ids]


@dataclass
class Team:
    """Team data model"""
    id: int
    name: str
    short_name: str
    code: int
    strength: int = 0
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Team':
        return cls(
            id=data.get('id', 0),
            name=data.get('name', ''),
            short_name=data.get('short_name', ''),
            code=data.get('code', 0),
            strength=data.get('strength', 0)
        )


@dataclass
class Fixture:
    """Fixture data model"""
    id: int
    event: int  # Gameweek
    team_h: int
    team_a: int
    team_h_difficulty: int = 3
    team_a_difficulty: int = 3
    finished: bool = False
    team_h_score: Optional[int] = None
    team_a_score: Optional[int] = None
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Fixture':
        return cls(
            id=data.get('id', 0),
            event=data.get('event', 0),
            team_h=data.get('team_h', 0),
            team_a=data.get('team_a', 0),
            team_h_difficulty=data.get('team_h_difficulty', 3),
            team_a_difficulty=data.get('team_a_difficulty', 3),
            finished=data.get('finished', False),
            team_h_score=data.get('team_h_score'),
            team_a_score=data.get('team_a_score')
        )


@dataclass
class Transfer:
    """Transfer data model"""
    gameweek: int
    player_in_id: int
    player_out_id: int
    player_in_cost: float
    player_out_cost: float
    transfer_type: TransferType
    timestamp: datetime = field(default_factory=datetime.now)
    
    @property
    def cost_difference(self) -> float:
        return self.player_in_cost - self.player_out_cost


@dataclass
class ChipUsage:
    """Chip usage data model"""
    gameweek: int
    chip: ChipType
    phase: str
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class GameWeek:
    """Gameweek data model"""
    id: int
    name: str
    deadline_time: datetime
    is_current: bool = False
    is_next: bool = False
    finished: bool = False
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'GameWeek':
        return cls(
            id=data.get('id', 0),
            name=data.get('name', ''),
            deadline_time=datetime.fromisoformat(
                data.get('deadline_time', '').replace('Z', '+00:00')
            ),
            is_current=data.get('is_current', False),
            is_next=data.get('is_next', False),
            finished=data.get('finished', False)
        )


@dataclass
class ManagerHistory:
    """Manager history data model"""
    event: int
    points: int
    total_points: int
    rank: int
    overall_rank: int
    bank: int = 0
    value: int = 0
    event_transfers: int = 0
    event_transfers_cost: int = 0
    points_on_bench: int = 0
    
    @property
    def team_value(self) -> float:
        return self.value / 10
    
    @property
    def bank_value(self) -> float:
        return self.bank / 10


@dataclass
class PredictedPoints:
    """Predicted points data model"""
    player_id: int
    gameweek: int
    predicted_points: float
    confidence: float
    predicted_goals: float = 0
    predicted_assists: float = 0
    predicted_clean_sheet_prob: float = 0
    predicted_bonus: float = 0
    predicted_minutes: float = 0
    fixture_difficulty: int = 3
    home_away: str = "home"
    timestamp: datetime = field(default_factory=datetime.now)