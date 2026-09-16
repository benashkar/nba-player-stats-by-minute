# Claude Code Instructions: NBA Player Points by Minute Database

**PROJECT GOAL:** Build a database showing how many points each NBA player has scored at each minute of every game from 2021-2025.

---

## PROJECT OVERVIEW

### Input Data
- **Source:** GitHub repository `shufinskiy/nba_data`
- **Files:** Pre-downloaded play-by-play CSV files for NBA seasons
- **Coverage:** 1996-2025 (we need 2021-2025)
- **Location:** https://github.com/shufinskiy/nba_data/tree/master/dataset

### Output Format
A database (CSV or SQLite) with the following structure:

```csv
game_id,game_date,player_name,elapsed_minute,cumulative_points
0022100001,2021-10-19,LeBron James,0,0
0022100001,2021-10-19,LeBron James,1,2
0022100001,2021-10-19,LeBron James,2,5
0022100001,2021-10-19,LeBron James,3,7
...
0022100001,2021-10-19,LeBron James,48,28
```

Or optionally as a wide format:
```csv
game_id,game_date,player_name,min_0,min_1,min_2,...,min_48
0022100001,2021-10-19,LeBron James,0,2,5,7,...,28
```

---

## PHASE 1: DATA ACQUISITION

### Task 1.1: Download Play-by-Play Data

**Option A: Direct Download (Recommended)**

Download these CSV files from GitHub:
- `nbastats_2021.csv` (2020-21 season)
- `nbastats_2022.csv` (2021-22 season)
- `nbastats_2023.csv` (2022-23 season)
- `nbastats_2024.csv` (2023-24 season)
- `nbastats_2025.csv` (2024-25 season)

**URLs:**
```
https://github.com/shufinskiy/nba_data/raw/master/dataset/nbastats_2021.csv
https://github.com/shufinskiy/nba_data/raw/master/dataset/nbastats_2022.csv
https://github.com/shufinskiy/nba_data/raw/master/dataset/nbastats_2023.csv
https://github.com/shufinskiy/nba_data/raw/master/dataset/nbastats_2024.csv
https://github.com/shufinskiy/nba_data/raw/master/dataset/nbastats_2025.csv
```

**Download Command:**
```bash
mkdir -p /home/claude/nba_data/raw
cd /home/claude/nba_data/raw

# Download each season
for year in 2021 2022 2023 2024 2025; do
    wget "https://github.com/shufinskiy/nba_data/raw/master/dataset/nbastats_${year}.csv" \
         -O "nbastats_${year}.csv"
done
```

**Option B: Use Python Package (Alternative)**

If direct download fails, use the nba_data Python package:

```python
# This requires installing the package first
pip install nba-data

from nba_data import load_nba_data

for year in [2021, 2022, 2023, 2024, 2025]:
    data = load_nba_data(
        path='/home/claude/nba_data/raw',
        seasons=[year],
        data='nbastats',
        seasontype='rg'  # regular season
    )
```

### Task 1.2: Verify Data Structure

Load one file and verify it has these critical columns:
- `GAME_ID` - Unique game identifier
- `PERIOD` - Quarter number (1-4, 5+ for OT)
- `PCTIMESTRING` - Time remaining in quarter (MM:SS format)
- `EVENTMSGTYPE` - Event type code
- `PLAYER1_NAME` - Player who performed the action
- `HOMEDESCRIPTION` - Description of home team events
- `VISITORDESCRIPTION` - Description of visitor team events
- `SCORE` - Current score

**Verification Code:**
```python
import pandas as pd

# Load sample
df = pd.read_csv('/home/claude/nba_data/raw/nbastats_2024.csv')

# Check columns
required_cols = ['GAME_ID', 'PERIOD', 'PCTIMESTRING', 'EVENTMSGTYPE', 
                 'PLAYER1_NAME', 'HOMEDESCRIPTION', 'VISITORDESCRIPTION']
missing = [col for col in required_cols if col not in df.columns]

if missing:
    print(f"ERROR: Missing columns: {missing}")
else:
    print("✓ All required columns present")
    print(f"Total rows: {len(df):,}")
    print(f"Unique games: {df['GAME_ID'].nunique()}")
```

---

## PHASE 2: DATA PROCESSING

### Task 2.1: Create Helper Functions

**Function 1: Parse Time to Elapsed Minutes**

```python
def calc_elapsed_minutes(period, pctimestring):
    """
    Convert PERIOD and PCTIMESTRING to elapsed game minutes.
    
    Args:
        period (int): Quarter number (1-4 for regulation, 5+ for OT)
        pctimestring (str): Time remaining in quarter (e.g., "11:47")
    
    Returns:
        float: Total elapsed minutes from start of game
    
    Examples:
        calc_elapsed_minutes(1, "12:00") → 0.0 (start of game)
        calc_elapsed_minutes(1, "11:47") → 0.22 (13 seconds elapsed)
        calc_elapsed_minutes(1, "0:00") → 12.0 (end of Q1)
        calc_elapsed_minutes(2, "6:00") → 18.0 (6 min into Q2)
        calc_elapsed_minutes(4, "0:00") → 48.0 (end of regulation)
        calc_elapsed_minutes(5, "5:00") → 48.0 (OT - cap at 48)
    """
    try:
        mins, secs = map(int, pctimestring.split(':'))
        time_remaining = mins + secs / 60
        
        # Calculate elapsed time
        if period <= 4:
            # Regular quarters
            elapsed = (period - 1) * 12 + (12 - time_remaining)
        else:
            # Overtime - cap at 48 minutes (end of regulation)
            # Or optionally track OT separately: 48 + (period - 5) * 5 + (5 - time_remaining)
            elapsed = 48.0
        
        return round(elapsed, 2)
    except:
        return None
```

**Function 2: Determine Points Scored**

```python
def get_points_scored(row):
    """
    Determine how many points were scored on this play.
    
    Args:
        row: DataFrame row with EVENTMSGTYPE and description fields
    
    Returns:
        int: Points scored (0, 1, 2, or 3)
    
    Event Types:
        EVENTMSGTYPE = 1: Made field goal (2PT or 3PT)
        EVENTMSGTYPE = 3: Made free throw (1PT)
        All others: 0 points
    """
    event_type = row['EVENTMSGTYPE']
    
    # Not a scoring event
    if event_type not in [1, 3]:
        return 0
    
    # Made free throw
    if event_type == 3:
        return 1
    
    # Made field goal - check if 3PT or 2PT
    description = str(row.get('HOMEDESCRIPTION', '')) + str(row.get('VISITORDESCRIPTION', ''))
    
    if '3PT' in description.upper():
        return 3
    else:
        return 2
```

**Function 3: Get Player Team**

```python
def get_player_team(row):
    """
    Determine which team the player belongs to based on description.
    
    Returns:
        str: 'HOME', 'VISITOR', or None
    """
    if pd.notna(row.get('HOMEDESCRIPTION')) and row.get('HOMEDESCRIPTION'):
        return 'HOME'
    elif pd.notna(row.get('VISITORDESCRIPTION')) and row.get('VISITORDESCRIPTION'):
        return 'VISITOR'
    return None
```

### Task 2.2: Process Single Game

**Function: Process One Game**

```python
def process_game(game_df):
    """
    Process a single game's play-by-play data into player points by minute.
    
    Args:
        game_df: DataFrame filtered to one GAME_ID
    
    Returns:
        DataFrame with columns: game_id, player_name, elapsed_minute, cumulative_points
    """
    game_id = game_df['GAME_ID'].iloc[0]
    
    # Filter to scoring events only
    scoring = game_df[game_df['EVENTMSGTYPE'].isin([1, 3])].copy()
    
    # Add helper columns
    scoring['elapsed_minutes'] = scoring.apply(
        lambda row: calc_elapsed_minutes(row['PERIOD'], row['PCTIMESTRING']), 
        axis=1
    )
    scoring['points_scored'] = scoring.apply(get_points_scored, axis=1)
    
    # Remove invalid rows
    scoring = scoring[scoring['elapsed_minutes'].notna()]
    scoring = scoring[scoring['PLAYER1_NAME'].notna()]
    
    # Sort by time
    scoring = scoring.sort_values('elapsed_minutes')
    
    # Calculate cumulative points by player
    player_results = []
    
    for player in scoring['PLAYER1_NAME'].unique():
        player_data = scoring[scoring['PLAYER1_NAME'] == player].copy()
        player_data['cumulative_points'] = player_data['points_scored'].cumsum()
        
        # Create minute-by-minute breakdown (0-48)
        minutes_data = []
        
        for minute in range(49):  # 0 through 48
            # Find cumulative points at this minute
            points_at_minute = player_data[
                player_data['elapsed_minutes'] <= minute
            ]['cumulative_points'].max()
            
            if pd.isna(points_at_minute):
                points_at_minute = 0
            
            minutes_data.append({
                'game_id': game_id,
                'player_name': player,
                'elapsed_minute': minute,
                'cumulative_points': int(points_at_minute)
            })
        
        player_results.extend(minutes_data)
    
    return pd.DataFrame(player_results)
```

### Task 2.3: Process All Games in a Season

```python
def process_season(season_year):
    """
    Process all games in a season.
    
    Args:
        season_year (int): Season year (e.g., 2024 for 2023-24 season)
    
    Returns:
        DataFrame with all player-minutes for the season
    """
    print(f"Processing season {season_year}...")
    
    # Load season data
    df = pd.read_csv(f'/home/claude/nba_data/raw/nbastats_{season_year}.csv')
    
    print(f"  Loaded {len(df):,} rows")
    print(f"  Games: {df['GAME_ID'].nunique()}")
    
    # Process each game
    all_results = []
    game_ids = df['GAME_ID'].unique()
    
    for i, game_id in enumerate(game_ids):
        if i % 100 == 0:
            print(f"  Processing game {i+1}/{len(game_ids)}...")
        
        game_df = df[df['GAME_ID'] == game_id]
        game_results = process_game(game_df)
        all_results.append(game_results)
    
    # Combine all games
    season_df = pd.concat(all_results, ignore_index=True)
    
    print(f"  Completed: {len(season_df):,} player-minute records")
    
    return season_df
```

### Task 2.4: Add Game Metadata (Optional but Recommended)

To make the database more useful, add game date and team information:

```python
def get_game_metadata(df):
    """
    Extract game-level metadata from play-by-play data.
    
    Returns:
        DataFrame with game_id, game_date, home_team, visitor_team
    """
    # Group by game
    games = df.groupby('GAME_ID').first().reset_index()
    
    # Extract metadata (if available in the dataset)
    metadata = games[['GAME_ID']].copy()
    
    # Game date - parse from GAME_ID or separate field if available
    # GAME_ID format: 00XXYZZZZZ where XX is season, Y is season type, ZZZZZ is game number
    # You may need to join with a separate games table for dates
    
    return metadata

def merge_metadata(player_minutes_df, metadata_df):
    """
    Add game metadata to player-minutes data.
    """
    return player_minutes_df.merge(
        metadata_df,
        on='game_id',
        how='left'
    )
```

---

## PHASE 3: DATABASE CREATION

### Task 3.1: Process All Seasons

```python
def build_full_database():
    """
    Process all seasons (2021-2025) and combine into single database.
    """
    all_seasons = []
    
    for year in [2021, 2022, 2023, 2024, 2025]:
        season_df = process_season(year)
        season_df['season'] = year
        all_seasons.append(season_df)
        
        # Save individual season
        output_path = f'/home/claude/nba_data/output/player_points_by_minute_{year}.csv'
        season_df.to_csv(output_path, index=False)
        print(f"  Saved: {output_path}")
    
    # Combine all seasons
    full_db = pd.concat(all_seasons, ignore_index=True)
    
    print(f"
Total database:")
    print(f"  Total rows: {len(full_db):,}")
    print(f"  Unique players: {full_db['player_name'].nunique()}")
    print(f"  Unique games: {full_db['game_id'].nunique()}")
    
    return full_db
```

### Task 3.2: Save Database

**Option A: CSV (Simple)**

```python
# Long format (recommended)
full_db.to_csv('/home/claude/nba_data/output/nba_player_points_by_minute_2021_2025.csv', 
               index=False)

# Wide format (optional - easier for some analyses)
wide_db = full_db.pivot(
    index=['game_id', 'player_name'],
    columns='elapsed_minute',
    values='cumulative_points'
).reset_index()

wide_db.columns = ['game_id', 'player_name'] + [f'min_{i}' for i in range(49)]
wide_db.to_csv('/home/claude/nba_data/output/nba_player_points_by_minute_wide.csv', 
               index=False)
```

**Option B: SQLite (More Professional)**

```python
import sqlite3

# Create database
conn = sqlite3.connect('/home/claude/nba_data/output/nba_player_points.db')

# Create table
full_db.to_sql('player_points_by_minute', conn, if_exists='replace', index=False)

# Create indexes for faster queries
conn.execute('CREATE INDEX idx_game ON player_points_by_minute(game_id)')
conn.execute('CREATE INDEX idx_player ON player_points_by_minute(player_name)')
conn.execute('CREATE INDEX idx_game_player ON player_points_by_minute(game_id, player_name)')

conn.close()

print("SQLite database created: /home/claude/nba_data/output/nba_player_points.db")
```

**Option C: Parquet (Most Efficient)**

```python
# Requires: pip install pyarrow
full_db.to_parquet('/home/claude/nba_data/output/nba_player_points_by_minute.parquet',
                   index=False,
                   compression='snappy')
```

---

## PHASE 4: VALIDATION & QUALITY CHECKS

### Task 4.1: Validate Output

```python
def validate_database(df):
    """
    Run quality checks on the output database.
    """
    print("
VALIDATION CHECKS:")
    print("=" * 50)
    
    # Check 1: All games have 49 minutes (0-48)
    minutes_per_game_player = df.groupby(['game_id', 'player_name'])['elapsed_minute'].nunique()
    if (minutes_per_game_player != 49).any():
        print("⚠️  WARNING: Some player-games don't have all 49 minutes")
        print(f"   Expected: 49 minutes per player per game")
        print(f"   Found: {minutes_per_game_player.value_counts()}")
    else:
        print("✓ All player-games have complete 49-minute records")
    
    # Check 2: Points are monotonically increasing
    def check_monotonic(group):
        return (group['cumulative_points'].diff().fillna(0) >= 0).all()
    
    monotonic_check = df.groupby(['game_id', 'player_name']).apply(check_monotonic)
    if not monotonic_check.all():
        print("⚠️  WARNING: Some players have decreasing cumulative points")
    else:
        print("✓ All cumulative points are monotonically increasing")
    
    # Check 3: No null values
    null_counts = df.isnull().sum()
    if null_counts.any():
        print("⚠️  WARNING: Null values found:")
        print(null_counts[null_counts > 0])
    else:
        print("✓ No null values")
    
    # Check 4: Reasonable point totals (0-100 range)
    max_points = df.groupby(['game_id', 'player_name'])['cumulative_points'].max()
    if (max_points > 100).any():
        print(f"⚠️  WARNING: Some players scored >100 points:")
        print(max_points[max_points > 100])
    else:
        print("✓ All point totals are reasonable (<100)")
    
    # Summary statistics
    print("
SUMMARY STATISTICS:")
    print(f"  Total records: {len(df):,}")
    print(f"  Unique games: {df['game_id'].nunique():,}")
    print(f"  Unique players: {df['player_name'].nunique():,}")
    print(f"  Average points per player per game: {df.groupby(['game_id', 'player_name'])['cumulative_points'].max().mean():.1f}")
    
    return True
```

### Task 4.2: Sample Output Check

```python
def show_sample_output(df, player_name="LeBron James", n_games=3):
    """
    Display sample output for a specific player.
    """
    player_data = df[df['player_name'] == player_name]
    
    if len(player_data) == 0:
        print(f"No data found for {player_name}")
        return
    
    # Get random games
    sample_games = player_data['game_id'].unique()[:n_games]
    
    for game_id in sample_games:
        game_data = player_data[player_data['game_id'] == game_id]
        
        print(f"
Game: {game_id}")
        print(f"Player: {player_name}")
        print(f"Final points: {game_data['cumulative_points'].max()}")
        print("
Points by Quarter:")
        print(f"  End Q1 (min 12): {game_data[game_data['elapsed_minute']==12]['cumulative_points'].values[0]}")
        print(f"  Halftime (min 24): {game_data[game_data['elapsed_minute']==24]['cumulative_points'].values[0]}")
        print(f"  End Q3 (min 36): {game_data[game_data['elapsed_minute']==36]['cumulative_points'].values[0]}")
        print(f"  Final (min 48): {game_data[game_data['elapsed_minute']==48]['cumulative_points'].values[0]}")
```

---

## PHASE 5: USAGE EXAMPLES

### Example 1: Query Player Performance

```python
# Get LeBron's points at halftime in all 2024 games
lebron_halftime = df[
    (df['player_name'] == 'LeBron James') &
    (df['elapsed_minute'] == 24) &
    (df['season'] == 2024)
][['game_id', 'cumulative_points']]

print(f"Average halftime points: {lebron_halftime['cumulative_points'].mean():.1f}")
```

### Example 2: Find Fastest to 20 Points

```python
# For each game, find which minute each player first hit 20 points
first_to_20 = df[df['cumulative_points'] >= 20].groupby(
    ['game_id', 'player_name']
)['elapsed_minute'].min().reset_index()

first_to_20.columns = ['game_id', 'player_name', 'minutes_to_20pts']

# Find fastest
fastest = first_to_20.nsmallest(10, 'minutes_to_20pts')
print(fastest)
```

### Example 3: Compare to Betting Lines

If you have betting lines data:

```python
# Load betting lines (hypothetical)
lines = pd.read_csv('player_prop_lines.csv')  # columns: game_id, player_name, points_line

# Merge with our data
merged = df.merge(lines, on=['game_id', 'player_name'])

# Find when player hit their over/under
merged['hit_over'] = merged['cumulative_points'] >= merged['points_line']
first_hit = merged[merged['hit_over']].groupby(
    ['game_id', 'player_name']
)['elapsed_minute'].min()

print(f"Average minute to hit over: {first_hit.mean():.1f}")
```

---

## COMPLETE WORKFLOW SCRIPT

Here's the complete script to run everything:

```python
import pandas as pd
import numpy as np
from pathlib import Path

# Setup directories
Path('/home/claude/nba_data/raw').mkdir(parents=True, exist_ok=True)
Path('/home/claude/nba_data/output').mkdir(parents=True, exist_ok=True)

# [Insert all helper functions from Phase 2 here]

def main():
    """
    Complete workflow to build NBA player points-by-minute database.
    """
    print("=" * 60)
    print("NBA PLAYER POINTS BY MINUTE DATABASE")
    print("=" * 60)
    
    # Phase 1: Download data (if needed)
    print("
PHASE 1: Data Acquisition")
    print("Ensure CSV files are in /home/claude/nba_data/raw/")
    print("Files needed: nbastats_2021.csv through nbastats_2025.csv")
    
    # Phase 2 & 3: Process and build database
    print("
PHASE 2 & 3: Processing and Database Creation")
    full_db = build_full_database()
    
    # Phase 4: Validation
    print("
PHASE 4: Validation")
    validate_database(full_db)
    
    # Show sample
    print("
SAMPLE OUTPUT:")
    show_sample_output(full_db, "LeBron James", n_games=2)
    
    # Final save
    print("
FINAL OUTPUT:")
    output_file = '/home/claude/nba_data/output/nba_player_points_by_minute_2021_2025.csv'
    full_db.to_csv(output_file, index=False)
    print(f"✓ Saved: {output_file}")
    print(f"  Size: {len(full_db):,} rows")
    print(f"  File size: ~{len(full_db) * 50 / 1024 / 1024:.1f} MB")
    
    print("
COMPLETE!")

if __name__ == "__main__":
    main()
```

---

## EXECUTION PLAN

### Step 1: Download Data Files
```bash
cd /home/claude/nba_data/raw
# Download the 5 CSV files from GitHub
```

### Step 2: Run Processing Script
```bash
cd /home/claude/nba_data
python build_database.py
```

### Step 3: Verify Output
```bash
# Check output file exists
ls -lh /home/claude/nba_data/output/

# Quick verification
head /home/claude/nba_data/output/nba_player_points_by_minute_2021_2025.csv
wc -l /home/claude/nba_data/output/nba_player_points_by_minute_2021_2025.csv
```

---

## ESTIMATED PERFORMANCE

### Processing Time
- Single game: ~0.1-0.5 seconds
- Full season (1,230 games): ~2-10 minutes
- All 5 seasons: ~10-50 minutes total

### Output Size
- Long format: ~6-8 million rows
- File size: ~400-500 MB CSV (uncompressed)
- Compressed: ~50-100 MB

### Memory Usage
- Peak: ~2-4 GB RAM
- Process in chunks if memory is limited

---

## TROUBLESHOOTING

### Issue: Missing columns in CSV
**Solution:** Verify you downloaded the correct files from `shufinskiy/nba_data`. Check file headers.

### Issue: Memory error
**Solution:** Process one season at a time, save intermediate results.

### Issue: Duplicate player names
**Solution:** Use PLAYER1_ID instead of PLAYER1_NAME if available.

### Issue: Overtime games
**Solution:** Current code caps at 48 minutes. To track OT separately, modify `calc_elapsed_minutes()`.

---

## FINAL DELIVERABLES

1. **Primary Output:** `/home/claude/nba_data/output/nba_player_points_by_minute_2021_2025.csv`
   - Long format: game_id, player_name, elapsed_minute, cumulative_points
   - Complete 2021-2025 seasons
   
2. **Individual Seasons:** (optional)
   - `/home/claude/nba_data/output/player_points_by_minute_2021.csv`
   - `/home/claude/nba_data/output/player_points_by_minute_2022.csv`
   - etc.

3. **Validation Report:** Console output showing:
   - Total records processed
   - Quality checks passed
   - Sample outputs

---

## NEXT STEPS AFTER COMPLETION

Once you have this database, you can:

1. **Compare to betting lines** (if you get those separately)
2. **Analyze player scoring patterns** (when do they score their points?)
3. **Build predictive models** (predict if player will hit over/under by certain time)
4. **Identify live betting opportunities** (compare live props to actual scoring pace)

Would you like any modifications to this instruction document?