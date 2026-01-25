#!/usr/bin/env python3
"""
Full Historical Scrape Script

Scrapes all NBA play-by-play data from 2021-22 to present with full stats.

Stats tracked per player per minute:
- Points, Field Goals (made/attempted), 3-Pointers (made/attempted), Free Throws (made/attempted)
- Rebounds (total, offensive, defensive)
- Assists, Steals, Blocks, Turnovers, Fouls
- Minutes Played

Usage:
    python run_full_scrape.py

Estimated time: 45-90 minutes
"""

import sys
import os
from pathlib import Path
from datetime import datetime

PROJECT_DIR = Path(__file__).parent
sys.path.insert(0, str(PROJECT_DIR))
os.chdir(PROJECT_DIR)

from nba_pbp_scraper import full_historical_scrape, logger

def main():
    logger.info("="*60)
    logger.info("FULL HISTORICAL SCRAPE - ALL STATS")
    logger.info(f"Start time: {datetime.now()}")
    logger.info("="*60)
    logger.info("")
    logger.info("Stats being tracked:")
    logger.info("  - Points, FGM, FGA, FG3M, FG3A, FTM, FTA")
    logger.info("  - Rebounds (total, offensive, defensive)")
    logger.info("  - Assists, Steals, Blocks, Turnovers, Fouls")
    logger.info("  - Minutes Played")
    logger.info("")

    try:
        result = full_historical_scrape()

        if len(result) > 0:
            logger.info(f"\n{'='*60}")
            logger.info("SCRAPE COMPLETE!")
            logger.info(f"{'='*60}")
            logger.info(f"Total records: {len(result):,}")
            logger.info(f"Unique games: {result['game_id'].nunique():,}")
            logger.info(f"Unique players: {result['player_name'].nunique()}")
            logger.info(f"Seasons: {sorted(result['season'].unique())}")
            logger.info(f"Date range: {result['game_date'].min()} to {result['game_date'].max()}")
        else:
            logger.warning("No data was scraped")

    except Exception as e:
        logger.error(f"Full scrape failed: {e}")
        raise

if __name__ == "__main__":
    main()
