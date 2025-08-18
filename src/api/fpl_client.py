import aiohttp
import asyncio
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
import json
from loguru import logger
from functools import lru_cache
import time


class FPLClient:
    BASE_URL = "https://fantasy.premierleague.com/api"
    
    ENDPOINTS = {
        "bootstrap": "/bootstrap-static/",
        "fixtures": "/fixtures/",
        "player": "/element-summary/{player_id}/",
        "gameweek_live": "/event/{gameweek}/live/",
        "manager": "/entry/{manager_id}/",
        "manager_history": "/entry/{manager_id}/history/",
        "manager_picks": "/entry/{manager_id}/event/{gameweek}/picks/",
        "league_classic": "/leagues-classic/{league_id}/standings/",
        "league_h2h": "/leagues-h2h/{league_id}/standings/",
        "dream_team": "/dream-team/{gameweek}/",
    }
    
    def __init__(self, session: Optional[aiohttp.ClientSession] = None):
        self.session = session
        self._owned_session = False
        self._cache = {}
        self._cache_expiry = {}
        self.cache_duration = 300  # 5 minutes default cache
        
    async def __aenter__(self):
        if not self.session:
            self.session = aiohttp.ClientSession()
            self._owned_session = True
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._owned_session and self.session:
            await self.session.close()
            
    def _get_cache_key(self, endpoint: str, **kwargs) -> str:
        return f"{endpoint}:{json.dumps(kwargs, sort_keys=True)}"
        
    def _is_cache_valid(self, cache_key: str) -> bool:
        if cache_key not in self._cache:
            return False
        return time.time() < self._cache_expiry.get(cache_key, 0)
        
    def _set_cache(self, cache_key: str, data: Any, duration: Optional[int] = None):
        self._cache[cache_key] = data
        self._cache_expiry[cache_key] = time.time() + (duration or self.cache_duration)
        
    async def _make_request(self, endpoint: str, **kwargs) -> Dict:
        cache_key = self._get_cache_key(endpoint, **kwargs)
        
        if self._is_cache_valid(cache_key):
            logger.debug(f"Cache hit for {endpoint}")
            return self._cache[cache_key]
            
        url = f"{self.BASE_URL}{endpoint}"
        
        if kwargs:
            for key, value in kwargs.items():
                url = url.replace(f"{{{key}}}", str(value))
                
        logger.debug(f"Making request to {url}")
        
        try:
            async with self.session.get(url) as response:
                response.raise_for_status()
                data = await response.json()
                self._set_cache(cache_key, data)
                return data
        except aiohttp.ClientError as e:
            logger.error(f"Request failed for {url}: {e}")
            raise
            
    async def get_bootstrap_data(self) -> Dict:
        """
        Get all general FPL data including:
        - All players with their current stats
        - All teams
        - Game settings
        - Current gameweek info
        - Phases of the season
        """
        return await self._make_request(self.ENDPOINTS["bootstrap"])
        
    async def get_fixtures(self, gameweek: Optional[int] = None) -> List[Dict]:
        """Get fixtures data, optionally filtered by gameweek"""
        endpoint = self.ENDPOINTS["fixtures"]
        if gameweek:
            endpoint += f"?event={gameweek}"
        return await self._make_request(endpoint)
        
    async def get_player_summary(self, player_id: int) -> Dict:
        """Get detailed player data including history and fixtures"""
        return await self._make_request(
            self.ENDPOINTS["player"].format(player_id=player_id)
        )
        
    async def get_gameweek_live_data(self, gameweek: int) -> Dict:
        """Get live data for a specific gameweek"""
        return await self._make_request(
            self.ENDPOINTS["gameweek_live"].format(gameweek=gameweek)
        )
        
    async def get_manager_data(self, manager_id: int) -> Dict:
        """Get manager's basic data"""
        return await self._make_request(
            self.ENDPOINTS["manager"].format(manager_id=manager_id)
        )
        
    async def get_manager_history(self, manager_id: int) -> Dict:
        """Get manager's season history"""
        return await self._make_request(
            self.ENDPOINTS["manager_history"].format(manager_id=manager_id)
        )
        
    async def get_manager_picks(self, manager_id: int, gameweek: int) -> Dict:
        """Get manager's picks for a specific gameweek"""
        return await self._make_request(
            self.ENDPOINTS["manager_picks"].format(
                manager_id=manager_id, gameweek=gameweek
            )
        )
        
    async def get_dream_team(self, gameweek: int) -> Dict:
        """Get the dream team for a specific gameweek"""
        return await self._make_request(
            self.ENDPOINTS["dream_team"].format(gameweek=gameweek)
        )
        
    async def get_league_standings(
        self, league_id: int, league_type: str = "classic"
    ) -> Dict:
        """Get league standings (classic or h2h)"""
        endpoint_key = f"league_{league_type}"
        if endpoint_key not in self.ENDPOINTS:
            raise ValueError(f"Invalid league type: {league_type}")
            
        return await self._make_request(
            self.ENDPOINTS[endpoint_key].format(league_id=league_id)
        )
        
    async def get_current_gameweek(self) -> int:
        """Get the current gameweek number"""
        data = await self.get_bootstrap_data()
        events = data.get("events", [])
        
        for event in events:
            if event.get("is_current"):
                return event.get("id")
                
        # If no current gameweek, find the next one
        for event in events:
            if event.get("is_next"):
                return event.get("id")
                
        return 1
        
    async def get_all_players(self) -> List[Dict]:
        """Get all players with their current data"""
        data = await self.get_bootstrap_data()
        return data.get("elements", [])
        
    async def get_all_teams(self) -> List[Dict]:
        """Get all teams data"""
        data = await self.get_bootstrap_data()
        return data.get("teams", [])
        
    async def get_game_settings(self) -> Dict:
        """Get game settings and rules"""
        data = await self.get_bootstrap_data()
        return data.get("game_settings", {})
        
    async def get_player_by_name(self, name: str) -> Optional[Dict]:
        """Find a player by name (partial match)"""
        players = await self.get_all_players()
        name_lower = name.lower()
        
        for player in players:
            full_name = f"{player.get('first_name', '')} {player.get('second_name', '')}".lower()
            web_name = player.get("web_name", "").lower()
            
            if name_lower in full_name or name_lower in web_name:
                return player
                
        return None
        
    async def get_team_players(self, team_id: int) -> List[Dict]:
        """Get all players from a specific team"""
        players = await self.get_all_players()
        return [p for p in players if p.get("team") == team_id]
        
    async def get_players_by_position(self, position: int) -> List[Dict]:
        """
        Get players by position
        1: Goalkeeper
        2: Defender
        3: Midfielder
        4: Forward
        """
        players = await self.get_all_players()
        return [p for p in players if p.get("element_type") == position]
        
    async def get_budget_players(
        self, max_price: float, position: Optional[int] = None
    ) -> List[Dict]:
        """Get players under a certain price"""
        players = await self.get_all_players()
        
        # Convert price to FPL format (multiply by 10)
        max_price_fpl = max_price * 10
        
        filtered = [p for p in players if p.get("now_cost", 0) <= max_price_fpl]
        
        if position:
            filtered = [p for p in filtered if p.get("element_type") == position]
            
        return filtered
        
    async def get_deadline_time(self) -> Optional[datetime]:
        """Get the next deadline time"""
        data = await self.get_bootstrap_data()
        events = data.get("events", [])
        
        for event in events:
            if event.get("is_next") or event.get("is_current"):
                deadline_str = event.get("deadline_time")
                if deadline_str:
                    return datetime.fromisoformat(deadline_str.replace("Z", "+00:00"))
                    
        return None


class FPLDataProcessor:
    """Helper class to process and enrich FPL data"""
    
    @staticmethod
    def calculate_player_value(player: Dict) -> float:
        """Calculate value metric (points per million)"""
        total_points = player.get("total_points", 0)
        cost = player.get("now_cost", 0) / 10  # Convert to millions
        
        if cost > 0:
            return total_points / cost
        return 0
        
    @staticmethod
    def calculate_form_trend(player: Dict, history: List[Dict]) -> float:
        """Calculate recent form trend"""
        if not history:
            return 0
            
        recent_games = history[-5:]  # Last 5 games
        if len(recent_games) < 2:
            return 0
            
        points = [g.get("total_points", 0) for g in recent_games]
        
        # Simple linear regression trend
        n = len(points)
        x_mean = (n - 1) / 2
        y_mean = sum(points) / n
        
        numerator = sum((i - x_mean) * (p - y_mean) for i, p in enumerate(points))
        denominator = sum((i - x_mean) ** 2 for i in range(n))
        
        if denominator > 0:
            return numerator / denominator
        return 0
        
    @staticmethod
    def get_fixture_difficulty(fixtures: List[Dict], team_id: int, next_n: int = 5) -> float:
        """Calculate average fixture difficulty for next N games"""
        team_fixtures = []
        
        for fixture in fixtures:
            if fixture.get("team_h") == team_id:
                team_fixtures.append(fixture.get("team_h_difficulty", 3))
            elif fixture.get("team_a") == team_id:
                team_fixtures.append(fixture.get("team_a_difficulty", 3))
                
        if not team_fixtures:
            return 3  # Neutral difficulty
            
        next_fixtures = team_fixtures[:next_n]
        return sum(next_fixtures) / len(next_fixtures) if next_fixtures else 3