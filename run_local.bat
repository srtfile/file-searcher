@echo off
setlocal
cd /d "%~dp0"

REM Change this to the folder you want to search on your Windows PC.
set "SEARCH_ROOT=C:\Users\AC\Desktop"
set "AUTH_TOKEN=local123"

py -3 -m pip install -r requirements.txt
py -3 app.py
pause
