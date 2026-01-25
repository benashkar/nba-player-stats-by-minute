#!/usr/bin/env python3
"""
Integrate Gambling Spread Data with Player Stats

Merges gambling odds (spreads, over/unders, moneylines) with player performance data
to enable analysis of player props based on game spreads.

Usage:
    python integrate_gambling_data.py --build    # Build team mappings and merge data
    python integrate_gambling_data.py --update   # Update with new games
    python integrate_gambling_data.py --verify   # Verify the integration
"""

import pandas as pd
import numpy as np
import sqlite3
import json
import time
import argparse
from pathlib import Path
from datetime import datetime
from typing import Dict, Tuple, Optional

# Try to import nba_api for team lookups
try:
    from nba_api.stats.endpoints import leaguegamefinder, boxscoretraditionalv2
    from nba_api.stats.static import teams
    HAS_NBA_API = True
except ImportError:
    HAS_NBA_API = False
    print("Warning: nba_api not available, will use alternative method")

# Configuration
PLAYER_STATS_PATH = Path(r"C:/Users/cashk/OneDrive/Projects/NBAPlayer Points")
GAMBLING_DATA_PATH = Path(r"C:/Users/cashk/OneDrive/Projects/NBAGambling/data/output")
PLAYER_DB = PLAYER_STATS_PATH / "output" / "nba_player_stats.db"
GAMBLING_CSV = GAMBLING_DATA_PATH / "nba_odds.csv"
OUTPUT_DB = PLAYER_STATS_PATH / "output" / "nba_player_stats_with_odds.db"

# Team abbreviation mappings (gambling data -> NBA standard)
TEAM_ABBREV_MAP = {
    # Standard mappings
    'ATL': 'ATL', 'BOS': 'BOS', 'BKN': 'BKN', 'CHA': 'CHA', 'CHI': 'CHI',
    'CLE': 'CLE', 'DAL': 'DAL', 'DEN': 'DEN', 'DET': 'DET', 'GSW': 'GSW',
    'HOU': 'HOU', 'IND': 'IND', 'LAC': 'LAC', 'LAL': 'LAL', 'MEM': 'MEM',
    'MIA': 'MIA', 'MIL': 'MIL', 'MIN': 'MIN', 'NOP': 'NOP', 'NYK': 'NYK',
    'OKC': 'OKC', 'ORL': 'ORL', 'PHI': 'PHI', 'PHX': 'PHX', 'POR': 'POR',
    'SAC': 'SAC', 'SAS': 'SAS', 'TOR': 'TOR', 'UTA': 'UTA', 'WAS': 'WAS',
    # Alternative abbreviations
    'BRK': 'BKN', 'BKLYN': 'BKN', 'BROOKLYN': 'BKN',
    'CHA': 'CHA', 'CHAR': 'CHA', 'CHARLOTTE': 'CHA',
    'GS': 'GSW', 'GOLDEN STATE': 'GSW',
    'LA': 'LAL', 'LAKERS': 'LAL',
    'LAC': 'LAC', 'CLIPPERS': 'LAC',
    'NO': 'NOP', 'NOLA': 'NOP', 'NEW ORLEANS': 'NOP',
    'NY': 'NYK', 'NEW YORK': 'NYK',
    'PHO': 'PHX', 'PHOENIX': 'PHX',
    'SA': 'SAS', 'SAN ANTONIO': 'SAS',
    'WSH': 'WAS', 'WASHINGTON': 'WAS',
}

# Team ID to abbreviation mapping
TEAM_ID_TO_ABBREV = {
    1610612737: 'ATL', 1610612738: 'BOS', 1610612751: 'BKN', 1610612766: 'CHA',
    1610612741: 'CHI', 1610612739: 'CLE', 1610612742: 'DAL', 1610612743: 'DEN',
    1610612765: 'DET', 1610612744: 'GSW', 1610612745: 'HOU', 1610612754: 'IND',
    1610612746: 'LAC', 1610612747: 'LAL', 1610612763: 'MEM', 1610612748: 'MIA',
    1610612749: 'MIL', 1610612750: 'MIN', 1610612740: 'NOP', 1610612752: 'NYK',
    1610612760: 'OKC', 1610612753: 'ORL', 1610612755: 'PHI', 1610612756: 'PHX',
    1610612757: 'POR', 1610612758: 'SAC', 1610612759: 'SAS', 1610612761: 'TOR',
    1610612762: 'UTA', 1610612764: 'WAS',
}


def normalize_team_abbrev(abbrev: str) -> str:
    """Normalize team abbreviation to standard NBA format."""
    if abbrev is None:
        return None
    abbrev = abbrev.upper().strip()
    return TEAM_ABBREV_MAP.get(abbrev, abbrev)


def get_team_from_game_id(game_id: str, game_date: str, season: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Get home and away team for a game using nba_api.
    Returns (home_team, away_team) abbreviations.
    """
    if not HAS_NBA_API:
        return None, None

    try:
        time.sleep(0.4)  # Rate limiting
        boxscore = boxscoretraditionalv2.BoxScoreTraditionalV2(game_id=game_id)
        data = boxscore.get_data_frames()

        if len(data) > 1:
            team_stats = data[1]  # Team stats DataFrame
            if len(team_stats) >= 2:
                # First row is usually away team, second is home team
                away_team_id = team_stats.iloc[0]['TEAM_ID']
                home_team_id = team_stats.iloc[1]['TEAM_ID']

                away_abbrev = TEAM_ID_TO_ABBREV.get(away_team_id)
                home_abbrev = TEAM_ID_TO_ABBREV.get(home_team_id)

                return home_abbrev, away_abbrev
    except Exception as e:
        print(f"  Error fetching team info for {game_id}: {e}")

    return None, None


def build_games_with_teams_from_api(seasons: list = None) -> pd.DataFrame:
    """
    Build games table with team info using nba_api.
    This is slower but more accurate.
    """
    if not HAS_NBA_API:
        print("nba_api not available")
        return pd.DataFrame()

    if seasons is None:
        seasons = ['2021-22', '2022-23', '2023-24', '2024-25', '2025-26']

    all_games = []

    for season in seasons:
        print(f"Fetching games for {season}...")
        try:
            time.sleep(0.5)
            gamefinder = leaguegamefinder.LeagueGameFinder(
                season_nullable=season,
                season_type_nullable="Regular Season",
                league_id_nullable="00"
            )
            games = gamefinder.get_data_frames()[0]

            # Group by game_id to get both teams
            for game_id in games['GAME_ID'].unique():
                game_data = games[games['GAME_ID'] == game_id]
                if len(game_data) >= 2:
                    # Determine home vs away from MATCHUP column
                    for _, row in game_data.iterrows():
                        matchup = row['MATCHUP']
                        team_abbrev = row['TEAM_ABBREVIATION']

                        if ' vs. ' in matchup:  # Home team
                            home_team = team_abbrev
                            away_team = matchup.split(' vs. ')[1]
                        elif ' @ ' in matchup:  # Away team
                            away_team = team_abbrev
                            home_team = matchup.split(' @ ')[1]

                    all_games.append({
                        'game_id': game_id,
                        'game_date': game_data.iloc[0]['GAME_DATE'],
                        'season': season,
                        'home_team': normalize_team_abbrev(home_team),
                        'away_team': normalize_team_abbrev(away_team),
                    })

            print(f"  Found {len(games['GAME_ID'].unique())} games")

        except Exception as e:
            print(f"  Error fetching {season}: {e}")

    return pd.DataFrame(all_games).drop_duplicates(subset=['game_id'])


def build_games_with_teams_from_db() -> pd.DataFrame:
    """
    Build games table using existing player stats database.
    Extracts team info from the play-by-play data indirectly.
    """
    print("Building games table from player database...")

    conn = sqlite3.connect(PLAYER_DB)

    # Get unique games
    games_df = pd.read_sql("""
        SELECT DISTINCT game_id, game_date, season
        FROM player_stats_by_minute
        ORDER BY game_date
    """, conn)

    conn.close()

    print(f"  Found {len(games_df)} unique games")
    return games_df


def load_gambling_data() -> pd.DataFrame:
    """Load and normalize gambling odds data."""
    print(f"Loading gambling data from {GAMBLING_CSV}...")

    odds_df = pd.read_csv(GAMBLING_CSV)

    # FIX: The gambling CSV has home/away columns SWAPPED
    # The game_id format is DATE_HOME_AWAY but the columns are reversed
    # Swap them to correct this
    print("  Fixing swapped home/away columns in gambling data...")
    odds_df['home_team'], odds_df['away_team'] = odds_df['away_team'].copy(), odds_df['home_team'].copy()
    odds_df['home_score'], odds_df['away_score'] = odds_df['away_score'].copy(), odds_df['home_score'].copy()

    # Note: The spread appears to have been recorded from the ACTUAL home team's perspective,
    # so we don't need to flip it - just the team columns and scores

    # Swap moneylines too (these are team-specific)
    if 'closing_moneyline_home' in odds_df.columns and 'closing_moneyline_away' in odds_df.columns:
        odds_df['closing_moneyline_home'], odds_df['closing_moneyline_away'] = \
            odds_df['closing_moneyline_away'].copy(), odds_df['closing_moneyline_home'].copy()

    # Normalize team abbreviations
    odds_df['home_team'] = odds_df['home_team'].apply(normalize_team_abbrev)
    odds_df['away_team'] = odds_df['away_team'].apply(normalize_team_abbrev)

    # Normalize season format (2021-2022 -> 2021-22)
    odds_df['season_normalized'] = odds_df['season'].apply(
        lambda x: f"{x.split('-')[0]}-{x.split('-')[1][2:]}" if '-' in str(x) else x
    )

    # Ensure game_date is string format
    odds_df['game_date'] = pd.to_datetime(odds_df['game_date']).dt.strftime('%Y-%m-%d')

    print(f"  Loaded {len(odds_df)} games with odds")
    print(f"  Seasons: {odds_df['season'].unique()}")

    return odds_df


def merge_games_with_odds(games_df: pd.DataFrame, odds_df: pd.DataFrame) -> pd.DataFrame:
    """
    Merge games data with gambling odds.
    Matches on game_date + home_team + away_team.
    """
    print("Merging games with odds data...")

    # Create a matching key from odds data
    odds_df['match_key'] = odds_df['game_date'] + '_' + odds_df['home_team'] + '_' + odds_df['away_team']

    # We need to get team info for games
    # Since we don't have teams in player data, we'll match by date and use odds data teams

    # Group odds by date to handle matching
    games_df['game_date_str'] = pd.to_datetime(games_df['game_date']).dt.strftime('%Y-%m-%d')

    # For now, we'll create a lookup by date + teams from odds
    odds_lookup = odds_df.set_index('match_key').to_dict('index')

    print(f"  Games in player data: {len(games_df)}")
    print(f"  Games in odds data: {len(odds_df)}")

    return games_df, odds_df, odds_lookup


def create_enhanced_database():
    """
    Create enhanced database with gambling odds integrated.
    """
    print("="*60)
    print("BUILDING ENHANCED DATABASE WITH GAMBLING ODDS")
    print("="*60)

    # Load player stats
    print("\nLoading player stats database...")
    conn = sqlite3.connect(PLAYER_DB)

    player_stats = pd.read_sql("SELECT * FROM player_stats_by_minute", conn)
    print(f"  Loaded {len(player_stats):,} player stat records")

    conn.close()

    # Load gambling data
    odds_df = load_gambling_data()

    # Build games with teams using nba_api
    print("\nBuilding games with team info...")
    games_with_teams = build_games_with_teams_from_api()

    if len(games_with_teams) == 0:
        print("Failed to get team info from API, using alternative method...")
        # Fall back to matching by date only
        games_with_teams = build_games_with_teams_from_db()

    # Merge with odds data
    print("\nMerging with odds data...")

    # Create match key for games
    games_with_teams['match_key'] = (
        games_with_teams['game_date'].astype(str).str[:10] + '_' +
        games_with_teams['home_team'] + '_' +
        games_with_teams['away_team']
    )

    # Create match key for odds
    odds_df['match_key'] = (
        odds_df['game_date'].astype(str).str[:10] + '_' +
        odds_df['home_team'] + '_' +
        odds_df['away_team']
    )

    # Merge
    games_with_odds = games_with_teams.merge(
        odds_df[['match_key', 'closing_spread', 'closing_over_under',
                 'closing_moneyline_home', 'closing_moneyline_away',
                 'home_score', 'away_score']],
        on='match_key',
        how='left'
    )

    matched = games_with_odds['closing_spread'].notna().sum()
    print(f"  Matched {matched} / {len(games_with_odds)} games with odds ({matched/len(games_with_odds)*100:.1f}%)")

    # Save enhanced games table
    print("\nSaving enhanced database...")

    conn = sqlite3.connect(OUTPUT_DB)

    # Save games with odds
    games_with_odds.to_sql('games_with_odds', conn, if_exists='replace', index=False)

    # Create indexes
    conn.execute('CREATE INDEX IF NOT EXISTS idx_games_date ON games_with_odds(game_date)')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_games_id ON games_with_odds(game_id)')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_games_spread ON games_with_odds(closing_spread)')

    # Copy player stats
    player_stats.to_sql('player_stats_by_minute', conn, if_exists='replace', index=False)

    # Create indexes on player stats
    conn.execute('CREATE INDEX IF NOT EXISTS idx_player_game ON player_stats_by_minute(game_id, player_name)')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_player_season ON player_stats_by_minute(season)')

    conn.commit()
    conn.close()

    print(f"\nSaved to: {OUTPUT_DB}")

    return games_with_odds


def create_player_game_totals_with_odds():
    """
    Create a player_game_totals table with odds information.
    """
    print("\nCreating player_game_totals_with_odds table...")

    conn = sqlite3.connect(OUTPUT_DB)

    # Get final stats per player per game
    player_totals = pd.read_sql("""
        SELECT
            game_id,
            player_name,
            season,
            game_date,
            MAX(elapsed_minute) as max_minute,
            MAX(cumulative_points) as pts,
            MAX(cumulative_rebounds) as reb,
            MAX(cumulative_offensive_rebounds) as oreb,
            MAX(cumulative_defensive_rebounds) as dreb,
            MAX(cumulative_assists) as ast,
            MAX(cumulative_steals) as stl,
            MAX(cumulative_blocks) as blk,
            MAX(cumulative_turnovers) as tov,
            MAX(cumulative_fouls) as pf,
            MAX(cumulative_fgm) as fgm,
            MAX(cumulative_fga) as fga,
            MAX(cumulative_fg3m) as fg3m,
            MAX(cumulative_fg3a) as fg3a,
            MAX(cumulative_ftm) as ftm,
            MAX(cumulative_fta) as fta,
            MAX(cumulative_minutes_played) as min_played
        FROM player_stats_by_minute
        GROUP BY game_id, player_name, season, game_date
    """, conn)

    # Get games with odds
    games_odds = pd.read_sql("SELECT * FROM games_with_odds", conn)

    # Merge
    player_totals_with_odds = player_totals.merge(
        games_odds[['game_id', 'home_team', 'away_team', 'closing_spread',
                    'closing_over_under', 'closing_moneyline_home', 'closing_moneyline_away']],
        on='game_id',
        how='left'
    )

    # Save
    player_totals_with_odds.to_sql('player_game_totals_with_odds', conn, if_exists='replace', index=False)

    # Create indexes
    conn.execute('CREATE INDEX IF NOT EXISTS idx_pgt_player ON player_game_totals_with_odds(player_name)')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_pgt_spread ON player_game_totals_with_odds(closing_spread)')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_pgt_date ON player_game_totals_with_odds(game_date)')

    conn.commit()
    conn.close()

    print(f"  Created player_game_totals_with_odds with {len(player_totals_with_odds):,} records")

    return player_totals_with_odds


def verify_integration():
    """Verify the integration was successful."""
    print("\n" + "="*60)
    print("VERIFYING INTEGRATION")
    print("="*60)

    conn = sqlite3.connect(OUTPUT_DB)

    # Check games with odds
    games = pd.read_sql("SELECT * FROM games_with_odds", conn)
    print(f"\nGames with odds table:")
    print(f"  Total games: {len(games)}")
    print(f"  Games with spread data: {games['closing_spread'].notna().sum()}")
    print(f"  Date range: {games['game_date'].min()} to {games['game_date'].max()}")

    # Check spread distribution
    print(f"\nSpread distribution:")
    spreads = games['closing_spread'].dropna()
    print(f"  Min: {spreads.min()}")
    print(f"  Max: {spreads.max()}")
    print(f"  Mean: {spreads.mean():.1f}")

    # Check player totals with odds
    player_totals = pd.read_sql("SELECT * FROM player_game_totals_with_odds LIMIT 5", conn)
    print(f"\nSample player_game_totals_with_odds:")
    print(player_totals[['player_name', 'game_date', 'pts', 'closing_spread']].to_string())

    # Check specific player
    edwards = pd.read_sql("""
        SELECT player_name, game_date, pts, closing_spread
        FROM player_game_totals_with_odds
        WHERE player_name = 'A. Edwards'
        AND closing_spread IS NOT NULL
        ORDER BY game_date DESC
        LIMIT 10
    """, conn)

    print(f"\nAnthony Edwards recent games with spreads:")
    print(edwards.to_string())

    conn.close()


def main():
    parser = argparse.ArgumentParser(description='Integrate gambling data with player stats')
    parser.add_argument('--build', action='store_true', help='Build the integrated database')
    parser.add_argument('--verify', action='store_true', help='Verify the integration')

    args = parser.parse_args()

    if args.build or (not args.build and not args.verify):
        create_enhanced_database()
        create_player_game_totals_with_odds()

    if args.verify or args.build:
        verify_integration()


if __name__ == "__main__":
    main()
