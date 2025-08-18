#!/usr/bin/env python3
"""
Run FPL agent continuously throughout the season
"""

import asyncio
import sys
import signal
from pathlib import Path
from datetime import datetime

# Add parent directory to path
sys.path.append(str(Path(__file__).parent.parent))

from src.core.team_manager import TeamManager
from src.utils.logging import app_logger
from src.utils.config import config


class ContinuousRunner:
    """Manages continuous running of the FPL agent"""
    
    def __init__(self, manager_id: int):
        self.manager_id = manager_id
        self.manager = TeamManager()
        self.running = False
        
    async def start(self):
        """Start the continuous runner"""
        
        app_logger.info("=" * 50)
        app_logger.info("FPL Agent - Continuous Mode")
        app_logger.info(f"Manager ID: {self.manager_id}")
        app_logger.info(f"Check interval: {config.check_interval_minutes} minutes")
        app_logger.info(f"Mode: {'DRY RUN' if config.dry_run else 'LIVE'}")
        app_logger.info("=" * 50)
        
        # Initialize team
        await self.manager.initialize(manager_id=self.manager_id)
        
        if not self.manager.current_squad:
            app_logger.error("Failed to load squad")
            return
            
        app_logger.info(f"✅ Squad loaded with {len(self.manager.current_squad.players)} players")
        app_logger.info("Starting continuous monitoring...")
        app_logger.info("Press Ctrl+C to stop\n")
        
        self.running = True
        
        # Start monitoring
        await self.monitor_loop()
        
    async def monitor_loop(self):
        """Main monitoring loop"""
        
        while self.running:
            try:
                # Check for upcoming deadline
                async with self.manager.api_client:
                    deadline = await self.manager.api_client.get_deadline_time()
                    current_gw = await self.manager.api_client.get_current_gameweek()
                    
                if deadline:
                    time_to_deadline = (deadline - datetime.now()).total_seconds() / 3600
                    
                    app_logger.info(f"\n📅 Gameweek {current_gw}")
                    app_logger.info(f"⏰ Deadline in {time_to_deadline:.1f} hours")
                    
                    # Run analysis if deadline is close
                    if time_to_deadline <= config.deadline_warning_hours:
                        app_logger.warning("Deadline approaching! Running analysis...")
                        
                        decision = await self.manager.run_gameweek(
                            gameweek=current_gw,
                            dry_run=config.dry_run
                        )
                        
                        # Log summary
                        self.log_decision_summary(decision)
                        
                        # Wait until after deadline before checking again
                        wait_time = max(time_to_deadline * 3600 + 300, 60)
                        app_logger.info(f"Waiting {wait_time/60:.0f} minutes until after deadline...")
                        await asyncio.sleep(wait_time)
                    else:
                        # Regular check
                        app_logger.info("No immediate action needed")
                        
                        # Quick health check
                        await self.health_check()
                        
                        # Wait for next check
                        wait_time = config.check_interval_minutes * 60
                        app_logger.info(f"Next check in {config.check_interval_minutes} minutes...")
                        await asyncio.sleep(wait_time)
                else:
                    app_logger.warning("Could not fetch deadline information")
                    await asyncio.sleep(config.check_interval_minutes * 60)
                    
            except asyncio.CancelledError:
                app_logger.info("Monitoring cancelled")
                break
            except Exception as e:
                app_logger.error(f"Error in monitoring loop: {e}")
                app_logger.info("Retrying in 5 minutes...")
                await asyncio.sleep(300)
                
    async def health_check(self):
        """Perform quick health check on squad"""
        
        async with self.manager.api_client:
            # Get latest player data
            all_players = await self.manager.api_client.get_all_players()
            
            injured_count = 0
            doubtful_count = 0
            
            for squad_player in self.manager.current_squad.players:
                current = next((p for p in all_players if p["id"] == squad_player.id), None)
                if current:
                    if current["status"] != "a":
                        injured_count += 1
                    elif current.get("chance_of_playing_this_round"):
                        if current["chance_of_playing_this_round"] < 75:
                            doubtful_count += 1
                            
            if injured_count > 0 or doubtful_count > 0:
                app_logger.warning(
                    f"⚠️  Squad issues: {injured_count} injured, {doubtful_count} doubtful"
                )
            else:
                app_logger.info("✅ Squad health: All players available")
                
    def log_decision_summary(self, decision):
        """Log summary of decisions made"""
        
        app_logger.info("\n" + "=" * 30)
        app_logger.info("DECISION SUMMARY")
        app_logger.info("=" * 30)
        
        if decision.transfers:
            app_logger.info(f"Transfers: {len(decision.transfers)}")
            for t in decision.transfers:
                app_logger.info(f"  • {t.player_out.web_name} -> {t.player_in.web_name}")
        else:
            app_logger.info("Transfers: None")
            
        if decision.chip:
            app_logger.info(f"Chip: {decision.chip.value}")
            
        app_logger.info("=" * 30)
        
    def stop(self):
        """Stop the runner"""
        app_logger.info("\nStopping continuous runner...")
        self.running = False


def main():
    """Main entry point"""
    
    import argparse
    
    parser = argparse.ArgumentParser(description="Run FPL agent continuously")
    parser.add_argument(
        "--manager-id",
        type=int,
        help="Manager ID (required if not in config)"
    )
    
    args = parser.parse_args()
    
    # Get manager ID
    manager_id = args.manager_id or config.fpl.manager_id
    
    if not manager_id:
        print("Error: Manager ID required. Set in config or pass --manager-id")
        sys.exit(1)
        
    # Create runner
    runner = ContinuousRunner(manager_id)
    
    # Handle signals
    def signal_handler(sig, frame):
        runner.stop()
        sys.exit(0)
        
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Start runner
    try:
        asyncio.run(runner.start())
    except KeyboardInterrupt:
        app_logger.info("\nShutdown requested")
    except Exception as e:
        app_logger.error(f"Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()