"""Headless UI checks. The database path is redirected to a temp file."""

from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

APP = Path(__file__).resolve().parents[1] / "app.py"
TIMEOUT = 180
PINNED_DEADLINE = date(2026, 11, 8)
PAST_DEADLINE = date(2026, 10, 24)
DEADLINE_NOTE = "This deadline has passed. Choose a future date to generate a plan."


def _redirect_db(path: Path):
    real = sqlite3.connect

    def connect(database=":memory:", *args, **kwargs):
        if isinstance(database, Path) or isinstance(database, str):
            if str(database).replace("\\", "/").endswith("studypilot.db"):
                database = path
        return real(database, *args, **kwargs)

    sqlite3.connect = connect
    return real


def _texts(at: AppTest) -> str:
    parts: list[str] = []
    for name in ("markdown", "warning", "error", "info", "success", "caption", "text"):
        group = getattr(at, name, None)
        if group is None:
            continue
        for element in group:
            value = getattr(element, "value", None)
            if value is None:
                value = getattr(element, "body", "")
            parts.append(str(value))
    return "\n".join(parts)


def _click(at: AppTest, label: str) -> AppTest:
    matches = [button for button in at.button if button.label == label]
    if not matches:
        found = [button.label for button in at.button]
        raise AssertionError(f"No button {label!r}. Found {found}")
    return matches[0].click().run(timeout=TIMEOUT)


def _completed_count(path: Path, profile: str) -> int:
    with sqlite3.connect(path) as con:
        row = con.execute(
            "SELECT COUNT(*) FROM sessions WHERE plan_id=? AND completed=1",
            (profile,),
        ).fetchone()
    return int(row[0])


@pytest.fixture(scope="module")
def ui(tmp_path_factory):
    path = tmp_path_factory.mktemp("ui") / "studypilot.db"
    real = _redirect_db(path)
    try:
        app = AppTest.from_file(APP, default_timeout=TIMEOUT).run()
        app.demo_db = path  # type: ignore[attr-defined]
        yield app
    finally:
        sqlite3.connect = real


def test_app_starts_without_an_exception(ui: AppTest):
    assert not ui.exception
    assert ui.selectbox[0].label == "Sample profile"
    assert len(ui.selectbox[0].options) == 3


def test_each_sample_profile_generates_a_schedule(ui: AppTest):
    ui.date_input(key="assessment_date").set_value(PINNED_DEADLINE).run(timeout=TIMEOUT)
    for name in list(ui.selectbox[0].options):
        ui.selectbox[0].select(name).run(timeout=TIMEOUT)
        ui = _click(ui, "Generate / regenerate plan")
        assert not ui.exception, ui.exception[0].value if ui.exception else ""
        body = _texts(ui)
        assert "PASS" in body or "No day exceeds" in body, body[-500:]
        assert ui.checkbox, f"{name} produced no session checkboxes"
        assert "No timetable is shown" not in body
        assert DEADLINE_NOTE not in body


def test_regenerate_keeps_completed_sessions(ui: AppTest):
    profile = "Beginner — limited time"
    ui.selectbox[0].select(profile).run(timeout=TIMEOUT)
    ui = _click(ui, "Generate / regenerate plan")
    assert ui.checkbox, "No Done checkbox was rendered for the schedule"
    ui.checkbox[0].check().run(timeout=TIMEOUT)
    before = _completed_count(ui.demo_db, profile)  # type: ignore[attr-defined]
    assert before >= 1
    ui = _click(ui, "Generate / regenerate plan")
    assert not ui.exception
    after = _completed_count(ui.demo_db, profile)  # type: ignore[attr-defined]
    assert after >= 1


def test_mastery_edit_then_regenerate_keeps_completed_sessions(ui: AppTest):
    """Drive a mastery change, then regenerate.

    streamlit.testing.v1.AppTest has no data_editor widget and Dataframe has
    no cell setter. st.data_editor is rendered as a dataframe. A committed
    cell is stored on the editor's session-state key as edited_rows, so the
    test writes that payload instead of clicking the canvas.
    """
    assert not hasattr(ui, "data_editor")
    profile = "Beginner — limited time"
    ui.date_input(key="assessment_date").set_value(PINNED_DEADLINE).run(timeout=TIMEOUT)
    ui.selectbox[0].select(profile).run(timeout=TIMEOUT)
    ui = _click(ui, "Generate / regenerate plan")
    assert len(ui.checkbox) >= 2, "Need two Done checkboxes so two sessions can be marked complete"
    ui.checkbox[0].check().run(timeout=TIMEOUT)
    ui.checkbox[1].check().run(timeout=TIMEOUT)
    before = _completed_count(ui.demo_db, profile)  # type: ignore[attr-defined]
    assert before >= 1
    assert before >= 2

    editor_keys = [
        element.key
        for element in ui.dataframe
        if element.key and str(element.key).startswith("topic_editor_")
    ]
    if not editor_keys:
        pytest.fail(
            "AppTest cannot edit mastery. The control is st.data_editor, "
            "a canvas grid in section 1. It is exposed only as a dataframe, "
            f"and none of those frames has a topic_editor_ key. "
            f"Dataframe keys: {[element.key for element in ui.dataframe]}."
        )
    topics = list(ui.session_state.topics)
    row = next(index for index, topic in enumerate(topics) if topic["topic"] == "Dynamic Programming")
    updated = min(100, int(topics[row]["mastery"]) + 40)
    ui.session_state[editor_keys[0]] = {
        "edited_rows": {row: {"mastery": updated}},
        "added_rows": [],
        "deleted_rows": [],
    }
    ui.run(timeout=TIMEOUT)
    assert not ui.exception, ui.exception[0].value if ui.exception else ""
    body = _texts(ui)
    assert f"{updated}%" in body, (
        "The data editor session state did not change mastery. "
        "AppTest cannot type into the canvas grid."
    )
    ui = _click(ui, "Generate / regenerate plan")
    assert not ui.exception, ui.exception[0].value if ui.exception else ""
    after = _completed_count(ui.demo_db, profile)  # type: ignore[attr-defined]
    assert after >= before
    assert f"{updated}%" in _texts(ui)


def test_mastery_jump_worsens_top_rank_in_at_least_two_profiles() -> None:
    """A 40-point mastery rise, capped at 100, must let another topic overtake the leader in at least two profiles."""
    import app as planner

    days_left = (PINNED_DEADLINE - date(2026, 10, 25)).days
    worsened: list[str] = []
    for name, profile in planner.SAMPLE_PROFILES.items():
        topics = [dict(topic) for topic in profile["topics"]]

        def sort_key(topic: dict) -> tuple[float, str]:
            score = planner.priority_score(int(topic["mastery"]), int(topic["importance"]), days_left)
            return (-score, str(topic["topic"]))

        ranked = sorted(topics, key=sort_key)
        top_name = str(ranked[0]["topic"])
        updated_topics = []
        for topic in topics:
            item = dict(topic)
            if item["topic"] == top_name:
                item["mastery"] = min(100, int(item["mastery"]) + 40)
            updated_topics.append(item)
        after = sorted(updated_topics, key=sort_key)
        rank_after = next(index for index, topic in enumerate(after, start=1) if topic["topic"] == top_name)
        if rank_after > 1:
            worsened.append(name)
    assert len(worsened) >= 2, worsened


def test_past_deadline_shows_overdue_and_no_timetable(ui: AppTest):
    ui.date_input(key="assessment_date").set_value(PAST_DEADLINE).run(timeout=TIMEOUT)
    assert not ui.exception
    body = _texts(ui)
    assert "DEADLINE OVERDUE" in body or "Overdue" in body
    assert DEADLINE_NOTE in body
    assert "No timetable is shown for an overdue deadline." in body
    assert not ui.checkbox


def test_deadline_today_shows_overdue_and_no_timetable(ui: AppTest):
    ui.date_input(key="assessment_date").set_value(date.today()).run(timeout=TIMEOUT)
    assert not ui.exception
    body = _texts(ui)
    assert "DEADLINE OVERDUE" in body or "today" in body.lower()
    assert DEADLINE_NOTE in body
    assert "No timetable is shown for an overdue deadline." in body
    assert not ui.checkbox


