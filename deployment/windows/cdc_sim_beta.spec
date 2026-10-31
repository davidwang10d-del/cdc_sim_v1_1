# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller one-folder build for CDC Sim's supported Windows beta."""

from pathlib import Path
import json
import os
import sys


spec_dir = Path(SPEC).resolve().parent
sys.path.insert(0, str(spec_dir))
from release_tools import load_release_config, pyinstaller_data
from PyInstaller.utils.hooks import collect_submodules


source_root = Path(os.environ["CDC_BUILD_SOURCE_ROOT"]).resolve()
config_path = Path(os.environ["CDC_BUILD_RELEASE_CONFIG"]).resolve()
build_info_path = Path(os.environ["CDC_BUILD_INFO_FILE"]).resolve()
version_info_path = Path(os.environ["CDC_BUILD_VERSION_INFO"]).resolve()
config = load_release_config(config_path)

datas = pyinstaller_data(source_root, config_path, build_info_path)
hidden_imports = collect_submodules("rasterio")

a = Analysis(
    [str(spec_dir / "launcher.py")],
    pathex=[str(source_root), str(spec_dir)],
    binaries=[],
    datas=datas,
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["pytest", "IPython", "notebook", "matplotlib", "requests"],
    noarchive=False,
    optimize=1,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=Path(config["executable_name"]).stem,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    version=str(version_info_path),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name=config["bundle_name"],
)
