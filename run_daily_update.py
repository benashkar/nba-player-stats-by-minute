#!/usr/bin/env python3
"""
Daily Update Script for NBA Player Stats

Run this daily via scheduler to fetch yesterday's games.

Stats tracked per player per minute:
- Points, FGM, FGA, FG3M, FG3A, FTM, FTA
- Rebounds (total, offensive, defensive)
- Assists, Steals, Blocks, Turnovers, Fouls
- Minutes Played

Schedule at 6:00 AM (after games complete):
    Windows: Task Scheduler
    Linux: crontab -e -> 0 6 * * * /usr/bin/python3 /path/to/run_daily_update.py
"""

import sys
import os
from pathlib import Path
from datetime import datetime

PROJECT_DIR = Path(__file__).parent
sys.path.insert(0, str(PROJECT_DIR))
os.chdir(PROJECT_DIR)

from nba_pbp_scraper import daily_update, logger

def main():
    logger.info("="*60)
    logger.info("SCHEDULED DAILY UPDATE - FULL STATS")
    logger.info(f"Run time: {datetime.now()}")
    logger.info("="*60)

    try:
        result = daily_update()

        if len(result) > 0:
            logger.info(f"Successfully added {len(result):,} records")
            logger.info(f"Games: {result['game_id'].nunique()}")
            logger.info(f"Stats: {[c for c in result.columns if 'cumulative' in c]}")
        else:
            logger.info("No new games (possibly no games yesterday)")

    except Exception as e:
        logger.error(f"Daily update failed: {e}")
        raise

if __name__ == "__main__":
    main()
