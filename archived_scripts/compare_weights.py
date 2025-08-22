#!/usr/bin/env python3
"""
Compare squads with different weight configurations
"""

import asyncio
import sys
import json
from pathlib import Path

# Add parent directory to path
sys.path.append(str(Path(__file__).parent.parent))

from src.core.squad_optimizer_advanced import AdvancedSquadOptimizer
from src.api.fpl_client import FPLClient
from src.utils.logging import app_logger


async def compare_weights():
    """Compare squads with different weight configurations"""
    
    configs = [
        {
            "name": "Historical Heavy (70% base)",
            "weights": {
                'base': 0.70,
                'form': 0.05,
                'fixtures': 0.10,
                'value': 0.10,
                'ownership': 0.03,
                'expected': 0.02
            }
        },
        {
            "name": "Form Heavy (70% form)",
            "weights": {
                'base': 0.05,
                'form': 0.70,
                'fixtures': 0.10,
                'value': 0.10,
                'ownership': 0.03,
                'expected': 0.02
            }
        },
        {
            "name": "Balanced",
            "weights": {
                'base': 0.25,
                'form': 0.25,
                'fixtures': 0.20,
                'value': 0.15,
                'ownership': 0.05,
                'expected': 0.10
            }
        },
        {
            "name": "Value Focused",
            "weights": {
                'base': 0.15,
                'form': 0.15,
                'fixtures': 0.10,
                'value': 0.50,
                'ownership': 0.05,
                'expected': 0.05
            }
        }
    ]
    
    squads = []
    
    for config in configs:
        app_logger.info(f"\n{'='*60}")
        app_logger.info(f"Testing: {config['name']}")
        app_logger.info(f"{'='*60}")
        
        optimizer = AdvancedSquadOptimizer()
        optimizer.weights = config['weights']
        
        # Show weights
        for key, value in config['weights'].items():
            app_logger.info(f"  {key}: {value:.0%}")
        
        app_logger.info("\nOptimizing...")
        
        # Run optimization
        squad = await optimizer.optimize_initial_squad_advanced()
        
        # Store results
        player_names = sorted([p.web_name for p in squad.players])
        squads.append({
            "name": config['name'],
            "weights": config['weights'],
            "players": player_names,
            "value": squad.value,
            "players_obj": squad.players
        })
        
        app_logger.info(f"Squad value: £{squad.value:.1f}m")
        app_logger.info(f"Players: {', '.join(player_names[:5])}...")
    
    # Compare all squads
    app_logger.info(f"\n{'='*60}")
    app_logger.info("COMPARISON SUMMARY")
    app_logger.info(f"{'='*60}")
    
    # Find common players across all configs
    all_players = set(squads[0]['players'])
    for squad in squads[1:]:
        all_players = all_players.intersection(set(squad['players']))
    
    app_logger.info(f"\n🔒 Players selected in ALL configurations ({len(all_players)}):")
    for player in sorted(all_players):
        app_logger.info(f"  • {player}")
    
    # Show unique players for each config
    for i, squad in enumerate(squads):
        unique = set(squad['players']) - all_players
        if unique:
            app_logger.info(f"\n🎯 Unique to {squad['name']} ({len(unique)}):")
            for player in sorted(unique):
                player_obj = next(p for p in squad['players_obj'] if p.web_name == player)
                app_logger.info(f"  • {player} (£{player_obj.price:.1f}m)")
    
    # Pairwise comparisons
    app_logger.info(f"\n📊 Pairwise Differences:")
    for i in range(len(squads)):
        for j in range(i+1, len(squads)):
            s1, s2 = squads[i], squads[j]
            common = len(set(s1['players']) & set(s2['players']))
            app_logger.info(f"  {s1['name'][:20]:<20} vs {s2['name'][:20]:<20}: {common}/15 common")
    
    # Save comparison to file
    comparison_file = Path("data/weight_comparison.json")
    comparison_data = {
        "configs": configs,
        "results": [
            {
                "name": s['name'],
                "weights": s['weights'],
                "players": s['players'],
                "value": s['value']
            }
            for s in squads
        ],
        "common_players": sorted(list(all_players))
    }
    
    with open(comparison_file, 'w') as f:
        json.dump(comparison_data, f, indent=2)
    
    app_logger.info(f"\n💾 Comparison saved to {comparison_file}")


def main():
    """Main entry point"""
    asyncio.run(compare_weights())


if __name__ == "__main__":
    main()