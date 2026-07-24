@echo off
cd /d "%~dp0"
echo Installing/updating dependencies...
pip install -r requirements.txt -q
echo Starting E-WAY Invoice Auditor on port 8502...
python -m streamlit run app.py --server.port 8502
pause
