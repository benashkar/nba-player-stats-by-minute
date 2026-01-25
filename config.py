"""
Configuration file for NBA Play-by-Play Scraper

Update these paths when deploying to your server.
"""

from pathlib import Path

# ============================================================================
# PATH CONFIGURATION - UPDATE THESE FOR YOUR SERVER
# ============================================================================

# Base directory for all data
BASE_PATH = Path(r"C:/Users/cashk/OneDrive/Projects/NBAPlayer Points")

# Subdirectories (automatically created)
RAW_PATH = BASE_PATH / "raw"
OUTPUT_PATH = BASE_PATH / "output"
LOG_PATH = BASE_PATH / "logs"

# ============================================================================
# DATABASE FILES
# ============================================================================

DB_FILE = OUTPUT_PATH / "nba_player_points.db"
CSV_FILE = OUTPUT_PATH / "nba_player_points_by_minute.csv"

# ============================================================================
# API SETTINGS
# ============================================================================

# Delay between API requests (seconds)
# Increase if you get rate limited
REQUEST_DELAY = 0.35

# Maximum retry attempts for failed requests
MAX_RETRIES = 3

# Request timeout (seconds)
TIMEOUT = 30

# ============================================================================
# SEASONS TO SCRAPE
# ============================================================================

# Seasons for full historical scrape
HISTORICAL_SEASONS = [
    "2021-22",
    "2022-23",
    "2023-24",
    "2024-25",
    "2025-26"
]

# ============================================================================
# LOGGING
# ============================================================================

# Log level: DEBUG, INFO, WARNING, ERROR
LOG_LEVEL = "INFO"

# Keep logs for this many days
LOG_RETENTION_DAYS = 30
