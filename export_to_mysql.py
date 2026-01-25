#!/usr/bin/env python3
"""
Export SQLite data to MySQL format.

Creates CSV files optimized for MySQL LOAD DATA INFILE,
or connects directly to MySQL for import.

Usage:
    python export_to_mysql.py --csv           # Export to CSV files
    python export_to_mysql.py --direct        # Direct MySQL import
    python export_to_mysql.py --direct --host localhost --user root --password xxx --database nba_stats
"""

import pandas as pd
import sqlite3
import argparse
from pathlib import Path
from datetime import datetime

# Configuration
BASE_PATH = Path(r"C:/Users/cashk/OneDrive/Projects/NBAPlayer Points")
SQLITE_DB = BASE_PATH / "output" / "nba_player_stats.db"
OUTPUT_PATH = BASE_PATH / "mysql_export"


def get_season_year(season: str) -> int:
    """Convert season string to year (e.g., '2021-22' -> 2021)."""
    return int(season.split('-')[0])


def export_to_csv():
    """Export data to CSV files for MySQL LOAD DATA INFILE."""
    OUTPUT_PATH.mkdir(exist_ok=True)

    print("Connecting to SQLite database...")
    conn = sqlite3.connect(SQLITE_DB)

    # Load all data
    print("Loading data from SQLite...")
    df = pd.read_sql("SELECT * FROM player_stats_by_minute", conn)
    print(f"  Loaded {len(df):,} rows")

    # Create players lookup table
    print("\nCreating players table...")
    players = df['player_name'].unique()
    players_df = pd.DataFrame({
        'player_id': range(1, len(players) + 1),
        'player_name': players
    })
    players_df.to_csv(OUTPUT_PATH / "players.csv", index=False)
    print(f"  {len(players_df):,} players")

    # Create player_id mapping
    player_map = dict(zip(players_df['player_name'], players_df['player_id']))

    # Create games lookup table
    print("\nCreating games table...")
    games_df = df[['game_id', 'game_date', 'season']].drop_duplicates()
    games_df['season_year'] = games_df['season'].apply(get_season_year)
    games_df.to_csv(OUTPUT_PATH / "games.csv", index=False)
    print(f"  {len(games_df):,} games")

    # Create main stats table
    print("\nCreating player_stats_by_minute table...")
    stats_df = df.copy()
    stats_df['player_id'] = stats_df['player_name'].map(player_map)
    stats_df['season_year'] = stats_df['season'].apply(get_season_year)

    # Rename columns to shorter MySQL names
    stats_df = stats_df.rename(columns={
        'cumulative_points': 'pts',
        'cumulative_rebounds': 'reb',
        'cumulative_offensive_rebounds': 'oreb',
        'cumulative_defensive_rebounds': 'dreb',
        'cumulative_assists': 'ast',
        'cumulative_steals': 'stl',
        'cumulative_blocks': 'blk',
        'cumulative_turnovers': 'tov',
        'cumulative_fouls': 'pf',
        'cumulative_fgm': 'fgm',
        'cumulative_fga': 'fga',
        'cumulative_fg3m': 'fg3m',
        'cumulative_fg3a': 'fg3a',
        'cumulative_ftm': 'ftm',
        'cumulative_fta': 'fta',
        'cumulative_minutes_played': 'min_played'
    })

    # Select columns for MySQL
    stats_cols = ['player_id', 'game_id', 'elapsed_minute', 'season_year',
                  'pts', 'reb', 'oreb', 'dreb', 'ast', 'stl', 'blk', 'tov', 'pf',
                  'fgm', 'fga', 'fg3m', 'fg3a', 'ftm', 'fta', 'min_played']
    stats_df = stats_df[stats_cols]

    # Export by season for easier loading
    for season_year in sorted(stats_df['season_year'].unique()):
        season_data = stats_df[stats_df['season_year'] == season_year]
        filename = f"player_stats_{season_year}.csv"
        season_data.to_csv(OUTPUT_PATH / filename, index=False)
        print(f"  {season_year}: {len(season_data):,} rows -> {filename}")

    # Create game totals table (final stats per player per game)
    print("\nCreating player_game_totals table...")
    # Get max minute per player per game (final stats)
    idx = df.groupby(['game_id', 'player_name'])['elapsed_minute'].idxmax()
    totals_df = df.loc[idx].copy()
    totals_df['player_id'] = totals_df['player_name'].map(player_map)
    totals_df['season_year'] = totals_df['season'].apply(get_season_year)

    totals_df = totals_df.rename(columns={
        'cumulative_points': 'pts',
        'cumulative_rebounds': 'reb',
        'cumulative_offensive_rebounds': 'oreb',
        'cumulative_defensive_rebounds': 'dreb',
        'cumulative_assists': 'ast',
        'cumulative_steals': 'stl',
        'cumulative_blocks': 'blk',
        'cumulative_turnovers': 'tov',
        'cumulative_fouls': 'pf',
        'cumulative_fgm': 'fgm',
        'cumulative_fga': 'fga',
        'cumulative_fg3m': 'fg3m',
        'cumulative_fg3a': 'fg3a',
        'cumulative_ftm': 'ftm',
        'cumulative_fta': 'fta',
        'cumulative_minutes_played': 'min_played'
    })

    totals_cols = ['player_id', 'game_id', 'game_date', 'season', 'season_year',
                   'pts', 'reb', 'oreb', 'dreb', 'ast', 'stl', 'blk', 'tov', 'pf',
                   'fgm', 'fga', 'fg3m', 'fg3a', 'ftm', 'fta', 'min_played']
    totals_df = totals_df[totals_cols]
    totals_df.to_csv(OUTPUT_PATH / "player_game_totals.csv", index=False)
    print(f"  {len(totals_df):,} game records")

    conn.close()

    print(f"\n{'='*60}")
    print("Export complete!")
    print(f"{'='*60}")
    print(f"Files saved to: {OUTPUT_PATH}")
    print("""
MySQL Import Commands:
----------------------
1. Create the database and tables:
   mysql -u root -p < mysql_schema.sql

2. Load the data:
   mysql -u root -p nba_stats

   LOAD DATA LOCAL INFILE 'mysql_export/players.csv'
   INTO TABLE players
   FIELDS TERMINATED BY ',' ENCLOSED BY '"'
   LINES TERMINATED BY '\\n'
   IGNORE 1 ROWS
   (player_id, player_name);

   LOAD DATA LOCAL INFILE 'mysql_export/games.csv'
   INTO TABLE games
   FIELDS TERMINATED BY ',' ENCLOSED BY '"'
   LINES TERMINATED BY '\\n'
   IGNORE 1 ROWS
   (game_id, game_date, season, season_year);

   -- Load stats by season (faster with partitions)
   LOAD DATA LOCAL INFILE 'mysql_export/player_stats_2021.csv'
   INTO TABLE player_stats_by_minute
   FIELDS TERMINATED BY ',' ENCLOSED BY '"'
   LINES TERMINATED BY '\\n'
   IGNORE 1 ROWS
   (player_id, game_id, elapsed_minute, season_year,
    pts, reb, oreb, dreb, ast, stl, blk, tov, pf,
    fgm, fga, fg3m, fg3a, ftm, fta, min_played);

   -- Repeat for each season file...

   LOAD DATA LOCAL INFILE 'mysql_export/player_game_totals.csv'
   INTO TABLE player_game_totals
   FIELDS TERMINATED BY ',' ENCLOSED BY '"'
   LINES TERMINATED BY '\\n'
   IGNORE 1 ROWS;
""")


def direct_mysql_import(host, user, password, database, port=3306):
    """Import directly to MySQL database."""
    try:
        import mysql.connector
    except ImportError:
        print("ERROR: mysql-connector-python not installed")
        print("Install with: pip install mysql-connector-python")
        return

    print(f"Connecting to MySQL at {host}:{port}...")

    # Connect to MySQL
    conn = mysql.connector.connect(
        host=host,
        user=user,
        password=password,
        database=database,
        port=port,
        allow_local_infile=True
    )
    cursor = conn.cursor()

    print("Loading data from SQLite...")
    sqlite_conn = sqlite3.connect(SQLITE_DB)
    df = pd.read_sql("SELECT * FROM player_stats_by_minute", sqlite_conn)
    sqlite_conn.close()
    print(f"  Loaded {len(df):,} rows")

    # Create players
    print("\nInserting players...")
    players = df['player_name'].unique()
    for i, name in enumerate(players):
        cursor.execute(
            "INSERT IGNORE INTO players (player_name) VALUES (%s)",
            (name,)
        )
        if (i + 1) % 100 == 0:
            print(f"  {i+1}/{len(players)}")
    conn.commit()

    # Get player ID mapping
    cursor.execute("SELECT player_id, player_name FROM players")
    player_map = {name: pid for pid, name in cursor.fetchall()}

    # Create games
    print("\nInserting games...")
    games = df[['game_id', 'game_date', 'season']].drop_duplicates()
    for _, row in games.iterrows():
        season_year = get_season_year(row['season'])
        cursor.execute(
            """INSERT IGNORE INTO games (game_id, game_date, season, season_year)
               VALUES (%s, %s, %s, %s)""",
            (row['game_id'], row['game_date'], row['season'], season_year)
        )
    conn.commit()
    print(f"  {len(games):,} games inserted")

    # Insert stats in batches
    print("\nInserting player stats (this may take a while)...")
    batch_size = 10000
    total = len(df)

    insert_sql = """
        INSERT INTO player_stats_by_minute
        (player_id, game_id, elapsed_minute, season_year,
         pts, reb, oreb, dreb, ast, stl, blk, tov, pf,
         fgm, fga, fg3m, fg3a, ftm, fta, min_played)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """

    for i in range(0, total, batch_size):
        batch = df.iloc[i:i+batch_size]
        values = []
        for _, row in batch.iterrows():
            values.append((
                player_map[row['player_name']],
                row['game_id'],
                row['elapsed_minute'],
                get_season_year(row['season']),
                row['cumulative_points'],
                row['cumulative_rebounds'],
                row['cumulative_offensive_rebounds'],
                row['cumulative_defensive_rebounds'],
                row['cumulative_assists'],
                row['cumulative_steals'],
                row['cumulative_blocks'],
                row['cumulative_turnovers'],
                row['cumulative_fouls'],
                row['cumulative_fgm'],
                row['cumulative_fga'],
                row['cumulative_fg3m'],
                row['cumulative_fg3a'],
                row['cumulative_ftm'],
                row['cumulative_fta'],
                row['cumulative_minutes_played']
            ))
        cursor.executemany(insert_sql, values)
        conn.commit()
        print(f"  {min(i+batch_size, total):,}/{total:,} rows")

    print("\nDone!")
    cursor.close()
    conn.close()


def main():
    parser = argparse.ArgumentParser(description='Export to MySQL')
    parser.add_argument('--csv', action='store_true', help='Export to CSV files')
    parser.add_argument('--direct', action='store_true', help='Direct MySQL import')
    parser.add_argument('--host', default='localhost', help='MySQL host')
    parser.add_argument('--port', type=int, default=3306, help='MySQL port')
    parser.add_argument('--user', default='root', help='MySQL user')
    parser.add_argument('--password', default='', help='MySQL password')
    parser.add_argument('--database', default='nba_stats', help='MySQL database')

    args = parser.parse_args()

    if args.direct:
        direct_mysql_import(args.host, args.user, args.password, args.database, args.port)
    else:
        export_to_csv()


if __name__ == "__main__":
    main()
