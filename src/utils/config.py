import os
from pathlib import Path
from typing import Dict, Any, Optional
import yaml
from pydantic import Field
from pydantic_settings import BaseSettings
from dotenv import load_dotenv


# Load environment variables
load_dotenv()


class DatabaseConfig(BaseSettings):
    type: str = Field(default="sqlite", alias="DB_TYPE")
    host: str = Field(default="localhost", alias="DB_HOST")
    port: int = Field(default=5432, alias="DB_PORT")
    name: str = Field(default="fpl_agent", alias="DB_NAME")
    user: str = Field(default="", alias="DB_USER")
    password: str = Field(default="", alias="DB_PASSWORD")
    
    model_config = {"extra": "ignore"}
    
    @property
    def url(self) -> str:
        if self.type == "sqlite":
            return f"sqlite:///data/{self.name}.db"
        elif self.type == "postgresql":
            return f"postgresql://{self.user}:{self.password}@{self.host}:{self.port}/{self.name}"
        else:
            raise ValueError(f"Unsupported database type: {self.type}")


class FPLConfig(BaseSettings):
    manager_id: Optional[int] = Field(default=None, alias="FPL_MANAGER_ID")
    email: Optional[str] = Field(default=None, alias="FPL_EMAIL")
    password: Optional[str] = Field(default=None, alias="FPL_PASSWORD")
    
    # Strategy settings
    max_hit_cost: int = Field(default=8, alias="MAX_HIT_COST")  # Max points to take as hit
    min_transfer_gain: float = Field(default=3.0, alias="MIN_TRANSFER_GAIN")  # Min expected point gain
    
    # Captain selection
    captain_threshold_multiplier: float = Field(default=1.5, alias="CAPTAIN_THRESHOLD")
    vice_captain_threshold_multiplier: float = Field(default=1.3, alias="VICE_CAPTAIN_THRESHOLD")
    
    # Chip usage thresholds
    wildcard_team_issues: int = Field(default=5, alias="WILDCARD_TEAM_ISSUES")  # Players to replace
    bench_boost_min_points: float = Field(default=20.0, alias="BENCH_BOOST_MIN_POINTS")
    triple_captain_min_points: float = Field(default=10.0, alias="TRIPLE_CAPTAIN_MIN_POINTS")
    free_hit_fixture_swing: float = Field(default=15.0, alias="FREE_HIT_FIXTURE_SWING")
    
    model_config = {"extra": "ignore"}


class OptimizationConfig(BaseSettings):
    solver: str = Field(default="CBC", alias="OPTIMIZATION_SOLVER")  # CBC, GLPK, CPLEX
    time_limit: int = Field(default=60, alias="OPTIMIZATION_TIME_LIMIT")  # seconds
    
    # Weights for optimization objectives
    points_weight: float = Field(default=1.0, alias="POINTS_WEIGHT")
    form_weight: float = Field(default=0.3, alias="FORM_WEIGHT")
    fixture_weight: float = Field(default=0.2, alias="FIXTURE_WEIGHT")
    value_weight: float = Field(default=0.1, alias="VALUE_WEIGHT")
    
    model_config = {"extra": "ignore"}


class NotificationConfig(BaseSettings):
    enabled: bool = Field(default=False, alias="NOTIFICATIONS_ENABLED")
    email_enabled: bool = Field(default=False, alias="EMAIL_NOTIFICATIONS")
    email_to: Optional[str] = Field(default=None, alias="NOTIFICATION_EMAIL")
    
    slack_enabled: bool = Field(default=False, alias="SLACK_NOTIFICATIONS")
    slack_webhook: Optional[str] = Field(default=None, alias="SLACK_WEBHOOK_URL")
    
    telegram_enabled: bool = Field(default=False, alias="TELEGRAM_NOTIFICATIONS")
    telegram_token: Optional[str] = Field(default=None, alias="TELEGRAM_BOT_TOKEN")
    telegram_chat_id: Optional[str] = Field(default=None, alias="TELEGRAM_CHAT_ID")
    
    model_config = {"extra": "ignore"}


class LoggingConfig(BaseSettings):
    level: str = Field(default="INFO", alias="LOG_LEVEL")
    format: str = Field(
        default="{time:YYYY-MM-DD HH:mm:ss} | {level} | {name}:{function}:{line} - {message}",
        alias="LOG_FORMAT"
    )
    rotation: str = Field(default="1 day", alias="LOG_ROTATION")
    retention: str = Field(default="7 days", alias="LOG_RETENTION")
    
    file_enabled: bool = Field(default=True, alias="LOG_TO_FILE")
    console_enabled: bool = Field(default=True, alias="LOG_TO_CONSOLE")
    
    model_config = {"extra": "ignore"}
    
    @property
    def file_path(self) -> str:
        return "logs/fpl_agent_{time:YYYY-MM-DD}.log"


class AppConfig(BaseSettings):
    # General settings
    environment: str = Field(default="development", alias="ENVIRONMENT")
    debug: bool = Field(default=False, alias="DEBUG")
    dry_run: bool = Field(default=True, alias="DRY_RUN")  # Don't make actual transfers
    
    # Sub-configurations
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    fpl: FPLConfig = Field(default_factory=FPLConfig)
    optimization: OptimizationConfig = Field(default_factory=OptimizationConfig)
    notifications: NotificationConfig = Field(default_factory=NotificationConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    
    # Scheduling
    check_interval_minutes: int = Field(default=60, alias="CHECK_INTERVAL")
    deadline_warning_hours: int = Field(default=2, alias="DEADLINE_WARNING_HOURS")
    
    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore"  # Ignore extra fields
    }


class ConfigManager:
    """Manages application configuration"""
    
    def __init__(self, config_path: Optional[Path] = None):
        self.config_path = config_path or Path("config/config.yaml")
        self.app_config = AppConfig()
        
        # Load additional config from YAML if exists
        if self.config_path.exists():
            self.load_yaml_config()
            
    def load_yaml_config(self):
        """Load configuration from YAML file"""
        try:
            with open(self.config_path, 'r') as f:
                yaml_config = yaml.safe_load(f)
                
            # Update app config with YAML values
            if yaml_config:
                self._update_config(yaml_config)
                
        except Exception as e:
            print(f"Warning: Could not load YAML config: {e}")
            
    def _update_config(self, yaml_config: Dict[str, Any]):
        """Update configuration with values from YAML"""
        # This is a simplified update - you might want more sophisticated merging
        for key, value in yaml_config.items():
            if hasattr(self.app_config, key):
                if isinstance(value, dict):
                    # For nested configs
                    config_obj = getattr(self.app_config, key)
                    for sub_key, sub_value in value.items():
                        if hasattr(config_obj, sub_key):
                            setattr(config_obj, sub_key, sub_value)
                else:
                    setattr(self.app_config, key, value)
                    
    def save_yaml_config(self):
        """Save current configuration to YAML file"""
        config_dict = self.app_config.dict()
        
        # Ensure config directory exists
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(self.config_path, 'w') as f:
            yaml.dump(config_dict, f, default_flow_style=False)
            
    def get_config(self) -> AppConfig:
        """Get the current configuration"""
        return self.app_config
        
    def update_config(self, **kwargs):
        """Update configuration values"""
        for key, value in kwargs.items():
            if hasattr(self.app_config, key):
                setattr(self.app_config, key, value)
                
    @property
    def is_production(self) -> bool:
        """Check if running in production mode"""
        return self.app_config.environment == "production"
        
    @property
    def is_dry_run(self) -> bool:
        """Check if running in dry-run mode"""
        return self.app_config.dry_run


# Global config instance
config_manager = ConfigManager()
config = config_manager.get_config()