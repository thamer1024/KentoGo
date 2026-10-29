"""Tests for kentogo.engines, with the fake KataGo."""

from dataclasses import replace

import pytest
from fake_engines import fake_katago_settings, make_fake_katago, started_in_the_background

from kentogo.engines import (
    COMPARE_CACHE,
    engines_for,
    make_command,
    measure_katago_speed,
    open_engines,
    start_engine,
    start_engines,
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


def test_start_engines_with_the_comparison_model(tmp_path):
    """With the comparison model turned on, a second KataGo is started when it is first needed."""
    settings = fake_katago_settings(tmp_path, compare_model=str(tmp_path / "normal.bin.gz"), use_compare=True)
    engine, compare, _, problem = start_engines(settings, turned_off=False)
    try:
        assert problem == "" and engine.is_running and not compare.is_running
        answers = []
        compare.query({"moves": []}, answers.append)
        assert compare.is_running  # Started by the first query.
        compare.stop()
        assert not compare.is_running
        assert "normal.bin.gz" in " ".join(compare.command.command)
        assert "-human-model" not in compare.command.command
        # The settings of the queries are on the command line, so a humanSLProfile in the file does no harm.
        assert compare.command.settings_in_command and not engine.command.settings_in_command
        assert "reportAnalysisWinratesAs=BLACK" in compare.command.command[-1]
    finally:
        engine.close()
        compare.close()


def test_quiz_starts_the_comparison_model_after_the_main_one(tmp_path):
    """In the quiz, the comparison model's KataGo is started when the main KataGo is ready."""
    settings = fake_katago_settings(tmp_path, compare_model=str(tmp_path / "normal.bin.gz"), use_compare=True)
    engines = open_engines(settings, turned_off=False)
    try:
        main, compare = engines.processes
        assert main.wait_until_ready(10) and started_in_the_background(compare)
    finally:
        engines.close()
    assert not compare.is_running


def test_engines_are_kept_when_only_the_visits_change(tmp_path):
    """New numbers of visits use the running KataGo; another model starts KataGo again."""
    settings = fake_katago_settings(tmp_path, compare_model=str(tmp_path / "normal.bin.gz"), use_compare=True)
    running = engines_for(None, settings, turned_off=False)
    try:
        same = engines_for(running, replace(settings, max_visits=77, compare_max_visits=11), turned_off=False)
        assert same.processes == running.processes and same.notices == ()
        assert (same.evaluation.max_visits, same.compare_evaluation.max_visits) == (77, 11)
        (tmp_path / "other.bin.gz").write_text("x")
        other = engines_for(same, replace(settings, model=str(tmp_path / "other.bin.gz")), turned_off=False)
        assert other.processes != running.processes and not running.processes[0].is_running
    finally:
        other.close()


def test_loading_follows_the_main_model_then_the_comparison_model(tmp_path):
    """The loading stages are the main KataGo, then the comparison model's; both get ready."""
    settings = fake_katago_settings(tmp_path, compare_model=str(tmp_path / "normal.bin.gz"), use_compare=True)
    engines = open_engines(settings, turned_off=False)
    try:
        stages = engines.loading_stages()
        assert [stage.text_key for stage in stages] == ["loading_main", "loading_compare"]
        assert started_in_the_background(engines.processes[1])
        assert all(stage.is_ready() and not stage.has_failed() for stage in stages)
        assert all(stage.seconds() is not None for stage in stages)
    finally:
        engines.close()
    assert open_engines(settings, turned_off=True).loading_stages() == []


def test_start_engines_without_the_comparison_model(tmp_path):
    """Without the comparison model, or with KataGo turned off, no second KataGo is started."""
    engine, compare, _, _ = start_engines(fake_katago_settings(tmp_path), turned_off=False)
    engine.close()
    assert compare is None
    assert start_engines(fake_katago_settings(tmp_path, use_compare=True), turned_off=True)[:2] == (None, None)


def test_comparison_model_that_judges_is_started_after_the_main_one(tmp_path):
    """When the comparison model judges every answer, its KataGo is also started after the main one."""
    settings = fake_katago_settings(
        tmp_path, compare_model=str(tmp_path / "normal.bin.gz"), use_compare=True, judge_model="compare"
    )
    engines = open_engines(settings, turned_off=False)
    try:
        assert engines.judge_with_compare and started_in_the_background(engines.processes[1])
    finally:
        engines.close()


def test_start_engines_tells_when_the_comparison_model_cannot_start(tmp_path):
    """If the comparison model cannot be started, the user is told in a dialog, and so is the judge fallback."""
    settings = fake_katago_settings(
        tmp_path, compare_model=str(tmp_path / "missing.bin.gz"), use_compare=True, judge_model="compare"
    )
    notices = []
    engine, compare, _, problem = start_engines(settings, turned_off=False, notices=notices)
    engine.close()
    assert compare is None and problem == ""
    assert len(notices) == 2
    first, second = (notice_text(notice) for notice in notices)
    assert "比較用モデル" in first and "missing.bin.gz" in first
    assert "メインのモデル" in second


def test_start_engines_tells_when_katago_cannot_start(tmp_path):
    """If KataGo cannot be started, the user is told why. Turning it off is not a problem to tell."""
    notices = []
    engine, _, _, problem = start_engines(EngineSettings(katago=str(tmp_path / "none")), False, notices)
    assert engine is None and problem
    assert len(notices) == 1 and "KataGoを起動できませんでした" in notice_text(notices[0])
    notices.clear()
    start_engines(EngineSettings(), turned_off=True, notices=notices)
    assert notices == []


def test_quiz_engines_start_when_asked_and_stop_when_closed(tmp_path):
    """KataGo for the quiz is started by open_engines, and stopped by close (when the quiz ends)."""
    engines = open_engines(fake_katago_settings(tmp_path), turned_off=False)
    process = engines.processes[0]
    assert engines.engine is not None and engines.engine_problem == "" and process.is_running
    engines.close()
    assert not process.is_running
    off = open_engines(fake_katago_settings(tmp_path), turned_off=True)
    assert off.engine is None and off.engine_problem != ""
    off.close()  # Nothing to stop.


def test_measure_katago_speed(tmp_path):
    """The speed is measured with a KataGo of its own (the fake one reads every visit at once)."""
    speed = measure_katago_speed(fake_katago_settings(tmp_path))
    assert speed.main > 0 and speed.compare is None


def test_measure_katago_speed_of_both_models(tmp_path):
    """With the comparison model turned on, it is measured too, with a KataGo of its own."""
    settings = fake_katago_settings(tmp_path, compare_model=str(tmp_path / "normal.bin.gz"), use_compare=True)
    speed = measure_katago_speed(settings)
    assert speed.main > 0 and speed.compare is not None and speed.compare > 0


def test_measure_katago_speed_without_katago(tmp_path):
    """When KataGo cannot be started, the error tells why."""
    with pytest.raises(RuntimeError, match="KataGo"):
        measure_katago_speed(EngineSettings(katago=str(tmp_path / "missing")))


def test_measure_the_same_model_once(tmp_path):
    """A comparison model that is the main model's file is not measured again: it has the same speed."""
    settings = fake_katago_settings(tmp_path, use_compare=True)
    settings = replace(settings, compare_model=settings.model)
    speed = measure_katago_speed(settings)
    assert speed.compare == speed.main


def test_the_comparison_model_has_a_smaller_cache(tmp_path):
    """The comparison model's KataGo is started with a smaller cache; the main one keeps KaTrain's."""
    settings = fake_katago_settings(tmp_path, compare_model=str(tmp_path / "normal.bin.gz"), use_compare=True)
    compare, _, _ = make_command(settings, settings.compare_engine())
    main, _, _ = make_command(settings)
    cache = f"nnCacheSizePowerOfTwo={COMPARE_CACHE['nnCacheSizePowerOfTwo']}"
    assert cache in " ".join(compare.command) and cache not in " ".join(main.command)
