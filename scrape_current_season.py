"""
NBA Play-by-Play Scraper for Current Season

This script scrapes play-by-play data from NBA's CDN endpoints
for the current NBA season.

Data source: cdn.nba.com/static/json/liveData/playbyplay/
"""

import pandas as pd
import numpy as np
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

# Ensure directories exist
RAW_PATH.mkdir(parents=True, exist_ok=True)
OUTPUT_PATH.mkdir(parents=True, exist_ok=True)

# Rate limiting settings
REQUEST_DELAY = 0.3  # seconds between requests (CDN is faster)


def get_season_games(season="2024-25", season_type="Regular Season"):
    """
    Get all games for a season using nba_api.
    """
    print(f"Fetching game list for {season} {season_type}...")

    try:
        gamefinder = leaguegamefinder.LeagueGameFinder(
            season_nullable=season,
            season_type_nullable=season_type,
            league_id_nullable="00"
        )
        games = gamefinder.get_data_frames()[0]
        unique_games = games.drop_duplicates(subset=['GAME_ID']).copy()
        unique_games = unique_games.sort_values('GAME_DATE')

        print(f"  Found {len(unique_games)} games")
        return unique_games

    except Exception as e:
        print(f"  Error fetching games: {e}")
        return pd.DataFrame()


def get_play_by_play_cdn(game_id):
    """
    Get play-by-play data from NBA CDN endpoint.

    Args:
        game_id: NBA game ID (e.g., "0022400001")

    Returns:
        List of play actions or empty list on error
    """
    url = f"https://cdn.nba.com/static/json/liveData/playbyplay/playbyplay_{game_id}.json"

    try:
        resp = requests.get(url, timeout=30)
        if resp.status_code == 200:
            data = resp.json()
            if 'game' in data and 'actions' in data['game']:
                return data['game']['actions']
        return []
    except Exception as e:
        return []


def parse_clock_to_elapsed(period, clock_str):
    """
    Convert period and clock string to elapsed minutes.

    Args:
        period: Quarter number (1-4, 5+ for OT)
        clock_str: Clock string like "PT11M43.00S" or "PT05M30.50S"

    Returns:
        Elapsed minutes from start of game
    """
    try:
        # Parse clock string (format: PT11M43.00S)
        clock_str = str(clock_str).replace('PT', '').replace('S', '')
        parts = clock_str.split('M')
        mins = int(parts[0])
        secs = float(parts[1]) if len(parts) > 1 else 0

        time_remaining = mins + secs / 60

        if period <= 4:
            elapsed = (period - 1) * 12 + (12 - time_remaining)
        else:
            # Overtime - cap at 48 minutes
            elapsed = 48.0

        return round(elapsed, 2)
    except:
        return None


def get_points_from_action(action):
    """
    Determine points scored from a play action.

    Returns:
        Tuple of (player_name, points_scored) or (None, 0)
    """
    action_type = action.get('actionType', '')
    description = action.get('description', '')

    # Check if it's a made shot
    if action_type == 'Made Shot' or (action_type == '2pt' and 'MISS' not in description.upper()):
        player_name = action.get('playerNameI', action.get('playerName', ''))
        if not player_name:
            return None, 0

        # Determine point value
        shot_type = action.get('shotResult', '')
        desc_upper = description.upper()

        if '3PT' in desc_upper or action.get('actionType') == '3pt':
            return player_name, 3
        else:
            return player_name, 2

    # Check for made free throw
    elif action_type == 'Free Throw' and 'MISS' not in description.upper():
        player_name = action.get('playerNameI', action.get('playerName', ''))
        if player_name:
            return player_name, 1

    return None, 0


def is_scoring_action(action):
    """Check if action is a scoring play."""
    action_type = action.get('actionType', '')
    description = action.get('description', '').upper()

    # Made field goal
    if action_type in ['2pt', '3pt', 'Made Shot']:
        if 'MISS' not in description:
            return True

    # Made free throw
    if action_type == 'Free Throw':
        if 'MISS' not in description and 'PTS' in description:
            return True

    return False


def process_cdn_actions(actions, game_id, game_date=None):
    """
    Process CDN play-by-play actions into player points by minute.
    """
    if not actions:
        return pd.DataFrame()

    # Extract scoring plays
    scoring_plays = []

    for action in actions:
        if not is_scoring_action(action):
            continue

        period = action.get('period', 0)
        clock = action.get('clock', '')
        player_name = action.get('playerNameI', action.get('playerName', ''))
        description = action.get('description', '').upper()

        if not player_name:
            continue

        elapsed = parse_clock_to_elapsed(period, clock)
        if elapsed is None:
            continue

        # Determine points
        if '3PT' in description:
            points = 3
        elif 'Free Throw' in action.get('actionType', '') or 'FREE THROW' in description:
            if 'MISS' not in description:
                points = 1
            else:
                continue
        else:
            points = 2

        scoring_plays.append({
            'elapsed_minutes': elapsed,
            'player_name': player_name,
            'points_scored': points
        })

    if not scoring_plays:
        return pd.DataFrame()

    # Convert to DataFrame and sort
    scoring_df = pd.DataFrame(scoring_plays)
    scoring_df = scoring_df.sort_values('elapsed_minutes')

    # Calculate cumulative points by player
    player_results = []

    for player in scoring_df['player_name'].unique():
        player_data = scoring_df[scoring_df['player_name'] == player].copy()
        player_data['cumulative_points'] = player_data['points_scored'].cumsum()

        for minute in range(49):
            points_at_minute = player_data[
                player_data['elapsed_minutes'] <= minute
            ]['cumulative_points'].max()

            if pd.isna(points_at_minute):
                points_at_minute = 0

            player_results.append({
                'game_id': game_id,
                'game_date': game_date,
                'player_name': player,
                'elapsed_minute': minute,
                'cumulative_points': int(points_at_minute)
            })

    return pd.DataFrame(player_results)


def scrape_season(season="2024-25", season_type="Regular Season",
                  save_raw=True, resume_from=0, max_games=None):
    """
    Scrape all play-by-play data for a season.
    """
    print(f"\n{'='*60}")
    print(f"SCRAPING {season} {season_type}")
    print(f"{'='*60}")

    # Get game list
    games = get_season_games(season, season_type)

    if len(games) == 0:
        print("No games found!")
        return pd.DataFrame()

    game_ids = games['GAME_ID'].tolist()
    game_dates = games['GAME_DATE'].tolist()

    total_games = len(game_ids)
    if max_games:
        total_games = min(total_games, max_games)
        game_ids = game_ids[:max_games]
        game_dates = game_dates[:max_games]

    print(f"\nScraping {total_games} games (starting from #{resume_from + 1})...")
    print(f"Estimated time: {(total_games - resume_from) * REQUEST_DELAY / 60:.1f} minutes")
    print()

    all_results = []
    raw_actions = []
    success_count = 0
    error_count = 0

    for i, (game_id, game_date) in enumerate(zip(game_ids, game_dates)):
        if i < resume_from:
            continue

        if (i + 1) % 100 == 0 or i == resume_from:
            print(f"  Processing game {i+1}/{total_games} ({game_id})...")

        # Fetch play-by-play from CDN
        actions = get_play_by_play_cdn(game_id)

        if actions:
            success_count += 1

            if save_raw:
                raw_actions.append({
                    'game_id': game_id,
                    'game_date': game_date,
                    'actions': actions
                })

            game_results = process_cdn_actions(actions, game_id, game_date)
            if len(game_results) > 0:
                all_results.append(game_results)
        else:
            error_count += 1

        time.sleep(REQUEST_DELAY)

        # Checkpoint save every 300 games
        if (i + 1) % 300 == 0 and all_results:
            print(f"    Checkpoint at game {i+1}... (success: {success_count}, errors: {error_count})")
            temp_df = pd.concat(all_results, ignore_index=True)
            checkpoint_path = OUTPUT_PATH / f"checkpoint_{season.replace('-', '_')}_{i+1}.csv"
            temp_df.to_csv(checkpoint_path, index=False)

    # Final results
    print(f"\n  Games fetched successfully: {success_count}")
    print(f"  Games with errors: {error_count}")

    if all_results:
        season_df = pd.concat(all_results, ignore_index=True)
        season_df['season'] = season

        print(f"  Total player-minute records: {len(season_df):,}")
        print(f"  Unique games: {season_df['game_id'].nunique()}")
        print(f"  Unique players: {season_df['player_name'].nunique()}")

        # Save raw data
        if save_raw and raw_actions:
            raw_path = RAW_PATH / f"raw_actions_{season.replace('-', '_')}.json"
            with open(raw_path, 'w') as f:
                json.dump(raw_actions, f)
            print(f"  Saved raw actions: {raw_path}")

        return season_df

    return pd.DataFrame()


def validate_and_show_sample(df):
    """Validate and show sample output."""
    if len(df) == 0:
        return

    print("\nVALIDATION:")
    print("=" * 50)

    # Check monotonic increasing
    def check_monotonic(group):
        return (group['cumulative_points'].diff().fillna(0) >= 0).all()

    monotonic = df.groupby(['game_id', 'player_name']).apply(check_monotonic)
    if monotonic.all():
        print("  All cumulative points are monotonically increasing")
    else:
        print(f"  WARNING: {(~monotonic).sum()} player-games have issues")

    # Stats
    print(f"\n  Total records: {len(df):,}")
    print(f"  Unique games: {df['game_id'].nunique()}")
    print(f"  Unique players: {df['player_name'].nunique()}")

    avg_pts = df.groupby(['game_id', 'player_name'])['cumulative_points'].max().mean()
    print(f"  Avg points per player per game: {avg_pts:.1f}")

    # Sample output
    print("\nSAMPLE OUTPUT:")
    print("=" * 50)

    # Find a high scorer
    max_pts = df.groupby(['game_id', 'player_name'])['cumulative_points'].max()
    top_game = max_pts.idxmax()
    player = top_game[1]

    sample = df[(df['game_id'] == top_game[0]) & (df['player_name'] == player)]
    print(f"\nPlayer: {player}")
    print(f"Game: {top_game[0]}")
    print(f"Final points: {sample['cumulative_points'].max()}")
    print("\nPoints by Quarter:")
    for min_mark, label in [(12, 'Q1'), (24, 'Half'), (36, 'Q3'), (48, 'Final')]:
        pts = sample[sample['elapsed_minute'] == min_mark]['cumulative_points'].iloc[0]
        print(f"  {label} (min {min_mark}): {pts}")


def update_combined_database(new_df):
    """Update the combined database with new season data."""
    existing_path = OUTPUT_PATH / "nba_player_points_by_minute_2021_2024.csv"

    if existing_path.exists():
        print(f"\nUpdating combined database...")
        existing_df = pd.read_csv(existing_path)

        # Remove overlapping season if exists
        new_season = new_df['season'].iloc[0]
        existing_df = existing_df[existing_df.get('season', 'unknown') != new_season]

        combined = pd.concat([existing_df, new_df], ignore_index=True)

        # Save updated
        new_combined_path = OUTPUT_PATH / "nba_player_points_by_minute_2021_2025.csv"
        combined.to_csv(new_combined_path, index=False)
        print(f"  Saved: {new_combined_path}")
        print(f"  Total records: {len(combined):,}")

        return combined
    else:
        return new_df


def main():
    """Main scraping function."""
    print("=" * 60)
    print("NBA PLAY-BY-PLAY SCRAPER (CDN Method)")
    print("=" * 60)
    print(f"Start time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # Scrape 2024-25 season
    season_df = scrape_season(
        season="2024-25",
        season_type="Regular Season",
        save_raw=True,
        resume_from=0,
        max_games=None  # Set to a number for testing
    )

    if len(season_df) > 0:
        # Validate and show sample
        validate_and_show_sample(season_df)

        # Save season file
        output_path = OUTPUT_PATH / "player_points_by_minute_2025.csv"
        season_df.to_csv(output_path, index=False)
        print(f"\nSaved: {output_path}")

        # Update combined database
        update_combined_database(season_df)

    print(f"\nEnd time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    print("COMPLETE!")
    print("=" * 60)


if __name__ == "__main__":
    main()
