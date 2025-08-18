#!/usr/bin/env python3
"""
Initialize an FPL squad using REAL historical data from the API
"""

import asyncio
import sys
import json
from pathlib import Path
from datetime import datetime

# Add parent directory to path
sys.path.append(str(Path(__file__).parent.parent))

from src.core.squad_optimizer_with_history import SquadOptimizerWithHistory
from src.api.fpl_client import FPLClient
from src.utils.logging import app_logger
from src.utils.config import config


async def initialize_historical_squad():
    """Initialize a new FPL squad with real historical data"""
    
    app_logger.info("=" * 60)
    app_logger.info("FPL Agent - Squad Initialization with REAL Historical Data")
    app_logger.info("=" * 60)
    app_logger.info("Fetching actual player history from FPL API...")
    app_logger.info("")
    
    optimizer = SquadOptimizerWithHistory()
    
    # Show current weights
    app_logger.info("Current weights:")
    for key, value in optimizer.weights.items():
        app_logger.info(f"  • {key}: {value:.0%}")
    app_logger.info("")
    
    try:
        # Run optimization with real historical data
        squad = await optimizer.optimize_initial_squad()
        
        if squad:
            app_logger.info("\n✅ Squad successfully created with REAL historical data!")
            app_logger.info(f"Total players: {len(squad.players)}")
            app_logger.info(f"Squad value: £{squad.value:.1f}m")
            app_logger.info(f"Remaining budget: £{squad.remaining_budget:.1f}m")
            app_logger.info(f"Formation: {squad.formation}")
            
            # Get team names for display
            async with FPLClient() as client:
                bootstrap = await client.get_bootstrap_data()
                teams_data = {t['id']: t['name'] for t in bootstrap.get('teams', [])}
            
            # Display squad by position with historical info
            positions = {1: "GK", 2: "DEF", 3: "MID", 4: "FWD"}
            
            for pos_id, pos_name in positions.items():
                app_logger.info(f"\n{pos_name}:")
                pos_players = [p for p in squad.players if p.element_type == pos_id]
                
                for p in sorted(pos_players, key=lambda x: x.now_cost, reverse=True):
                    team_name = teams_data.get(p.team, "Unknown")
                    
                    # Get ownership and form
                    ownership = f"{p.selected_by_percent:.1f}%" if p.selected_by_percent else "0%"
                    form = f"{p.form:.1f}" if p.form else "0.0"
                    
                    # Try to get last season points from cache
                    history = optimizer.player_histories.get(p.id, {})
                    last_season_pts = "N/A"
                    if history and 'history_past' in history:
                        past = history.get('history_past', [])
                        if past:
                            last_season_pts = str(past[-1].get('total_points', 'N/A'))
                    
                    app_logger.info(
                        f"  - {p.web_name:<15} ({team_name:<12}) "
                        f"£{p.price:.1f}m | "
                        f"GW1: {p.total_points:>3}pts | "
                        f"Last season: {last_season_pts:>3}pts | "
                        f"Form: {form:>3} | "
                        f"Own: {ownership:>5}"
                    )
            
            # Squad analysis
            app_logger.info("\n📊 Squad Analysis:")
            
            # Count players with strong historical records
            strong_history = 0
            for p in squad.players:
                history = optimizer.player_histories.get(p.id, {})
                if history and 'history_past' in history:
                    past = history.get('history_past', [])
                    if past and past[-1].get('total_points', 0) > 150:
                        strong_history += 1
            
            app_logger.info(f"  • Players with 150+ points last season: {strong_history}")
            
            # Premium players
            premiums = [p for p in squad.players if p.price >= 10.0]
            app_logger.info(f"  • Premium players (£10m+): {len(premiums)}")
            for p in premiums:
                history = optimizer.player_histories.get(p.id, {})
                last_pts = "N/A"
                if history and 'history_past' in history:
                    past = history.get('history_past', [])
                    if past:
                        last_pts = str(past[-1].get('total_points', 'N/A'))
                app_logger.info(f"    - {p.web_name} £{p.price:.1f}m (Last season: {last_pts}pts)")
            
            # Budget players
            budget_players = [p for p in squad.players if p.price <= 5.0]
            app_logger.info(f"  • Budget players (£5m or less): {len(budget_players)}")
            
            # Average metrics
            avg_ownership = sum(p.selected_by_percent for p in squad.players) / len(squad.players)
            avg_form = sum(p.form for p in squad.players if p.form) / len([p for p in squad.players if p.form])
            
            # Calculate average historical points
            total_historical = 0
            players_with_history = 0
            for p in squad.players:
                history = optimizer.player_histories.get(p.id, {})
                if history and 'history_past' in history:
                    past = history.get('history_past', [])
                    if past:
                        total_historical += past[-1].get('total_points', 0)
                        players_with_history += 1
            
            avg_historical = total_historical / players_with_history if players_with_history > 0 else 0
            
            app_logger.info(f"\n📈 Squad Metrics:")
            app_logger.info(f"  • Average ownership: {avg_ownership:.1f}%")
            app_logger.info(f"  • Average form: {avg_form:.2f}")
            app_logger.info(f"  • Average last season points: {avg_historical:.1f}")
            app_logger.info(f"  • Total GW1 points: {sum(p.total_points for p in squad.players)}")
            
            # Save squad to file
            squad_file = Path("data/historical_squad.json")
            squad_file.parent.mkdir(exist_ok=True)
            
            squad_data = {
                "metadata": {
                    "created_at": datetime.now().isoformat(),
                    "gameweek": 1,
                    "optimization_type": "historical",
                    "weights": optimizer.weights,
                    "budget_used": squad.value,
                    "budget_remaining": squad.remaining_budget
                },
                "players": [
                    {
                        "id": p.id,
                        "name": p.web_name,
                        "team": teams_data.get(p.team, "Unknown"),
                        "position": positions[p.element_type],
                        "price": p.price,
                        "gw1_points": p.total_points,
                        "form": float(p.form) if p.form else 0,
                        "ownership": p.selected_by_percent,
                        "last_season_points": optimizer.player_histories.get(p.id, {})
                            .get('history_past', [{}])[-1].get('total_points', 0)
                            if optimizer.player_histories.get(p.id, {}).get('history_past')
                            else 0,
                        "status": p.status
                    }
                    for p in squad.players
                ],
                "formation": squad.formation,
                "analysis": {
                    "premium_players": len(premiums),
                    "budget_players": len(budget_players),
                    "strong_history_players": strong_history,
                    "avg_ownership": avg_ownership,
                    "avg_form": avg_form,
                    "avg_historical_points": avg_historical,
                    "total_gw1_points": sum(p.total_points for p in squad.players)
                }
            }
            
            with open(squad_file, 'w') as f:
                json.dump(squad_data, f, indent=2)
            
            app_logger.info(f"\n💾 Squad with historical data saved to {squad_file}")
            
            # Compare with non-historical optimization
            prev_file = Path("data/advanced_squad.json")
            if prev_file.exists():
                with open(prev_file, 'r') as f:
                    prev_data = json.load(f)
                
                app_logger.info("\n🔄 Comparison with previous (non-historical) optimization:")
                
                prev_players = set(p['name'] for p in prev_data.get('players', []))
                current_players = set(p.web_name for p in squad.players)
                
                only_in_historical = current_players - prev_players
                only_in_previous = prev_players - current_players
                
                if only_in_historical:
                    app_logger.info(f"  • New players (historical pick): {', '.join(only_in_historical)}")
                if only_in_previous:
                    app_logger.info(f"  • Removed (no historical backing): {', '.join(only_in_previous)}")
                
                common = len(current_players & prev_players)
                app_logger.info(f"  • Common players: {common}/15")
            
            app_logger.info("\n✨ Optimization with REAL historical data complete!")
            app_logger.info("This squad prioritizes:")
            app_logger.info("  ✓ Players with proven track records from last season")
            app_logger.info("  ✓ Consistent performers over one-week wonders")
            app_logger.info("  ✓ Actual historical points, not just current form")
            
        else:
            app_logger.error("Failed to create squad")
            
    except Exception as e:
        app_logger.error(f"Error initializing squad with historical data: {e}")
        raise


def main():
    """Main entry point"""
    asyncio.run(initialize_historical_squad())


if __name__ == "__main__":
    main()