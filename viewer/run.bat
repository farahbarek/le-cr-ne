@echo off
rem Lance l'interface web (Windows). Double-cliquer sur ce fichier.
cd /d "%~dp0.."

if not exist venv (
  echo Creation de l'environnement Python (premiere fois seulement)...
  python -m venv venv || goto :error
  venv\Scripts\python -m pip install --upgrade pip || goto :error
  venv\Scripts\pip install -r requirements.txt || goto :error
  venv\Scripts\pip install -r viewer\requirements.txt || goto :error
)

start "" http://127.0.0.1:5000
venv\Scripts\python viewer\app.py
goto :eof

:error
echo.
echo Une erreur est survenue. Verifiez que Python 3.11 ou plus recent est installe.
pause
