#!/usr/bin/env python3
"""
Initialize an FPL squad using advanced optimization - NO CACHE VERSION
This version bypasses the API cache to ensure fresh data on each run
"""

import asyncio
import sys
import json
from pathlib import Path
from datetime import datetime

# Add parent directory to path
sys.path.append(str(Path(__file__).parent.parent))

from src.core.squad_optimizer_advanced_nocache import AdvancedSquadOptimizerNoCache
from src.api.fpl_client import FPLClient
from src.utils.logging import app_logger
from src.utils.config import config


async def initialize_advanced_squad():
    """Initialize a new FPL squad with advanced optimization"""
    
    app_logger.info("=" * 60)
    app_logger.info("FPL Agent - Advanced Squad Initialization (NO CACHE)")
    app_logger.info("=" * 60)
    app_logger.info("Using historical data, fixtures, and expected stats...")
    app_logger.info("")
    
    # Show current weights
    optimizer = AdvancedSquadOptimizerNoCache()
    app_logger.info("Current weights:")
    for key, value in optimizer.weights.items():
        app_logger.info(f"  • {key}: {value:.2%}")
    app_logger.info("")
    
    try:
        # Create client with cache disabled
        async with FPLClient() as client:
            client.cache_duration = 0  # Disable cache
            
            # Run advanced optimization with the no-cache client
            squad = await optimizer.optimize_initial_squad_advanced(client=client)
        
        if squad:
            app_logger.info("\n✅ Advanced squad successfully created!")
            app_logger.info(f"Total players: {len(squad.players)}")
            app_logger.info(f"Squad value: £{squad.value:.1f}m")
            app_logger.info(f"Remaining budget: £{squad.remaining_budget:.1f}m")
            app_logger.info(f"Formation: {squad.formation}")
            
            # Analyze squad composition
            async with FPLClient() as client:
                client.cache_duration = 0  # Disable cache here too
                bootstrap = await client.get_bootstrap_data()
                teams_data = {t['id']: t['name'] for t in bootstrap.get('teams', [])}
            
            # Display squad by position with more details
            positions = {1: "GK", 2: "DEF", 3: "MID", 4: "FWD"}
            
            for pos_id, pos_name in positions.items():
                app_logger.info(f"\n{pos_name}:")
                pos_players = [p for p in squad.players if p.element_type == pos_id]
                
                for p in sorted(pos_players, key=lambda x: x.now_cost, reverse=True):
                    team_name = teams_data.get(p.team, "Unknown")
                    
                    # Get ownership and form
                    ownership = f"{p.selected_by_percent:.1f}%" if p.selected_by_percent else "0%"
                    form = f"{p.form:.1f}" if p.form else "0.0"
                    
                    app_logger.info(
                        f"  - {p.web_name:<15} ({team_name:<12}) "
                        f"£{p.price:.1f}m | "
                        f"Points: {p.total_points:>3} | "
                        f"Form: {form:>3} | "
                        f"Own: {ownership:>5}"
                    )
            
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
            
            # Team distribution
            team_counts = {}
            for p in squad.players:
                team = teams_data.get(p.team, "Unknown")
                team_counts[team] = team_counts.get(team, 0) + 1
            
            app_logger.info(f"  • Team distribution:")
            for team, count in sorted(team_counts.items(), key=lambda x: x[1], reverse=True):
                if count > 1:
                    app_logger.info(f"    - {team}: {count} players")
            
            # Average metrics
            avg_ownership = sum(p.selected_by_percent for p in squad.players) / len(squad.players)
            avg_form = sum(p.form for p in squad.players if p.form) / len([p for p in squad.players if p.form])
            
            app_logger.info(f"\n📈 Squad Metrics:")
            app_logger.info(f"  • Average ownership: {avg_ownership:.1f}%")
            app_logger.info(f"  • Average form: {avg_form:.2f}")
            app_logger.info(f"  • Total GW1 points: {sum(p.total_points for p in squad.players)}")
            
            # Save squad to file with metadata
            squad_file = Path("data/advanced_squad_nocache.json")
            squad_file.parent.mkdir(exist_ok=True)
            
            squad_data = {
                "metadata": {
                    "created_at": datetime.now().isoformat(),
                    "gameweek": 1,
                    "optimization_type": "advanced_nocache",
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
                        "points": p.total_points,
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
            
            with open(squad_file, 'w') as f:
                json.dump(squad_data, f, indent=2)
            
            app_logger.info(f"\n💾 Advanced squad saved to {squad_file}")
            
            # Comparison with previous run
            prev_file = Path("data/advanced_squad.json")
            if prev_file.exists():
                with open(prev_file, 'r') as f:
                    prev_data = json.load(f)
                
                app_logger.info("\n🔄 Comparison with previous optimization:")
                
                # Show weight differences
                prev_weights = prev_data.get('metadata', {}).get('weights', {})
                if prev_weights:
                    app_logger.info("  Weight changes:")
                    for key in optimizer.weights:
                        if key in prev_weights:
                            old_val = prev_weights[key]
                            new_val = optimizer.weights[key]
                            if old_val != new_val:
                                app_logger.info(f"    • {key}: {old_val:.2%} → {new_val:.2%}")
                
                # Find differences
                prev_players = set(p['name'] for p in prev_data.get('players', []))
                current_players = set(p.web_name for p in squad.players)
                
                only_in_current = current_players - prev_players
                only_in_previous = prev_players - current_players
                
                if only_in_current:
                    app_logger.info(f"  • New players in this squad: {', '.join(only_in_current)}")
                if only_in_previous:
                    app_logger.info(f"  • Removed from previous: {', '.join(only_in_previous)}")
                
                if not only_in_current and not only_in_previous:
                    app_logger.info("  • Same players selected (weights may not be affecting selection)")
            
            app_logger.info("\n✨ Advanced optimization complete (cache disabled)!")
            
        else:
            app_logger.error("Failed to create squad")
            
    except Exception as e:
        app_logger.error(f"Error initializing advanced squad: {e}")
        raise


def main():
    """Main entry point"""
    
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Initialize FPL squad with advanced optimization (no cache)"
    )
    parser.add_argument(
        "--compare",
        action="store_true",
        help="Compare with basic optimization"
    )
    
    args = parser.parse_args()
    
    asyncio.run(initialize_advanced_squad())


if __name__ == "__main__":
    main()