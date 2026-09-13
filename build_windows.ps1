# ============================================================
# RentFlow — Windows desktop build script (run in PowerShell)
# ============================================================
# One-time prerequisites:
#   1. Install Python 3.11+ from https://www.python.org/downloads/
#      (tick "Add python.exe to PATH" during install)
#   2. Open PowerShell in this folder and run:  .\build_windows.ps1
# ------------------------------------------------------------

# 1. Create & activate a virtual environment
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# 2. Install runtime + desktop + build dependencies
pip install --upgrade pip
pip install -r requirements.txt
pip install pywebview pyinstaller

# 3. Prepare the database and demo data (first run only)
python manage.py migrate
python manage.py seed_demo

# 4. (Optional) quick test as a desktop window before packaging
#    python desktop.py

# 5. Build the standalone Windows app
pyinstaller rentflow.spec --noconfirm

Write-Host ""
Write-Host "Done. Your Windows app is at:  dist\RentFlow\RentFlow.exe" -ForegroundColor Green
Write-Host "Copy the whole dist\RentFlow folder anywhere - no Python needed on the target PC."
Write-Host "Default login: admin / rentflow123"
