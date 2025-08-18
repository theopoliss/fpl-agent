from pydantic import BaseModel, Field, ConfigDict, field_validator
from typing import List, Optional, Dict, Any
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
    HIT = "hit"  # -4 points
    WILDCARD = "wildcard"
    FREE_HIT = "freehit"


class Player(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    first_name: str
    second_name: str
    web_name: str
    team: int
    team_code: int
    element_type: int  # 1=GK, 2=DEF, 3=MID, 4=FWD
    position: Optional[PlayerPosition] = None
    
    # Price
    now_cost: int  # Price in tenths (e.g., 55 = £5.5m)
    cost_change_start: int
    cost_change_event: int
    
    # Stats
    total_points: int
    event_points: int = 0
    points_per_game: float
    selected_by_percent: float
    form: float
    
    # Performance metrics
    minutes: int
    goals_scored: int
    assists: int
    clean_sheets: int
    goals_conceded: int
    own_goals: int
    penalties_saved: int
    penalties_missed: int
    yellow_cards: int
    red_cards: int
    saves: int
    bonus: int
    bps: int  # Bonus Points System
    
    # Expected stats
    expected_goals: float = Field(alias="expected_goals", default=0.0)
    expected_assists: float = Field(alias="expected_assists", default=0.0)
    expected_goal_involvements: float = Field(alias="expected_goal_involvements", default=0.0)
    expected_goals_conceded: float = Field(alias="expected_goals_conceded", default=0.0)
    
    # ICT Index
    influence: float
    creativity: float
    threat: float
    ict_index: float
    
    # Additional info
    status: str  # a=available, i=injured, s=suspended, u=unavailable
    chance_of_playing_this_round: Optional[int] = None
    chance_of_playing_next_round: Optional[int] = None
    news: str = ""
    news_added: Optional[datetime] = None
    
    # Transfers
    transfers_in: int = 0
    transfers_out: int = 0
    transfers_in_event: int = 0
    transfers_out_event: int = 0
    
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


class Team(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    name: str
    short_name: str
    code: int
    strength: int
    strength_overall_home: int
    strength_overall_away: int
    strength_attack_home: int
    strength_attack_away: int
    strength_defence_home: int
    strength_defence_away: int
    
    played: int = 0
    win: int = 0
    draw: int = 0
    loss: int = 0
    points: int = 0
    position: int = 0
    
    form: Optional[str] = None
    
    @property
    def avg_strength(self) -> float:
        return (self.strength_overall_home + self.strength_overall_away) / 2


class Fixture(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    code: int
    event: int  # Gameweek
    kickoff_time: Optional[datetime] = None
    
    team_h: int  # Home team ID
    team_a: int  # Away team ID
    team_h_score: Optional[int] = None
    team_a_score: Optional[int] = None
    
    team_h_difficulty: int  # FDR for home team
    team_a_difficulty: int  # FDR for away team
    
    finished: bool = False
    started: bool = False
    
    stats: List[Dict[str, Any]] = []
    
    @property
    def is_blank(self) -> bool:
        return self.event is None


class GameWeek(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    name: str
    deadline_time: datetime
    average_entry_score: int = 0
    highest_score: int = 0
    highest_scoring_entry: Optional[int] = None
    
    is_previous: bool = False
    is_current: bool = False
    is_next: bool = False
    finished: bool = False
    
    most_selected: Optional[int] = None  # Player ID
    most_transferred_in: Optional[int] = None
    most_captained: Optional[int] = None
    most_vice_captained: Optional[int] = None
    
    top_element: Optional[int] = None  # Highest scoring player
    top_element_info: Optional[Dict] = None
    
    transfers_made: int = 0
    
    chip_plays: List[Dict[str, int]] = []  # Stats on chip usage


class Squad(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    players: List[Player]
    formation: tuple = (1, 4, 4, 2)  # GK-DEF-MID-FWD
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
            # Sort by total points descending
            pos_players.sort(key=lambda x: x.total_points, reverse=True)
            starting.extend(pos_players[:count])
            
        return starting
        
    def get_bench(self) -> List[Player]:
        """Get bench players"""
        starting_ids = {p.id for p in self.get_starting_xi()}
        return [p for p in self.players if p.id not in starting_ids]


class Transfer(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    gameweek: int
    player_in_id: int
    player_out_id: int
    player_in_cost: float
    player_out_cost: float
    
    transfer_type: TransferType
    
    timestamp: datetime = Field(default_factory=datetime.now)
    
    @property
    def cost_difference(self) -> float:
        return self.player_in_cost - self.player_out_cost


class ManagerPick(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    element: int  # Player ID
    position: int  # Squad position (1-15)
    multiplier: int  # 0=bench, 1=playing, 2=captain, 3=triple captain
    is_captain: bool = False
    is_vice_captain: bool = False


class ManagerHistory(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    event: int  # Gameweek
    points: int
    total_points: int
    rank: int
    rank_sort: int
    overall_rank: int
    event_transfers: int
    event_transfers_cost: int
    value: int  # Team value in tenths
    bank: int  # Money in bank in tenths
    points_on_bench: int
    
    @property
    def team_value(self) -> float:
        return self.value / 10
        
    @property
    def bank_value(self) -> float:
        return self.bank / 10


class ChipUsage(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    gameweek: int
    chip: ChipType
    phase: str  # "first_half" or "second_half"
    timestamp: datetime = Field(default_factory=datetime.now)


class PredictedPoints(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    player_id: int
    gameweek: int
    predicted_points: float
    confidence: float  # 0-1 confidence score
    
    # Breakdown
    predicted_goals: float = 0
    predicted_assists: float = 0
    predicted_clean_sheet_prob: float = 0
    predicted_bonus: float = 0
    predicted_minutes: float = 0
    
    fixture_difficulty: int = 3
    home_away: str = "home"
    
    timestamp: datetime = Field(default_factory=datetime.now)