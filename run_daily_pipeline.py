#!/usr/bin/env python3
"""
Daily Pipeline - NBA Player Stats + Gambling Odds Integration

Runs both scrapers and integrates the data into a unified database.

This script:
1. Scrapes yesterday's NBA player stats (from nba.com CDN)
2. Scrapes latest gambling odds (from OddsPortal via NBAGambling project)
3. Integrates new data into the combined database
4. Updates player_game_totals_with_odds table

Schedule at 6:00 AM (after games complete):
    Windows: Task Scheduler
    Linux: crontab -e -> 0 6 * * * /usr/bin/python3 /path/to/run_daily_pipeline.py

Usage:
    python run_daily_pipeline.py                    # Full pipeline
    python run_daily_pipeline.py --stats-only       # Only player stats
    python run_daily_pipeline.py --odds-only        # Only gambling odds
    python run_daily_pipeline.py --integrate-only   # Only run integration
"""

import sys
import os
import subprocess
import logging
from pathlib import Path
from datetime import datetime
import argparse

# Project paths
PLAYER_STATS_PROJECT = Path(r"C:/Users/cashk/OneDrive/Projects/NBAPlayer Points")
GAMBLING_PROJECT = Path(r"C:/Users/cashk/OneDrive/Projects/NBAGambling")

# Ensure we're in the right directory
os.chdir(PLAYER_STATS_PROJECT)
sys.path.insert(0, str(PLAYER_STATS_PROJECT))

# Setup logging
LOG_PATH = PLAYER_STATS_PROJECT / "logs"
LOG_PATH.mkdir(parents=True, exist_ok=True)

log_file = LOG_PATH / f"daily_pipeline_{datetime.now().strftime('%Y%m%d')}.log"
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler(log_file, encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


def run_player_stats_update() -> bool:
    """
    Run the NBA player stats daily update.
    Returns True if successful.
    """
    logger.info("="*60)
    logger.info("STEP 1: NBA Player Stats Update")
    logger.info("="*60)

    try:
        from nba_pbp_scraper import daily_update

        result = daily_update()

        if result is not None and len(result) > 0:
            logger.info(f"  Added {len(result):,} new records")
            logger.info(f"  Games: {result['game_id'].nunique()}")
            return True
        else:
            logger.info("  No new games (possibly no games yesterday)")
            return True  # Not an error, just no games

    except Exception as e:
        logger.error(f"  Player stats update failed: {e}")
        return False


def run_gambling_odds_update() -> bool:
    """
    Run the gambling odds scraper for the current season.
    Returns True if successful.
    """
    logger.info("="*60)
    logger.info("STEP 2: Gambling Odds Update")
    logger.info("="*60)

    # Determine current season (NBA season runs Oct-Apr)
    today = datetime.now()
    if today.month >= 10:
        # Oct-Dec: season started this year
        season_start = today.year
    else:
        # Jan-Sep: season started last year
        season_start = today.year - 1

    current_season = f"{season_start}-{season_start + 1}"
    logger.info(f"  Current season: {current_season}")

    # Path to gambling scraper
    gambling_script = GAMBLING_PROJECT / "main.py"

    if not gambling_script.exists():
        logger.error(f"  Gambling scraper not found: {gambling_script}")
        return False

    try:
        # Run the gambling scraper
        # Using subprocess to run in the gambling project directory
        cmd = [
            sys.executable,
            str(gambling_script),
            "--season", current_season,
            "--headless",
        ]

        logger.info(f"  Running: {' '.join(cmd)}")

        result = subprocess.run(
            cmd,
            cwd=str(GAMBLING_PROJECT),
            capture_output=True,
            text=True,
            timeout=600  # 10 minute timeout
        )

        if result.returncode == 0:
            logger.info("  Gambling odds update completed successfully")
            # Log last few lines of output
            for line in result.stdout.split('\n')[-5:]:
                if line.strip():
                    logger.info(f"    {line}")
            return True
        else:
            logger.error(f"  Gambling scraper failed with code {result.returncode}")
            logger.error(f"  stderr: {result.stderr}")
            return False

    except subprocess.TimeoutExpired:
        logger.error("  Gambling scraper timed out after 10 minutes")
        return False
    except Exception as e:
        logger.error(f"  Error running gambling scraper: {e}")
        return False


def run_integration() -> bool:
    """
    Run the data integration to merge player stats with gambling odds.
    Returns True if successful.
    """
    logger.info("="*60)
    logger.info("STEP 3: Data Integration")
    logger.info("="*60)

    try:
        # Import integration module
        from integrate_gambling_data import (
            create_enhanced_database,
            create_player_game_totals_with_odds,
            verify_integration
        )

        # Run integration
        games_with_odds = create_enhanced_database()
        player_totals = create_player_game_totals_with_odds()

        # Verify
        verify_integration()

        matched = games_with_odds['closing_spread'].notna().sum()
        logger.info(f"  Integration complete: {matched} games with odds")

        return True

    except Exception as e:
        logger.error(f"  Integration failed: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return False


def main():
    parser = argparse.ArgumentParser(description='Daily Pipeline for NBA Stats + Odds')
    parser.add_argument('--stats-only', action='store_true', help='Only run player stats update')
    parser.add_argument('--odds-only', action='store_true', help='Only run gambling odds update')
    parser.add_argument('--integrate-only', action='store_true', help='Only run integration')
    parser.add_argument('--skip-odds', action='store_true', help='Skip gambling odds (stats + integration)')

    args = parser.parse_args()

    logger.info("="*60)
    logger.info("DAILY PIPELINE STARTING")
    logger.info(f"Time: {datetime.now()}")
    logger.info("="*60)

    results = {
        'stats': None,
        'odds': None,
        'integration': None
    }

    # Determine what to run
    run_stats = not args.odds_only and not args.integrate_only
    run_odds = not args.stats_only and not args.integrate_only and not args.skip_odds
    run_integrate = not args.stats_only and not args.odds_only

    # Step 1: Player Stats
    if run_stats:
        results['stats'] = run_player_stats_update()

    # Step 2: Gambling Odds
    if run_odds:
        results['odds'] = run_gambling_odds_update()

    # Step 3: Integration
    if run_integrate:
        results['integration'] = run_integration()

    # Summary
    logger.info("="*60)
    logger.info("PIPELINE COMPLETE")
    logger.info("="*60)

    for step, success in results.items():
        if success is None:
            status = "SKIPPED"
        elif success:
            status = "SUCCESS"
        else:
            status = "FAILED"
        logger.info(f"  {step.upper()}: {status}")

    # Return non-zero if any step failed
    if any(v is False for v in results.values()):
        logger.error("Pipeline completed with errors")
        sys.exit(1)
    else:
        logger.info("Pipeline completed successfully")


if __name__ == "__main__":
    main()
