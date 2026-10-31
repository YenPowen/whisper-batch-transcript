# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec —— 批量提取视频文案 v6（onedir）。"""
import os

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

SPEC_DIR = os.path.dirname(os.path.abspath(SPEC))
PROJECT = os.path.abspath(os.path.join(SPEC_DIR, ".."))
ENTRY = os.path.join(PROJECT, "批量提取视频文案工具v6.py")
ICON = os.path.join(PROJECT, "图片相关_256x256.ico")

datas = []
for pkg in ("whisper", "funasr", "opencc", "modelscope"):
    try:
        datas += collect_data_files(pkg)
    except Exception as exc:  # 缺包时不影响其它部分
        print("collect_data_files failed for", pkg, exc)

hiddenimports = []
hiddenimports += collect_submodules("funasr")
hiddenimports += collect_submodules("whisper")
hiddenimports += [
    "modelscope.hub.snapshot_download",
    "modelscope.hub.api",
    "torchaudio",
    "opencc",
]

a = Analysis(
    [ENTRY],
    pathex=[PROJECT],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[os.path.join(SPEC_DIR, "rthook_gui.py")],
    excludes=[
        "matplotlib", "IPython", "jupyter", "notebook", "pytest",
        "PyQt5", "PyQt6", "PySide2", "PySide6", "wx",
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="批量提取视频文案工具v6",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    icon=ICON if os.path.isfile(ICON) else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="批量提取视频文案工具v6",
)
