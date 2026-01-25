"""
NBA Player Points Analysis by Minute

This script provides analysis functions to answer questions like:
- "How many points does each player average after 6 game minutes?"
- "Which players score the fastest?"
- "What's the scoring distribution by quarter?"
"""

import pandas as pd
import numpy as np
from pathlib import Path

# Configuration
BASE_PATH = Path(r"C:/Users/cashk/OneDrive/Projects/NBAPlayer Points")
OUTPUT_PATH = BASE_PATH / "output"


def load_database(file_name=None):
    """Load the player points by minute database."""
    if file_name:
        path = OUTPUT_PATH / file_name
    else:
        # Try to find the most complete database
        candidates = [
            "nba_player_points_by_minute_2021_2025.csv",
            "nba_player_points_by_minute_2021_2024.csv",
            "player_points_by_minute_2025.csv"
        ]
        for candidate in candidates:
            path = OUTPUT_PATH / candidate
            if path.exists():
                break

    print(f"Loading: {path}")
    df = pd.read_csv(path)
    print(f"  Records: {len(df):,}")
    print(f"  Games: {df['game_id'].nunique():,}")
    print(f"  Players: {df['player_name'].nunique()}")
    return df


def average_points_at_minute(df, minute=6, min_games=10):
    """
    Calculate average points each player has scored at a specific game minute.

    Args:
        df: Database DataFrame
        minute: Game minute to analyze (0-48)
        min_games: Minimum games required to include player

    Returns:
        DataFrame with player averages at that minute
    """
    # Filter to the specific minute
    at_minute = df[df['elapsed_minute'] == minute].copy()

    # Calculate averages
    player_stats = at_minute.groupby('player_name').agg({
        'cumulative_points': ['mean', 'std', 'min', 'max', 'count']
    }).round(2)

    player_stats.columns = ['avg_points', 'std_points', 'min_points', 'max_points', 'games']
    player_stats = player_stats.reset_index()

    # Filter by minimum games
    player_stats = player_stats[player_stats['games'] >= min_games]

    # Sort by average
    player_stats = player_stats.sort_values('avg_points', ascending=False)

    return player_stats


def scoring_pace_by_minute(df, player_name):
    """
    Get a player's average scoring pace at each minute.

    Args:
        df: Database DataFrame
        player_name: Player name to analyze

    Returns:
        DataFrame with minute-by-minute averages
    """
    player_data = df[df['player_name'] == player_name]

    if len(player_data) == 0:
        # Try partial match
        matches = df[df['player_name'].str.contains(player_name, case=False, na=False)]
        if len(matches) > 0:
            player_name = matches['player_name'].iloc[0]
            player_data = df[df['player_name'] == player_name]
            print(f"Using: {player_name}")
        else:
            print(f"Player not found: {player_name}")
            return pd.DataFrame()

    pace = player_data.groupby('elapsed_minute')['cumulative_points'].agg(['mean', 'std', 'count']).round(2)
    pace.columns = ['avg_points', 'std_points', 'games']
    pace = pace.reset_index()

    return pace


def fastest_to_points(df, target_points=20, min_games=10):
    """
    Find which players reach a target point total fastest.

    Args:
        df: Database DataFrame
        target_points: Point threshold to analyze
        min_games: Minimum games where player hit the target

    Returns:
        DataFrame with average minutes to reach target
    """
    # Find first minute each player hit target in each game
    hit_target = df[df['cumulative_points'] >= target_points].copy()

    if len(hit_target) == 0:
        print(f"No instances of players scoring {target_points}+ points")
        return pd.DataFrame()

    first_hit = hit_target.groupby(['game_id', 'player_name'])['elapsed_minute'].min().reset_index()
    first_hit.columns = ['game_id', 'player_name', 'minutes_to_target']

    # Calculate player averages
    player_avg = first_hit.groupby('player_name').agg({
        'minutes_to_target': ['mean', 'std', 'count']
    }).round(2)

    player_avg.columns = ['avg_minutes', 'std_minutes', 'games_hit']
    player_avg = player_avg.reset_index()

    # Filter by minimum games
    player_avg = player_avg[player_avg['games_hit'] >= min_games]

    # Sort by fastest
    player_avg = player_avg.sort_values('avg_minutes')

    return player_avg


def points_by_quarter(df, min_games=20):
    """
    Analyze how many points players score in each quarter.

    Returns:
        DataFrame with quarter-by-quarter scoring averages
    """
    results = []

    for player in df['player_name'].unique():
        player_data = df[df['player_name'] == player]
        games = player_data['game_id'].nunique()

        if games < min_games:
            continue

        # Get points at quarter boundaries
        q1 = player_data[player_data['elapsed_minute'] == 12]['cumulative_points'].mean()
        q2 = player_data[player_data['elapsed_minute'] == 24]['cumulative_points'].mean() - q1
        q3 = player_data[player_data['elapsed_minute'] == 36]['cumulative_points'].mean() - q1 - q2
        q4 = player_data[player_data['elapsed_minute'] == 48]['cumulative_points'].mean() - q1 - q2 - q3

        results.append({
            'player_name': player,
            'games': games,
            'q1_avg': round(q1, 1),
            'q2_avg': round(q2, 1),
            'q3_avg': round(q3, 1),
            'q4_avg': round(q4, 1),
            'total_avg': round(q1 + q2 + q3 + q4, 1)
        })

    return pd.DataFrame(results).sort_values('total_avg', ascending=False)


def compare_players_at_minute(df, players, minute=6):
    """
    Compare specific players' scoring at a given minute.
    """
    results = []

    for player in players:
        player_data = df[(df['player_name'] == player) & (df['elapsed_minute'] == minute)]

        if len(player_data) == 0:
            # Try partial match
            matches = df[df['player_name'].str.contains(player, case=False, na=False)]
            if len(matches) > 0:
                player = matches['player_name'].iloc[0]
                player_data = df[(df['player_name'] == player) & (df['elapsed_minute'] == minute)]

        if len(player_data) > 0:
            results.append({
                'player': player,
                'avg_points': round(player_data['cumulative_points'].mean(), 2),
                'std': round(player_data['cumulative_points'].std(), 2),
                'games': len(player_data)
            })

    return pd.DataFrame(results)


def main():
    """Run example analyses."""
    print("="*60)
    print("NBA PLAYER POINTS BY MINUTE ANALYSIS")
    print("="*60)

    # Load data
    df = load_database()

    # Analysis 1: Average points at minute 6
    print("\n" + "="*60)
    print("AVERAGE POINTS AFTER 6 MINUTES (Top 20 players)")
    print("="*60)

    avg_at_6 = average_points_at_minute(df, minute=6, min_games=20)
    print(avg_at_6.head(20).to_string(index=False))

    # Analysis 2: Fastest to 20 points
    print("\n" + "="*60)
    print("FASTEST TO 20 POINTS (Top 20 players)")
    print("="*60)

    fastest = fastest_to_points(df, target_points=20, min_games=10)
    print(fastest.head(20).to_string(index=False))

    # Analysis 3: Points by quarter
    print("\n" + "="*60)
    print("POINTS BY QUARTER (Top 20 scorers)")
    print("="*60)

    by_quarter = points_by_quarter(df, min_games=30)
    print(by_quarter.head(20).to_string(index=False))

    # Analysis 4: Compare specific players at different minutes
    print("\n" + "="*60)
    print("STAR PLAYERS SCORING PROGRESSION")
    print("="*60)

    stars = ['LeBron James', 'Stephen Curry', 'Kevin Durant', 'Giannis Antetokounmpo', 'Luka Doncic']

    for minute in [6, 12, 24, 36, 48]:
        print(f"\nAt minute {minute}:")
        comparison = compare_players_at_minute(df, stars, minute)
        if len(comparison) > 0:
            print(comparison.to_string(index=False))

    # Save analysis results
    print("\n" + "="*60)
    print("SAVING ANALYSIS RESULTS")
    print("="*60)

    avg_at_6.to_csv(OUTPUT_PATH / "analysis_avg_points_at_6min.csv", index=False)
    print(f"  Saved: analysis_avg_points_at_6min.csv")

    fastest.to_csv(OUTPUT_PATH / "analysis_fastest_to_20pts.csv", index=False)
    print(f"  Saved: analysis_fastest_to_20pts.csv")

    by_quarter.to_csv(OUTPUT_PATH / "analysis_points_by_quarter.csv", index=False)
    print(f"  Saved: analysis_points_by_quarter.csv")


if __name__ == "__main__":
    main()
