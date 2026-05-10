@echo off
title Snehin Check Request Helper V2.0.0
color 0A

echo.
echo  ====================================================
echo   SNEHIN CHECK REQUEST HELPER  -  V2.0.0
echo   A Project by Wasi Mahin
echo  ====================================================
echo.
echo  Launching...
echo.

py -3.13 app.py

if %errorlevel% neq 0 (
    echo.
    echo  ERROR: App exited with code %errorlevel%
    echo  Check last_error.log for details.
    pause
)
