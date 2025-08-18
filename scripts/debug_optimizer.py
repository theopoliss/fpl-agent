#!/usr/bin/env python3
"""
Debug script to understand why weight changes aren't affecting squad selection
"""

import asyncio
import sys
from pathlib import Path
from datetime import datetime

# Add parent directory to path
sys.path.append(str(Path(__file__).parent.parent))

from src.core.squad_optimizer_advanced import AdvancedSquadOptimizer
from src.api.fpl_client import FPLClient
from src.data.models import Player
from src.utils.logging import app_logger
from src.utils.config import config


async def debug_optimization():
    """Debug why weights aren't affecting selection"""
    
    app_logger.info("=" * 60)
    app_logger.info("FPL Agent - Optimization Debugger")
    app_logger.info("=" * 60)
    
    # Create two optimizers with different weights
    optimizer1 = AdvancedSquadOptimizer()
    optimizer1.weights = {
        'base': 0.50,      # Historical/last season 
        'form': 0.0,       # Recent form
        'fixtures': 0.15,  # Fixture difficulty
        'value': 0.20,     # Value for money
        'ownership': 0.02, # Differential 
        'expected': 0.13   # Expected stats
    }
    
    optimizer2 = AdvancedSquadOptimizer()
    optimizer2.weights = {
        'base': 0.10,      # Much less historical
        'form': 0.40,      # Much more form
        'fixtures': 0.20,  # Fixture difficulty
        'value': 0.20,     # Value for money
        'ownership': 0.05, # Differential 
        'expected': 0.05   # Expected stats
    }
    
    app_logger.info("Optimizer 1 weights (base heavy):")
    for key, value in optimizer1.weights.items():
        app_logger.info(f"  • {key}: {value:.2%}")
    
    app_logger.info("\nOptimizer 2 weights (form heavy):")
    for key, value in optimizer2.weights.items():
        app_logger.info(f"  • {key}: {value:.2%}")
    
    try:
        # Fetch data once to use for both optimizations
        async with FPLClient() as client:
            client.cache_duration = 0  # Disable cache
            
            app_logger.info("\nFetching player data...")
            bootstrap_data = await client.get_bootstrap_data()
            all_players_data = bootstrap_data.get('elements', [])
            teams_data = bootstrap_data.get('teams', [])
            fixtures_data = await client.get_fixtures()
            
            # Convert to Player objects
            all_players = [Player(**p) for p in all_players_data]
            
            app_logger.info(f"Loaded {len(all_players)} players")
            
            # Calculate scores with both optimizers
            app_logger.info("\nCalculating scores with Optimizer 1...")
            scores1 = await optimizer1._calculate_player_scores(
                all_players, 
                all_players_data,
                fixtures_data,
                teams_data
            )
            
            app_logger.info("Calculating scores with Optimizer 2...")
            scores2 = await optimizer2._calculate_player_scores(
                all_players, 
                all_players_data,
                fixtures_data,
                teams_data
            )
            
            # Find players with biggest score differences
            score_diffs = []
            for player in all_players[:100]:  # Check top 100 players
                score1 = scores1[player.id].total_score
                score2 = scores2[player.id].total_score
                diff = abs(score1 - score2)
                score_diffs.append((player, score1, score2, diff))
            
            # Sort by difference
            score_diffs.sort(key=lambda x: x[3], reverse=True)
            
            app_logger.info("\n📊 Top 20 players with biggest score differences:")
            app_logger.info(f"{'Player':<20} {'Team':<4} {'Price':<6} {'Opt1':<8} {'Opt2':<8} {'Diff':<8}")
            app_logger.info("-" * 70)
            
            team_names = {t['id']: t['short_name'] for t in teams_data}
            
            for player, score1, score2, diff in score_diffs[:20]:
                team = team_names.get(player.team, "UNK")
                app_logger.info(
                    f"{player.web_name:<20} {team:<4} £{player.price:<5.1f} "
                    f"{score1:<8.2f} {score2:<8.2f} {diff:<8.2f}"
                )
            
            # Show breakdown for top differential player
            if score_diffs:
                top_diff_player = score_diffs[0][0]
                app_logger.info(f"\n🔍 Detailed breakdown for {top_diff_player.web_name}:")
                
                s1 = scores1[top_diff_player.id]
                s2 = scores2[top_diff_player.id]
                
                app_logger.info("\nOptimizer 1 scores:")
                app_logger.info(f"  Base: {s1.base_score:.2f} × {optimizer1.weights['base']:.2f} = {s1.base_score * optimizer1.weights['base']:.2f}")
                app_logger.info(f"  Form: {s1.form_score:.2f} × {optimizer1.weights['form']:.2f} = {s1.form_score * optimizer1.weights['form']:.2f}")
                app_logger.info(f"  Fixtures: {s1.fixture_score:.2f} × {optimizer1.weights['fixtures']:.2f} = {s1.fixture_score * optimizer1.weights['fixtures']:.2f}")
                app_logger.info(f"  Value: {s1.value_score:.2f} × {optimizer1.weights['value']:.2f} = {s1.value_score * optimizer1.weights['value']:.2f}")
                app_logger.info(f"  Ownership: {s1.ownership_score:.2f} × {optimizer1.weights['ownership']:.2f} = {s1.ownership_score * optimizer1.weights['ownership']:.2f}")
                app_logger.info(f"  Expected: {s1.expected_score:.2f} × {optimizer1.weights['expected']:.2f} = {s1.expected_score * optimizer1.weights['expected']:.2f}")
                app_logger.info(f"  TOTAL: {s1.total_score:.2f}")
                
                app_logger.info("\nOptimizer 2 scores:")
                app_logger.info(f"  Base: {s2.base_score:.2f} × {optimizer2.weights['base']:.2f} = {s2.base_score * optimizer2.weights['base']:.2f}")
                app_logger.info(f"  Form: {s2.form_score:.2f} × {optimizer2.weights['form']:.2f} = {s2.form_score * optimizer2.weights['form']:.2f}")
                app_logger.info(f"  Fixtures: {s2.fixture_score:.2f} × {optimizer2.weights['fixtures']:.2f} = {s2.fixture_score * optimizer2.weights['fixtures']:.2f}")
                app_logger.info(f"  Value: {s2.value_score:.2f} × {optimizer2.weights['value']:.2f} = {s2.value_score * optimizer2.weights['value']:.2f}")
                app_logger.info(f"  Ownership: {s2.ownership_score:.2f} × {optimizer2.weights['ownership']:.2f} = {s2.ownership_score * optimizer2.weights['ownership']:.2f}")
                app_logger.info(f"  Expected: {s2.expected_score:.2f} × {optimizer2.weights['expected']:.2f} = {s2.expected_score * optimizer2.weights['expected']:.2f}")
                app_logger.info(f"  TOTAL: {s2.total_score:.2f}")
            
            # Now run actual optimization with both
            app_logger.info("\n🎯 Running actual optimization...")
            
            squad1 = optimizer1._optimize_with_scores(
                all_players,
                scores1,
                100.0
            )
            
            squad2 = optimizer2._optimize_with_scores(
                all_players,
                scores2,
                100.0
            )
            
            # Compare squads
            players1 = set(p.web_name for p in squad1.players)
            players2 = set(p.web_name for p in squad2.players)
            
            only_in_1 = players1 - players2
            only_in_2 = players2 - players1
            
            app_logger.info(f"\n📋 Squad comparison:")
            app_logger.info(f"Squad 1 value: £{squad1.value:.1f}m")
            app_logger.info(f"Squad 2 value: £{squad2.value:.1f}m")
            app_logger.info(f"Common players: {len(players1 & players2)}/15")
            
            if only_in_1:
                app_logger.info(f"\nOnly in Squad 1 (base-heavy):")
                for name in only_in_1:
                    player = next(p for p in squad1.players if p.web_name == name)
                    app_logger.info(f"  • {name} (£{player.price:.1f}m)")
            
            if only_in_2:
                app_logger.info(f"\nOnly in Squad 2 (form-heavy):")
                for name in only_in_2:
                    player = next(p for p in squad2.players if p.web_name == name)
                    app_logger.info(f"  • {name} (£{player.price:.1f}m)")
            
            # Check if the problem is with constraints
            app_logger.info("\n🔍 Checking constraint impact...")
            
            # Count how many players meet various constraints
            regular_starters = [
                p for p in all_players 
                if p.minutes > 60 and p.chance_of_playing_this_round in [None, 100]
            ]
            premiums = [p for p in all_players if p.now_cost >= 100]
            cheap = [p for p in all_players if p.now_cost <= 45]
            
            app_logger.info(f"Regular starters available: {len(regular_starters)}")
            app_logger.info(f"Premium players (£10m+) available: {len(premiums)}")
            app_logger.info(f"Cheap players (£4.5m-) available: {len(cheap)}")
            
            # Check if constraints are limiting selection
            top_scorers1 = sorted(scores1.values(), key=lambda x: x.total_score, reverse=True)[:30]
            top_scorers2 = sorted(scores2.values(), key=lambda x: x.total_score, reverse=True)[:30]
            
            top_players1 = [next(p for p in all_players if p.id == s.player_id) for s in top_scorers1]
            top_players2 = [next(p for p in all_players if p.id == s.player_id) for s in top_scorers2]
            
            app_logger.info(f"\n📈 Top 15 scorers by Optimizer 1:")
            for i, (player, score) in enumerate(zip(top_players1[:15], top_scorers1[:15]), 1):
                selected = "✓" if player.web_name in players1 else "✗"
                app_logger.info(f"{i:2}. {selected} {player.web_name:<20} £{player.price:<5.1f} Score: {score.total_score:.2f}")
            
            app_logger.info(f"\n📈 Top 15 scorers by Optimizer 2:")
            for i, (player, score) in enumerate(zip(top_players2[:15], top_scorers2[:15]), 1):
                selected = "✓" if player.web_name in players2 else "✗"
                app_logger.info(f"{i:2}. {selected} {player.web_name:<20} £{player.price:<5.1f} Score: {score.total_score:.2f}")
            
    except Exception as e:
        app_logger.error(f"Error in debugging: {e}")
        raise


def main():
    """Main entry point"""
    asyncio.run(debug_optimization())


if __name__ == "__main__":
    main()