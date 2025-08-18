#!/usr/bin/env python3
"""
Run FPL agent for a specific gameweek
"""

import asyncio
import sys
from pathlib import Path

# Add parent directory to path
sys.path.append(str(Path(__file__).parent.parent))

from src.core.team_manager import TeamManager
from src.utils.logging import app_logger
from src.utils.config import config


async def run_gameweek(gameweek: int = None, manager_id: int = None, dry_run: bool = True):
    """Run analysis and decisions for a gameweek"""
    
    app_logger.info("=" * 50)
    app_logger.info(f"FPL Agent - Gameweek Analysis")
    app_logger.info(f"Mode: {'DRY RUN' if dry_run else 'LIVE'}")
    app_logger.info("=" * 50)
    
    manager = TeamManager()
    
    try:
        # Initialize team
        await manager.initialize(manager_id=manager_id)
        
        if not manager.current_squad:
            app_logger.error("No squad loaded. Run initialize_squad.py first.")
            return
            
        # Run gameweek analysis
        decision = await manager.run_gameweek(gameweek=gameweek, dry_run=dry_run)
        
        # Display decisions
        app_logger.info("\n" + "=" * 50)
        app_logger.info(f"GAMEWEEK {decision.gameweek} DECISIONS")
        app_logger.info("=" * 50)
        
        # Transfers
        if decision.transfers:
            app_logger.info(f"\n📊 TRANSFERS ({len(decision.transfers)}):")
            for i, transfer in enumerate(decision.transfers, 1):
                cost_symbol = "🔴" if transfer.cost_difference > 0 else "🟢"
                app_logger.info(
                    f"  {i}. OUT: {transfer.player_out.web_name} "
                    f"-> IN: {transfer.player_in.web_name}"
                )
                app_logger.info(
                    f"     {cost_symbol} Cost: £{abs(transfer.cost_difference):.1f}m "
                    f"| Expected gain: +{transfer.expected_gain:.1f} pts"
                )
                app_logger.info(f"     Reason: {transfer.reasoning}")
        else:
            app_logger.info("\n📊 TRANSFERS: None recommended")
            
        # Captain choices
        app_logger.info("\n👑 CAPTAINCY:")
        app_logger.info(f"  Captain (C): Player #{decision.captain_id}")
        app_logger.info(f"  Vice-Captain (V): Player #{decision.vice_captain_id}")
        
        # Chip usage
        if decision.chip:
            app_logger.info(f"\n🎯 CHIP: {decision.chip.value}")
        else:
            app_logger.info("\n🎯 CHIP: None")
            
        # Formation
        app_logger.info(f"\n⚽ FORMATION: {'-'.join(map(str, decision.formation))}")
        
        # Summary
        total_hits = max(0, len(decision.transfers) - manager.current_squad.free_transfers)
        hit_cost = total_hits * 4
        
        app_logger.info("\n" + "=" * 50)
        app_logger.info("SUMMARY")
        app_logger.info("=" * 50)
        app_logger.info(f"Free transfers available: {manager.current_squad.free_transfers}")
        app_logger.info(f"Transfers to make: {len(decision.transfers)}")
        app_logger.info(f"Hits to take: {total_hits} (-{hit_cost} pts)")
        
        if not dry_run:
            app_logger.info("\n✅ Changes have been applied!")
        else:
            app_logger.info("\n⚠️  DRY RUN - No changes made")
            app_logger.info("Run with --execute to apply changes")
            
    except Exception as e:
        app_logger.error(f"Error running gameweek: {e}")
        raise


def main():
    """Main entry point"""
    
    import argparse
    
    parser = argparse.ArgumentParser(description="Run FPL agent for gameweek")
    parser.add_argument(
        "--gameweek",
        type=int,
        help="Gameweek number (omit for current)"
    )
    parser.add_argument(
        "--manager-id",
        type=int,
        help="Manager ID (required if not in config)"
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Execute changes (default is dry run)"
    )
    
    args = parser.parse_args()
    
    # Get manager ID from config or args
    manager_id = args.manager_id or config.fpl.manager_id
    
    if not manager_id:
        print("Error: Manager ID required. Set in config or pass --manager-id")
        sys.exit(1)
        
    asyncio.run(
        run_gameweek(
            gameweek=args.gameweek,
            manager_id=manager_id,
            dry_run=not args.execute
        )
    )


if __name__ == "__main__":
    main()