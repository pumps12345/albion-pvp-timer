# PyInstaller build:  .venv/Scripts/pyinstaller pvptimer.spec --noconfirm
# MODEL must equal pvptimer.paths.MODEL_NAME.
from PyInstaller.utils.hooks import collect_dynamic_libs

MODEL = "vosk-model-small-en-us-0.15"

a = Analysis(
    ["src/pvptimer/__main__.py"],
    pathex=["src"],
    binaries=collect_dynamic_libs("vosk"),
    datas=[
        ("src/pvptimer/data", "pvptimer/data"),
        (f"models/{MODEL}", f"models/{MODEL}"),
    ],
    hiddenimports=["pynput.keyboard._win32", "pynput.mouse._win32"],
    excludes=["tkinter"],
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="PVPTimer", console=False, upx=False)
coll = COLLECT(exe, a.binaries, a.datas, name="PVPTimer", upx=False)
