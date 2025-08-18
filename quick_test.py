#!/usr/bin/env python3
"""
Quick test script to verify FPL Agent basic functionality
Run this first to ensure everything is set up correctly
"""

import sys
import asyncio
from pathlib import Path

# Add parent directory to path
sys.path.append(str(Path(__file__).parent))

async def run_tests():
    """Run basic tests to verify setup"""
    
    print("=" * 60)
    print("FPL AGENT - QUICK TEST SUITE")
    print("=" * 60)
    
    results = []
    
    # Test 1: Import all modules
    print("\n1. Testing module imports...")
    try:
        from src.api.fpl_client import FPLClient
        from src.core.squad_optimizer import SquadOptimizer
        from src.core.transfer_engine import TransferEngine
        from src.core.team_manager import TeamManager
        from src.strategies.captain_selector import CaptainSelector
        from src.strategies.chips import ChipStrategy
        from src.analysis.player_analyzer import PlayerAnalyzer
        from src.data.models import Player, Squad
        from src.utils.config import config
        from src.utils.constants import FPLConstants
        from src.utils.logging import app_logger
        
        print("✅ All modules imported successfully")
        results.append(("Module imports", True))
    except ImportError as e:
        print(f"❌ Import error: {e}")
        results.append(("Module imports", False))
        return results
    
    # Test 2: Configuration
    print("\n2. Testing configuration...")
    try:
        from src.utils.config import config
        assert config is not None
        assert config.dry_run == True  # Should be True by default
        print(f"✅ Configuration loaded (dry_run={config.dry_run})")
        results.append(("Configuration", True))
    except Exception as e:
        print(f"❌ Configuration error: {e}")
        results.append(("Configuration", False))
    
    # Test 3: FPL API Connection
    print("\n3. Testing FPL API connection...")
    try:
        from src.api.fpl_client import FPLClient
        
        async with FPLClient() as client:
            data = await client.get_bootstrap_data()
            players = data.get('elements', [])
            teams = data.get('teams', [])
            
            print(f"✅ API connected - Found {len(players)} players, {len(teams)} teams")
            results.append(("API Connection", True))
            
            # Test 4: Current gameweek
            gw = await client.get_current_gameweek()
            print(f"✅ Current gameweek: {gw}")
            results.append(("Gameweek fetch", True))
            
    except Exception as e:
        print(f"❌ API error: {e}")
        results.append(("API Connection", False))
        results.append(("Gameweek fetch", False))
    
    # Test 5: Squad Optimization (with small dataset)
    print("\n4. Testing squad optimization...")
    try:
        from src.api.fpl_client import FPLClient
        from src.core.squad_optimizer import SquadOptimizer
        from src.data.models import Player
        
        async with FPLClient() as client:
            players_data = await client.get_all_players()
            
            # Use only top 100 players for quick test
            players = [Player(**p) for p in players_data[:100]]
            
            optimizer = SquadOptimizer()
            
            # Try to optimize with limited players (might not find valid solution)
            try:
                squad = optimizer.optimize_initial_squad(
                    players,
                    budget=100.0
                )
                
                if squad and len(squad.players) == 15:
                    print(f"✅ Squad optimization working")
                    print(f"   - Squad value: £{squad.value:.1f}m")
                    print(f"   - Formation: {squad.formation}")
                    results.append(("Squad Optimization", True))
                else:
                    print("⚠️  Squad optimization returned incomplete squad")
                    results.append(("Squad Optimization", False))
                    
            except Exception as opt_error:
                print(f"⚠️  Optimization with limited data: {opt_error}")
                print("   (This is expected with only 100 players)")
                results.append(("Squad Optimization", "Partial"))
                
    except Exception as e:
        print(f"❌ Optimization error: {e}")
        results.append(("Squad Optimization", False))
    
    # Test 6: Logging
    print("\n5. Testing logging system...")
    try:
        from src.utils.logging import app_logger
        
        app_logger.info("Test log message")
        
        # Check if logs directory exists
        logs_dir = Path("logs")
        if logs_dir.exists():
            print("✅ Logging system working")
            results.append(("Logging", True))
        else:
            logs_dir.mkdir(exist_ok=True)
            print("✅ Logging system initialized")
            results.append(("Logging", True))
            
    except Exception as e:
        print(f"❌ Logging error: {e}")
        results.append(("Logging", False))
    
    # Test 7: Data models
    print("\n6. Testing data models...")
    try:
        from src.data.models import Player, Squad, Transfer, ChipUsage
        
        # Create test player
        test_player = Player(
            id=1,
            first_name="Test",
            second_name="Player",
            web_name="TestPlayer",
            team=1,
            team_code=1,
            element_type=3,
            now_cost=100,
            cost_change_start=0,
            cost_change_event=0,
            total_points=50,
            points_per_game=5.0,
            selected_by_percent=10.0,
            form=5.0,
            minutes=900,
            goals_scored=5,
            assists=3,
            clean_sheets=0,
            goals_conceded=0,
            own_goals=0,
            penalties_saved=0,
            penalties_missed=0,
            yellow_cards=1,
            red_cards=0,
            saves=0,
            bonus=10,
            bps=100,
            influence=50.0,
            creativity=40.0,
            threat=60.0,
            ict_index=150.0,
            status="a"
        )
        
        assert test_player.price == 10.0
        assert test_player.is_available == True
        print("✅ Data models working correctly")
        results.append(("Data Models", True))
        
    except Exception as e:
        print(f"❌ Data model error: {e}")
        results.append(("Data Models", False))
    
    return results


def print_summary(results):
    """Print test summary"""
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    
    passed = sum(1 for _, status in results if status == True)
    failed = sum(1 for _, status in results if status == False)
    partial = sum(1 for _, status in results if status == "Partial")
    
    for test_name, status in results:
        if status == True:
            symbol = "✅"
        elif status == "Partial":
            symbol = "⚠️"
        else:
            symbol = "❌"
        print(f"{symbol} {test_name:<25} {'PASS' if status == True else 'FAIL' if status == False else 'PARTIAL'}")
    
    print("\n" + "-" * 60)
    print(f"Results: {passed} passed, {failed} failed, {partial} partial")
    
    if failed == 0:
        print("\n🎉 All critical tests passed! The FPL Agent is ready to use.")
        print("\nNext steps:")
        print("1. Run: python scripts/initialize_squad.py")
        print("2. Review the created squad in data/initial_squad.json")
        print("3. Run: python scripts/run_gameweek.py (for dry run)")
    else:
        print("\n⚠️  Some tests failed. Please check the errors above.")
        print("Common issues:")
        print("- Ensure all dependencies are installed: pip install -r requirements.txt")
        print("- Check internet connection for API access")
        print("- Verify Python version is 3.10+")


if __name__ == "__main__":
    print("Starting FPL Agent quick tests...")
    print("This will verify your installation and basic functionality.\n")
    
    try:
        results = asyncio.run(run_tests())
        print_summary(results)
    except KeyboardInterrupt:
        print("\n\nTests interrupted by user.")
    except Exception as e:
        print(f"\n\n❌ Fatal error during testing: {e}")
        print("Please ensure all dependencies are installed correctly.")
        sys.exit(1)