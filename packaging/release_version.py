"""Print the version of a release of KentoGo, made from the time of the last commit.

Used by .github/workflows/release.yaml. The hour of the commit is the major version, the minute
the minor version and the second the patch: a commit made at 01:02:00 is version 1.2.0. The time
is read in the time zone written in the commit (the one it was made in), not in that of the
computer that runs this (GitHub's computers use UTC).
"""

import subprocess
from datetime import datetime


def version_of(commit_date: str) -> str:
    """Make the version from the date of a commit.

    Args:
        commit_date: The date in ISO 8601 with its time zone, as `git log --format=%cI` writes it.

    Returns:
        The version, such as "1.2.0" (the numbers have no leading zeros).
    """
    time = datetime.fromisoformat(commit_date)
    return f"{time.hour}.{time.minute}.{time.second}"


def last_commit_date() -> str:
    """Read the date of the last commit (its committer date) in ISO 8601."""
    result = subprocess.run(["git", "log", "-1", "--format=%cI"], check=True, capture_output=True, text=True)
    return result.stdout.strip()


if __name__ == "__main__":
    print(version_of(last_commit_date()))
