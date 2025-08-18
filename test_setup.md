# FPL Agent - Comprehensive Testing Guide

## 1. Initial Setup & Environment Testing

### Step 1.1: Create Virtual Environment
```bash
# Create and activate virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Verify Python version (should be 3.10+)
python --version
```

### Step 1.2: Install Dependencies
```bash
# Install all requirements
pip install -r requirements.txt

# Verify key packages installed
python -c "import pulp; print('PuLP installed:', pulp.__version__)"
python -c "import aiohttp; print('aiohttp installed:', aiohttp.__version__)"
python -c "import pandas; print('pandas installed:', pandas.__version__)"
```

### Step 1.3: Setup Environment Variables
```bash
# Copy example env file
cp .env.example .env

# Edit .env file - for testing, keep DRY_RUN=True
# No FPL credentials needed for basic testing
```

## 2. Module-by-Module Testing

### Step 2.1: Test FPL API Client
Create `test_api.py`:
```python
import asyncio
from src.api.fpl_client import FPLClient

async def test_api():
    async with FPLClient() as client:
        # Test bootstrap data
        print("Testing bootstrap data...")
        data = await client.get_bootstrap_data()
        print(f"✓ Got {len(data.get('elements', []))} players")
        print(f"✓ Got {len(data.get('teams', []))} teams")
        
        # Test current gameweek
        gw = await client.get_current_gameweek()
        print(f"✓ Current gameweek: {gw}")
        
        # Test fixtures
        fixtures = await client.get_fixtures()
        print(f"✓ Got {len(fixtures)} fixtures")
        
        # Test player search
        player = await client.get_player_by_name("Haaland")
        if player:
            print(f"✓ Found player: {player.get('web_name')}")

asyncio.run(test_api())
```

Run: `python test_api.py`

### Step 2.2: Test Squad Optimizer
Create `test_optimizer.py`:
```python
import asyncio
from src.api.fpl_client import FPLClient
from src.core.squad_optimizer import SquadOptimizer
from src.data.models import Player

async def test_optimizer():
    async with FPLClient() as client:
        # Get all players
        players_data = await client.get_all_players()
        players = [Player(**p) for p in players_data]
        
        # Test squad optimization
        optimizer = SquadOptimizer()
        squad = optimizer.optimize_initial_squad(
            players[:500],  # Use subset for faster testing
            budget=100.0
        )
        
        print(f"✓ Squad created with {len(squad.players)} players")
        print(f"✓ Total value: £{squad.value:.1f}m")
        print(f"✓ Remaining budget: £{squad.remaining_budget:.1f}m")
        print(f"✓ Formation: {squad.formation}")
        
        # Verify constraints
        assert len(squad.players) == 15, "Squad must have 15 players"
        assert squad.value <= 100.0, "Squad must be within budget"
        print("✓ All constraints satisfied")

asyncio.run(test_optimizer())
```

Run: `python test_optimizer.py`

### Step 2.3: Test Configuration & Logging
Create `test_config.py`:
```python
from src.utils.config import config, config_manager
from src.utils.logging import app_logger, log_decision

# Test configuration loading
print("Testing configuration...")
print(f"✓ Environment: {config.environment}")
print(f"✓ Dry run mode: {config.dry_run}")
print(f"✓ Max hit cost: {config.fpl.max_hit_cost}")
print(f"✓ Database type: {config.database.type}")

# Test logging
app_logger.info("Test info message")
app_logger.warning("Test warning message")
log_decision("test_decision", action="test", value=123)
print("✓ Logging working")

# Check log file created
import os
assert os.path.exists("logs"), "Logs directory should exist"
print("✓ Log files created")
```

Run: `python test_config.py`

## 3. Integration Testing

### Step 3.1: Test Squad Initialization
```bash
# Test creating a new squad
python scripts/initialize_squad.py

# Expected output:
# - Squad with 15 players created
# - Budget properly allocated
# - Formation selected
# - Squad saved to data/initial_squad.json
```

### Step 3.2: Test with Sample Data
Create `test_integration.py`:
```python
import asyncio
import json
from src.core.team_manager import TeamManager

async def test_integration():
    manager = TeamManager()
    
    try:
        # Initialize new team
        print("Creating new team...")
        await manager.initialize(manager_id=None)
        
        if manager.current_squad:
            print(f"✓ Squad initialized with {len(manager.current_squad.players)} players")
            
            # Save for inspection
            squad_data = {
                "players": [
                    {
                        "id": p.id,
                        "name": p.web_name,
                        "position": p.element_type,
                        "team": p.team,
                        "price": p.price,
                        "points": p.total_points
                    }
                    for p in manager.current_squad.players
                ],
                "total_value": manager.current_squad.value,
                "formation": manager.current_squad.formation
            }
            
            with open("test_squad.json", "w") as f:
                json.dump(squad_data, f, indent=2)
            print("✓ Test squad saved to test_squad.json")
            
            # Test gameweek run (dry run)
            print("\nTesting gameweek analysis...")
            decision = await manager.run_gameweek(gameweek=None, dry_run=True)
            
            print(f"✓ Gameweek {decision.gameweek} analysis complete")
            print(f"  - Transfers recommended: {len(decision.transfers)}")
            print(f"  - Captain selected: {decision.captain_id}")
            print(f"  - Formation: {decision.formation}")
            
    except Exception as e:
        print(f"✗ Error: {e}")
        raise

asyncio.run(test_integration())
```

Run: `python test_integration.py`

## 4. Performance Testing

### Step 4.1: Test Optimization Speed
Create `test_performance.py`:
```python
import asyncio
import time
from src.api.fpl_client import FPLClient
from src.core.squad_optimizer import SquadOptimizer
from src.data.models import Player

async def test_performance():
    async with FPLClient() as client:
        # Get all players
        print("Fetching player data...")
        start = time.time()
        players_data = await client.get_all_players()
        players = [Player(**p) for p in players_data]
        fetch_time = time.time() - start
        print(f"✓ Fetched {len(players)} players in {fetch_time:.2f}s")
        
        # Test optimization speed
        print("\nTesting optimization speed...")
        optimizer = SquadOptimizer()
        
        start = time.time()
        squad = optimizer.optimize_initial_squad(players, budget=100.0)
        opt_time = time.time() - start
        print(f"✓ Optimization completed in {opt_time:.2f}s")
        
        # Test prediction generation
        print("\nTesting prediction generation...")
        start = time.time()
        predictions = {p.id: p.points_per_game * 1.1 for p in players}
        pred_time = time.time() - start
        print(f"✓ Generated {len(predictions)} predictions in {pred_time:.2f}s")
        
        print(f"\nTotal time: {fetch_time + opt_time + pred_time:.2f}s")

asyncio.run(test_performance())
```

Run: `python test_performance.py`

## 5. Validation Testing

### Step 5.1: Validate FPL Rules
Create `test_validation.py`:
```python
import asyncio
from src.api.fpl_client import FPLClient
from src.core.squad_optimizer import SquadOptimizer
from src.utils.constants import FPLConstants, SquadValidator
from src.data.models import Player

async def test_validation():
    async with FPLClient() as client:
        players_data = await client.get_all_players()
        players = [Player(**p) for p in players_data]
        
        optimizer = SquadOptimizer()
        squad = optimizer.optimize_initial_squad(players, budget=100.0)
        
        # Validate squad
        validation = SquadValidator.validate_squad(squad.players)
        
        print("Squad Validation Results:")
        print(f"✓ Valid size: {validation['valid_size']}")
        print(f"✓ Valid positions: {validation['valid_positions']}")
        print(f"✓ Valid teams: {validation['valid_teams']}")
        
        if validation['errors']:
            print("✗ Errors found:")
            for error in validation['errors']:
                print(f"  - {error}")
        else:
            print("✓ All validations passed!")
        
        # Check specific constraints
        position_counts = {}
        for p in squad.players:
            pos = p.element_type
            position_counts[pos] = position_counts.get(pos, 0) + 1
        
        print("\nPosition breakdown:")
        print(f"  GK: {position_counts.get(1, 0)} (required: 2)")
        print(f"  DEF: {position_counts.get(2, 0)} (required: 5)")
        print(f"  MID: {position_counts.get(3, 0)} (required: 5)")
        print(f"  FWD: {position_counts.get(4, 0)} (required: 3)")
        
        # Check team distribution
        team_counts = {}
        for p in squad.players:
            team_counts[p.team] = team_counts.get(p.team, 0) + 1
        
        max_per_team = max(team_counts.values())
        print(f"\nMax players from one team: {max_per_team} (limit: 3)")
        assert max_per_team <= 3, "Too many players from one team!"

asyncio.run(test_validation())
```

Run: `python test_validation.py`

## 6. Error Handling Testing

### Step 6.1: Test Error Recovery
Create `test_errors.py`:
```python
import asyncio
from src.core.team_manager import TeamManager

async def test_error_handling():
    manager = TeamManager()
    
    print("Testing error handling...")
    
    # Test with invalid manager ID
    try:
        await manager.initialize(manager_id=999999999)
        print("✗ Should have raised error for invalid manager")
    except Exception as e:
        print(f"✓ Correctly handled invalid manager: {type(e).__name__}")
    
    # Test with no squad
    try:
        decision = await manager.run_gameweek(dry_run=True)
        print("✗ Should have raised error for no squad")
    except Exception as e:
        print(f"✓ Correctly handled no squad: {type(e).__name__}")
    
    print("\n✓ Error handling tests passed")

asyncio.run(test_error_handling())
```

Run: `python test_errors.py`

## 7. End-to-End Testing Checklist

Run through this checklist:

```bash
# 1. Fresh install test
rm -rf venv data/*.json logs/*.log
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 2. Initialize squad
python scripts/initialize_squad.py
# CHECK: Squad created with 15 players within budget

# 3. Run gameweek analysis (dry run)
python scripts/run_gameweek.py
# CHECK: Analysis completes, shows transfers/captain/formation

# 4. Test continuous mode (let it run for 1 minute)
timeout 60 python scripts/run_continuous.py || true
# CHECK: Starts monitoring, shows next check time

# 5. Check logs
ls -la logs/
cat logs/*.log | grep ERROR
# CHECK: Log files created, no errors

# 6. Check data files
ls -la data/
# CHECK: initial_squad.json created

# 7. Verify all modules import correctly
python -c "from src.api import fpl_client"
python -c "from src.core import squad_optimizer, transfer_engine, team_manager"
python -c "from src.strategies import captain_selector, chips"
python -c "from src.analysis import player_analyzer"
python -c "from src.utils import config, constants, logging"
# CHECK: All imports work without errors
```

## 8. Expected Results Summary

After running all tests, you should see:
- ✅ API successfully fetches FPL data
- ✅ Squad optimizer creates valid 15-player squads
- ✅ All FPL rules validated (budget, positions, team limits)
- ✅ Configuration and logging working
- ✅ Gameweek analysis provides sensible recommendations
- ✅ Performance is acceptable (optimization < 5 seconds)
- ✅ Error handling works correctly
- ✅ All modules import without issues

## Troubleshooting

If tests fail:

1. **API Connection Issues**: Check internet connection, FPL API might be down
2. **Import Errors**: Ensure you're in the project root and venv is activated
3. **Optimization Failures**: Check PuLP is installed correctly: `pip install --upgrade pulp`
4. **Permission Errors**: Ensure data/ and logs/ directories are writable

## Next Steps

Once all tests pass:
1. Get an FPL account and manager ID
2. Update .env with your manager ID
3. Run with `--execute` flag to make real changes (carefully!)
4. Monitor performance over several gameweeks
5. Adjust strategy parameters based on results