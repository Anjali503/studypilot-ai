import os
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app as planner


def clock_minutes(value: str) -> int:
    hour, minute = value.split(":")
    return int(hour) * 60 + int(minute)


def assert_within_each_day(plan, availability, start):
    for index, hours in enumerate(availability):
        day = (start + timedelta(days=index)).isoformat()
        sessions = [session for session in plan if session["day_date"] == day]
        used = sum(int(session["duration_minutes"]) for session in sessions)
        assert used <= int(round(float(hours) * 60))
        spans = sorted(
            (clock_minutes(session["start_time"]), clock_minutes(session["end_time"]))
            for session in sessions
        )
        for (first_start, first_end), (next_start, next_end) in zip(spans, spans[1:]):
            assert first_end <= next_start
            assert next_end >= next_start
        for start_min, end_min in spans:
            assert end_min - start_min > 0


def use_temp_db(monkeypatch, tmp_path):
    db_path = tmp_path / "studypilot.db"
    monkeypatch.setattr(planner, "DB_PATH", db_path)
    planner.init_db()
    return db_path


def topic_ranking(plan):
    priority_by_topic = {}
    for session in plan:
        priority_by_topic[session["topic"]] = float(session["priority"])
    return tuple(sorted(priority_by_topic, key=lambda name: (-priority_by_topic[name], name)))


def session_identity(row):
    return (
        row["topic"],
        row["task_type"],
        row["day_date"],
        int(row["duration_minutes"]),
        row["start_time"],
    )


def test_lower_mastery_increases_priority():
    assert planner.priority_score(20, 5, 10) > planner.priority_score(80, 5, 10)


def test_higher_importance_increases_priority():
    assert planner.priority_score(50, 5, 10) > planner.priority_score(50, 2, 10)


def test_priority_formula_and_urgency():
    # mastery 40, importance 5: gap 0.60, importance 1.
    # base = 100 * (0.55 * 0.60 + 0.45) = 78.
    # urgency = 1 + 0.5 / days_left.
    assert planner.urgency_multiplier(10) == 1.05
    assert planner.priority_score(40, 5, 10) == 81.9
    assert planner.priority_score(40, 5, 7) == 83.6
    assert planner.priority_score(40, 5, 2) == 97.5
    assert planner.priority_score(0, 5, 1) == 100.0


def test_priority_increases_as_deadline_approaches():
    topic = (40, 5)
    scores = [planner.priority_score(*topic, days_left) for days_left in (14, 7, 3, 1)]
    assert scores[0] < scores[1] < scores[2] < scores[3]


def test_all_three_sample_profiles_load():
    names = list(planner.SAMPLE_PROFILES)
    assert len(names) == 3
    assert names[0].startswith("Beginner")
    assert names[1].startswith("Intermediate")
    assert names[2].startswith("Advanced")

    signatures = []
    mastery_averages = []
    weekly_hours = []
    start = date(2026, 10, 25)
    assert start.weekday() == 6  # Sunday, independent of the Windows locale
    deadline = start + timedelta(days=7)

    for name in names:
        profile = planner.SAMPLE_PROFILES[name]
        assert len(profile["daily_hours"]) == 7
        assert profile["topics"]
        for topic in profile["topics"]:
            assert topic["topic"]
            assert 0 <= topic["mastery"] <= 100
            assert 1 <= topic["importance"] <= 5
            assert topic["hours"] > 0
        signatures.append(
            (
                tuple(profile["daily_hours"]),
                tuple(
                    (topic["topic"], topic["mastery"], topic["importance"], topic["hours"])
                    for topic in profile["topics"]
                ),
            )
        )
        mastery_averages.append(
            sum(topic["mastery"] for topic in profile["topics"]) / len(profile["topics"])
        )
        weekly_hours.append(sum(profile["daily_hours"]))
        hours = planner.availability_for_window(profile["daily_hours"], start, 7)
        plan, summary = planner.generate_plan(profile["topics"], hours, start, deadline)
        assert summary["ok"], summary["message"]
        assert summary["status"] == "PASS"
        assert summary["total_scheduled_minutes"] + summary["unallocated_minutes"] == summary[
            "total_requested_minutes"
        ]
        assert planner.validate_schedule(plan, hours, summary["schedulable_days"], start)["valid"]
        assert_within_each_day(plan, hours, start)
        assert all(date.fromisoformat(session["day_date"]) < deadline for session in plan)
        task_types = {session["task_type"] for session in plan}
        assert "Learn / review" in task_types
        assert "Coding practice" in task_types
        assert "Recall / revision" in task_types

    assert len(set(signatures)) == 3
    assert mastery_averages[0] < mastery_averages[1] < mastery_averages[2]
    assert weekly_hours[0] < weekly_hours[1] < weekly_hours[2]

    beginner_hours = planner.availability_for_window(
        planner.SAMPLE_PROFILES[names[0]]["daily_hours"], start, 7
    )
    assert beginner_hours[0] == 0.0
    beginner_plan, _ = planner.generate_plan(
        planner.SAMPLE_PROFILES[names[0]]["topics"], beginner_hours, start, deadline
    )
    assert beginner_plan
    assert beginner_plan[0]["topic"] == "Dynamic Programming"
    assert all(session["day_date"] != start.isoformat() for session in beginner_plan)


def test_daily_scheduled_time_never_exceeds_availability():
    topics = [
        {"topic": "Arrays", "mastery": 20, "importance": 5, "hours": 8},
        {"topic": "Trees", "mastery": 10, "importance": 5, "hours": 8},
    ]
    availability = [1, 1, 1, 1, 1, 1, 1]
    start = date(2026, 10, 26)
    deadline = start + timedelta(days=7)
    plan, summary = planner.generate_plan(topics, availability, start, deadline)
    assert summary["ok"]
    assert planner.validate_schedule(plan, availability, 7, start)["valid"]
    assert_within_each_day(plan, availability, start)
    for index in range(7):
        day = (start + timedelta(days=index)).isoformat()
        used = sum(session["duration_minutes"] for session in plan if session["day_date"] == day)
        assert used <= availability[index] * 60
    assert all(session["day_date"] < deadline.isoformat() for session in plan)

    uneven = [0, 2, 0, 2, 0, 2, 0]
    uneven_plan, uneven_summary = planner.generate_plan(topics, uneven, start, deadline)
    assert uneven_summary["ok"]
    assert uneven_summary["unallocated_minutes"] > 0
    assert_within_each_day(uneven_plan, uneven, start)
    for index, hours in enumerate(uneven):
        if hours == 0:
            day = (start + timedelta(days=index)).isoformat()
            assert sum(session["duration_minutes"] for session in uneven_plan if session["day_date"] == day) == 0


def test_validator_uses_each_day_and_detects_overlap():
    start = date(2026, 10, 26)
    overloaded = [
        {
            "day_date": start.isoformat(),
            "topic": "Trees",
            "task_type": "Coding practice",
            "task": "Practise trees",
            "duration_minutes": 120,
            "start_time": "09:00",
            "end_time": "11:00",
            "priority": 80,
            "reason": "test",
        }
    ]
    # Six free hours later in the week would hide this if only the weekly total was checked.
    report = planner.validate_schedule(overloaded, [1, 6, 0, 0, 0, 0, 0], 7, start)
    assert not report["valid"]
    assert report["status"] == "FAIL"
    assert report["days"][0]["within_limit"] is False
    assert report["days"][0]["scheduled"] == 120
    assert report["days"][1]["scheduled"] == 0

    overlap = [
        {
            "day_date": start.isoformat(),
            "topic": "Arrays",
            "task_type": "Learn / review",
            "task": "Read arrays",
            "duration_minutes": 60,
            "start_time": "09:00",
            "end_time": "10:00",
        },
        {
            "day_date": start.isoformat(),
            "topic": "Trees",
            "task_type": "Coding practice",
            "task": "Practise trees",
            "duration_minutes": 60,
            "start_time": "09:30",
            "end_time": "10:30",
        },
    ]
    overlap_report = planner.validate_schedule(overlap, [3, 0, 0, 0, 0, 0, 0], 7, start)
    assert not overlap_report["valid"]
    assert any("overlap" in error.lower() for error in overlap_report["errors"])


def test_zero_availability_is_reported_not_exceeded():
    topics = [{"topic": "Trees", "mastery": 15, "importance": 5, "hours": 3}]
    start = date(2026, 10, 26)
    plan, summary = planner.generate_plan(topics, [0, 0, 0, 0, 0, 0, 0], start, start + timedelta(days=7))
    assert plan == []
    assert summary["ok"]
    assert summary["status"] == "PASS"
    assert summary["total_scheduled_minutes"] == 0
    assert summary["total_requested_minutes"] == 180
    assert summary["unallocated_minutes"] == 180
    assert summary["validation"]["valid"]
    for day in summary["validation"]["days"]:
        assert day["scheduled"] == 0
        assert day["available"] == 0
        assert day["within_limit"]


def test_past_deadline_is_rejected():
    plan, summary = planner.generate_plan([], [1] * 7, date.today(), date.today() - timedelta(days=1))
    assert plan == []
    assert not summary["ok"]

    scenario_plan, scenario_summary = planner.generate_plan(
        [{"topic": "Trees", "mastery": 20, "importance": 5, "hours": 2}],
        [1, 1, 1, 1, 1, 1, 1],
        date(2026, 10, 25),
        date(2026, 10, 24),
    )
    assert scenario_plan == []
    assert scenario_summary["ok"] is False
    assert scenario_summary["status"] == "OVERDUE"
    assert "overdue" in scenario_summary["message"].lower()
    assert "passed" in scenario_summary["message"].lower()


def test_deadline_today_is_rejected():
    start = date(2026, 10, 25)
    topics = [{"topic": "Trees", "mastery": 20, "importance": 5, "hours": 2}]
    availability = [2, 2, 2, 2, 2, 2, 2]

    plan, summary = planner.generate_plan(topics, availability, start, date(2026, 10, 25))
    assert plan == []
    assert summary["status"] == "OVERDUE"
    assert summary["ok"] is False

    # The day after the pinned start, not the machine's current date.
    tomorrow = date(2026, 10, 26)
    future_plan, future_summary = planner.generate_plan(topics, availability, start, tomorrow)
    assert future_plan
    report = planner.validate_schedule(
        future_plan, availability, future_summary["schedulable_days"], start
    )
    assert report["valid"]
    assert report["status"] == "PASS"


def test_explanation_contains_real_values():
    near = {"topic": "Trees", "mastery": 40, "importance": 5}
    near_days = 2
    near_text = planner.explain_priority(near, planner.priority_score(40, 5, near_days), near_days)
    assert "40%" in near_text
    assert "5/5" in near_text
    assert "2 days left, urgency x1.25" in near_text

    distant = {"topic": "Arrays", "mastery": 80, "importance": 2}
    distant_days = 10
    distant_text = planner.explain_priority(
        distant, planner.priority_score(80, 2, distant_days), distant_days
    )
    assert "80%" in distant_text
    assert "2/5" in distant_text
    assert "10 days left, urgency x1.05" in distant_text
    assert near_text != distant_text


def test_explanations_exist_for_every_ranked_topic():
    start = date(2026, 10, 25)
    deadline = date(2026, 11, 8)
    days_left = (deadline - start).days
    assert days_left == 14

    for profile in planner.SAMPLE_PROFILES.values():
        ranked = []
        for topic in profile["topics"]:
            score = planner.priority_score(topic["mastery"], topic["importance"], days_left)
            text = planner.explain_priority(topic, score, days_left).strip()
            assert text
            assert f"{topic['mastery']}%" in text
            assert f"{topic['importance']}/5" in text
            assert f"{days_left} days left" in text
            ranked.append((score, topic["topic"], text))
        assert len(ranked) == len(profile["topics"])
        assert len({name for _, name, _ in ranked}) == len(profile["topics"])

        hours = planner.availability_for_window(profile["daily_hours"], start, 7)
        plan, summary = planner.generate_plan(profile["topics"], hours, start, deadline)
        assert summary["ok"], summary["message"]
        assert plan
        topics = {topic["topic"]: topic for topic in profile["topics"]}
        seen = set()
        for session in plan:
            reason = str(session.get("reason", "")).strip()
            assert reason
            topic = topics[session["topic"]]
            expected = planner.explain_priority(
                topic,
                planner.priority_score(topic["mastery"], topic["importance"], days_left),
                days_left,
            )
            assert reason == expected
            seen.add(session["topic"])
        assert seen


def test_regeneration_availability_all_profiles(monkeypatch, tmp_path):
    use_temp_db(monkeypatch, tmp_path)
    start = date(2026, 10, 25)
    deadline = date(2026, 11, 8)
    ranking_changed = False

    for name, profile in planner.SAMPLE_PROFILES.items():
        topics = [dict(topic) for topic in profile["topics"]]
        hours = planner.availability_for_window(profile["daily_hours"], start, 7)
        plan, summary = planner.generate_plan(topics, hours, start, deadline)
        assert summary["status"] == "PASS", summary["message"]
        report = planner.validate_schedule(plan, hours, summary["schedulable_days"], start)
        assert report["valid"]
        assert report["status"] == "PASS"
        assert len(plan) >= 2
        before = topic_ranking(plan)

        topics[0]["mastery"] = 5
        topics[1]["mastery"] = 95
        planner.save_plan(plan, name, preserve_completed=False)
        saved = planner.load_plan(name)
        planner.set_completed(saved[0]["id"], True)
        planner.set_completed(saved[1]["id"], True)
        completed = [row for row in planner.load_plan(name) if int(row["completed"]) == 1]
        marked = [session_identity(row) for row in completed]
        assert len(marked) == 2

        new_plan, new_summary = planner.generate_plan(
            topics,
            hours,
            start,
            deadline,
            completed_sessions=completed,
        )
        assert new_summary["status"] == "PASS", new_summary["message"]
        remaining = planner.validate_schedule(
            new_plan, hours, new_summary["schedulable_days"], start
        )
        assert remaining["valid"]
        assert remaining["status"] == "PASS"
        planner.save_plan(
            new_plan,
            name,
            preserve_completed=True,
            completed_rows=new_summary["preserved_sessions"],
        )
        reloaded = planner.load_plan(name)
        kept = [session_identity(row) for row in reloaded if int(row["completed"]) == 1]
        assert len(kept) == 2
        for identity in marked:
            assert identity in kept
        if topic_ranking(new_plan) != before:
            ranking_changed = True

    assert ranking_changed


def test_zero_hour_day_has_no_sessions():
    start = date(2026, 10, 25)
    deadline = date(2026, 11, 8)
    wednesday = date(2026, 10, 28)
    assert start.weekday() == 6
    assert wednesday.weekday() == 2
    topics = [{"topic": "Trees", "mastery": 20, "importance": 5, "hours": 8}]
    monday_first = [2.0, 2.0, 0.0, 2.0, 2.0, 2.0, 2.0]
    hours = planner.availability_for_window(monday_first, start, planner.PLANNING_HORIZON_DAYS)
    offset = (wednesday - start).days
    assert hours[offset] == 0.0
    plan, summary = planner.generate_plan(topics, hours, start, deadline)
    assert summary["status"] == "PASS", summary["message"]
    assert plan
    for session in plan:
        assert date.fromisoformat(session["day_date"]).weekday() != wednesday.weekday()
    report = planner.validate_schedule(plan, hours, summary["schedulable_days"], start)
    assert report["status"] == "PASS"
    assert report["days"][offset]["available"] == 0
    assert report["days"][offset]["scheduled"] == 0


def test_completed_sessions_remain_completed_after_regeneration(monkeypatch, tmp_path):
    use_temp_db(monkeypatch, tmp_path)
    topics = [
        {"topic": "Arrays", "mastery": 20, "importance": 5, "hours": 4},
        {"topic": "Trees", "mastery": 10, "importance": 5, "hours": 4},
    ]
    availability = [1, 1, 1, 1, 1, 1, 1]
    start = date(2026, 10, 26)
    deadline = start + timedelta(days=7)
    plan, summary = planner.generate_plan(topics, availability, start, deadline)
    assert summary["ok"] and plan
    planner.save_plan(plan, "Beginner", preserve_completed=False)
    saved = planner.load_plan("Beginner")
    first = saved[0]
    planner.set_completed(first["id"], True)

    completed = [row for row in planner.load_plan("Beginner") if row["completed"] == 1]
    new_plan, new_summary = planner.generate_plan(
        topics,
        availability,
        start,
        deadline,
        completed_sessions=completed,
    )
    assert new_summary["ok"], new_summary["message"]
    planner.save_plan(
        new_plan,
        "Beginner",
        preserve_completed=True,
        completed_rows=new_summary["preserved_sessions"],
    )
    reloaded = planner.load_plan("Beginner")
    kept = [
        row
        for row in reloaded
        if row["topic"] == first["topic"]
        and row["task_type"] == first["task_type"]
        and int(row["duration_minutes"]) == int(first["duration_minutes"])
        and row["day_date"] == first["day_date"]
        and int(row["completed"]) == 1
    ]
    assert len(kept) == 1
    assert sum(1 for row in reloaded if int(row["completed"]) == 1) == 1
    in_window = [
        row
        for row in reloaded
        if start <= date.fromisoformat(row["day_date"]) < deadline
    ]
    assert planner.validate_schedule(in_window, availability, 7, start)["valid"]
    assert_within_each_day(in_window, availability, start)
    assert (
        new_summary["total_scheduled_minutes"] + new_summary["unallocated_minutes"]
        == new_summary["total_requested_minutes"]
    )
    assert sum(int(row["duration_minutes"]) for row in reloaded) <= sum(
        int(row["duration_minutes"]) for row in saved
    )


def test_mastery_changes_recalculate_priority():
    topics = [
        {"topic": "Arrays", "mastery": 80, "importance": 5, "hours": 2},
        {"topic": "Dynamic Programming", "mastery": 80, "importance": 5, "hours": 2},
    ]
    start = date(2026, 10, 26)
    deadline = start + timedelta(days=7)
    before, before_summary = planner.generate_plan(topics, [2] * 7, start, deadline)
    assert before_summary["ok"]
    assert before[0]["topic"] == "Arrays"
    assert planner.priority_score(80, 5, 7) == before[0]["priority"]

    topics[1]["mastery"] = 10
    after, after_summary = planner.generate_plan(topics, [2] * 7, start, deadline)
    assert after_summary["ok"]
    assert after[0]["topic"] == "Dynamic Programming"
    assert planner.priority_score(10, 5, 7) > planner.priority_score(80, 5, 7)
    assert after[0]["priority"] == planner.priority_score(10, 5, 7)


def test_saved_mastery_reloads(monkeypatch, tmp_path):
    use_temp_db(monkeypatch, tmp_path)
    topics = [{"topic": "Trees", "mastery": 55, "importance": 5, "hours": 2}]
    planner.save_mastery("Beginner", topics)
    loaded = planner.load_mastery(
        "Beginner",
        [{"topic": "Trees", "mastery": 10, "importance": 5, "hours": 2}],
    )
    assert loaded[0]["mastery"] == 55


def test_unallocated_work_is_reported():
    topics = [{"topic": "Dynamic Programming", "mastery": 10, "importance": 5, "hours": 8}]
    start = date(2026, 10, 26)
    deadline = start + timedelta(days=1)
    plan, summary = planner.generate_plan(topics, [1, 0, 0, 0, 0, 0, 0], start, deadline)
    assert summary["ok"]
    assert summary["schedulable_days"] == 1
    assert summary["total_available_minutes"] == 60
    assert summary["total_scheduled_minutes"] == 60
    assert summary["total_requested_minutes"] == 480
    assert summary["unallocated_minutes"] == 420
    assert summary["total_scheduled_minutes"] + summary["unallocated_minutes"] == summary[
        "total_requested_minutes"
    ]
    assert sum(item["duration_minutes"] for item in summary["unallocated_tasks"]) == 420
    assert summary["unallocated_tasks"]
    assert all(item["unallocated_reason"] for item in summary["unallocated_tasks"])
    assert sum(session["duration_minutes"] for session in plan) == 60
    assert all(session["day_date"] == start.isoformat() for session in plan)
    assert planner.validate_schedule(plan, [1, 0, 0, 0, 0, 0, 0], 1, start)["valid"]


def test_sample_profiles_regenerate_after_progress(monkeypatch, tmp_path):
    use_temp_db(monkeypatch, tmp_path)
    start = date(2026, 10, 25)
    deadline = start + timedelta(days=7)
    names = list(planner.SAMPLE_PROFILES)
    assert names[0].startswith("Beginner")
    assert names[1].startswith("Intermediate")
    assert names[2].startswith("Advanced")
    ranking_changed = False

    for name in names:
        profile = planner.SAMPLE_PROFILES[name]
        topics = [dict(topic) for topic in profile["topics"]]
        hours = planner.availability_for_window(profile["daily_hours"], start, 7)
        plan, summary = planner.generate_plan(topics, hours, start, deadline)
        assert summary["status"] == "PASS", summary["message"]
        report = planner.validate_schedule(plan, hours, summary["schedulable_days"], start)
        assert report["valid"]
        assert report["status"] == "PASS"
        assert len(plan) >= 2
        before = topic_ranking(plan)

        topics[0]["mastery"] = 0
        topics[-1]["mastery"] = 100
        planner.save_mastery(name, topics)
        topics = planner.load_mastery(name, [dict(topic) for topic in profile["topics"]])
        assert topics[0]["mastery"] == 0
        assert topics[-1]["mastery"] == 100

        planner.save_plan(plan, name, preserve_completed=False)
        saved = planner.load_plan(name)
        planner.set_completed(saved[0]["id"], True)
        planner.set_completed(saved[1]["id"], True)
        completed = [row for row in planner.load_plan(name) if int(row["completed"]) == 1]
        assert len(completed) == 2
        marked = [session_identity(row) for row in completed]

        new_plan, new_summary = planner.generate_plan(
            topics,
            hours,
            start,
            deadline,
            completed_sessions=completed,
        )
        assert new_summary["status"] == "PASS", new_summary["message"]
        remaining = planner.validate_schedule(
            new_plan, hours, new_summary["schedulable_days"], start
        )
        assert remaining["valid"]
        assert remaining["status"] == "PASS"

        planner.save_plan(
            new_plan,
            name,
            preserve_completed=True,
            completed_rows=new_summary["preserved_sessions"],
        )
        reloaded = planner.load_plan(name)
        kept = [session_identity(row) for row in reloaded if int(row["completed"]) == 1]
        assert len(kept) == 2
        for identity in marked:
            assert identity in kept
        in_window = [
            row
            for row in reloaded
            if start <= date.fromisoformat(row["day_date"]) < deadline
        ]
        again = planner.validate_schedule(
            in_window, hours, new_summary["schedulable_days"], start
        )
        assert again["valid"]
        assert again["status"] == "PASS", again["errors"]
        if topic_ranking(new_plan) != before:
            ranking_changed = True

    assert ranking_changed


def test_activity_minutes_sum_to_the_request():
    for total in range(0, 301):
        parts = planner.study_activity_minutes(total)
        assert sum(minutes for _, minutes in parts) == total
        assert all(minutes >= 0 for _, minutes in parts)


def test_app_starts_without_an_api_key(tmp_path):
    source = Path(planner.__file__).read_text(encoding="utf-8").lower()
    for banned in ("openai", "anthropic", "api_key", "gemini"):
        assert banned not in source
    requirements = (Path(planner.__file__).parent / "requirements.txt").read_text(encoding="utf-8").lower()
    for banned in ("openai", "anthropic", "google-generativeai"):
        assert banned not in requirements

    env = os.environ.copy()
    for name in (
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "GOOGLE_API_KEY",
        "GEMINI_API_KEY",
        "AZURE_OPENAI_API_KEY",
    ):
        env.pop(name, None)
    env["PYTHONIOENCODING"] = "utf-8"
    result = subprocess.run(
        [sys.executable, "-c", "import app; print(app.priority_score(20, 5, 10))"],
        cwd=Path(planner.__file__).parent,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip()
