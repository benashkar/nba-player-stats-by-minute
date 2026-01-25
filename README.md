# NBA Player Stats by Minute Database

A complete solution for tracking NBA player statistics minute-by-minute throughout each game.

## Stats Tracked

Per player, per game minute (0-48+):
- **Scoring**: Points, FGM, FGA, FG3M, FG3A, FTM, FTA
- **Rebounds**: Total, Offensive, Defensive
- **Playmaking**: Assists, Turnovers
- **Defense**: Steals, Blocks, Fouls
- **Time**: Minutes Played

## Quick Start

### 1. Install Dependencies

```bash
pip install pandas numpy requests nba_api
```

### 2. Configure Paths

Edit `config.py` to set your data directory:

```python
BASE_PATH = Path("/your/server/path/nba_data")
```

### 3. Run Full Historical Scrape (First Time)

```bash
python run_full_scrape.py
```

This scrapes all data from 2021-22 to present (~30-60 minutes).

### 4. Set Up Daily Updates

Schedule `run_daily_update.py` to run daily at 6:00 AM.

---

## Usage

### Command Line Options

```bash
# Full historical scrape
python nba_pbp_scraper.py --full

# Daily update (yesterday's games)
python nba_pbp_scraper.py --daily

# Specific season
python nba_pbp_scraper.py --season 2024-25

# Date range
python nba_pbp_scraper.py --start 2024-01-01 --end 2024-01-31
```

### Querying the Data

```python
import pandas as pd

# Load data
df = pd.read_csv('output/nba_player_stats_by_minute.csv')

# Average points after 6 minutes
at_6 = df[df['elapsed_minute'] == 6]
player_avg = at_6.groupby('player_name')['cumulative_points'].mean()
print(player_avg.sort_values(ascending=False).head(20))

# Filter by season
season_2024 = df[df['season'] == '2023-24']
```

---

## Scheduling Daily Updates

### Windows Task Scheduler

1. Open Task Scheduler
2. Create Basic Task
3. Name: "NBA Daily Update"
4. Trigger: Daily at 6:00 AM
5. Action: Start a program
6. Program: `python`
7. Arguments: `C:\path\to\run_daily_update.py`
8. Start in: `C:\path\to\project`

### Linux Cron

```bash
# Edit crontab
crontab -e

# Add this line (runs at 6:00 AM daily)
0 6 * * * /usr/bin/python3 /path/to/run_daily_update.py >> /path/to/logs/cron.log 2>&1
```

### Docker (optional)

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
CMD ["python", "run_daily_update.py"]
```

---

## Data Schema

### player_stats_by_minute

| Column | Type | Description |
|--------|------|-------------|
| game_id | string | NBA game ID |
| game_date | string | Game date (YYYY-MM-DD) |
| season | string | Season (e.g., "2024-25") |
| player_name | string | Player name |
| elapsed_minute | int | Game minutes elapsed (0-48+) |
| cumulative_points | int | Total points scored |
| cumulative_rebounds | int | Total rebounds |
| cumulative_offensive_rebounds | int | Offensive rebounds |
| cumulative_defensive_rebounds | int | Defensive rebounds |
| cumulative_assists | int | Total assists |
| cumulative_steals | int | Total steals |
| cumulative_blocks | int | Total blocks |
| cumulative_turnovers | int | Total turnovers |
| cumulative_fouls | int | Total fouls |
| cumulative_fgm | int | Field goals made |
| cumulative_fga | int | Field goals attempted |
| cumulative_fg3m | int | 3-pointers made |
| cumulative_fg3a | int | 3-pointers attempted |
| cumulative_ftm | int | Free throws made |
| cumulative_fta | int | Free throws attempted |
| cumulative_minutes_played | float | Minutes played by the player |

### Example Queries

```python
import pandas as pd

df = pd.read_csv('output/nba_player_stats_by_minute.csv')

# Get final game stats (at minute 48)
final_stats = df[df['elapsed_minute'] == 48]

# Average points after 6 minutes
at_6 = df[df['elapsed_minute'] == 6]
player_avg = at_6.groupby('player_name')['cumulative_points'].mean()

# Total minutes per player per game
game_totals = df.groupby(['game_id', 'player_name']).agg({
    'cumulative_minutes_played': 'max',
    'cumulative_points': 'max'
}).reset_index()

# Stats at end of each quarter
quarters = df[df['elapsed_minute'].isin([12, 24, 36, 48])]
```

---

## Troubleshooting

### Rate Limiting

If you get errors, increase `REQUEST_DELAY` in `config.py`:

```python
REQUEST_DELAY = 0.5  # or higher
```

### Missing Games

Some games may not have play-by-play data available immediately. Run the daily update again the next day.

### Database Locked

If you get SQLite lock errors, ensure only one instance of the scraper is running.

---

## Files

| File | Description |
|------|-------------|
| `nba_pbp_scraper.py` | Main scraper with all functions |
| `config.py` | Configuration settings |
| `run_full_scrape.py` | One-time full historical scrape |
| `run_daily_update.py` | Daily update script for scheduling |
| `analyze_points_by_minute.py` | Analysis utilities |

---

## Data Source

This scraper uses NBA's CDN endpoint (`cdn.nba.com`) which provides reliable play-by-play data. The `nba_api` package is used to get game schedules.
