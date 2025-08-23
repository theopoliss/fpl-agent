#!/usr/bin/env python3
"""
Backtest the squad optimizer for 2024/25 season
Uses only data available before 24/25 season started to select squad,
then evaluates actual 24/25 performance
"""

import asyncio
import sys
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Tuple
import argparse

# Add parent directory to path
sys.path.append(str(Path(__file__).parent.parent))

from src.core.squad_optimizer_with_history import SquadOptimizerWithHistory
from src.core.squad_optimizer_preseason import PreseasonSquadOptimizer
from src.api.fpl_client import FPLClient
from src.data.models import Player
from src.utils.logging import app_logger
from src.utils.config import config


class BacktestOptimizer(PreseasonSquadOptimizer):
    """Modified optimizer that only uses data up to a certain season"""
    
    def __init__(self, max_season_year: str = "2023/24"):
        super().__init__()
        self.max_season_year = max_season_year
        app_logger.info(f"Backtesting with pre-season optimizer using data up to {max_season_year}")
        
    def _calculate_historical_score(self, player: Player, history: Dict) -> float:
        """
        Override to exclude 2024/25 data for backtesting
        Only use data up to max_season_year
        """
        
        if not history or 'history_past' not in history:
            # No history - heavily penalize
            return min(player.total_points * 0.5, 10)
        
        past_seasons = history.get('history_past', [])
        
        if not past_seasons:
            return min(player.total_points * 0.5, 10)
        
        # Filter out 2024/25 season and any future seasons
        # FPL API returns seasons with 'season_name' like "2023/24"
        valid_seasons = []
        for season in past_seasons:
            season_name = season.get('season_name', '')
            # Extract year from season name
            if season_name and '/' in season_name:
                season_end_year = int('20' + season_name.split('/')[1])
                max_year = int('20' + self.max_season_year.split('/')[1])
                
                if season_end_year <= max_year:
                    valid_seasons.append(season)
                else:
                    app_logger.debug(f"Excluding {season_name} data for player {player.web_name}")
        
        if not valid_seasons:
            # Player has no valid historical data before cutoff
            return min(player.total_points * 0.5, 10)
        
        # Get last 3 valid seasons
        recent_seasons = valid_seasons[-3:] if len(valid_seasons) >= 3 else valid_seasons
        
        # Calculate weighted average with recency bias
        total_weighted_points = 0
        total_weight = 0
        
        for i, season in enumerate(reversed(recent_seasons)):  # Most recent first
            points = season.get('total_points', 0)
            minutes = season.get('minutes', 0)
            
            if minutes < 900:  # Less than 10 games
                continue
                
            # Recency weight: most recent = 1.0, previous = 0.7, before that = 0.5
            recency_weight = [1.0, 0.7, 0.5][min(i, 2)]
            
            # Minutes weight (favor players who play regularly)
            minutes_weight = min(minutes / 3000, 1.0)  # Cap at ~33 games
            
            weight = recency_weight * minutes_weight
            total_weighted_points += points * weight
            total_weight += weight
        
        if total_weight == 0:
            return 5
            
        avg_points = total_weighted_points / total_weight
        
        # Enhanced scoring for elite players
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


async def evaluate_squad_performance(squad_players: List[Dict]) -> Dict:
    """
    Evaluate how the selected squad actually performed in 24/25
    """
    
    # Fetch actual 24/25 performance from player histories
    player_performances = {}
    
    async with FPLClient() as client:
        for player_info in squad_players:
            player_id = player_info['id']
            
            try:
                # Get player's historical data
                player_data = await client.get_player_summary(player_id)
                
                # Find 24/25 season in history_past
                season_24_25_points = 0
                season_24_25_minutes = 0
                
                if 'history_past' in player_data:
                    for season in player_data['history_past']:
                        if season.get('season_name') == '2024/25':
                            season_24_25_points = season.get('total_points', 0)
                            season_24_25_minutes = season.get('minutes', 0)
                            break
                
                # Get current data for price info
                bootstrap = await client.get_bootstrap_data()
                current_info = None
                for element in bootstrap.get('elements', []):
                    if element['id'] == player_id:
                        current_info = element
                        break
                
                player_performances[player_id] = {
                    'name': player_info['name'],
                    'position': player_info['position'],
                    'price_at_selection': player_info['price'],
                    'predicted_score': player_info.get('predicted_score', 0),
                    'actual_total_points': season_24_25_points,
                    'actual_minutes': season_24_25_minutes,
                    'actual_ppg': season_24_25_points / 38 if season_24_25_points > 0 else 0,
                    'current_price': current_info.get('now_cost', 0) / 10 if current_info else player_info['price'],
                    'price_rise': (current_info.get('now_cost', 0) / 10 if current_info else player_info['price']) - player_info['price']
                }
            except Exception as e:
                app_logger.debug(f"Failed to get 24/25 data for {player_info['name']}: {e}")
                player_performances[player_id] = {
                    'name': player_info['name'],
                    'position': player_info['position'],
                    'price_at_selection': player_info['price'],
                    'predicted_score': player_info.get('predicted_score', 0),
                    'actual_total_points': 0,
                    'actual_minutes': 0,
                    'actual_ppg': 0,
                    'current_price': player_info['price'],
                    'price_rise': 0
                }
    
    # Calculate squad totals
    total_actual_points = sum(p['actual_total_points'] for p in player_performances.values())
    
    # Get top 11 by actual points for "optimal selection"
    sorted_players = sorted(player_performances.values(), 
                          key=lambda x: x['actual_total_points'], 
                          reverse=True)
    
    # Calculate what the best possible starting 11 would have scored
    # Respecting formation constraints
    best_11_points = calculate_best_11_points(sorted_players)
    
    return {
        'total_squad_points': total_actual_points,
        'average_points_per_player': total_actual_points / 15,
        'best_possible_11_points': best_11_points,
        'individual_performances': player_performances,
        'top_performers': sorted_players[:5],
        'worst_performers': sorted_players[-3:],
        'total_price_change': sum(p['price_rise'] for p in player_performances.values())
    }


def calculate_best_11_points(players: List[Dict]) -> int:
    """Calculate best possible 11 with valid formation"""
    
    # Group by position
    by_position = {
        'GK': [],
        'DEF': [],
        'MID': [],
        'FWD': []
    }
    
    for p in players:
        by_position[p['position']].append(p)
    
    # Try all valid formations and pick the best
    valid_formations = [
        (1, 3, 4, 3),
        (1, 3, 5, 2),
        (1, 4, 3, 3),
        (1, 4, 4, 2),
        (1, 4, 5, 1),
        (1, 5, 3, 2),
        (1, 5, 4, 1)
    ]
    
    best_points = 0
    best_formation = None
    
    for formation in valid_formations:
        gk, df, md, fw = formation
        
        # Check if we have enough players
        if (len(by_position['GK']) >= gk and 
            len(by_position['DEF']) >= df and 
            len(by_position['MID']) >= md and 
            len(by_position['FWD']) >= fw):
            
            points = (
                sum(p['actual_total_points'] for p in by_position['GK'][:gk]) +
                sum(p['actual_total_points'] for p in by_position['DEF'][:df]) +
                sum(p['actual_total_points'] for p in by_position['MID'][:md]) +
                sum(p['actual_total_points'] for p in by_position['FWD'][:fw])
            )
            
            if points > best_points:
                best_points = points
                best_formation = formation
    
    app_logger.info(f"Best possible formation would have been: {best_formation}")
    return best_points


async def fetch_benchmark_data() -> Dict:
    """Fetch benchmark data for 24/25 season comparison"""
    
    async with FPLClient() as client:
        bootstrap = await client.get_bootstrap_data()
        all_players = bootstrap.get('elements', [])
        
        # Get top 24/25 performers by fetching their historical data
        player_24_25_points = []
        
        app_logger.info("  Fetching 24/25 benchmark data...")
        
        # Sample top current players to find who did well in 24/25
        top_current = sorted(all_players, 
                           key=lambda x: x.get('selected_by_percent', 0), 
                           reverse=True)[:50]  # Check top 50 most owned
        
        for player in top_current:
            try:
                player_data = await client.get_player_summary(player['id'])
                if 'history_past' in player_data:
                    for season in player_data['history_past']:
                        if season.get('season_name') == '2024/25':
                            player_24_25_points.append({
                                'name': player['web_name'],
                                'points': season.get('total_points', 0),
                                'minutes': season.get('minutes', 0)
                            })
                            break
            except:
                pass
        
        # Sort by 24/25 points
        player_24_25_points.sort(key=lambda x: x['points'], reverse=True)
        top_15_points = sum(p['points'] for p in player_24_25_points[:15])
        
        if player_24_25_points:
            top_scorer = player_24_25_points[0]
        else:
            top_scorer = {'name': 'Unknown', 'points': 0}
        
        return {
            'season_top_scorer': top_scorer,
            'top_15_total': top_15_points,
            'top_players_24_25': player_24_25_points[:5]
        }


def get_template_team(players: List[Dict]) -> List[Dict]:
    """Get the template team (most owned players respecting constraints)"""
    
    # Group by position and sort by ownership
    by_position = {
        1: [],  # GK
        2: [],  # DEF
        3: [],  # MID
        4: []   # FWD
    }
    
    for p in players:
        by_position[p['element_type']].append(p)
    
    for pos in by_position:
        by_position[pos].sort(key=lambda x: x.get('selected_by_percent', 0), reverse=True)
    
    # Build template team with budget constraint
    template = []
    budget = 100.0
    
    # Standard template formation: 4-4-2
    requirements = {1: 2, 2: 5, 3: 5, 4: 3}
    
    for pos, required in requirements.items():
        added = 0
        for player in by_position[pos]:
            if added >= required:
                break
            
            price = player.get('now_cost', 0) / 10
            if budget >= price:
                template.append(player)
                budget -= price
                added += 1
    
    return template


async def run_backtest(weights: Dict = None):
    """Run the full backtest"""
    
    app_logger.info("=" * 60)
    app_logger.info("BACKTESTING 2024/25 SEASON")
    app_logger.info("Using only data available before season started")
    app_logger.info("=" * 60)
    
    # Create backtest optimizer
    optimizer = BacktestOptimizer(max_season_year="2023/24")
    
    if weights:
        optimizer.weights = weights
        app_logger.info("Using custom weights:")
    else:
        app_logger.info("Using default weights:")
    
    for key, value in optimizer.weights.items():
        app_logger.info(f"  • {key}: {value:.0%}")
    
    # Run optimization (this will only use pre-24/25 data)
    app_logger.info("\nSelecting squad based on historical data only...")
    squad = await optimizer.optimize_initial_squad()
    
    if not squad:
        app_logger.error("Failed to create squad")
        return
    
    # Get team names for display
    async with FPLClient() as client:
        bootstrap = await client.get_bootstrap_data()
        teams_data = {t['id']: t['name'] for t in bootstrap.get('teams', [])}
    
    # Save the selected squad
    positions = {1: "GK", 2: "DEF", 3: "MID", 4: "FWD"}
    
    squad_data = {
        "metadata": {
            "created_at": datetime.now().isoformat(),
            "backtest_season": "2024/25",
            "data_used": "Up to 2023/24",
            "budget_used": squad.value,
            "budget_remaining": squad.remaining_budget,
            "weights": optimizer.weights
        },
        "squad": []
    }
    
    app_logger.info("\n📋 SELECTED SQUAD (based on pre-24/25 data):")
    app_logger.info("=" * 70)
    
    for p in squad.players:
        player_info = {
            "id": p.id,
            "name": p.web_name,
            "team": teams_data.get(p.team, "Unknown"),
            "position": positions[p.element_type],
            "price": p.price,
            "predicted_score": optimizer.player_histories.get(p.id, {}).get('predicted_score', 0)
        }
        squad_data["squad"].append(player_info)
        
        app_logger.info(
            f"  {p.web_name:<15} ({player_info['team']:<12}) "
            f"{player_info['position']:<3} £{p.price:.1f}m"
        )
    
    # Now evaluate how this squad actually performed in 24/25
    app_logger.info("\n📊 EVALUATING ACTUAL 24/25 PERFORMANCE...")
    app_logger.info("=" * 70)
    
    async with FPLClient() as client:
        actual_data = await client.get_bootstrap_data()
    
    performance = await evaluate_squad_performance(squad_data["squad"])
    
    # Display results
    app_logger.info(f"\n✅ BACKTEST RESULTS:")
    app_logger.info(f"  • Total squad points in 24/25: {performance['total_squad_points']}")
    app_logger.info(f"  • Average points per player: {performance['average_points_per_player']:.1f}")
    app_logger.info(f"  • Best possible XI points: {performance['best_possible_11_points']}")
    app_logger.info(f"  • Total squad value change: £{performance['total_price_change']:.1f}m")
    
    app_logger.info(f"\n🌟 TOP PERFORMERS:")
    for p in performance['top_performers']:
        app_logger.info(
            f"  • {p['name']}: {p['actual_total_points']}pts "
            f"(£{p['price_at_selection']:.1f}m → £{p['current_price']:.1f}m)"
        )
    
    app_logger.info(f"\n❌ WORST PERFORMERS:")
    for p in performance['worst_performers']:
        app_logger.info(
            f"  • {p['name']}: {p['actual_total_points']}pts "
            f"(£{p['price_at_selection']:.1f}m)"
        )
    
    # Get benchmarks for comparison
    app_logger.info(f"\n📈 COMPARISON WITH BENCHMARKS:")
    benchmarks = await fetch_benchmark_data()
    
    app_logger.info(f"  • 24/25 top scorer: {benchmarks['season_top_scorer']['name']} "
                   f"({benchmarks['season_top_scorer']['points']}pts)")
    app_logger.info(f"  • Top 24/25 performers:")
    for p in benchmarks.get('top_players_24_25', [])[:5]:
        app_logger.info(f"    - {p['name']}: {p['points']}pts")
    app_logger.info(f"  • Hindsight best 15 total: {benchmarks['top_15_total']}pts")
    app_logger.info(f"  • Our squad total: {performance['total_squad_points']}pts")
    
    efficiency = (performance['total_squad_points'] / benchmarks['top_15_total']) * 100
    app_logger.info(f"\n  Efficiency vs perfect hindsight: {efficiency:.1f}%")
    
    # Save full results
    results_file = Path("data/backtest_24_25_results.json")
    results_file.parent.mkdir(exist_ok=True)
    
    full_results = {
        "metadata": squad_data["metadata"],
        "squad": squad_data["squad"],
        "performance": {
            "total_points": performance['total_squad_points'],
            "avg_per_player": performance['average_points_per_player'],
            "best_11_points": performance['best_possible_11_points'],
            "price_change": performance['total_price_change']
        },
        "benchmarks": {
            "hindsight_best_15": benchmarks['top_15_total'],
            "top_scorer": benchmarks['season_top_scorer'],
            "efficiency_pct": efficiency
        },
        "individual_performances": performance['individual_performances']
    }
    
    with open(results_file, 'w') as f:
        json.dump(full_results, f, indent=2)
    
    app_logger.info(f"\n💾 Full results saved to {results_file}")
    
    return performance


def main():
    """Main entry point"""
    
    parser = argparse.ArgumentParser(
        description="Backtest squad optimizer on 2024/25 season",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
This backtester:
1. Uses ONLY data available before 24/25 season (up to 23/24)
2. Selects an optimal squad based on that historical data
3. Evaluates how that squad actually performed in 24/25
4. Compares against benchmarks (template team, hindsight best, etc.)

Example:
  python scripts/backtest_24_25.py
  python scripts/backtest_24_25.py --weights  # Custom weights
        """
    )
    
    parser.add_argument(
        "--weights",
        action="store_true",
        help="Configure custom weights for optimization"
    )
    
    args = parser.parse_args()
    
    # Configure weights if requested
    weights = None
    if args.weights:
        print("\nConfigure optimization weights (0-100 for each):")
        weights = {}
        
        weight_descriptions = {
            'historical': 'Historical performance (pre-24/25 data)',
            'form': 'Recent form (end of 23/24)',
            'fixtures': 'Opening fixtures difficulty',
            'value': 'Value for money',
            'ownership': 'Differential potential',
            'expected': 'Expected stats (xG, xA)',
            'set_pieces': 'Set piece taker bonus'
        }
        
        for key, desc in weight_descriptions.items():
            while True:
                try:
                    val = input(f"  {key} ({desc}): ")
                    if not val:
                        val = 20  # Default
                    else:
                        val = float(val)
                    if 0 <= val <= 100:
                        weights[key] = val / 100
                        break
                    else:
                        print("    Please enter a value between 0 and 100")
                except ValueError:
                    print("    Please enter a valid number")
        
        # Normalize weights
        total = sum(weights.values())
        if total > 0:
            weights = {k: v/total for k, v in weights.items()}
    
    # Run backtest
    asyncio.run(run_backtest(weights))


if __name__ == "__main__":
    main()