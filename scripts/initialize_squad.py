#!/usr/bin/env python3
"""
Initialize a new FPL squad from scratch
"""

import asyncio
import sys
from pathlib import Path

# Add parent directory to path
sys.path.append(str(Path(__file__).parent.parent))

from src.core.team_manager import TeamManager
from src.utils.logging import app_logger
from src.utils.config import config


async def initialize_new_squad():
    """Initialize a new FPL squad"""
    
    app_logger.info("=" * 50)
    app_logger.info("FPL Agent - Squad Initialization")
    app_logger.info("=" * 50)
    
    manager = TeamManager()
    
    try:
        # Initialize without manager ID to create new team
        await manager.initialize(manager_id=None)
        
        if manager.current_squad:
            app_logger.info("\n✅ Squad successfully created!")
            app_logger.info(f"Total players: {len(manager.current_squad.players)}")
            app_logger.info(f"Squad value: £{manager.current_squad.value:.1f}m")
            app_logger.info(f"Remaining budget: £{manager.current_squad.remaining_budget:.1f}m")
            app_logger.info(f"Formation: {manager.current_squad.formation}")
            
            # Display squad by position
            positions = {1: "GK", 2: "DEF", 3: "MID", 4: "FWD"}
            
            for pos_id, pos_name in positions.items():
                app_logger.info(f"\n{pos_name}:")
                pos_players = [p for p in manager.current_squad.players 
                             if p.element_type == pos_id]
                for p in sorted(pos_players, key=lambda x: x.now_cost, reverse=True):
                    app_logger.info(
                        f"  - {p.web_name:<15} £{p.price:.1f}m  "
                        f"Points: {p.total_points}  Form: {p.form:.1f}"
                    )
                    
            # Save squad to file
            squad_file = Path("data/initial_squad.json")
            squad_file.parent.mkdir(exist_ok=True)
            
            import json
            squad_data = {
                "players": [
                    {
                        "id": p.id,
                        "name": p.web_name,
                        "team": p.team,
                        "position": p.element_type,
                        "price": p.price
                    }
                    for p in manager.current_squad.players
                ],
                "formation": manager.current_squad.formation,
                "value": manager.current_squad.value,
                "budget_remaining": manager.current_squad.remaining_budget
            }
            
            with open(squad_file, 'w') as f:
                json.dump(squad_data, f, indent=2)
                
            app_logger.info(f"\n💾 Squad saved to {squad_file}")
            
        else:
            app_logger.error("Failed to create squad")
            
    except Exception as e:
        app_logger.error(f"Error initializing squad: {e}")
        raise


async def load_existing_squad(manager_id: int):
    """Load an existing FPL squad"""
    
    app_logger.info("=" * 50)
    app_logger.info(f"Loading squad for manager {manager_id}")
    app_logger.info("=" * 50)
    
    manager = TeamManager()
    
    try:
        await manager.initialize(manager_id=manager_id)
        
        if manager.current_squad:
            app_logger.info("\n✅ Squad successfully loaded!")
            app_logger.info(f"Total players: {len(manager.current_squad.players)}")
            app_logger.info(f"Free transfers: {manager.current_squad.free_transfers}")
            
            # Display recent history
            if manager.manager_history:
                app_logger.info("\nRecent history:")
                for event in manager.manager_history[-5:]:
                    app_logger.info(
                        f"  GW{event.event}: {event.points} pts "
                        f"(Total: {event.total_points}, Rank: {event.overall_rank:,})"
                    )
                    
            # Display chips used
            if manager.chips_used:
                app_logger.info("\nChips used:")
                for chip in manager.chips_used:
                    app_logger.info(f"  - {chip.chip.value} in GW{chip.gameweek}")
                    
        else:
            app_logger.error("Failed to load squad")
            
    except Exception as e:
        app_logger.error(f"Error loading squad: {e}")
        raise


def main():
    """Main entry point"""
    
    import argparse
    
    parser = argparse.ArgumentParser(description="Initialize FPL squad")
    parser.add_argument(
        "--manager-id",
        type=int,
        help="Manager ID to load existing team (omit to create new)"
    )
    
    args = parser.parse_args()
    
    if args.manager_id:
        asyncio.run(load_existing_squad(args.manager_id))
    else:
        asyncio.run(initialize_new_squad())


if __name__ == "__main__":
    main()