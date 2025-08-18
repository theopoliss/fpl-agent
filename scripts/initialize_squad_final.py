#!/usr/bin/env python3
"""
FINAL Squad Initialization Script - Use this one!
Combines real historical data with smart defaults and faster execution
"""

import asyncio
import sys
import json
from pathlib import Path
from datetime import datetime
import argparse

# Add parent directory to path
sys.path.append(str(Path(__file__).parent.parent))

from src.core.squad_optimizer_with_history import SquadOptimizerWithHistory
from src.core.squad_optimizer import SquadOptimizer
from src.api.fpl_client import FPLClient
from src.utils.logging import app_logger
from src.utils.config import config


async def initialize_squad(use_history: bool = True, weights: dict = None):
    """
    Initialize an FPL squad with configurable settings
    
    Args:
        use_history: Whether to fetch and use historical data (slower but better)
        weights: Custom weights for optimization
    """
    
    mode = "HISTORICAL" if use_history else "BASIC"
    app_logger.info("=" * 60)
    app_logger.info(f"FPL Agent - Squad Initialization ({mode} MODE)")
    app_logger.info("=" * 60)
    
    if use_history:
        app_logger.info("Using REAL historical data from FPL API (this may take ~30 seconds)...")
        optimizer = SquadOptimizerWithHistory()
        
        # Apply custom weights if provided
        if weights:
            optimizer.weights = weights
            app_logger.info("Using custom weights:")
        else:
            app_logger.info("Using default weights:")
            
        for key, value in optimizer.weights.items():
            app_logger.info(f"  • {key}: {value:.0%}")
            
        squad = await optimizer.optimize_initial_squad()
        
    else:
        app_logger.info("Using basic optimization (fast, current season only)...")
        optimizer = SquadOptimizer()
        squad = await optimizer.optimize_initial_squad()
    
    if not squad:
        app_logger.error("Failed to create squad")
        return None
    
    # Display results
    app_logger.info(f"\n✅ Squad successfully created!")
    app_logger.info(f"Total players: {len(squad.players)}")
    app_logger.info(f"Squad value: £{squad.value:.1f}m")
    app_logger.info(f"Remaining budget: £{squad.remaining_budget:.1f}m")
    app_logger.info(f"Formation: {squad.formation}")
    
    # Get team names
    async with FPLClient() as client:
        bootstrap = await client.get_bootstrap_data()
        teams_data = {t['id']: t['name'] for t in bootstrap.get('teams', [])}
    
    # Display squad by position
    positions = {1: "GK", 2: "DEF", 3: "MID", 4: "FWD"}
    
    for pos_id, pos_name in positions.items():
        app_logger.info(f"\n{pos_name}:")
        pos_players = [p for p in squad.players if p.element_type == pos_id]
        
        for p in sorted(pos_players, key=lambda x: x.now_cost, reverse=True):
            team_name = teams_data.get(p.team, "Unknown")
            ownership = f"{p.selected_by_percent:.1f}%" if p.selected_by_percent else "0%"
            form = f"{p.form:.1f}" if p.form else "0.0"
            
            display_str = (
                f"  - {p.web_name:<15} ({team_name:<12}) "
                f"£{p.price:.1f}m | "
                f"GW1: {p.total_points:>3}pts | "
                f"Form: {form:>3} | "
                f"Own: {ownership:>5}"
            )
            
            # Add historical info if available
            if use_history and hasattr(optimizer, 'player_histories'):
                history = optimizer.player_histories.get(p.id, {})
                if history and 'history_past' in history:
                    past = history.get('history_past', [])
                    if past:
                        last_pts = past[-1].get('total_points', 0)
                        display_str += f" | Last season: {last_pts:>3}pts"
            
            app_logger.info(display_str)
    
    # Squad analysis
    app_logger.info("\n📊 Squad Analysis:")
    
    # Premium players
    premiums = [p for p in squad.players if p.price >= 10.0]
    app_logger.info(f"  • Premium players (£10m+): {len(premiums)}")
    for p in premiums:
        app_logger.info(f"    - {p.web_name} £{p.price:.1f}m")
    
    # Budget players
    budget_players = [p for p in squad.players if p.price <= 5.0]
    app_logger.info(f"  • Budget players (£5m or less): {len(budget_players)}")
    
    # Metrics
    avg_ownership = sum(p.selected_by_percent for p in squad.players) / len(squad.players)
    avg_form = sum(p.form for p in squad.players if p.form) / len([p for p in squad.players if p.form])
    
    app_logger.info(f"\n📈 Squad Metrics:")
    app_logger.info(f"  • Average ownership: {avg_ownership:.1f}%")
    app_logger.info(f"  • Average form: {avg_form:.2f}")
    app_logger.info(f"  • Total GW1 points: {sum(p.total_points for p in squad.players)}")
    
    # Save to file
    squad_file = Path(f"data/squad_{'historical' if use_history else 'basic'}.json")
    squad_file.parent.mkdir(exist_ok=True)
    
    squad_data = {
        "metadata": {
            "created_at": datetime.now().isoformat(),
            "gameweek": 1,
            "optimization_type": "historical" if use_history else "basic",
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
                "status": p.status
            }
            for p in squad.players
        ],
        "formation": squad.formation,
        "analysis": {
            "premium_players": len(premiums),
            "budget_players": len(budget_players),
            "avg_ownership": avg_ownership,
            "avg_form": avg_form,
            "total_gw1_points": sum(p.total_points for p in squad.players)
        }
    }
    
    # Add weights if using historical mode
    if use_history and hasattr(optimizer, 'weights'):
        squad_data["metadata"]["weights"] = optimizer.weights
        
        # Add historical points
        for player_data in squad_data["players"]:
            if hasattr(optimizer, 'player_histories'):
                history = optimizer.player_histories.get(player_data["id"], {})
                if history and 'history_past' in history:
                    past = history.get('history_past', [])
                    if past:
                        player_data["last_season_points"] = past[-1].get('total_points', 0)
    
    with open(squad_file, 'w') as f:
        json.dump(squad_data, f, indent=2)
    
    app_logger.info(f"\n💾 Squad saved to {squad_file}")
    
    return squad


def main():
    """Main entry point"""
    
    parser = argparse.ArgumentParser(
        description="Initialize your FPL squad with smart optimization",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/initialize_squad_final.py              # Best mode (with history)
  python scripts/initialize_squad_final.py --fast       # Quick mode (no history)
  python scripts/initialize_squad_final.py --weights    # Custom weight configuration
        """
    )
    
    parser.add_argument(
        "--fast",
        action="store_true",
        help="Use fast mode without historical data (takes 2 seconds vs 30 seconds)"
    )
    
    parser.add_argument(
        "--weights",
        action="store_true",
        help="Configure custom weights for optimization"
    )
    
    args = parser.parse_args()
    
    # Configure weights if requested
    weights = None
    if args.weights and not args.fast:
        print("\nConfigure optimization weights (0-100 for each):")
        weights = {}
        
        weight_descriptions = {
            'historical': 'Historical performance (last season points)',
            'form': 'Recent form (last 5 games)',
            'fixtures': 'Upcoming fixture difficulty',
            'value': 'Value for money (points per million)',
            'ownership': 'Differential potential (low ownership)',
            'expected': 'Expected stats (xG, xA)'
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
        
        # Normalize weights to sum to 1
        total = sum(weights.values())
        if total > 0:
            weights = {k: v/total for k, v in weights.items()}
        
        print(f"\nNormalized weights: {weights}\n")
    
    # Run optimization
    asyncio.run(initialize_squad(use_history=not args.fast, weights=weights))


if __name__ == "__main__":
    main()