@echo off
cd /d "C:\Users\cashk\OneDrive\Projects\NBAPlayer Points"
python run_daily_pipeline.py >> logs\scheduled_run.log 2>&1
