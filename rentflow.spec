# PyInstaller spec — build with:  pyinstaller rentflow.spec
# Produces dist/RentFlow/RentFlow.exe (windowed, no console).
from PyInstaller.utils.hooks import collect_submodules

hiddenimports = (
    collect_submodules("django")
    + collect_submodules("accounts")
    + collect_submodules("properties")
    + collect_submodules("payments")
    + collect_submodules("dashboard")
    + collect_submodules("reportlab")
    + ["waitress", "dateutil", "PIL"]
)

a = Analysis(
    ["desktop.py"],
    pathex=["."],
    binaries=[],
    datas=[
        ("templates", "templates"),
        ("static", "static"),
        ("config", "config"),
        ("accounts", "accounts"),
        ("properties", "properties"),
        ("payments", "payments"),
        ("dashboard", "dashboard"),
    ],
    hiddenimports=hiddenimports,
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="RentFlow",
    console=False,          # windowed app — no terminal
    icon="static/images/logo/rentflow-mark.png",
)
coll = COLLECT(exe, a.binaries, a.datas, name="RentFlow")
