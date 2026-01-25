-- ============================================================================
-- NBA Player Stats by Minute - MySQL Schema
-- Optimized for queries on players, stats, date ranges, and seasons
-- ============================================================================

-- Drop existing tables if they exist
DROP TABLE IF EXISTS player_stats_by_minute;
DROP TABLE IF EXISTS games;
DROP TABLE IF EXISTS players;

-- ============================================================================
-- PLAYERS TABLE
-- Normalized player lookup with auto-increment ID for faster joins
-- ============================================================================
CREATE TABLE players (
    player_id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    player_name VARCHAR(100) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY idx_player_name (player_name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================================
-- GAMES TABLE
-- Normalized game lookup for faster joins and game-level queries
-- ============================================================================
CREATE TABLE games (
    game_id VARCHAR(20) PRIMARY KEY,
    game_date DATE NOT NULL,
    season VARCHAR(10) NOT NULL,
    season_year SMALLINT UNSIGNED NOT NULL,  -- For partitioning (e.g., 2021, 2022)
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    INDEX idx_game_date (game_date),
    INDEX idx_season (season),
    INDEX idx_season_year (season_year),
    INDEX idx_season_date (season, game_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ============================================================================
-- PLAYER STATS BY MINUTE TABLE (PARTITIONED)
-- Main stats table partitioned by season for fast queries
-- ============================================================================
CREATE TABLE player_stats_by_minute (
    id BIGINT UNSIGNED AUTO_INCREMENT,
    player_id INT UNSIGNED NOT NULL,
    game_id VARCHAR(20) NOT NULL,
    elapsed_minute TINYINT UNSIGNED NOT NULL,
    season_year SMALLINT UNSIGNED NOT NULL,  -- Partition key

    -- Cumulative stats at this minute
    pts SMALLINT UNSIGNED DEFAULT 0,
    reb SMALLINT UNSIGNED DEFAULT 0,
    oreb SMALLINT UNSIGNED DEFAULT 0,
    dreb SMALLINT UNSIGNED DEFAULT 0,
    ast SMALLINT UNSIGNED DEFAULT 0,
    stl SMALLINT UNSIGNED DEFAULT 0,
    blk SMALLINT UNSIGNED DEFAULT 0,
    tov SMALLINT UNSIGNED DEFAULT 0,
    pf SMALLINT UNSIGNED DEFAULT 0,
    fgm SMALLINT UNSIGNED DEFAULT 0,
    fga SMALLINT UNSIGNED DEFAULT 0,
    fg3m SMALLINT UNSIGNED DEFAULT 0,
    fg3a SMALLINT UNSIGNED DEFAULT 0,
    ftm SMALLINT UNSIGNED DEFAULT 0,
    fta SMALLINT UNSIGNED DEFAULT 0,
    min_played DECIMAL(4,1) DEFAULT 0.0,

    PRIMARY KEY (id, season_year),

    -- Key indexes for common queries
    INDEX idx_player_game (player_id, game_id),
    INDEX idx_player_season (player_id, season_year),
    INDEX idx_player_minute (player_id, elapsed_minute),
    INDEX idx_game_minute (game_id, elapsed_minute),

    -- Foreign keys (commented out for faster bulk inserts, enable after)
    -- CONSTRAINT fk_player FOREIGN KEY (player_id) REFERENCES players(player_id),
    -- CONSTRAINT fk_game FOREIGN KEY (game_id) REFERENCES games(game_id)

    UNIQUE KEY uk_player_game_minute (player_id, game_id, elapsed_minute, season_year)

) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
PARTITION BY RANGE (season_year) (
    PARTITION p2021 VALUES LESS THAN (2022),
    PARTITION p2022 VALUES LESS THAN (2023),
    PARTITION p2023 VALUES LESS THAN (2024),
    PARTITION p2024 VALUES LESS THAN (2025),
    PARTITION p2025 VALUES LESS THAN (2026),
    PARTITION p2026 VALUES LESS THAN (2027),
    PARTITION p_future VALUES LESS THAN MAXVALUE
);

-- ============================================================================
-- GAME TOTALS VIEW (Materialized as table for fast queries)
-- Pre-aggregated final stats per player per game
-- ============================================================================
CREATE TABLE player_game_totals (
    player_id INT UNSIGNED NOT NULL,
    game_id VARCHAR(20) NOT NULL,
    game_date DATE NOT NULL,
    season VARCHAR(10) NOT NULL,
    season_year SMALLINT UNSIGNED NOT NULL,

    -- Final game stats (at max minute)
    pts SMALLINT UNSIGNED DEFAULT 0,
    reb SMALLINT UNSIGNED DEFAULT 0,
    oreb SMALLINT UNSIGNED DEFAULT 0,
    dreb SMALLINT UNSIGNED DEFAULT 0,
    ast SMALLINT UNSIGNED DEFAULT 0,
    stl SMALLINT UNSIGNED DEFAULT 0,
    blk SMALLINT UNSIGNED DEFAULT 0,
    tov SMALLINT UNSIGNED DEFAULT 0,
    pf SMALLINT UNSIGNED DEFAULT 0,
    fgm SMALLINT UNSIGNED DEFAULT 0,
    fga SMALLINT UNSIGNED DEFAULT 0,
    fg3m SMALLINT UNSIGNED DEFAULT 0,
    fg3a SMALLINT UNSIGNED DEFAULT 0,
    ftm SMALLINT UNSIGNED DEFAULT 0,
    fta SMALLINT UNSIGNED DEFAULT 0,
    min_played DECIMAL(4,1) DEFAULT 0.0,

    PRIMARY KEY (player_id, game_id),

    -- Indexes for common queries
    INDEX idx_player_date (player_id, game_date),
    INDEX idx_player_season (player_id, season_year),
    INDEX idx_season_date (season_year, game_date),
    INDEX idx_game_date (game_date),

    -- Indexes on each stat for "top performers" queries
    INDEX idx_pts (pts DESC),
    INDEX idx_reb (reb DESC),
    INDEX idx_ast (ast DESC),
    INDEX idx_stl (stl DESC),
    INDEX idx_blk (blk DESC)

) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
PARTITION BY RANGE (season_year) (
    PARTITION p2021 VALUES LESS THAN (2022),
    PARTITION p2022 VALUES LESS THAN (2023),
    PARTITION p2023 VALUES LESS THAN (2024),
    PARTITION p2024 VALUES LESS THAN (2025),
    PARTITION p2025 VALUES LESS THAN (2026),
    PARTITION p2026 VALUES LESS THAN (2027),
    PARTITION p_future VALUES LESS THAN MAXVALUE
);

-- ============================================================================
-- USEFUL VIEWS
-- ============================================================================

-- View: Join stats with player names for easy querying
CREATE OR REPLACE VIEW v_player_stats AS
SELECT
    p.player_name,
    g.game_date,
    g.season,
    s.game_id,
    s.elapsed_minute,
    s.pts, s.reb, s.oreb, s.dreb, s.ast, s.stl, s.blk, s.tov, s.pf,
    s.fgm, s.fga, s.fg3m, s.fg3a, s.ftm, s.fta, s.min_played
FROM player_stats_by_minute s
JOIN players p ON s.player_id = p.player_id
JOIN games g ON s.game_id = g.game_id;

-- View: Game totals with player names
CREATE OR REPLACE VIEW v_player_game_totals AS
SELECT
    p.player_name,
    t.game_date,
    t.season,
    t.game_id,
    t.pts, t.reb, t.oreb, t.dreb, t.ast, t.stl, t.blk, t.tov, t.pf,
    t.fgm, t.fga, t.fg3m, t.fg3a, t.ftm, t.fta, t.min_played,
    CASE WHEN t.fga > 0 THEN ROUND(t.fgm / t.fga * 100, 1) ELSE 0 END AS fg_pct,
    CASE WHEN t.fg3a > 0 THEN ROUND(t.fg3m / t.fg3a * 100, 1) ELSE 0 END AS fg3_pct,
    CASE WHEN t.fta > 0 THEN ROUND(t.ftm / t.fta * 100, 1) ELSE 0 END AS ft_pct
FROM player_game_totals t
JOIN players p ON t.player_id = p.player_id;

-- ============================================================================
-- EXAMPLE QUERIES
-- ============================================================================

-- Query 1: Player's average stats over last N games
-- SELECT player_name,
--        AVG(pts) as avg_pts, AVG(reb) as avg_reb, AVG(ast) as avg_ast
-- FROM v_player_game_totals
-- WHERE player_name = 'A. Edwards'
-- ORDER BY game_date DESC
-- LIMIT 10;

-- Query 2: Player stats at specific minute across a season
-- SELECT player_name,
--        AVG(pts) as avg_pts_at_min_8, COUNT(*) as games
-- FROM v_player_stats
-- WHERE player_name = 'A. Edwards'
--   AND elapsed_minute = 8
--   AND season = '2023-24'
-- GROUP BY player_name;

-- Query 3: Top scorers in a date range
-- SELECT player_name, AVG(pts) as avg_pts, COUNT(*) as games
-- FROM v_player_game_totals
-- WHERE game_date BETWEEN '2024-01-01' AND '2024-01-31'
-- GROUP BY player_name
-- HAVING games >= 5
-- ORDER BY avg_pts DESC
-- LIMIT 20;

-- Query 4: Player performance when scoring X points by minute Y
-- SELECT player_name,
--        AVG(final.pts) as avg_final_pts,
--        COUNT(*) as games
-- FROM v_player_stats early
-- JOIN v_player_game_totals final
--   ON early.player_name = final.player_name AND early.game_id = final.game_id
-- WHERE early.player_name = 'A. Edwards'
--   AND early.elapsed_minute = 8
--   AND early.pts <= 4
-- GROUP BY early.player_name;

-- ============================================================================
-- Q1 PERFORMANCE ANALYSIS VIEWS
-- For analyzing final game totals based on Q1 (first 12 minutes) performance
-- ============================================================================

-- View: Q1 stats joined with final game totals
-- This is the core view for Q1 prediction analysis
CREATE OR REPLACE VIEW v_q1_vs_final AS
SELECT
    p.player_name,
    g.game_date,
    g.season,
    g.season_year,
    q1.game_id,

    -- Q1 stats (at minute 12)
    q1.pts AS q1_pts,
    q1.reb AS q1_reb,
    q1.ast AS q1_ast,
    q1.min_played AS q1_min,
    q1.fgm AS q1_fgm,
    q1.fga AS q1_fga,
    q1.fg3m AS q1_fg3m,
    q1.fg3a AS q1_fg3a,

    -- Final game stats
    f.pts AS final_pts,
    f.reb AS final_reb,
    f.ast AS final_ast,
    f.min_played AS final_min,
    f.fgm AS final_fgm,
    f.fga AS final_fga,
    f.fg3m AS final_fg3m,
    f.fg3a AS final_fg3a

FROM player_stats_by_minute q1
JOIN players p ON q1.player_id = p.player_id
JOIN games g ON q1.game_id = g.game_id
JOIN player_game_totals f ON q1.player_id = f.player_id AND q1.game_id = f.game_id
WHERE q1.elapsed_minute = 12;

-- ============================================================================
-- Q1 ANALYSIS QUERIES
-- ============================================================================

-- Query: Anthony Edwards - games with 4 or less Q1 points (2024-25, 2025-26)
-- Shows mean, count, min, max for final points
/*
SELECT
    player_name,
    COUNT(*) AS games,
    ROUND(AVG(final_pts), 2) AS mean_final_pts,
    ROUND(MIN(final_pts), 0) AS min_pts,
    ROUND(MAX(final_pts), 0) AS max_pts,
    ROUND(STDDEV_SAMP(final_pts), 2) AS std_dev,
    ROUND(STDDEV_SAMP(final_pts) / AVG(final_pts) * 100, 1) AS std_pct
FROM v_q1_vs_final
WHERE player_name = 'A. Edwards'
  AND q1_pts <= 4
  AND season_year IN (2024, 2025)
GROUP BY player_name;
*/

-- Query: Get all Q1 ranges for a player with statistics
/*
SELECT
    player_name,
    CASE
        WHEN q1_pts <= 2 THEN '0-2'
        WHEN q1_pts <= 4 THEN '3-4'
        WHEN q1_pts <= 7 THEN '5-7'
        WHEN q1_pts <= 10 THEN '8-10'
        WHEN q1_pts <= 14 THEN '11-14'
        ELSE '15+'
    END AS q1_range,
    COUNT(*) AS games,
    ROUND(AVG(final_pts), 1) AS mean_pts,
    ROUND(STDDEV_SAMP(final_pts), 1) AS std_dev,
    MIN(final_pts) AS min_pts,
    MAX(final_pts) AS max_pts
FROM v_q1_vs_final
WHERE player_name = 'A. Edwards'
  AND season_year IN (2024, 2025)
GROUP BY player_name,
    CASE
        WHEN q1_pts <= 2 THEN '0-2'
        WHEN q1_pts <= 4 THEN '3-4'
        WHEN q1_pts <= 7 THEN '5-7'
        WHEN q1_pts <= 10 THEN '8-10'
        WHEN q1_pts <= 14 THEN '11-14'
        ELSE '15+'
    END
ORDER BY MIN(q1_pts);
*/

-- Query: Get individual games for a player with Q1 filter
/*
SELECT
    player_name,
    game_date,
    season,
    q1_pts,
    final_pts
FROM v_q1_vs_final
WHERE player_name = 'A. Edwards'
  AND q1_pts <= 4
  AND season_year IN (2024, 2025)
ORDER BY game_date;
*/

-- Query: Percentile calculation using window functions (MySQL 8.0+)
-- Gets the TOP outcome thresholds (top 10%, 25%, 33%, 40%, 50%)
/*
WITH ranked AS (
    SELECT
        player_name,
        final_pts,
        PERCENT_RANK() OVER (ORDER BY final_pts DESC) AS pct_rank,
        COUNT(*) OVER () AS total_games
    FROM v_q1_vs_final
    WHERE player_name = 'A. Edwards'
      AND q1_pts <= 4
      AND season_year IN (2024, 2025)
)
SELECT
    player_name,
    MAX(total_games) AS games_in_sample,
    MIN(CASE WHEN pct_rank <= 0.10 THEN final_pts END) AS top_10_pct,
    MIN(CASE WHEN pct_rank <= 0.25 THEN final_pts END) AS top_25_pct,
    MIN(CASE WHEN pct_rank <= 0.33 THEN final_pts END) AS top_33_pct,
    MIN(CASE WHEN pct_rank <= 0.40 THEN final_pts END) AS top_40_pct,
    MIN(CASE WHEN pct_rank <= 0.50 THEN final_pts END) AS median_top_50_pct
FROM ranked
GROUP BY player_name;
*/

-- Query: Complete analysis with all stats and percentiles
/*
SELECT
    player_name,
    COUNT(*) AS games,
    ROUND(AVG(final_pts), 2) AS mean_pts,
    ROUND(STDDEV_SAMP(final_pts), 2) AS std_dev,
    ROUND(STDDEV_SAMP(final_pts) / AVG(final_pts) * 100, 1) AS std_pct,
    MIN(final_pts) AS min_pts,
    MAX(final_pts) AS max_pts
FROM v_q1_vs_final
WHERE player_name = 'A. Edwards'
  AND q1_pts <= 4
  AND season_year IN (2024, 2025)
GROUP BY player_name;
*/

-- ============================================================================
-- STORED PROCEDURE: Analyze Q1 Performance
-- Call with: CALL sp_analyze_q1('A. Edwards', 0, 4, 2024, 2025);
-- ============================================================================

/*
DELIMITER //

CREATE PROCEDURE sp_analyze_q1(
    IN p_player_name VARCHAR(100),
    IN p_q1_min INT,
    IN p_q1_max INT,
    IN p_season_start INT,
    IN p_season_end INT
)
BEGIN
    -- Basic statistics
    SELECT
        player_name,
        COUNT(*) AS games,
        ROUND(AVG(final_pts), 2) AS mean_pts,
        ROUND(STDDEV_SAMP(final_pts), 2) AS std_dev,
        ROUND(STDDEV_SAMP(final_pts) / AVG(final_pts) * 100, 1) AS std_pct,
        MIN(final_pts) AS min_pts,
        MAX(final_pts) AS max_pts
    FROM v_q1_vs_final
    WHERE player_name = p_player_name
      AND q1_pts >= p_q1_min
      AND q1_pts <= p_q1_max
      AND season_year BETWEEN p_season_start AND p_season_end
    GROUP BY player_name;

    -- Individual games
    SELECT
        game_date,
        season,
        q1_pts,
        final_pts
    FROM v_q1_vs_final
    WHERE player_name = p_player_name
      AND q1_pts >= p_q1_min
      AND q1_pts <= p_q1_max
      AND season_year BETWEEN p_season_start AND p_season_end
    ORDER BY game_date;
END //

DELIMITER ;
*/
