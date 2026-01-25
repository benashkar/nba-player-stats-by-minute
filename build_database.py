"""
NBA Player Points by Minute Database Builder

This script processes NBA play-by-play data to create a database showing
how many points each player scored at each minute of every game.
"""

import pandas as pd
import numpy as np
from pathlib import Path
import sqlite3


# Configuration
BASE_PATH = Path(r"C:/Users/cashk/OneDrive/Projects/NBAPlayer Points")
RAW_PATH = BASE_PATH / "raw"
OUTPUT_PATH = BASE_PATH / "output"

# Ensure output directory exists
OUTPUT_PATH.mkdir(parents=True, exist_ok=True)


def calc_elapsed_minutes(period, pctimestring):
    """
    Convert PERIOD and PCTIMESTRING to elapsed game minutes.

    Args:
        period (int): Quarter number (1-4 for regulation, 5+ for OT)
        pctimestring (str): Time remaining in quarter (e.g., "11:47")

    Returns:
        float: Total elapsed minutes from start of game

    Examples:
        calc_elapsed_minutes(1, "12:00") -> 0.0 (start of game)
        calc_elapsed_minutes(1, "0:00") -> 12.0 (end of Q1)
        calc_elapsed_minutes(4, "0:00") -> 48.0 (end of regulation)
    """
    try:
        if pd.isna(pctimestring):
            return None
        mins, secs = map(int, str(pctimestring).split(':'))
        time_remaining = mins + secs / 60

        # Calculate elapsed time
        if period <= 4:
            # Regular quarters (12 minutes each)
            elapsed = (period - 1) * 12 + (12 - time_remaining)
        else:
            # Overtime - cap at 48 minutes
            elapsed = 48.0

        return round(elapsed, 2)
    except:
        return None


def get_points_scored(row):
    """
    Determine how many points were scored on this play.

    Event Types:
        EVENTMSGTYPE = 1: Made field goal (2PT or 3PT)
        EVENTMSGTYPE = 3: Made free throw (1PT)
    """
    event_type = row['EVENTMSGTYPE']

    # Not a scoring event
    if event_type not in [1, 3]:
        return 0

    # Made free throw
    if event_type == 3:
        return 1

    # Made field goal - check if 3PT or 2PT
    home_desc = str(row.get('HOMEDESCRIPTION', '') or '')
    visitor_desc = str(row.get('VISITORDESCRIPTION', '') or '')
    description = home_desc + visitor_desc

    if '3PT' in description.upper():
        return 3
    else:
        return 2


def process_game(game_df):
    """
    Process a single game's play-by-play data into player points by minute.

    Args:
        game_df: DataFrame filtered to one GAME_ID

    Returns:
        DataFrame with columns: game_id, player_name, elapsed_minute, cumulative_points
    """
    game_id = game_df['GAME_ID'].iloc[0]

    # Filter to scoring events only (made shots and free throws)
    scoring = game_df[game_df['EVENTMSGTYPE'].isin([1, 3])].copy()

    if len(scoring) == 0:
        return pd.DataFrame()

    # Add helper columns
    scoring['elapsed_minutes'] = scoring.apply(
        lambda row: calc_elapsed_minutes(row['PERIOD'], row['PCTIMESTRING']),
        axis=1
    )
    scoring['points_scored'] = scoring.apply(get_points_scored, axis=1)

    # Remove invalid rows
    scoring = scoring[scoring['elapsed_minutes'].notna()]
    scoring = scoring[scoring['PLAYER1_NAME'].notna()]

    if len(scoring) == 0:
        return pd.DataFrame()

    # Sort by time
    scoring = scoring.sort_values('elapsed_minutes')

    # Calculate cumulative points by player
    player_results = []

    for player in scoring['PLAYER1_NAME'].unique():
        player_data = scoring[scoring['PLAYER1_NAME'] == player].copy()
        player_data['cumulative_points'] = player_data['points_scored'].cumsum()

        # Create minute-by-minute breakdown (0-48)
        for minute in range(49):  # 0 through 48
            # Find cumulative points at this minute
            points_at_minute = player_data[
                player_data['elapsed_minutes'] <= minute
            ]['cumulative_points'].max()

            if pd.isna(points_at_minute):
                points_at_minute = 0

            player_results.append({
                'game_id': game_id,
                'player_name': player,
                'elapsed_minute': minute,
                'cumulative_points': int(points_at_minute)
            })

    return pd.DataFrame(player_results)


def process_season(season_year, progress_interval=100):
    """
    Process all games in a season.

    Args:
        season_year (int): Season year (e.g., 2024 for 2023-24 season)
        progress_interval (int): How often to print progress

    Returns:
        DataFrame with all player-minutes for the season
    """
    print(f"\nProcessing season {season_year}...")

    # Load season data
    file_path = RAW_PATH / f"nbastats_{season_year}.csv"
    df = pd.read_csv(file_path)

    print(f"  Loaded {len(df):,} rows")
    print(f"  Games: {df['GAME_ID'].nunique()}")

    # Process each game
    all_results = []
    game_ids = df['GAME_ID'].unique()

    for i, game_id in enumerate(game_ids):
        if i % progress_interval == 0:
            print(f"  Processing game {i+1}/{len(game_ids)}...")

        game_df = df[df['GAME_ID'] == game_id]
        game_results = process_game(game_df)
        if len(game_results) > 0:
            all_results.append(game_results)

    # Combine all games
    if all_results:
        season_df = pd.concat(all_results, ignore_index=True)
        print(f"  Completed: {len(season_df):,} player-minute records")
        return season_df
    else:
        print(f"  Warning: No data processed for season {season_year}")
        return pd.DataFrame()


def build_full_database(seasons=None):
    """
    Process all seasons and combine into single database.

    Args:
        seasons: List of season years to process (default: 2021-2024)
    """
    if seasons is None:
        seasons = [2021, 2022, 2023, 2024]

    all_seasons = []

    for year in seasons:
        file_path = RAW_PATH / f"nbastats_{year}.csv"
        if not file_path.exists():
            print(f"  Skipping {year}: file not found")
            continue

        season_df = process_season(year)
        if len(season_df) > 0:
            season_df['season'] = year
            all_seasons.append(season_df)

            # Save individual season
            output_path = OUTPUT_PATH / f"player_points_by_minute_{year}.csv"
            season_df.to_csv(output_path, index=False)
            print(f"  Saved: {output_path}")

    # Combine all seasons
    if all_seasons:
        full_db = pd.concat(all_seasons, ignore_index=True)

        print(f"\nTotal database:")
        print(f"  Total rows: {len(full_db):,}")
        print(f"  Unique players: {full_db['player_name'].nunique()}")
        print(f"  Unique games: {full_db['game_id'].nunique()}")

        return full_db
    else:
        print("Warning: No data was processed")
        return pd.DataFrame()


def validate_database(df):
    """
    Run quality checks on the output database.
    """
    print("\nVALIDATION CHECKS:")
    print("=" * 50)

    if len(df) == 0:
        print("ERROR: Database is empty!")
        return False

    # Check 1: All games have 49 minutes (0-48)
    minutes_per_game_player = df.groupby(['game_id', 'player_name'])['elapsed_minute'].nunique()
    incomplete = (minutes_per_game_player != 49).sum()
    if incomplete > 0:
        print(f"  WARNING: {incomplete} player-games don't have all 49 minutes")
    else:
        print("  All player-games have complete 49-minute records")

    # Check 2: Points are monotonically increasing
    def check_monotonic(group):
        return (group['cumulative_points'].diff().fillna(0) >= 0).all()

    monotonic_check = df.groupby(['game_id', 'player_name']).apply(check_monotonic)
    non_monotonic = (~monotonic_check).sum()
    if non_monotonic > 0:
        print(f"  WARNING: {non_monotonic} players have decreasing cumulative points")
    else:
        print("  All cumulative points are monotonically increasing")

    # Check 3: No null values
    null_counts = df.isnull().sum()
    total_nulls = null_counts.sum()
    if total_nulls > 0:
        print(f"  WARNING: {total_nulls} null values found")
    else:
        print("  No null values")

    # Check 4: Reasonable point totals (0-100 range)
    max_points = df.groupby(['game_id', 'player_name'])['cumulative_points'].max()
    high_scorers = (max_points > 100).sum()
    if high_scorers > 0:
        print(f"  WARNING: {high_scorers} players scored >100 points in a game")
    else:
        print("  All point totals are reasonable (<100)")

    # Summary statistics
    print("\nSUMMARY STATISTICS:")
    print(f"  Total records: {len(df):,}")
    print(f"  Unique games: {df['game_id'].nunique():,}")
    print(f"  Unique players: {df['player_name'].nunique():,}")
    avg_pts = df.groupby(['game_id', 'player_name'])['cumulative_points'].max().mean()
    print(f"  Average points per player per game: {avg_pts:.1f}")

    return True


def show_sample_output(df, player_name="LeBron James", n_games=3):
    """
    Display sample output for a specific player.
    """
    player_data = df[df['player_name'] == player_name]

    if len(player_data) == 0:
        # Try to find a similar player
        similar = df[df['player_name'].str.contains('LeBron', case=False, na=False)]
        if len(similar) > 0:
            player_name = similar['player_name'].iloc[0]
            player_data = df[df['player_name'] == player_name]
        else:
            # Use any player with high scoring
            top_scorers = df.groupby('player_name')['cumulative_points'].max().nlargest(1)
            if len(top_scorers) > 0:
                player_name = top_scorers.index[0]
                player_data = df[df['player_name'] == player_name]

    if len(player_data) == 0:
        print(f"No data found for sample output")
        return

    # Get sample games
    sample_games = player_data['game_id'].unique()[:n_games]

    print(f"\nSAMPLE OUTPUT FOR: {player_name}")
    print("=" * 50)

    for game_id in sample_games:
        game_data = player_data[player_data['game_id'] == game_id]

        print(f"\nGame: {game_id}")
        final_pts = game_data['cumulative_points'].max()
        print(f"Final points: {final_pts}")
        print("Points by Quarter:")

        for minute, label in [(12, "End Q1"), (24, "Halftime"), (36, "End Q3"), (48, "Final")]:
            pts = game_data[game_data['elapsed_minute'] == minute]['cumulative_points'].values
            if len(pts) > 0:
                print(f"  {label} (min {minute}): {pts[0]}")


def save_database(df):
    """
    Save the database in multiple formats.
    """
    # CSV - Long format
    csv_path = OUTPUT_PATH / "nba_player_points_by_minute_2021_2024.csv"
    df.to_csv(csv_path, index=False)
    print(f"\nSaved CSV: {csv_path}")

    # SQLite
    db_path = OUTPUT_PATH / "nba_player_points.db"
    conn = sqlite3.connect(db_path)
    df.to_sql('player_points_by_minute', conn, if_exists='replace', index=False)

    # Create indexes for faster queries
    conn.execute('CREATE INDEX IF NOT EXISTS idx_game ON player_points_by_minute(game_id)')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_player ON player_points_by_minute(player_name)')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_game_player ON player_points_by_minute(game_id, player_name)')
    conn.close()
    print(f"Saved SQLite: {db_path}")

    return csv_path, db_path


def main():
    """
    Complete workflow to build NBA player points-by-minute database.
    """
    print("=" * 60)
    print("NBA PLAYER POINTS BY MINUTE DATABASE")
    print("=" * 60)

    # Phase 1: Check data files
    print("\nPHASE 1: Data Verification")
    available_seasons = []
    for year in [2021, 2022, 2023, 2024, 2025]:
        file_path = RAW_PATH / f"nbastats_{year}.csv"
        if file_path.exists():
            size_mb = file_path.stat().st_size / (1024 * 1024)
            print(f"  Found: nbastats_{year}.csv ({size_mb:.1f} MB)")
            available_seasons.append(year)
        else:
            print(f"  Missing: nbastats_{year}.csv")

    if not available_seasons:
        print("ERROR: No data files found!")
        return

    # Phase 2 & 3: Process and build database
    print("\nPHASE 2 & 3: Processing and Database Creation")
    full_db = build_full_database(available_seasons)

    if len(full_db) == 0:
        print("ERROR: No data was processed!")
        return

    # Phase 4: Validation
    print("\nPHASE 4: Validation")
    validate_database(full_db)

    # Show sample
    show_sample_output(full_db)

    # Final save
    print("\nFINAL OUTPUT:")
    csv_path, db_path = save_database(full_db)

    file_size_mb = csv_path.stat().st_size / (1024 * 1024)
    print(f"\nFile size: {file_size_mb:.1f} MB")

    print("\n" + "=" * 60)
    print("COMPLETE!")
    print("=" * 60)


if __name__ == "__main__":
    main()
