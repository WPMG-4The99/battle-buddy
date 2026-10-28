# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec. Windowed onedir. BattleBuddy.exe. No account."""

from PyInstaller.utils.hooks import collect_submodules
from PyInstaller.utils.win32.versioninfo import (
    FixedFileInfo,
    StringFileInfo,
    StringStruct,
    StringTable,
    VarFileInfo,
    VarStruct,
    VSVersionInfo,
)

from battlebuddy import __version__

# Hiddenimports must cover battlebuddy.* and tkinter. Listed so a Linux
# smoke test can read the names without running PyInstaller.
_BATTLEBUDDY_MODULES = [
    "battlebuddy",
    "battlebuddy.ui",
    "battlebuddy.ui.app",
    "battlebuddy.reminders",
    "battlebuddy.reminders.commands",
    "battlebuddy.reminders.engine",
    "battlebuddy.reminders.notify",
    "battlebuddy.reminders.parse",
    "battlebuddy.reminders.warn",
    "battlebuddy.databank",
    "battlebuddy.databank.clean",
    "battlebuddy.databank.fetch",
    "battlebuddy.databank.reason",
    "battlebuddy.databank.search",
    "battlebuddy.databank.slug",
    "battlebuddy.databank.store",
    "battlebuddy.databank.wiki",
    "battlebuddy.xai",
    "battlebuddy.xai.loop",
    "battlebuddy.game_detect",
    "battlebuddy.game_detect.names",
    "battlebuddy.game_detect.scan",
    "battlebuddy.voice",
    "battlebuddy.voice.stt",
    "battlebuddy.voice.tts",
    "battlebuddy.voice.tick",
    "battlebuddy.memory",
    "battlebuddy.memory.store",
    "battlebuddy.memory.catalog",
    "battlebuddy.win_entry",
    "battlebuddy.readthis",
    "battlebuddy.readthis.capture",
    "battlebuddy.readthis.clean",
    "battlebuddy.readthis.config",
    "battlebuddy.readthis.hints",
    "battlebuddy.readthis.hotkey",
    "battlebuddy.readthis.listen",
    "battlebuddy.readthis.ocr",
    "battlebuddy.readthis.overlay",
    "battlebuddy.readthis.region",
    "battlebuddy.readthis.screen",
    "battlebuddy.readthis.service",
    "battlebuddy.snap",
    "battlebuddy.snap.answer",
    "battlebuddy.snap.config",
    "battlebuddy.snap.context",
    "battlebuddy.snap.facts",
    "battlebuddy.snap.pipeline",
    "battlebuddy.snap.service",
    "battlebuddy.snap.shots",
    "battlebuddy.ui.layout",
    "battlebuddy.ui.hud",
    "battlebuddy.ui.tray",
    "battlebuddy.ui.overlay_model",
    "battlebuddy.ui.overlay_win",
    "battlebuddy.ui.overlay_hotkey",
    "battlebuddy.ui.context_menu",
    "battlebuddy.ui.multiline",
]

_BUNDLED_EXTRAS = [
    "pystray",
    "PIL",
    "PIL.Image",
    "PIL.ImageDraw",
    "mss",
    "pytesseract",
    "winsdk",
]

hiddenimports = [
    "tkinter",
    "tkinter.font",
    "tkinter.messagebox",
    "tkinter.ttk",
    "_tkinter",
    "winsound",
    *_BATTLEBUDDY_MODULES,
    *_BUNDLED_EXTRAS,
]

try:
    hiddenimports.extend(collect_submodules("battlebuddy"))
except Exception:
    pass

# Optional Windows SAPI / STT / TTS extras. Missing must not fail the build
# or crash the UI. Voice already falls back to PowerShell SAPI or typed input.
for _optional in (
    "speech_recognition",
    "pocketsphinx",
    "pyttsx3",
    "win32com",
    "win32com.client",
    "pythoncom",
    "pystray",
    "PIL",
    "mss",
    "pytesseract",
    "winsdk",
):
    try:
        hiddenimports.extend(collect_submodules(_optional))
    except Exception:
        pass


def _file_version(raw: str) -> tuple[int, int, int, int]:
    parts: list[int] = []
    for chunk in raw.split("."):
        digits = "".join(ch for ch in chunk if ch.isdigit())
        parts.append(int(digits) if digits else 0)
        if len(parts) == 4:
            break
    while len(parts) < 4:
        parts.append(0)
    return parts[0], parts[1], parts[2], parts[3]


_ver = _file_version(__version__)
version_info = VSVersionInfo(
    ffi=FixedFileInfo(
        filevers=_ver,
        prodvers=_ver,
        mask=0x3F,
        flags=0x0,
        OS=0x40004,
        fileType=0x1,
        subtype=0x0,
        date=(0, 0),
    ),
    kids=[
        StringFileInfo(
            [
                StringTable(
                    "040904B0",
                    [
                        StringStruct("CompanyName", "Captain Phyre"),
                        StringStruct("FileDescription", "Battle Buddy"),
                        StringStruct("FileVersion", __version__),
                        StringStruct("InternalName", "BattleBuddy"),
                        StringStruct("LegalCopyright", "MIT"),
                        StringStruct("OriginalFilename", "BattleBuddy.exe"),
                        StringStruct("ProductName", "Battle Buddy"),
                        StringStruct("ProductVersion", __version__),
                    ],
                )
            ]
        ),
        VarFileInfo([VarStruct("Translation", [1033, 1200])]),
    ],
)

a = Analysis(
    ["battlebuddy/win_entry.py"],
    pathex=[],
    binaries=[],
    # GGUF and llama-server stay in dist/BattleBuddy/llm after the build script.
    # Do not embed them in the PYZ.
    datas=[],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="BattleBuddy",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    version=version_info,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="BattleBuddy",
)
