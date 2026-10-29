# -*- mode: python ; coding: utf-8 -*-
# The PyInstaller settings of KentoGo.app (macOS). Make it with packaging/macos/build.sh (see README.md).
#
# The app is made for the processor of the Mac that makes it (Apple silicon or Intel). The data
# files of KentoGo are put at the same places under "kentogo" as in the source, so the code finds
# them as it does when it runs from the source.

import tomllib
from pathlib import Path

from kivy.tools.packaging.pyinstaller_hooks import get_deps_all, hookspath, runtime_hooks

HERE = Path(SPECPATH).resolve()
ROOT = HERE.parents[1]
PACKAGE = ROOT / "src" / "kentogo"

# The data files of KentoGo (tests/test_packaging.py checks that every folder of data is here).
DATA = [
    (PACKAGE / "fonts", "kentogo/fonts"),
    (PACKAGE / "images", "kentogo/images"),
    (PACKAGE / "locales", "kentogo/locales"),
    (PACKAGE / "commentary" / "default_prompt.txt", "kentogo/commentary"),
    (PACKAGE / "commentary" / "default_prompt_en.txt", "kentogo/commentary"),
    (ROOT / "LICENSE", "."),
    (ROOT / "THIRD_PARTY_NOTICES.md", "."),
]
# The version of a release, written by .github/workflows/release.yaml (it is not in git). KentoGo
# shows it at the bottom of the top screen (see kentogo/version.py).
VERSION_FILE = ROOT / "packaging" / "version.txt"
if VERSION_FILE.is_file():
    DATA.append((VERSION_FILE, "kentogo"))
    VERSION = VERSION_FILE.read_text(encoding="utf-8-sig").strip()
else:
    VERSION = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]

a = Analysis(
    [str(HERE.parent / "kentogo_entry.py")],
    pathex=[str(ROOT / "src")],
    datas=[(str(source), target) for source, target in DATA],
    hookspath=hookspath(),
    runtime_hooks=runtime_hooks(),
    **get_deps_all(),
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="KentoGo",
    console=False,
    argv_emulation=False,
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="KentoGo", upx=False)
app = BUNDLE(
    coll,
    name="KentoGo.app",
    icon=str(HERE.parent / "icons" / "kentogo.icns"),
    bundle_identifier="org.kentogo.KentoGo",
    version=VERSION,
    info_plist={
        "CFBundleDisplayName": "KentoGo",
        "CFBundleShortVersionString": VERSION,
        "NSHighResolutionCapable": True,
    },
)
