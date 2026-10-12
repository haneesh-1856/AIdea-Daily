import shutil
from datetime import date

import pytest

from steps.testkit import make_root
from sqlalchemy import select

from common import db, runlog
from common.settings import ROOT, SettingsError, database_url
from steps.step01_start.step import StartError, start

DAY = date(2026, 10, 6)


@pytest.fixture
def root(tmp_path, monkeypatch):
    return make_root(tmp_path, monkeypatch)


def run(root, **kwargs):
    return start(DAY, root=root, checks=[], **kwargs)


def edit(root, name, old, new):
    path = root / name
    text = path.read_text(encoding="utf-8")
    assert old in text
    path.write_text(text.replace(old, new), encoding="utf-8")


def test_first_call_starts_a_run_and_marks_step_one_done(root):
    result = run(root)
    assert (result.state, result.attempt, result.next_step) == ("new", 1, 2)
    assert result.report.exists()
    assert "A new run was started." in result.report.read_text(encoding="utf-8")


def test_second_call_resumes_the_same_run(root):
    first = run(root)
    second = run(root)
    assert second.state == "resumed"
    assert second.run_id == first.run_id


def test_finished_run_is_left_alone_unless_forced(root):
    first = run(root)
    engine = db.connect(database_url(root))
    with engine.begin() as conn:
        conn.execute(db.runs.update().where(db.runs.c.id == first.run_id).values(status="done"))

    again = run(root)
    assert again.state == "already_done"
    assert again.run_id == first.run_id

    forced = run(root, force=True)
    assert (forced.state, forced.attempt) == ("new", 2)
    with engine.connect() as conn:
        assert len(conn.execute(select(db.runs)).all()) == 2


def test_settings_are_frozen_when_the_run_starts(root):
    run(root)
    edit(root, "settings.toml", "length_minutes = 15", "length_minutes = 30")
    assert run(root).settings["episode"]["length_minutes"] == 15


def test_a_different_day_gets_its_own_run(root):
    first = run(root)
    other = start(date(2026, 10, 7), root=root, checks=[])
    assert other.state == "new"
    assert other.run_id != first.run_id


def test_bad_setting_stops_the_run_with_a_clear_message(root):
    edit(root, "settings.toml", "length_minutes = 15", "length_minutes = 500")
    with pytest.raises(SettingsError, match="length_minutes must be a whole number from 1 to 120"):
        run(root)
    assert not (root / "data").exists()


def test_missing_settings_file_is_reported(root):
    (root / "sources.toml").unlink()
    with pytest.raises(SettingsError, match="sources.toml is missing"):
        run(root)


def test_failed_check_stops_before_any_run_is_recorded(root):
    with pytest.raises(StartError, match="Internet connection: no route"):
        start(DAY, root=root, checks=[("Internet connection", lambda: "no route")])
    assert not (root / "data").exists()


def test_next_step_moves_on_as_steps_finish(root):
    result = run(root)
    engine = db.connect(database_url(root))
    with engine.begin() as conn:
        runlog.begin_step(conn, result.run_id, 2)
        runlog.finish_step(conn, result.run_id, 2)
    assert run(root).next_step == 3
