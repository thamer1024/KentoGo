"""Tests for kentogo.katago.startup."""

from pathlib import Path

from kentogo.katago.startup import Loading, LoadingStage, LoadingState, StartTimes


class Clock:
    """A clock that the test moves."""

    def __init__(self):
        self.now = 100.0

    def __call__(self) -> float:
        return self.now


class FakeKataGo:
    """A KataGo that the test makes ready or failed."""

    def __init__(self, seconds: float = 0.0):
        self.ready = False
        self.failed = False
        self.seconds = seconds

    def stage(self, text_key: str, key: str) -> LoadingStage:
        return LoadingStage(
            text_key, key, lambda: self.ready, lambda: self.failed, lambda: self.seconds if self.ready else None
        )


def test_start_times_are_kept_in_a_file(tmp_path):
    """The loading time of each command line is written, and read at the next start."""
    path = tmp_path / "times.json"
    times = StartTimes(path)
    assert times.expected("katago main") is None
    times.remember("katago main", 12.34)
    assert StartTimes(path).expected("katago main") == 12.3


def test_the_file_is_made_in_the_home_folder(tmp_path, monkeypatch):
    """A path that starts with "~" is in the home folder, and its folder is made when it is missing."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))  # The home folder on Windows.
    StartTimes(Path("~/.kentogo/times.json")).remember("katago main", 5.0)
    assert (tmp_path / ".kentogo" / "times.json").exists()
    assert StartTimes(Path("~/.kentogo/times.json")).expected("katago main") == 5.0


def test_a_broken_file_is_no_times(tmp_path):
    """A file that cannot be read gives no times, and is written again when a time is kept."""
    path = tmp_path / "times.json"
    path.write_text("not json")
    times = StartTimes(path)
    assert times.expected("x") is None
    times.remember("x", 3.0)
    assert StartTimes(path).expected("x") == 3.0
    StartTimes(None).remember("x", 1.0)  # Nothing is written without a file.


def test_the_stages_follow_one_after_the_other():
    """The main model is loaded first, then the comparison model; the times are kept for the next start."""
    clock, times = Clock(), StartTimes(None)
    times.remember("compare", 20.0)
    main, compare = FakeKataGo(8.0), FakeKataGo(15.0)
    loading = Loading([main.stage("loading_main", "main"), compare.stage("loading_compare", "compare")], times, clock)
    clock.now += 3
    assert loading.update() == LoadingState("loading_main", 3.0, None)
    main.ready = True
    clock.now += 5
    state = loading.update()
    assert state == LoadingState("loading_compare", 0.0, 20.0) and state.remaining == 20.0
    clock.now += 25
    assert loading.update().remaining is None  # Longer than last time: only the time passed is shown.
    compare.ready = True
    assert loading.update() is None
    assert (times.expected("main"), times.expected("compare")) == (8.0, 15.0)


def test_a_failed_stage_is_passed():
    """A KataGo that cannot start does not stop the loading; its time is not kept."""
    times = StartTimes(None)
    main = FakeKataGo()
    main.failed = True
    assert Loading([main.stage("loading_main", "main")], times, Clock()).update() is None
    assert times.expected("main") is None
