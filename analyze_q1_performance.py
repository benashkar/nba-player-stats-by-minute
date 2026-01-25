#!/usr/bin/env python3
"""
Q1 Performance Analysis - Predict Final Game Totals

Analyzes player performance based on Q1 (first 12 minutes) scoring to predict
final game totals. Calculates mean, median, standard deviation, and percentiles.

Usage:
    python analyze_q1_performance.py --player "A. Edwards" --q1_max 4
    python analyze_q1_performance.py --player "A. Edwards" --q1_max 4 --season 2025-26
    python analyze_q1_performance.py --player "A. Edwards" --q1_max 4 --seasons 2024-25 2025-26
    python analyze_q1_performance.py --player "A. Edwards" --q1_min 0 --q1_max 4
    python analyze_q1_performance.py --list-players  # Show all players
"""

import pandas as pd
import numpy as np
import sqlite3
import argparse
from pathlib import Path

# Configuration
BASE_PATH = Path(r"C:/Users/cashk/OneDrive/Projects/NBAPlayer Points")
SQLITE_DB = BASE_PATH / "output" / "nba_player_stats.db"

# Default seasons for analysis
RECENT_SEASONS = ['2024-25', '2025-26']


def load_data(seasons: list = None) -> pd.DataFrame:
    """Load data from SQLite, optionally filtered by seasons."""
    conn = sqlite3.connect(SQLITE_DB)

    if seasons:
        placeholders = ','.join(['?' for _ in seasons])
        query = f"SELECT * FROM player_stats_by_minute WHERE season IN ({placeholders})"
        df = pd.read_sql(query, conn, params=seasons)
    else:
        df = pd.read_sql("SELECT * FROM player_stats_by_minute", conn)

    conn.close()
    return df


def get_q1_vs_final(df: pd.DataFrame, minute: int = 12) -> pd.DataFrame:
    """
    Create dataset joining Q1 stats (at specified minute) with final game totals.

    Returns DataFrame with:
    - q1_pts: Points at end of Q1 (minute 12)
    - final_pts: Final game points
    - Plus all other stats
    """
    # Get Q1 stats (at minute 12)
    q1_stats = df[df['elapsed_minute'] == minute].copy()
    q1_stats = q1_stats.rename(columns={
        'cumulative_points': 'q1_pts',
        'cumulative_rebounds': 'q1_reb',
        'cumulative_assists': 'q1_ast',
        'cumulative_minutes_played': 'q1_min'
    })

    # Get final game stats (max minute per player per game)
    idx = df.groupby(['game_id', 'player_name'])['elapsed_minute'].idxmax()
    final_stats = df.loc[idx].copy()
    final_stats = final_stats.rename(columns={
        'cumulative_points': 'final_pts',
        'cumulative_rebounds': 'final_reb',
        'cumulative_assists': 'final_ast',
        'cumulative_minutes_played': 'final_min'
    })

    # Merge Q1 and final stats
    merged = q1_stats.merge(
        final_stats[['game_id', 'player_name', 'final_pts', 'final_reb', 'final_ast', 'final_min']],
        on=['game_id', 'player_name'],
        how='inner'
    )

    return merged


def calculate_percentile_thresholds(values: np.ndarray) -> dict:
    """
    Calculate the top X% outcome thresholds.

    Top 10% = 90th percentile (best 10% of games scored at least this)
    Top 25% = 75th percentile (best 25% of games scored at least this)
    Top 33% = 67th percentile (best 33% of games scored at least this)
    Top 40% = 60th percentile (best 40% of games scored at least this)
    Top 50% = 50th percentile (median)
    """
    if len(values) == 0:
        return {}

    return {
        'top_10_pct': np.percentile(values, 90),   # Top 10% of games score at least this
        'top_25_pct': np.percentile(values, 75),   # Top 25% of games score at least this
        'top_33_pct': np.percentile(values, 67),   # Top 33% of games score at least this
        'top_40_pct': np.percentile(values, 60),   # Top 40% of games score at least this
        'top_50_pct': np.percentile(values, 50),   # Median (top 50%)
        'median': np.median(values),               # Pure median
    }


def calculate_stats(values: np.ndarray) -> dict:
    """Calculate comprehensive statistics for a set of values."""
    if len(values) == 0:
        return {}

    mean = np.mean(values)
    median = np.median(values)
    std = np.std(values, ddof=1)  # Sample standard deviation

    # Standard deviation as percentage of mean
    std_pct = (std / mean * 100) if mean > 0 else 0

    # Confidence intervals (assuming normal distribution)
    # 1 std = 68%, 1.5 std = 87%, 2 std = 95%
    ci_68_low = mean - std
    ci_68_high = mean + std
    ci_95_low = mean - 2 * std
    ci_95_high = mean + 2 * std

    return {
        'count': len(values),
        'mean': round(mean, 2),
        'median': round(median, 2),
        'std': round(std, 2),
        'std_pct': round(std_pct, 1),
        'min': int(np.min(values)),
        'max': int(np.max(values)),
        'ci_68': (round(ci_68_low, 1), round(ci_68_high, 1)),
        'ci_95': (round(ci_95_low, 1), round(ci_95_high, 1)),
    }


def analyze_player_q1(df: pd.DataFrame, player_name: str,
                      q1_min: int = None, q1_max: int = None,
                      stat: str = 'pts') -> dict:
    """
    Analyze a player's final game totals based on Q1 performance.

    Args:
        df: DataFrame with q1_pts and final_pts columns
        player_name: Player to analyze (e.g., 'A. Edwards')
        q1_min: Minimum Q1 points (inclusive), None for no minimum
        q1_max: Maximum Q1 points (inclusive), None for no maximum
        stat: Stat to analyze ('pts', 'reb', 'ast')

    Returns:
        Dictionary with statistical analysis
    """
    q1_col = f'q1_{stat}'
    final_col = f'final_{stat}'

    # Filter to player
    player_df = df[df['player_name'] == player_name].copy()

    if len(player_df) == 0:
        return {'error': f'Player "{player_name}" not found'}

    # Apply Q1 filters
    if q1_min is not None:
        player_df = player_df[player_df[q1_col] >= q1_min]
    if q1_max is not None:
        player_df = player_df[player_df[q1_col] <= q1_max]

    if len(player_df) == 0:
        return {'error': 'No games match the Q1 criteria'}

    final_values = player_df[final_col].values

    # Calculate statistics
    basic_stats = calculate_stats(final_values)
    percentiles = calculate_percentile_thresholds(final_values)

    # Get game details
    games = player_df[['game_date', 'season', q1_col, final_col]].sort_values('game_date')

    return {
        'player': player_name,
        'q1_filter': f'{q1_min if q1_min else 0}-{q1_max if q1_max else "any"} {stat}',
        'seasons': player_df['season'].unique().tolist(),
        'statistics': basic_stats,
        'percentile_thresholds': percentiles,
        'games': games.to_dict('records')
    }


def print_analysis(result: dict, show_games: bool = False):
    """Pretty print the analysis results."""
    if 'error' in result:
        print(f"Error: {result['error']}")
        return

    print("\n" + "="*70)
    print(f"PLAYER: {result['player']}")
    print(f"Q1 FILTER: {result['q1_filter']} points after 12 minutes")
    print(f"SEASONS: {', '.join(result['seasons'])}")
    print("="*70)

    stats = result['statistics']
    pcts = result['percentile_thresholds']
    n_games = stats['count']

    print(f"\nSAMPLE SIZE: {n_games} games")
    print(f"\nFINAL POINTS DISTRIBUTION:")
    print(f"  Mean:   {stats['mean']} pts")
    print(f"  Median: {stats['median']} pts")
    print(f"  Std Dev: {stats['std']} pts ({stats['std_pct']}% of mean)")
    print(f"  Range:  {stats['min']} - {stats['max']} pts")

    print(f"\nCONFIDENCE INTERVALS:")
    print(f"  68% of games: {stats['ci_68'][0]} - {stats['ci_68'][1]} pts")
    print(f"  95% of games: {stats['ci_95'][0]} - {stats['ci_95'][1]} pts")

    print(f"\nTOP OUTCOME THRESHOLDS ({n_games} games in sample):")
    print(f"  +-------------+------------+-----------------------------+")
    print(f"  | Percentile  | Min Points | Interpretation              |")
    print(f"  +-------------+------------+-----------------------------+")
    print(f"  | Top 10%     | >= {pcts['top_10_pct']:5.1f}   | Best {max(1, int(n_games * 0.10)):2} game(s)              |")
    print(f"  | Top 25%     | >= {pcts['top_25_pct']:5.1f}   | Best {max(1, int(n_games * 0.25)):2} game(s)              |")
    print(f"  | Top 33%     | >= {pcts['top_33_pct']:5.1f}   | Best {max(1, int(n_games * 0.33)):2} game(s)              |")
    print(f"  | Top 40%     | >= {pcts['top_40_pct']:5.1f}   | Best {max(1, int(n_games * 0.40)):2} game(s)              |")
    print(f"  | Top 50%     | >= {pcts['top_50_pct']:5.1f}   | Best {max(1, int(n_games * 0.50)):2} game(s) (median)     |")
    print(f"  +-------------+------------+-----------------------------+")
    print(f"\n  Pure Median: {pcts['median']:.1f} pts (middle value of {n_games} games)")

    if show_games:
        print(f"\nGAME-BY-GAME BREAKDOWN ({n_games} games):")
        print("-"*50)
        for game in result['games']:
            print(f"  {game['game_date']} ({game['season']}): Q1={game['q1_pts']} -> Final={game['final_pts']}")


def list_players(df: pd.DataFrame, seasons: list = None):
    """List all players with game counts."""
    if seasons:
        df = df[df['season'].isin(seasons)]

    # Get unique players with game counts
    player_games = df.groupby('player_name')['game_id'].nunique().reset_index()
    player_games.columns = ['player_name', 'games']
    player_games = player_games.sort_values('games', ascending=False)

    print(f"\nPlayers with games in {seasons if seasons else 'all seasons'}:")
    print("-"*40)
    for _, row in player_games.head(50).iterrows():
        print(f"  {row['player_name']}: {row['games']} games")


def analyze_all_q1_ranges(df: pd.DataFrame, player_name: str,
                          ranges: list = None) -> pd.DataFrame:
    """
    Analyze player across multiple Q1 point ranges.

    Returns a summary DataFrame comparing outcomes for different Q1 performances.
    """
    if ranges is None:
        ranges = [
            (0, 2),   # Very slow start
            (3, 4),   # Slow start
            (5, 7),   # Below average
            (8, 10),  # Average
            (11, 14), # Good start
            (15, None), # Hot start
        ]

    results = []
    for q1_min, q1_max in ranges:
        analysis = analyze_player_q1(df, player_name, q1_min, q1_max)
        if 'error' not in analysis:
            stats = analysis['statistics']
            pcts = analysis['percentile_thresholds']
            results.append({
                'Q1 Range': f"{q1_min}-{q1_max if q1_max else '+'}",
                'Games': stats['count'],
                'Mean': stats['mean'],
                'Median': stats['median'],
                'Std Dev': stats['std'],
                'Min': stats['min'],
                'Max': stats['max'],
                'Top 75%': round(pcts.get('top_75_pct', 0), 1),
                'Top 66%': round(pcts.get('top_66_pct', 0), 1),
            })

    return pd.DataFrame(results)


def main():
    parser = argparse.ArgumentParser(description='Q1 Performance Analysis')
    parser.add_argument('--player', type=str, help='Player name (e.g., "A. Edwards")')
    parser.add_argument('--q1_min', type=int, default=None, help='Minimum Q1 points')
    parser.add_argument('--q1_max', type=int, default=None, help='Maximum Q1 points')
    parser.add_argument('--season', type=str, help='Single season (e.g., "2024-25")')
    parser.add_argument('--seasons', nargs='+', help='Multiple seasons')
    parser.add_argument('--current', action='store_true', help='Current season only (2025-26)')
    parser.add_argument('--recent', action='store_true', help='Recent seasons (2024-25, 2025-26)')
    parser.add_argument('--show-games', action='store_true', help='Show individual games')
    parser.add_argument('--all-ranges', action='store_true', help='Analyze all Q1 ranges')
    parser.add_argument('--list-players', action='store_true', help='List all players')
    parser.add_argument('--minute', type=int, default=12, help='Minute to use for Q1 (default: 12)')

    args = parser.parse_args()

    # Determine seasons
    if args.current:
        seasons = ['2025-26']
    elif args.recent:
        seasons = RECENT_SEASONS
    elif args.season:
        seasons = [args.season]
    elif args.seasons:
        seasons = args.seasons
    else:
        seasons = RECENT_SEASONS  # Default to recent

    print(f"Loading data for seasons: {seasons}")
    df = load_data(seasons)
    print(f"Loaded {len(df):,} rows")

    # Get Q1 vs Final dataset
    q1_final = get_q1_vs_final(df, minute=args.minute)
    print(f"Created Q1 vs Final dataset: {len(q1_final):,} player-games")

    if args.list_players:
        list_players(df, seasons)
        return

    if not args.player:
        print("\nNo player specified. Use --player 'Name' or --list-players")
        print("Example: python analyze_q1_performance.py --player 'A. Edwards' --q1_max 4")
        return

    if args.all_ranges:
        print(f"\n{'='*70}")
        print(f"Q1 RANGE ANALYSIS FOR: {args.player}")
        print(f"{'='*70}")
        summary = analyze_all_q1_ranges(q1_final, args.player)
        print(summary.to_string(index=False))
    else:
        result = analyze_player_q1(q1_final, args.player, args.q1_min, args.q1_max)
        print_analysis(result, args.show_games)


if __name__ == "__main__":
    main()
