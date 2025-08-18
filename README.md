# FPL Agent

An intelligent AI agent for managing Fantasy Premier League teams automatically throughout the season. The agent makes data-driven decisions on transfers, captaincy, formations, and chip usage while respecting all FPL rules and constraints.

## Features

### Core Capabilities

- **Squad Optimization**: Uses linear programming to select optimal initial squad and weekly lineups
- **Transfer Engine**: Evaluates and executes strategic transfers based on form, fixtures, and predictions
- **Captain Selection**: Data-driven captain and vice-captain choices
- **Chip Strategy**: Intelligent usage of all 8 chips (2x each: Wildcard, Free Hit, Bench Boost, Triple Captain)
- **Formation Management**: Dynamic formation optimization based on player strengths
- **Continuous Monitoring**: Runs throughout the season with deadline alerts

### 2025/26 Season Features

- Support for double chip usage (each chip usable twice per season)
- Defensive contribution points tracking
- Enhanced assist detection
- AFCON transfer boost handling (GW16)
- Banking up to 5 free transfers

## Installation

### Prerequisites

- Python 3.10 or higher
- pip package manager

### Setup

1. Clone the repository:

```bash
git clone https://github.com/yourusername/fpl-agent.git
cd fpl-agent
```

2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Create a `.env` file for configuration:

```bash
cp .env.example .env
```

4. Edit `.env` with your settings:

```env
# FPL Settings
FPL_MANAGER_ID=your_manager_id  # Optional for existing team
FPL_EMAIL=your_email            # Optional for authentication
FPL_PASSWORD=your_password      # Optional for authentication

# Strategy Settings
MAX_HIT_COST=8                  # Maximum points to take as hits
MIN_TRANSFER_GAIN=3.0           # Minimum expected point gain per transfer

# System Settings
ENVIRONMENT=development
DEBUG=False
DRY_RUN=True                    # Set to False to make actual changes

# Database
DB_TYPE=sqlite                  # or postgresql
DB_NAME=fpl_agent

# Logging
LOG_LEVEL=INFO
```

## Usage 📖

### Initialize a New Squad

Create an optimal initial squad from scratch:

```bash
python scripts/initialize_squad.py
```

Load an existing team:

```bash
python scripts/initialize_squad.py --manager-id YOUR_MANAGER_ID
```

### Run Gameweek Analysis

Analyze and make decisions for a specific gameweek:

```bash
# Dry run (no changes made)
python scripts/run_gameweek.py --gameweek 10 --manager-id YOUR_MANAGER_ID

# Execute changes
python scripts/run_gameweek.py --gameweek 10 --manager-id YOUR_MANAGER_ID --execute
```

### Continuous Mode

Run the agent continuously throughout the season:

```bash
python scripts/run_continuous.py --manager-id YOUR_MANAGER_ID
```

The agent will:

- Monitor upcoming deadlines
- Run analysis before each deadline
- Make transfers and team selections
- Log all decisions and reasoning

## Architecture

### Project Structure

```
fpl-agent/
├── src/
│   ├── api/             # FPL API client and data fetching
│   ├── core/            # Core logic (optimizer, transfers, manager)
│   ├── analysis/        # Player and fixture analysis
│   ├── strategies/      # Chips and captain strategies
│   ├── data/            # Data models and database
│   └── utils/           # Configuration, logging, constants
├── scripts/             # Executable scripts
├── config/              # Configuration files
├── data/                # Local data storage
├── logs/                # Application logs
└── tests/               # Unit and integration tests
```

### Key Components

#### Squad Optimizer (`src/core/squad_optimizer.py`)

- Linear programming solver using PuLP
- Considers expected points, form, fixtures, and value
- Handles all FPL constraints (budget, positions, team limits)

#### Transfer Engine (`src/core/transfer_engine.py`)

- Evaluates all possible transfers
- Considers hit costs and expected gains
- Handles injuries and price changes
- Wildcard squad building

#### Captain Selector (`src/strategies/captain_selector.py`)

- Statistical model for captain selection
- Confidence scoring
- Differential captain identification
- Triple Captain timing

#### Chip Strategy (`src/strategies/chips.py`)

- Evaluates optimal chip usage
- Plans chip schedule for the season
- Considers double gameweeks and blank gameweeks

## Configuration ⚙️

### Strategy Parameters

Edit `src/utils/config.py` or use environment variables:

- `MAX_HIT_COST`: Maximum points to spend on hits (default: 8)
- `MIN_TRANSFER_GAIN`: Minimum expected gain per transfer (default: 3.0)
- `CAPTAIN_THRESHOLD`: Multiplier for captain selection (default: 1.5)
- `WILDCARD_TEAM_ISSUES`: Number of issues to trigger wildcard (default: 5)
- `BENCH_BOOST_MIN_POINTS`: Minimum bench points for BB (default: 20)
- `TRIPLE_CAPTAIN_MIN_POINTS`: Minimum captain points for TC (default: 10)

### Optimization Weights

Adjust in config for different strategies:

- `POINTS_WEIGHT`: Weight for total points (default: 1.0)
- `FORM_WEIGHT`: Weight for recent form (default: 0.3)
- `FIXTURE_WEIGHT`: Weight for fixtures (default: 0.2)
- `VALUE_WEIGHT`: Weight for value (default: 0.1)

## Monitoring

### Logs

The agent provides detailed logging:

- Decision rationale
- Transfer recommendations
- Chip usage
- Performance metrics

Logs are stored in `logs/` with daily rotation.

### Notifications (Optional)

Configure notifications in `.env`:

- Email alerts
- Slack webhooks
- Telegram bot

## Development

### Running Tests

```bash
pytest tests/
```

### Code Quality

```bash
# Format code
black src/

# Lint
flake8 src/

# Type checking
mypy src/
```

## Docker Support

Build and run with Docker:

```bash
# Build image
docker build -t fpl-agent .

# Run container
docker run -d \
  -e FPL_MANAGER_ID=your_id \
  -e DRY_RUN=False \
  -v $(pwd)/data:/app/data \
  -v $(pwd)/logs:/app/logs \
  fpl-agent
```

## Roadmap

### Planned Features

- [ ] Web dashboard for monitoring
- [ ] Machine learning predictions
- [ ] News sentiment analysis
- [ ] Social media integration
- [ ] Multi-account support
- [ ] Advanced injury prediction
- [ ] Price change predictions
- [ ] Mini-league optimization

### Improvements

- [ ] Better fixture difficulty rating
- [ ] xG/xA data integration
- [ ] Historical performance analysis
- [ ] Opponent analysis
- [ ] Set piece taker tracking

## Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests
5. Submit a pull request

## Disclaimer

This tool is for educational and personal use. Always review decisions before executing them in your actual FPL team. The agent's performance depends on data quality and prediction accuracy.

## License

MIT License - see LICENSE file for details

## Support

For issues, questions, or suggestions:

- Open an issue on GitHub
- Check existing issues for solutions
- Read the documentation

## Acknowledgments

- Fantasy Premier League for the game and API
- FPL community for strategies and insights
- Open source contributors

---
