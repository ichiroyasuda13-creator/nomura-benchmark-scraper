@echo off
chcp 65001 > nul
echo ========================================================
echo   AM Intelligence Terminal (Nomura / Daiwa / MUAM)
echo   Starting local dashboard...
echo ========================================================
cd /d "%~dp0"
call .venv\Scripts\streamlit run streamlit_app.py
pause
