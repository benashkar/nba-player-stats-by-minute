"""
NBA Play-by-Play Scraper - All Available Seasons

Scrapes both 2024-25 (complete) and 2025-26 (ongoing) seasons
from NBA's CDN endpoints.
"""

import pandas as pd
from pathlib import Path
import time
import json
import requests
from datetime import datetime

from nba_api.stats.endpoints import leaguegamefinder

# Configuration
BASE_PATH = Path(r"C:/Users/cashk/OneDrive/Projects/NBAPlayer Points")
RAW_PATH = BASE_PATH / "raw"
OUTPUT_PATH = BASE_PATH / "output"

RAW_PATH.mkdir(parents=True, exist_ok=True)
OUTPUT_PATH.mkdir(parents=True, exist_ok=True)

REQUEST_DELAY = 0.3


def get_season_games(season, season_type="Regular Season"):
    """Get all games for a season."""
    print(f"  Fetching {season} {season_type} games...")
    try:
        gamefinder = leaguegamefinder.LeagueGameFinder(
            season_nullable=season,
            season_type_nullable=season_type,
            league_id_nullable="00"
        )
        games = gamefinder.get_data_frames()[0]
        unique_games = games.drop_duplicates(subset=['GAME_ID']).sort_values('GAME_DATE')
        print(f"    Found {len(unique_games)} games")
        return unique_games
    except Exception as e:
        print(f"    Error: {e}")
        return pd.DataFrame()


def get_play_by_play_cdn(game_id):
    """Get play-by-play from CDN."""
    url = f"https://cdn.nba.com/static/json/liveData/playbyplay/playbyplay_{game_id}.json"
    try:
        resp = requests.get(url, timeout=30)
        if resp.status_code == 200:
            data = resp.json()
            if 'game' in data and 'actions' in data['game']:
                return data['game']['actions']
        return []
    except:
        return []


def parse_clock_to_elapsed(period, clock_str):
    """Convert clock to elapsed minutes."""
    try:
        clock_str = str(clock_str).replace('PT', '').replace('S', '')
        parts = clock_str.split('M')
        mins = int(parts[0])
        secs = float(parts[1]) if len(parts) > 1 else 0
        time_remaining = mins + secs / 60

        if period <= 4:
            elapsed = (period - 1) * 12 + (12 - time_remaining)
        else:
            elapsed = 48.0
        return round(elapsed, 2)
    except:
        return None


def process_actions(actions, game_id, game_date):
    """Process actions into player points by minute."""
    if not actions:
        return pd.DataFrame()

    scoring_plays = []

    for action in actions:
        action_type = action.get('actionType', '')
        description = action.get('description', '').upper()

        # Check for made shots
        is_made = False
        points = 0

        if action_type in ['2pt', '3pt'] and 'MISS' not in description:
            is_made = True
            points = 3 if '3PT' in description else 2
        elif action_type == 'Free Throw' and 'MISS' not in description and 'PTS' in description:
            is_made = True
            points = 1

        if not is_made:
            continue

        player_name = action.get('playerNameI', action.get('playerName', ''))
        if not player_name:
            continue

        elapsed = parse_clock_to_elapsed(action.get('period', 0), action.get('clock', ''))
        if elapsed is None:
            continue

        scoring_plays.append({
            'elapsed_minutes': elapsed,
            'player_name': player_name,
            'points_scored': points
        })

    if not scoring_plays:
        return pd.DataFrame()

    scoring_df = pd.DataFrame(scoring_plays).sort_values('elapsed_minutes')

    player_results = []
    for player in scoring_df['player_name'].unique():
        player_data = scoring_df[scoring_df['player_name'] == player].copy()
        player_data['cumulative_points'] = player_data['points_scored'].cumsum()

        for minute in range(49):
            pts = player_data[player_data['elapsed_minutes'] <= minute]['cumulative_points'].max()
            if pd.isna(pts):
                pts = 0
            player_results.append({
                'game_id': game_id,
                'game_date': game_date,
                'player_name': player,
                'elapsed_minute': minute,
                'cumulative_points': int(pts)
            })

    return pd.DataFrame(player_results)


def scrape_season(season, max_games=None):
    """Scrape a full season."""
    print(f"\nScraping {season}...")

    games = get_season_games(season)
    if len(games) == 0:
        return pd.DataFrame()

    game_ids = games['GAME_ID'].tolist()
    game_dates = games['GAME_DATE'].tolist()

    if max_games:
        game_ids = game_ids[:max_games]
        game_dates = game_dates[:max_games]

    total = len(game_ids)
    print(f"  Scraping {total} games...")

    all_results = []
    success = 0

    for i, (gid, gdate) in enumerate(zip(game_ids, game_dates)):
        if (i + 1) % 100 == 0:
            print(f"    Game {i+1}/{total}...")

        actions = get_play_by_play_cdn(gid)
        if actions:
            success += 1
            result = process_actions(actions, gid, gdate)
            if len(result) > 0:
                all_results.append(result)

        time.sleep(REQUEST_DELAY)

    print(f"  Successfully scraped: {success}/{total}")

    if all_results:
        df = pd.concat(all_results, ignore_index=True)
        df['season'] = season
        return df
    return pd.DataFrame()


def main():
    """Scrape all available seasons."""
    print("="*60)
    print("NBA PLAY-BY-PLAY SCRAPER - ALL SEASONS")
    print("="*60)
    print(f"Start: {datetime.now()}")

    all_data = []

    # Scrape 2024-25
    df_2025 = scrape_season("2024-25")
    if len(df_2025) > 0:
        df_2025.to_csv(OUTPUT_PATH / "player_points_by_minute_2025.csv", index=False)
        all_data.append(df_2025)
        print(f"  Saved 2024-25: {len(df_2025):,} records")

    # Scrape 2025-26 (current season)
    df_2026 = scrape_season("2025-26")
    if len(df_2026) > 0:
        df_2026.to_csv(OUTPUT_PATH / "player_points_by_minute_2026.csv", index=False)
        all_data.append(df_2026)
        print(f"  Saved 2025-26: {len(df_2026):,} records")

    # Combine with existing 2021-2024 data
    existing_path = OUTPUT_PATH / "nba_player_points_by_minute_2021_2024.csv"
    if existing_path.exists():
        print("\nCombining with existing 2021-2024 data...")
        existing = pd.read_csv(existing_path)
        all_data.insert(0, existing)

    if all_data:
        combined = pd.concat(all_data, ignore_index=True)
        combined_path = OUTPUT_PATH / "nba_player_points_by_minute_ALL.csv"
        combined.to_csv(combined_path, index=False)
        print(f"\nSaved combined database: {combined_path}")
        print(f"  Total records: {len(combined):,}")
        print(f"  Unique games: {combined['game_id'].nunique():,}")
        print(f"  Unique players: {combined['player_name'].nunique()}")

    print(f"\nEnd: {datetime.now()}")
    print("="*60)


if __name__ == "__main__":
    main()
