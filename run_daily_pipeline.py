#!/usr/bin/env python3
"""
Daily Pipeline - NBA Player Stats + Gambling Odds Integration

Runs both scrapers and integrates the data into a unified database.

This script:
1. Scrapes yesterday's NBA player stats (from nba.com CDN)
2. Scrapes latest gambling odds (from OddsPortal via NBAGambling project)
3. Merges new odds with historical data (preserves kaggle historical data)
4. Integrates new data into the combined database
5. Updates player_game_totals_with_odds table

Schedule at 6:00 AM CST (after games complete):
    Windows: Task Scheduler
    Linux: crontab -e -> 0 6 * * * /usr/bin/python3 /path/to/run_daily_pipeline.py

Usage:
    python run_daily_pipeline.py                    # Full pipeline (fast mode, 2 pages)
    python run_daily_pipeline.py --full-scrape      # Full season scrape (all pages)
    python run_daily_pipeline.py --stats-only       # Only player stats
    python run_daily_pipeline.py --odds-only        # Only gambling odds
    python run_daily_pipeline.py --integrate-only   # Only run integration
    python run_daily_pipeline.py --max-pages 5      # Custom page limit
"""

import sys
import os
import subprocess
import logging
import pandas as pd
from pathlib import Path
from datetime import datetime
import argparse

# Project paths
PLAYER_STATS_PROJECT = Path(r"C:/Users/cashk/OneDrive/Projects/NBAPlayer Points")
GAMBLING_PROJECT = Path(r"C:/Users/cashk/OneDrive/Projects/NBAGambling")
GAMBLING_DATA_PATH = GAMBLING_PROJECT / "data" / "output"

# Historical data file (kaggle data + all previous scrapes)
HISTORICAL_ODDS_FILE = GAMBLING_DATA_PATH / "nba_odds_kaggle.csv"
# Current combined odds file (used by integration)
COMBINED_ODDS_FILE = GAMBLING_DATA_PATH / "nba_odds.csv"

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
        import traceback
        logger.error(traceback.format_exc())
        return False


def run_gambling_odds_update(max_pages: int = 2, fetch_details: bool = True) -> bool:
    """
    Run the gambling odds scraper for the current season.

    Args:
        max_pages: Maximum pages to scrape (default 2 for daily updates)
        fetch_details: Whether to fetch spread/O/U from game detail pages

    Returns True if successful.
    """
    logger.info("="*60)
    logger.info("STEP 2: Gambling Odds Update")
    logger.info("="*60)

    # Determine current season (NBA season runs Oct-Jun)
    today = datetime.now()
    if today.month >= 10:
        # Oct-Dec: season started this year
        season_start = today.year
    else:
        # Jan-Sep: season started last year
        season_start = today.year - 1

    current_season = f"{season_start}-{season_start + 1}"
    logger.info(f"  Current season: {current_season}")
    logger.info(f"  Max pages: {max_pages if max_pages else 'all'}")
    logger.info(f"  Fetch details: {fetch_details}")

    # Path to gambling scraper
    gambling_script = GAMBLING_PROJECT / "main.py"

    if not gambling_script.exists():
        logger.error(f"  Gambling scraper not found: {gambling_script}")
        return False

    try:
        # Build command
        cmd = [
            sys.executable,
            str(gambling_script),
            "--season", current_season,
            "--headless",
        ]

        # Add fetch-details for spreads/O/U
        if fetch_details:
            cmd.append("--fetch-details")

        # Add max-pages for faster daily runs
        if max_pages:
            cmd.extend(["--max-pages", str(max_pages)])

        logger.info(f"  Running: {' '.join(cmd)}")

        # Calculate timeout based on mode
        # With fetch-details: ~12 seconds per game, 30 games per page
        # Without fetch-details: ~10 seconds per page
        if fetch_details:
            timeout_seconds = (max_pages or 20) * 30 * 15  # 15 sec per game buffer
        else:
            timeout_seconds = (max_pages or 20) * 30  # 30 sec per page

        timeout_seconds = max(timeout_seconds, 300)  # Minimum 5 minutes
        logger.info(f"  Timeout: {timeout_seconds // 60} minutes")

        result = subprocess.run(
            cmd,
            cwd=str(GAMBLING_PROJECT),
            capture_output=True,
            text=True,
            timeout=timeout_seconds
        )

        if result.returncode == 0:
            logger.info("  Gambling odds scrape completed successfully")
            # Log last few lines of output
            for line in result.stdout.split('\n')[-5:]:
                if line.strip():
                    logger.info(f"    {line}")
            return True
        else:
            logger.error(f"  Gambling scraper failed with code {result.returncode}")
            logger.error(f"  stderr: {result.stderr[-500:] if result.stderr else 'None'}")
            return False

    except subprocess.TimeoutExpired:
        logger.error(f"  Gambling scraper timed out after {timeout_seconds // 60} minutes")
        return False
    except Exception as e:
        logger.error(f"  Error running gambling scraper: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return False


def merge_odds_data() -> bool:
    """
    Merge newly scraped odds with historical data.

    The scraper outputs to nba_odds.csv. This function:
    1. Loads historical data from nba_odds_kaggle.csv
    2. Loads newly scraped data from nba_odds.csv (scraper output)
    3. Combines them, removing duplicates (keeping newest)
    4. Saves back to nba_odds.csv for integration

    Returns True if successful.
    """
    logger.info("="*60)
    logger.info("STEP 2b: Merge Odds Data")
    logger.info("="*60)

    try:
        # Find the most recent scraper output (timestamped file)
        scraper_outputs = list(GAMBLING_DATA_PATH.glob("nba_odds_202*.csv"))
        scraper_outputs = [f for f in scraper_outputs if 'kaggle' not in f.name and 'combined' not in f.name]

        if not scraper_outputs:
            logger.warning("  No new scraper output found")
            return True  # Not an error, just nothing new

        # Get the most recent output file
        latest_scrape = max(scraper_outputs, key=lambda f: f.stat().st_mtime)
        logger.info(f"  Latest scrape: {latest_scrape.name}")

        # Load historical data
        if HISTORICAL_ODDS_FILE.exists():
            historical_df = pd.read_csv(HISTORICAL_ODDS_FILE)
            logger.info(f"  Historical data: {len(historical_df):,} games")
        else:
            historical_df = pd.DataFrame()
            logger.info("  No historical data file found")

        # Load new scrape
        new_df = pd.read_csv(latest_scrape)
        logger.info(f"  New scrape: {len(new_df):,} games")

        # Ensure is_playoff column exists in new data
        if 'is_playoff' not in new_df.columns:
            new_df['is_playoff'] = 0

        # Combine dataframes
        if len(historical_df) > 0:
            combined_df = pd.concat([historical_df, new_df], ignore_index=True)
        else:
            combined_df = new_df

        # Remove duplicates, keeping the most recent scrape (last occurrence)
        initial_count = len(combined_df)
        combined_df = combined_df.drop_duplicates(subset=['game_id'], keep='last')

        if len(combined_df) < initial_count:
            logger.info(f"  Removed {initial_count - len(combined_df):,} duplicate games")

        # Sort by date
        combined_df = combined_df.sort_values('game_date')

        # Save combined file
        combined_df.to_csv(COMBINED_ODDS_FILE, index=False)
        logger.info(f"  Saved combined data: {len(combined_df):,} games")

        # Show season breakdown
        season_counts = combined_df.groupby('season')['game_id'].count()
        logger.info(f"  Seasons: {len(season_counts)} ({season_counts.index.min()} to {season_counts.index.max()})")

        return True

    except Exception as e:
        logger.error(f"  Merge failed: {e}")
        import traceback
        logger.error(traceback.format_exc())
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
        total = len(games_with_odds)
        logger.info(f"  Integration complete: {matched:,}/{total:,} games with odds ({matched/total*100:.1f}%)")

        return True

    except Exception as e:
        logger.error(f"  Integration failed: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return False


def main():
    parser = argparse.ArgumentParser(
        description='Daily Pipeline for NBA Stats + Odds',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python run_daily_pipeline.py                 # Daily update (2 pages, fast)
  python run_daily_pipeline.py --full-scrape   # Full season scrape
  python run_daily_pipeline.py --max-pages 5   # Custom page limit
  python run_daily_pipeline.py --skip-odds     # Skip odds, just stats + integrate
        """
    )
    parser.add_argument('--stats-only', action='store_true',
                        help='Only run player stats update')
    parser.add_argument('--odds-only', action='store_true',
                        help='Only run gambling odds update')
    parser.add_argument('--integrate-only', action='store_true',
                        help='Only run integration')
    parser.add_argument('--skip-odds', action='store_true',
                        help='Skip gambling odds (stats + integration)')
    parser.add_argument('--full-scrape', action='store_true',
                        help='Scrape all pages (slower, use for backfill)')
    parser.add_argument('--max-pages', type=int, default=2,
                        help='Max pages to scrape (default: 2 for daily updates)')
    parser.add_argument('--no-fetch-details', action='store_true',
                        help='Skip fetching spread/O/U details (faster but less data)')

    args = parser.parse_args()

    logger.info("="*60)
    logger.info("DAILY PIPELINE STARTING")
    logger.info(f"Time: {datetime.now()}")
    logger.info("="*60)

    results = {
        'stats': None,
        'odds': None,
        'merge': None,
        'integration': None
    }

    # Determine what to run
    run_stats = not args.odds_only and not args.integrate_only
    run_odds = not args.stats_only and not args.integrate_only and not args.skip_odds
    run_merge = run_odds  # Always merge after odds scrape
    run_integrate = not args.stats_only and not args.odds_only

    # Determine scrape settings
    max_pages = None if args.full_scrape else args.max_pages
    fetch_details = not args.no_fetch_details

    # Step 1: Player Stats
    if run_stats:
        results['stats'] = run_player_stats_update()

    # Step 2: Gambling Odds
    if run_odds:
        results['odds'] = run_gambling_odds_update(
            max_pages=max_pages,
            fetch_details=fetch_details
        )

    # Step 2b: Merge odds data
    if run_merge and results.get('odds', False):
        results['merge'] = merge_odds_data()

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
