"""The version information of KentoGo.exe, shown in the "Details" tab of the file's properties.

Used by packaging/windows/kentogo.spec, when the version of a release is written (packaging/version.txt).
Windows keeps a version of four numbers: the version of a release (such as "1.3.2", see
packaging/release_version.py) gets 0 as the fourth.
"""

NAME = "KentoGo"
# English (United States) and Unicode: the language and the code page of the texts below.
LANGUAGE = 0x0409
CODE_PAGE = 1200


def version_numbers(version: str) -> tuple[int, int, int, int]:
    """Make the four numbers of Windows from the version of a release.

    Args:
        version: The version, such as "1.3.2".

    Returns:
        The four numbers, such as (1, 3, 2, 0).
    """
    numbers = tuple(int(part) for part in version.split("."))
    return (*numbers, 0, 0, 0, 0)[:4]


def version_info(version: str):
    """Make PyInstaller's version information of KentoGo.exe.

    Args:
        version: The version of the release, such as "1.3.2".

    Returns:
        A VSVersionInfo, given to EXE(version=...) in the spec.
    """
    from PyInstaller.utils.win32 import versioninfo as info  # Only where the program is made.

    numbers = version_numbers(version)
    texts = {
        "FileDescription": NAME,
        "FileVersion": version,
        "InternalName": NAME,
        "OriginalFilename": f"{NAME}.exe",
        "ProductName": NAME,
        "ProductVersion": version,
    }
    return info.VSVersionInfo(
        ffi=info.FixedFileInfo(
            filevers=numbers,
            prodvers=numbers,
            mask=0x3F,
            flags=0x0,
            OS=0x40004,  # Windows NT.
            fileType=0x1,  # An application.
            subtype=0x0,
            date=(0, 0),
        ),
        kids=[
            info.StringFileInfo(
                [
                    info.StringTable(
                        f"{LANGUAGE:04X}{CODE_PAGE:04X}", [info.StringStruct(*item) for item in texts.items()]
                    )
                ]
            ),
            info.VarFileInfo([info.VarStruct("Translation", [LANGUAGE, CODE_PAGE])]),
        ],
    )
