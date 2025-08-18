#!/usr/bin/env python3
"""
Simple test without pydantic complications
"""

import asyncio
import sys
from pathlib import Path

# Add parent directory to path
sys.path.append(str(Path(__file__).parent))

async def test_api():
    """Test FPL API directly"""
    print("Testing FPL API connection...")
    
    try:
        from src.api.fpl_client import FPLClient
        
        async with FPLClient() as client:
            # Test basic API call
            data = await client.get_bootstrap_data()
            
            players = data.get('elements', [])
            teams = data.get('teams', [])
            events = data.get('events', [])
            
            print(f"✅ API Connected!")
            print(f"   - Players: {len(players)}")
            print(f"   - Teams: {len(teams)}")
            print(f"   - Gameweeks: {len(events)}")
            
            # Find current gameweek
            current_gw = None
            for event in events:
                if event.get('is_current'):
                    current_gw = event.get('id')
                    break
            
            if current_gw:
                print(f"   - Current Gameweek: {current_gw}")
            
            # Test getting a specific player
            if players:
                sample_player = players[0]
                print(f"\n📊 Sample Player:")
                print(f"   - Name: {sample_player.get('web_name')}")
                print(f"   - Team: {sample_player.get('team')}")
                print(f"   - Price: £{sample_player.get('now_cost', 0) / 10}m")
                print(f"   - Points: {sample_player.get('total_points')}")
            
            return True
            
    except Exception as e:
        print(f"❌ API Error: {e}")
        return False

async def test_squad_creation():
    """Test creating a squad with simple models"""
    print("\n\nTesting Squad Creation...")
    
    try:
        from src.api.fpl_client import FPLClient
        from src.data.models_simple import Player, Squad
        
        async with FPLClient() as client:
            # Get players
            players_data = await client.get_all_players()
            
            # Convert to simple Player objects
            players = []
            for p_data in players_data[:50]:  # Just use first 50 for testing
                player = Player.from_dict(p_data)
                players.append(player)
            
            print(f"✅ Loaded {len(players)} players")
            
            # Create a simple squad
            squad = Squad(players=players[:15])  # Just take first 15
            
            print(f"✅ Created squad:")
            print(f"   - Players: {len(squad.players)}")
            print(f"   - Value: £{squad.value:.1f}m")
            print(f"   - Budget remaining: £{squad.remaining_budget:.1f}m")
            
            return True
            
    except ImportError:
        print("⚠️  Simple models not found, using original models")
        
        try:
            from src.data.models import Player, Squad
            from src.api.fpl_client import FPLClient
            
            async with FPLClient() as client:
                players_data = await client.get_all_players()
                
                # Just create a basic squad
                players = []
                for p_data in players_data[:15]:
                    try:
                        player = Player(**p_data)
                        players.append(player)
                    except:
                        pass
                
                if players:
                    print(f"✅ Created {len(players)} player objects")
                    return True
                    
        except Exception as e:
            print(f"❌ Error: {e}")
            
    except Exception as e:
        print(f"❌ Squad Error: {e}")
        return False

async def main():
    print("=" * 60)
    print("FPL AGENT - SIMPLE TEST")
    print("=" * 60)
    
    # Test 1: API Connection
    api_success = await test_api()
    
    # Test 2: Squad Creation
    squad_success = await test_squad_creation()
    
    print("\n" + "=" * 60)
    print("TEST RESULTS")
    print("=" * 60)
    print(f"{'✅' if api_success else '❌'} API Connection")
    print(f"{'✅' if squad_success else '❌'} Squad Creation")
    
    if api_success and squad_success:
        print("\n🎉 Basic tests passed!")
        print("\nNext steps:")
        print("1. Run: python scripts/initialize_squad.py")
        print("2. Check the squad in data/initial_squad.json")
    else:
        print("\n⚠️  Some tests failed")
        print("Check the errors above for details")

if __name__ == "__main__":
    asyncio.run(main())