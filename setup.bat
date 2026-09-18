@echo off
REM Windows Batch Setup Script for DeBERTa-v3 Discord Bot
title DeBERTa-v3 Bot Setup

echo ========================================================
echo Starting DeBERTa-v3 Dependencies and Model Setup...
echo ========================================================

REM Check for virtualenv python first
if exist "C:\Users\LorenzoPezo\v\Scripts\python.exe" (
    set PYTHON_EXE="C:\Users\LorenzoPezo\v\Scripts\python.exe"
) else (
    set PYTHON_EXE=python
)

%PYTHON_EXE% setup_environment.py

pause
