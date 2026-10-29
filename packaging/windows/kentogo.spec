# -*- mode: python ; coding: utf-8 -*-
# The PyInstaller settings of KentoGo.exe (Windows). Make it with packaging/windows/build.ps1 (see README.md).
#
# Two programs are made from the same files, as KaTrain does:
#
# - dist/KentoGo.exe: one file with everything in it. It unpacks itself into a temporary folder at
#   each start, so it starts a little slower.
# - dist/KentoGo: a folder with KentoGo.exe in it. It starts faster, and Kivy recommends it.
#
# The data files of KentoGo are put at the same places under "kentogo" as in the source, so the
# code finds them as it does when it runs from the source.

import sys
from pathlib import Path

from kivy.tools.packaging.pyinstaller_hooks import get_deps_all, hookspath, runtime_hooks
from kivy_deps import angle, glew, sdl2

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
VERSION_INFO = None  # The version in the file's properties (see version_info.py).
if VERSION_FILE.is_file():
    DATA.append((VERSION_FILE, "kentogo"))
    sys.path.append(str(HERE))
    from version_info import version_info

    VERSION_INFO = version_info(VERSION_FILE.read_text(encoding="utf-8-sig").strip())

a = Analysis(
    [str(HERE.parent / "kentogo_entry.py")],
    pathex=[str(ROOT / "src")],
    datas=[(str(source), target) for source, target in DATA],
    hookspath=hookspath(),
    runtime_hooks=runtime_hooks(),
    **get_deps_all(),
)
# The DLLs of SDL2, GLEW and ANGLE, which Kivy needs on Windows.
DLLS = [Tree(folder) for folder in (sdl2.dep_bins + glew.dep_bins + angle.dep_bins)]

pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="KentoGo",
    console=False,
    icon=str(HERE.parent / "icons" / "kentogo.ico"),
    version=VERSION_INFO,
    upx=False,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    *DLLS,
    name="KentoGo",
    upx=False,
)
# The program in one file: the same files as the folder, put into the exe. It is made after the
# folder, which is complete by then (the two exe files have the same name).
one_file = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    *DLLS,
    name="KentoGo",
    console=False,
    icon=str(HERE.parent / "icons" / "kentogo.ico"),
    version=VERSION_INFO,
    upx=False,
)
