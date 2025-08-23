#!/usr/bin/env python3
"""
Test the pre-season optimizer on 2025/26 season
See how it would have performed in GW1
"""

import asyncio
import sys
import json
from pathlib import Path
from datetime import datetime

# Add parent directory to path
sys.path.append(str(Path(__file__).parent.parent))

from src.core.squad_optimizer_preseason import PreseasonSquadOptimizer
from src.api.fpl_client import FPLClient
from src.data.models import Player
from src.utils.logging import app_logger


async def test_current_season():
    """
    Test pre-season optimizer for 2025/26 season
    Compare selected squad with actual GW1 performance
    """
    
    app_logger.info("=" * 60)
    app_logger.info("TESTING PRE-SEASON OPTIMIZER FOR 2025/26")
    app_logger.info("Evaluating GW1 performance")
    app_logger.info("=" * 60)
    
    # Create optimizer
    optimizer = PreseasonSquadOptimizer()
    
    app_logger.info("Using pre-season weights:")
    for key, value in optimizer.weights.items():
        app_logger.info(f"  • {key}: {value:.0%}")
    
    # Run optimization
    app_logger.info("\nSelecting optimal squad for 2025/26...")
    squad = await optimizer.optimize_initial_squad()
    
    if not squad:
        app_logger.error("Failed to create squad")
        return
    
    # Get team names and GW1 points
    async with FPLClient() as client:
        bootstrap = await client.get_bootstrap_data()
        teams_data = {t['id']: t['name'] for t in bootstrap.get('teams', [])}
        
        # Get GW1 live data
        gw1_live = await client.get_gameweek_live_data(1)
        
        # Map player IDs to GW1 points
        gw1_points = {}
        for element in gw1_live.get('elements', []):
            player_id = element.get('id')
            stats = element.get('stats', {})
            # Sum up all the points from GW1
            total_points = stats.get('total_points', 0)
            gw1_points[player_id] = total_points
    
    # Display and analyze squad
    positions = {1: "GK", 2: "DEF", 3: "MID", 4: "FWD"}
    
    # First show starting 11
    app_logger.info("\n⚽ STARTING XI:")
    app_logger.info("=" * 70)
    app_logger.info(f"Formation: {squad.formation}")
    
    starting_11_points = 0
    starting_11_data = []
    
    if squad.starting_11:
        for p in squad.starting_11:
            pts = gw1_points.get(p.id, 0)
            starting_11_points += pts
            player_info = {
                "id": p.id,
                "name": p.web_name,
                "team": teams_data.get(p.team, "Unknown"),
                "position": positions[p.element_type],
                "price": p.price,
                "gw1_points": pts
            }
            starting_11_data.append(player_info)
            
            # Add (C) for highest scoring player as likely captain
            captain_marker = ""
            app_logger.info(
                f"  {p.web_name:<15} ({player_info['team']:<12}) "
                f"{player_info['position']:<3} £{p.price:.1f}m | "
                f"GW1: {pts:>2}pts{captain_marker}"
            )
    
    app_logger.info(f"\nStarting XI Total: {starting_11_points} points")
    
    # Then show bench
    app_logger.info("\n🪑 BENCH:")
    app_logger.info("=" * 70)
    
    bench_points = 0
    if squad.bench:
        for i, p in enumerate(squad.bench):
            pts = gw1_points.get(p.id, 0)
            bench_points += pts
            player_info = {
                "id": p.id,
                "name": p.web_name,
                "team": teams_data.get(p.team, "Unknown"),
                "position": positions[p.element_type],
                "price": p.price,
                "gw1_points": pts
            }
            
            bench_label = f"{i+1}." if i < 3 else "GK"
            app_logger.info(
                f"  {bench_label:<3} {p.web_name:<15} ({player_info['team']:<12}) "
                f"{player_info['position']:<3} £{p.price:.1f}m | "
                f"GW1: {pts:>2}pts"
            )
    
    app_logger.info(f"\nBench Total: {bench_points} points")
    
    total_gw1_points = starting_11_points + bench_points
    squad_data = starting_11_data + [{
        "id": p.id,
        "name": p.web_name,
        "team": teams_data.get(p.team, "Unknown"),
        "position": positions[p.element_type],
        "price": p.price,
        "gw1_points": gw1_points.get(p.id, 0)
    } for p in squad.bench] if squad.bench else starting_11_data
    
    # Sort by GW1 points to see best/worst
    squad_data.sort(key=lambda x: x['gw1_points'], reverse=True)
    
    app_logger.info(f"\n📊 GW1 PERFORMANCE:")
    app_logger.info("=" * 70)
    app_logger.info(f"Total GW1 points: {total_gw1_points}")
    app_logger.info(f"Squad value: £{squad.value:.1f}m")
    app_logger.info(f"Budget remaining: £{squad.remaining_budget:.1f}m")
    
    # Show best performers
    app_logger.info(f"\n🌟 BEST GW1 PERFORMERS:")
    for p in squad_data[:5]:
        app_logger.info(f"  • {p['name']}: {p['gw1_points']}pts (£{p['price']:.1f}m)")
    
    # Show worst performers
    app_logger.info(f"\n❌ WORST GW1 PERFORMERS:")
    for p in squad_data[-3:]:
        app_logger.info(f"  • {p['name']}: {p['gw1_points']}pts (£{p['price']:.1f}m)")
    
    # Note: starting_11_points already calculated above
    
    # Compare with template/popular picks
    app_logger.info(f"\n📈 COMPARISON WITH POPULAR PICKS:")
    
    # Get most owned players
    all_elements = bootstrap.get('elements', [])
    most_owned = sorted(all_elements, 
                       key=lambda x: x.get('selected_by_percent', 0), 
                       reverse=True)[:15]
    
    # Calculate template team GW1 points
    template_points = 0
    for p in most_owned:
        template_points += gw1_points.get(p['id'], 0)
    template_value = sum(p.get('now_cost', 0) / 10 for p in most_owned)
    
    app_logger.info(f"  • Template team (most owned 15): {template_points}pts (£{template_value:.1f}m)")
    app_logger.info(f"  • Our squad: {total_gw1_points}pts (£{squad.value:.1f}m)")
    
    # Show top GW1 scorers we missed
    top_gw1 = sorted(all_elements, 
                    key=lambda x: x.get('event_points', 0), 
                    reverse=True)[:10]
    
    our_player_ids = {p.id for p in squad.players}
    
    app_logger.info(f"\n💔 TOP GW1 SCORERS WE MISSED:")
    missed_count = 0
    for player in top_gw1:
        if player['id'] not in our_player_ids:
            app_logger.info(
                f"  • {player['web_name']}: {player['event_points']}pts "
                f"(£{player['now_cost']/10:.1f}m, {float(player.get('selected_by_percent', 0)):.1f}% owned)"
            )
            missed_count += 1
            if missed_count >= 5:
                break
    
    # Save results
    results = {
        "metadata": {
            "created_at": datetime.now().isoformat(),
            "season": "2025/26",
            "gameweek": 1,
            "budget_used": squad.value,
            "weights": optimizer.weights
        },
        "squad": squad_data,
        "performance": {
            "total_gw1_points": total_gw1_points,
            "starting_11_points": starting_11_points,
            "template_points": template_points,
            "efficiency_vs_template": (total_gw1_points / template_points * 100) if template_points > 0 else 0
        }
    }
    
    results_file = Path("data/preseason_gw1_test.json")
    results_file.parent.mkdir(exist_ok=True)
    
    with open(results_file, 'w') as f:
        json.dump(results, f, indent=2)
    
    app_logger.info(f"\n💾 Results saved to {results_file}")
    
    return results


def main():
    """Main entry point"""
    asyncio.run(test_current_season())


if __name__ == "__main__":
    main()