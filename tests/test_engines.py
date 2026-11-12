"""Tests for kentogo.engines, with the fake KataGo."""

from dataclasses import replace

import pytest
from fake_engines import fake_katago_settings, make_fake_katago

from kentogo.engines import (
    engine_command_line,
    engines_for,
    measure_katago_speed,
    open_engines,
    start_app_engine,
    start_engine,
)
from kentogo.gui.texts import notice_text
from kentogo.katago.engine_settings import EngineSettings


def test_start_engine_without_katago(tmp_path):
    """Without KataGo, it is not started, and the reason is given."""
    engine, settings, problem = start_engine(EngineSettings(katago=str(tmp_path / "missing"), max_visits=100))
    assert engine is None
    assert settings.max_visits == 100
    assert "not found" in problem


def test_start_engine(tmp_path):
    """KataGo is started with the engine settings, and the visits and noise are used."""
    files = {name: tmp_path / name for name in ("model.bin.gz", "analysis.cfg")}
    for path in files.values():
        path.write_text("x")
    katago = make_fake_katago(tmp_path)
    settings = EngineSettings(
        katago=str(katago),
        model=str(files["model.bin.gz"]),
        config=str(files["analysis.cfg"]),
        max_visits=2500,
        wide_root_noise=0.04,
    )
    engine, evaluation, problem = start_engine(settings)
    try:
        assert problem == ""
        assert engine.is_running
        assert (evaluation.max_visits, evaluation.wide_root_noise) == (2500, 0.04)
    finally:
        engine.close()


def test_engines_are_kept_when_only_the_visits_change(tmp_path):
    """New numbers of visits use the running KataGo; another model starts KataGo again."""
    settings = fake_katago_settings(tmp_path)
    running = engines_for(None, settings, turned_off=False)
    try:
        same = engines_for(running, replace(settings, max_visits=77), turned_off=False)
        assert same.process is running.process and same.notices == () and same.evaluation.max_visits == 77
        (tmp_path / "other.bin.gz").write_text("x")
        other = engines_for(same, replace(settings, model=str(tmp_path / "other.bin.gz")), turned_off=False)
        assert other.process is not running.process and not running.process.is_running
    finally:
        other.close()


def test_loading_follows_the_main_model(tmp_path):
    """The loading stage is the main KataGo, which gets ready; without KataGo there is none."""
    settings = fake_katago_settings(tmp_path)
    engines = open_engines(settings, turned_off=False)
    try:
        stages = engines.loading_stages()
        assert [stage.text_key for stage in stages] == ["loading_main"]
        assert engines.process.wait_until_ready(10)
        assert all(stage.is_ready() and not stage.has_failed() and stage.seconds() is not None for stage in stages)
    finally:
        engines.close()
    assert open_engines(settings, turned_off=True).loading_stages() == []


def test_start_app_engine_when_turned_off(tmp_path):
    """With KataGo turned off, it is not started and has no command line."""
    engine, _, problem = start_app_engine(fake_katago_settings(tmp_path), turned_off=True)
    assert engine is None and problem
    assert engine_command_line(fake_katago_settings(tmp_path), turned_off=True) is None


def test_start_app_engine_tells_when_katago_cannot_start(tmp_path):
    """If KataGo cannot be started, the user is told why. Turning it off is not a problem to tell."""
    notices = []
    engine, _, problem = start_app_engine(EngineSettings(katago=str(tmp_path / "none")), False, notices)
    assert engine is None and problem
    assert len(notices) == 1 and "KataGoを起動できませんでした" in notice_text(notices[0])
    notices.clear()
    start_app_engine(EngineSettings(), turned_off=True, notices=notices)
    assert notices == []


def test_quiz_engines_start_when_asked_and_stop_when_closed(tmp_path):
    """KataGo for the quiz is started by open_engines, and stopped by close (when the quiz ends)."""
    engines = open_engines(fake_katago_settings(tmp_path), turned_off=False)
    process = engines.process
    assert engines.engine is not None and engines.engine_problem == "" and process.is_running
    engines.close()
    assert not process.is_running
    off = open_engines(fake_katago_settings(tmp_path), turned_off=True)
    assert off.engine is None and off.engine_problem != ""
    off.close()  # Nothing to stop.


def test_measure_katago_speed(tmp_path):
    """The speed is measured with a KataGo of its own (the fake one reads every visit at once)."""
    speed = measure_katago_speed(fake_katago_settings(tmp_path))
    assert speed.main > 0


def test_measure_katago_speed_without_katago(tmp_path):
    """When KataGo cannot be started, the error tells why."""
    with pytest.raises(RuntimeError, match="KataGo"):
        measure_katago_speed(EngineSettings(katago=str(tmp_path / "missing")))
