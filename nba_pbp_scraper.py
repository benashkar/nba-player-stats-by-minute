"""
NBA Play-by-Play Scraper - Full Stats Edition

Scrapes NBA play-by-play data and converts it to player stats by minute.
Tracks: Points, Rebounds, Assists, Steals, Blocks, Turnovers, Fouls, Minutes Played

Data source: cdn.nba.com/static/json/liveData/playbyplay/

Usage:
    python nba_pbp_scraper.py --full      # Full historical scrape
    python nba_pbp_scraper.py --daily     # Yesterday's games
    python nba_pbp_scraper.py --season 2024-25  # Specific season
"""

import pandas as pd
import numpy as np
from pathlib import Path
import time
import json
import requests
import logging
import argparse
import sqlite3
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Set, Tuple
from collections import defaultdict

from nba_api.stats.endpoints import leaguegamefinder, scoreboardv2

# ============================================================================
# CONFIGURATION
# ============================================================================

BASE_PATH = Path(r"C:/Users/cashk/OneDrive/Projects/NBAPlayer Points")
RAW_PATH = BASE_PATH / "raw"
OUTPUT_PATH = BASE_PATH / "output"
LOG_PATH = BASE_PATH / "logs"

for path in [RAW_PATH, OUTPUT_PATH, LOG_PATH]:
    path.mkdir(parents=True, exist_ok=True)

REQUEST_DELAY = 0.35
MAX_RETRIES = 3
TIMEOUT = 30

DB_FILE = OUTPUT_PATH / "nba_player_stats.db"
CSV_FILE = OUTPUT_PATH / "nba_player_stats_by_minute.csv"

HISTORICAL_SEASONS = ["2021-22", "2022-23", "2023-24", "2024-25", "2025-26"]

# ============================================================================
# LOGGING
# ============================================================================

def setup_logging():
    log_file = LOG_PATH / f"scraper_{datetime.now().strftime('%Y%m%d')}.log"
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(message)s',
        handlers=[
            logging.FileHandler(log_file, encoding='utf-8'),
            logging.StreamHandler()
        ]
    )
    return logging.getLogger(__name__)

logger = setup_logging()

# ============================================================================
# NBA API FUNCTIONS
# ============================================================================

def get_season_games(season: str, season_type: str = "Regular Season") -> pd.DataFrame:
    """Get all games for a season."""
    logger.info(f"Fetching game list for {season} {season_type}...")
    try:
        time.sleep(REQUEST_DELAY)
        gamefinder = leaguegamefinder.LeagueGameFinder(
            season_nullable=season,
            season_type_nullable=season_type,
            league_id_nullable="00"
        )
        games = gamefinder.get_data_frames()[0]
        unique_games = games.drop_duplicates(subset=['GAME_ID']).sort_values('GAME_DATE')
        logger.info(f"  Found {len(unique_games)} games")
        return unique_games
    except Exception as e:
        logger.error(f"  Error fetching games: {e}")
        return pd.DataFrame()


def get_play_by_play_cdn(game_id: str) -> List[Dict]:
    """Get play-by-play data from NBA CDN endpoint."""
    url = f"https://cdn.nba.com/static/json/liveData/playbyplay/playbyplay_{game_id}.json"

    for attempt in range(MAX_RETRIES):
        try:
            resp = requests.get(url, timeout=TIMEOUT)
            if resp.status_code == 200:
                data = resp.json()
                if 'game' in data and 'actions' in data['game']:
                    return data['game']['actions']
            elif resp.status_code == 404:
                return []
        except requests.exceptions.Timeout:
            logger.warning(f"  Timeout for {game_id}, attempt {attempt + 1}")
            time.sleep(REQUEST_DELAY * 2)
        except Exception as e:
            logger.warning(f"  Error fetching {game_id}: {e}")

        if attempt < MAX_RETRIES - 1:
            time.sleep(REQUEST_DELAY)

    return []


# ============================================================================
# DATA PROCESSING
# ============================================================================

def parse_clock_to_elapsed(period: int, clock_str: str) -> Optional[float]:
    """Convert period and clock to elapsed minutes."""
    try:
        clock_str = str(clock_str).replace('PT', '').replace('S', '')
        parts = clock_str.split('M')
        mins = int(parts[0])
        secs = float(parts[1]) if len(parts) > 1 else 0
        time_remaining = mins + secs / 60

        if period <= 4:
            elapsed = (period - 1) * 12 + (12 - time_remaining)
        else:
            # Overtime periods are 5 minutes each
            elapsed = 48.0 + (period - 5) * 5 + (5 - time_remaining)

        return round(elapsed, 2)
    except:
        return None


def process_actions_full_stats(actions: List[Dict], game_id: str, game_date: str, season: str) -> pd.DataFrame:
    """
    Process play-by-play actions into player stats by minute.

    Tracks: points, rebounds, assists, steals, blocks, turnovers, fouls,
            field goals, 3-pointers, free throws (made and attempted),
            minutes played
    """
    if not actions:
        return pd.DataFrame()

    # Track when players are on court for minutes calculation
    # {player_name: [(enter_time, exit_time), ...]}
    player_on_court_intervals = defaultdict(list)

    # Track players currently on court per team
    # {team_id: set of player_names}
    players_on_court_by_team = defaultdict(set)

    # Track stat events
    # {player_name: {stat_name: [(elapsed_minute, value), ...]}}
    player_events = defaultdict(lambda: {
        'points': [],
        'rebounds': [],
        'offensive_rebounds': [],
        'defensive_rebounds': [],
        'assists': [],
        'steals': [],
        'blocks': [],
        'turnovers': [],
        'fouls': [],
        'fgm': [],
        'fga': [],
        'fg3m': [],
        'fg3a': [],
        'ftm': [],
        'fta': [],
    })

    # Track max game time for calculating final minutes
    max_elapsed = 0.0
    current_period = 0

    # First pass: track substitutions and identify all players on court
    for action in actions:
        action_type = action.get('actionType', '')
        period = action.get('period', 0)
        clock = action.get('clock', '')
        elapsed = parse_clock_to_elapsed(period, clock)
        team_id = action.get('teamId', 0)

        if elapsed is None:
            continue

        max_elapsed = max(max_elapsed, elapsed)

        # Track period starts
        if action_type == 'period' and action.get('subType') == 'start':
            current_period = period

        # SUBSTITUTIONS - properly track IN and OUT
        if action_type == 'substitution':
            player_name = action.get('playerNameI', action.get('playerName', ''))
            sub_type = action.get('subType', '').lower()

            if player_name:
                if sub_type == 'in':
                    # Player entering the game
                    if player_name not in players_on_court_by_team[team_id]:
                        players_on_court_by_team[team_id].add(player_name)
                        player_on_court_intervals[player_name].append([elapsed, None])

                elif sub_type == 'out':
                    # Player leaving the game - close their current interval
                    if player_name in players_on_court_by_team[team_id]:
                        players_on_court_by_team[team_id].discard(player_name)
                        # Close the most recent open interval
                        if player_on_court_intervals[player_name]:
                            intervals = player_on_court_intervals[player_name]
                            if intervals[-1][1] is None:
                                intervals[-1][1] = elapsed

        # Track any player activity as being "on court" (for starters detection)
        player_name = action.get('playerNameI', action.get('playerName', ''))
        if player_name and action_type not in ['period', 'game', 'timeout', 'substitution']:
            all_on_court = set()
            for team_players in players_on_court_by_team.values():
                all_on_court.update(team_players)

            if player_name not in all_on_court:
                # Player is active but we haven't seen them sub in - they're a starter
                players_on_court_by_team[team_id].add(player_name)
                # Assume they started at beginning of current period
                period_start = (current_period - 1) * 12 if current_period <= 4 else 48 + (current_period - 5) * 5
                if period_start < 0:
                    period_start = 0
                player_on_court_intervals[player_name].append([period_start, None])

    # Close any open intervals at game end
    for player_name in player_on_court_intervals:
        intervals = player_on_court_intervals[player_name]
        if intervals and intervals[-1][1] is None:
            intervals[-1][1] = max_elapsed

    # Second pass: collect all stat events
    for action in actions:
        action_type = action.get('actionType', '')
        description = action.get('description', '').upper()
        player_name = action.get('playerNameI', action.get('playerName', ''))

        if not player_name:
            continue

        period = action.get('period', 0)
        clock = action.get('clock', '')
        elapsed = parse_clock_to_elapsed(period, clock)

        if elapsed is None:
            continue

        # FIELD GOALS (2PT and 3PT)
        if action_type in ['2pt', '3pt']:
            is_three = action_type == '3pt' or '3PT' in description
            is_made = 'MISS' not in description

            if is_three:
                player_events[player_name]['fg3a'].append((elapsed, 1))
                player_events[player_name]['fga'].append((elapsed, 1))
                if is_made:
                    player_events[player_name]['fg3m'].append((elapsed, 1))
                    player_events[player_name]['fgm'].append((elapsed, 1))
                    player_events[player_name]['points'].append((elapsed, 3))
            else:
                player_events[player_name]['fga'].append((elapsed, 1))
                if is_made:
                    player_events[player_name]['fgm'].append((elapsed, 1))
                    player_events[player_name]['points'].append((elapsed, 2))

            # Check for assist
            if is_made:
                assist_player = action.get('assistPlayerNameInitial', '')
                if assist_player:
                    player_events[assist_player]['assists'].append((elapsed, 1))

        # FREE THROWS
        elif action_type in ['freethrow', 'Free Throw']:
            player_events[player_name]['fta'].append((elapsed, 1))
            if 'MISS' not in description:
                player_events[player_name]['ftm'].append((elapsed, 1))
                player_events[player_name]['points'].append((elapsed, 1))

        # REBOUNDS
        elif action_type == 'rebound':
            sub_type = action.get('subType', '').lower()
            player_events[player_name]['rebounds'].append((elapsed, 1))
            if 'offensive' in sub_type:
                player_events[player_name]['offensive_rebounds'].append((elapsed, 1))
            else:
                player_events[player_name]['defensive_rebounds'].append((elapsed, 1))

        # STEALS
        elif action_type == 'steal':
            player_events[player_name]['steals'].append((elapsed, 1))

        # BLOCKS
        elif action_type == 'block':
            player_events[player_name]['blocks'].append((elapsed, 1))

        # TURNOVERS
        elif action_type == 'turnover':
            player_events[player_name]['turnovers'].append((elapsed, 1))

        # FOULS
        elif action_type == 'foul':
            player_events[player_name]['fouls'].append((elapsed, 1))

    if not player_events:
        return pd.DataFrame()

    # Get all players (from events or on-court tracking)
    all_players = set(player_events.keys()) | set(player_on_court_intervals.keys())

    # Determine max minute to track (handle overtime)
    max_minute = int(max_elapsed) + 1
    if max_minute < 48:
        max_minute = 49  # At least regulation

    # Convert to minute-by-minute cumulative stats
    results = []

    for player_name in all_players:
        stats = player_events.get(player_name, {stat: [] for stat in [
            'points', 'rebounds', 'offensive_rebounds', 'defensive_rebounds',
            'assists', 'steals', 'blocks', 'turnovers', 'fouls',
            'fgm', 'fga', 'fg3m', 'fg3a', 'ftm', 'fta'
        ]})

        intervals = player_on_court_intervals.get(player_name, [])

        for minute in range(max_minute):
            row = {
                'game_id': game_id,
                'game_date': game_date,
                'season': season,
                'player_name': player_name,
                'elapsed_minute': minute,
            }

            # Calculate cumulative stats at this minute
            for stat_name in ['points', 'rebounds', 'offensive_rebounds', 'defensive_rebounds',
                              'assists', 'steals', 'blocks', 'turnovers', 'fouls',
                              'fgm', 'fga', 'fg3m', 'fg3a', 'ftm', 'fta']:
                events = stats.get(stat_name, [])
                cumulative = sum(val for t, val in events if t <= minute)
                row[f'cumulative_{stat_name}'] = cumulative

            # Calculate minutes played up to this game minute
            minutes_played = 0.0
            for interval in intervals:
                enter_time, exit_time = interval
                if exit_time is None:
                    exit_time = max_elapsed

                if enter_time <= minute:
                    # Player was on court at some point up to this minute
                    interval_start = enter_time
                    interval_end = min(exit_time, minute)
                    if interval_end > interval_start:
                        minutes_played += (interval_end - interval_start)

            row['cumulative_minutes_played'] = round(minutes_played, 1)

            results.append(row)

    return pd.DataFrame(results)


# ============================================================================
# SCRAPING FUNCTIONS
# ============================================================================

def scrape_season(season: str, season_type: str = "Regular Season",
                  save_checkpoints: bool = True) -> pd.DataFrame:
    """Scrape all games for a season."""
    logger.info(f"{'='*60}")
    logger.info(f"SCRAPING {season} {season_type}")
    logger.info(f"{'='*60}")

    games = get_season_games(season, season_type)
    if len(games) == 0:
        return pd.DataFrame()

    game_ids = games['GAME_ID'].tolist()
    game_dates = games['GAME_DATE'].tolist()
    total_games = len(game_ids)

    logger.info(f"Scraping {total_games} games...")

    all_results = []
    success_count = 0
    error_count = 0

    for i, (game_id, game_date) in enumerate(zip(game_ids, game_dates)):
        if (i + 1) % 100 == 0:
            logger.info(f"  Progress: {i+1}/{total_games} (success: {success_count}, errors: {error_count})")

        actions = get_play_by_play_cdn(game_id)

        if actions:
            success_count += 1
            result = process_actions_full_stats(actions, game_id, game_date, season)
            if len(result) > 0:
                all_results.append(result)
        else:
            error_count += 1

        time.sleep(REQUEST_DELAY)

        # Checkpoint every 300 games
        if save_checkpoints and (i + 1) % 300 == 0 and all_results:
            checkpoint_df = pd.concat(all_results, ignore_index=True)
            checkpoint_path = OUTPUT_PATH / f"checkpoint_{season.replace('-', '_')}_{i+1}.csv"
            checkpoint_df.to_csv(checkpoint_path, index=False)
            logger.info(f"  Checkpoint saved: {checkpoint_path}")

    logger.info(f"  Completed: success={success_count}, errors={error_count}")

    if all_results:
        season_df = pd.concat(all_results, ignore_index=True)
        logger.info(f"  Total records: {len(season_df):,}")
        return season_df

    return pd.DataFrame()


def scrape_date_range(start_date: str, end_date: str, season: str) -> pd.DataFrame:
    """Scrape games within a date range."""
    logger.info(f"Scraping games from {start_date} to {end_date}")

    games = get_season_games(season)
    if len(games) == 0:
        return pd.DataFrame()

    games = games[(games['GAME_DATE'] >= start_date) & (games['GAME_DATE'] <= end_date)]
    if len(games) == 0:
        logger.info("No games in date range")
        return pd.DataFrame()

    logger.info(f"Found {len(games)} games")

    all_results = []
    for _, game in games.iterrows():
        game_id = game['GAME_ID']
        game_date = game['GAME_DATE']

        actions = get_play_by_play_cdn(game_id)
        if actions:
            result = process_actions_full_stats(actions, game_id, game_date, season)
            if len(result) > 0:
                all_results.append(result)

        time.sleep(REQUEST_DELAY)

    if all_results:
        return pd.concat(all_results, ignore_index=True)
    return pd.DataFrame()


def scrape_yesterday() -> pd.DataFrame:
    """Scrape yesterday's games."""
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    logger.info(f"Scraping yesterday's games ({yesterday})")

    year = int(yesterday[:4])
    month = int(yesterday[5:7])
    if month >= 10:
        season = f"{year}-{str(year+1)[2:]}"
    else:
        season = f"{year-1}-{str(year)[2:]}"

    return scrape_date_range(yesterday, yesterday, season)


# ============================================================================
# DATABASE FUNCTIONS
# ============================================================================

def save_to_database(df: pd.DataFrame, append: bool = True):
    """Save DataFrame to SQLite database."""
    if len(df) == 0:
        logger.warning("No data to save")
        return

    logger.info(f"Saving {len(df):,} records to database...")

    conn = sqlite3.connect(DB_FILE)

    if append:
        game_ids = df['game_id'].unique().tolist()
        placeholders = ','.join(['?' for _ in game_ids])
        try:
            conn.execute(f"DELETE FROM player_stats_by_minute WHERE game_id IN ({placeholders})", game_ids)
        except:
            pass

    df.to_sql('player_stats_by_minute', conn, if_exists='append' if append else 'replace', index=False)

    # Create indexes
    indexes = [
        ('idx_game', 'game_id'),
        ('idx_player', 'player_name'),
        ('idx_season', 'season'),
        ('idx_date', 'game_date'),
        ('idx_game_player', 'game_id, player_name'),
        ('idx_player_minute', 'player_name, elapsed_minute'),
    ]

    for idx_name, columns in indexes:
        try:
            conn.execute(f'CREATE INDEX IF NOT EXISTS {idx_name} ON player_stats_by_minute({columns})')
        except:
            pass

    conn.commit()
    conn.close()
    logger.info(f"  Saved to {DB_FILE}")


def save_to_csv(df: pd.DataFrame, append: bool = True):
    """Save DataFrame to CSV file."""
    if len(df) == 0:
        return

    if append and CSV_FILE.exists():
        existing = pd.read_csv(CSV_FILE)
        game_ids = df['game_id'].unique()
        existing = existing[~existing['game_id'].isin(game_ids)]
        combined = pd.concat([existing, df], ignore_index=True)
        combined.to_csv(CSV_FILE, index=False)
    else:
        df.to_csv(CSV_FILE, index=False)

    logger.info(f"  Saved to {CSV_FILE}")


# ============================================================================
# MAIN FUNCTIONS
# ============================================================================

def full_historical_scrape():
    """Scrape all historical data."""
    logger.info("="*60)
    logger.info("FULL HISTORICAL SCRAPE - ALL STATS")
    logger.info("="*60)

    all_data = []

    for season in HISTORICAL_SEASONS:
        logger.info(f"\nProcessing {season}...")
        season_df = scrape_season(season)

        if len(season_df) > 0:
            all_data.append(season_df)
            season_file = OUTPUT_PATH / f"player_stats_by_minute_{season.replace('-', '_')}.csv"
            season_df.to_csv(season_file, index=False)
            logger.info(f"  Saved: {season_file}")

    if all_data:
        full_df = pd.concat(all_data, ignore_index=True)
        save_to_database(full_df, append=False)
        save_to_csv(full_df, append=False)

        logger.info(f"\nFull scrape complete!")
        logger.info(f"  Total records: {len(full_df):,}")
        logger.info(f"  Unique games: {full_df['game_id'].nunique():,}")
        logger.info(f"  Unique players: {full_df['player_name'].nunique()}")
        logger.info(f"  Stats tracked: {[c for c in full_df.columns if 'cumulative' in c]}")

        return full_df

    return pd.DataFrame()


def daily_update():
    """Run daily update."""
    logger.info("="*60)
    logger.info("DAILY UPDATE - ALL STATS")
    logger.info("="*60)

    new_data = scrape_yesterday()

    if len(new_data) > 0:
        save_to_database(new_data, append=True)
        save_to_csv(new_data, append=True)

        logger.info(f"\nDaily update complete!")
        logger.info(f"  New records: {len(new_data):,}")
        logger.info(f"  Games added: {new_data['game_id'].nunique()}")
    else:
        logger.info("No new games to add")

    return new_data


def scrape_specific_season(season: str):
    """Scrape a specific season."""
    logger.info(f"Scraping season: {season}")

    season_df = scrape_season(season)

    if len(season_df) > 0:
        season_file = OUTPUT_PATH / f"player_stats_by_minute_{season.replace('-', '_')}.csv"
        season_df.to_csv(season_file, index=False)
        save_to_database(season_df, append=True)
        save_to_csv(season_df, append=True)

    return season_df


# ============================================================================
# CLI
# ============================================================================

def main():
    parser = argparse.ArgumentParser(description='NBA Play-by-Play Scraper - Full Stats')
    parser.add_argument('--full', action='store_true', help='Full historical scrape')
    parser.add_argument('--daily', action='store_true', help='Daily update')
    parser.add_argument('--season', type=str, help='Specific season (e.g., 2024-25)')
    parser.add_argument('--start', type=str, help='Start date (YYYY-MM-DD)')
    parser.add_argument('--end', type=str, help='End date (YYYY-MM-DD)')

    args = parser.parse_args()

    start_time = datetime.now()
    logger.info(f"Start time: {start_time}")

    if args.full:
        full_historical_scrape()
    elif args.daily:
        daily_update()
    elif args.season:
        scrape_specific_season(args.season)
    elif args.start and args.end:
        year = int(args.start[:4])
        month = int(args.start[5:7])
        season = f"{year}-{str(year+1)[2:]}" if month >= 10 else f"{year-1}-{str(year)[2:]}"
        data = scrape_date_range(args.start, args.end, season)
        if len(data) > 0:
            save_to_database(data, append=True)
            save_to_csv(data, append=True)
    else:
        daily_update()

    logger.info(f"End time: {datetime.now()}")
    logger.info(f"Duration: {datetime.now() - start_time}")


if __name__ == "__main__":
    main()
