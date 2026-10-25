"""Print a deterministic StudyPilot demo for the three sample profiles.

Uses the planner functions in app.py. No Streamlit UI and no external API.
The database is a temporary file, so studypilot.db is not opened.
"""

from __future__ import annotations

import sys
import tempfile
from datetime import date
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import app as planner

START = date(2026, 10, 25)
DEADLINE = date(2026, 11, 8)
MASTERY_RAISE = 40
OUTPUT = ROOT / "demo_output.txt"
ACTIVITY = {
    "Learn / review": "Learn",
    "Coding practice": "Practice",
    "Recall / revision": "Revision",
}


def rank_topics(topics: list[dict[str, Any]], days_left: int) -> list[dict[str, Any]]:
    ranked: list[dict[str, Any]] = []
    for raw in topics:
        topic = dict(raw)
        parts = planner.priority_parts(int(topic["mastery"]), int(topic["importance"]), days_left)
        topic["mastery"] = parts["mastery"]
        topic["importance"] = parts["importance"]
        topic["priority"] = parts["score"]
        topic["reason"] = planner.explain_priority(topic, parts["score"], days_left)
        ranked.append(topic)
    ranked.sort(key=lambda item: (-item["priority"], item["topic"]))
    return ranked


def activity_label(task_type: str) -> str:
    return ACTIVITY.get(str(task_type), str(task_type))


def format_ranking(ranked: list[dict[str, Any]]) -> str:
    lines = []
    for index, topic in enumerate(ranked, start=1):
        lines.append(
            f"{index}. {topic['topic']} — priority {topic['priority']} — mastery {topic['mastery']}"
        )
        lines.append(f"   Why prioritised: {topic['reason']}")
    return "\n".join(lines)


def format_plan(plan: list[dict[str, Any]]) -> str:
    lines = [f"{'date':<12} {'topic':<24} {'activity':<10} minutes"]
    if not plan:
        lines.append("(no sessions)")
        return "\n".join(lines)
    counts = {"Learn": 0, "Practice": 0, "Revision": 0}
    for session in plan:
        label = activity_label(str(session["task_type"]))
        if label in counts:
            counts[label] += 1
        lines.append(
            f"{session['day_date']:<12} {session['topic']:<24} "
            f"{label:<10} {int(session['duration_minutes'])}"
        )
    lines.append(
        "Sessions: "
        + ", ".join(f"{name} {counts[name]}" for name in ("Learn", "Practice", "Revision"))
    )
    return "\n".join(lines)


def format_availability(report: dict[str, Any]) -> str:
    lines = [f"{'date':<12} {'available':>9} {'scheduled':>10}  result"]
    for day in report["days"]:
        result = "PASS" if int(day["scheduled"]) <= int(day["available"]) and not day["overlap"] else "FAIL"
        lines.append(
            f"{day['date']:<12} {int(day['available']):>9} {int(day['scheduled']):>10}  {result}"
        )
    lines.append(f"overall: {report['status']}")
    if report["errors"]:
        lines.extend(f"error: {error}" for error in report["errors"])
    return "\n".join(lines)


def what_changed(before: list[dict[str, Any]], after: list[dict[str, Any]]) -> str:
    before_index = {topic["topic"]: index for index, topic in enumerate(before, start=1)}
    before_by_name = {topic["topic"]: topic for topic in before}
    lines = []
    for index, topic in enumerate(after, start=1):
        name = str(topic["topic"])
        old = before_by_name[name]
        old_rank = before_index[name]
        if old_rank != index:
            lines.append(
                f"{name} moved from #{old_rank} to #{index} "
                f"(priority {old['priority']} to {topic['priority']}, "
                f"mastery {old['mastery']} to {topic['mastery']})."
            )
        elif old["priority"] != topic["priority"] or old["mastery"] != topic["mastery"]:
            lines.append(
                f"{name} stayed at #{index} "
                f"(priority {old['priority']} to {topic['priority']}, "
                f"mastery {old['mastery']} to {topic['mastery']})."
            )
        else:
            lines.append(f"{name} stayed at #{index}.")
    return "\n".join(lines)


def session_identity(session: dict[str, Any]) -> tuple[str, str, str, int]:
    return (
        str(session["topic"]),
        str(session["task_type"]),
        str(session["day_date"]),
        int(session["duration_minutes"]),
    )


def over_capacity(report: dict[str, Any]) -> list[str]:
    problems = []
    for day in report["days"]:
        if int(day["scheduled"]) > int(day["available"]):
            problems.append(
                f"{day['date']}: scheduled {int(day['scheduled'])} > available {int(day['available'])}"
            )
    return problems


def build_report(failures: list[str]) -> str:
    days_left = (DEADLINE - START).days
    sections = [
        "StudyPilot demo",
        f"Start: {START.isoformat()} ({planner.weekday_name(START)})",
        f"Deadline: {DEADLINE.isoformat()} ({planner.weekday_name(DEADLINE)})",
        f"Days left: {days_left}",
        f"Planning window: {planner.PLANNING_HORIZON_DAYS} days from the start date.",
        f"Temporary database: {planner.DB_PATH}",
        "Planner only. No Streamlit UI and no external API.",
        "",
    ]
    rank_drops: list[str] = []
    for name, profile in planner.SAMPLE_PROFILES.items():
        topics = [dict(topic) for topic in profile["topics"]]
        hours = planner.availability_for_window(profile["daily_hours"], START, 7)
        ranked = rank_topics(topics, days_left)
        plan, summary = planner.generate_plan(topics, hours, START, DEADLINE)
        report = planner.validate_schedule(plan, hours, summary["schedulable_days"], START)
        for problem in over_capacity(report):
            failures.append(f"{name} before regeneration: {problem}")

        sections.append("=" * 78)
        sections.append(name)
        sections.append(profile["description"])
        sections.append("")
        sections.append("Ranked topics")
        sections.append(format_ranking(ranked))
        sections.append("")
        sections.append("Weekly plan")
        sections.append(format_plan(plan))
        sections.append("")
        sections.append("Availability (minutes)")
        sections.append(format_availability(report))
        sections.append("")

        planner.save_plan(plan, name, preserve_completed=False)
        saved = planner.load_plan(name)
        top = ranked[0]
        top_name = str(top["topic"])
        matching = [session for session in saved if session["topic"] == top_name]
        if len(matching) < 2:
            failures.append(f"{name}: {top_name} has fewer than two sessions to mark complete.")
        first_two = matching[:2]
        first = first_two[0]
        for session in first_two:
            planner.set_completed(int(session["id"]), True)
        updated = []
        for topic in topics:
            item = dict(topic)
            if item["topic"] == top_name:
                item["mastery"] = min(100, int(item["mastery"]) + MASTERY_RAISE)
            updated.append(item)
        completed = [row for row in planner.load_plan(name) if int(row["completed"]) == 1]
        new_plan, new_summary = planner.generate_plan(
            updated,
            hours,
            START,
            DEADLINE,
            completed_sessions=completed,
        )
        planner.save_plan(
            new_plan,
            name,
            preserve_completed=True,
            completed_rows=new_summary["preserved_sessions"],
        )
        reloaded = planner.load_plan(name)
        kept = [
            row
            for row in reloaded
            if int(row["completed"]) == 1 and session_identity(row) == session_identity(first)
        ]
        if not kept:
            failures.append(f"{name}: completed session was not kept after regeneration.")
        kept_identities = {session_identity(row) for row in reloaded if int(row["completed"]) == 1}
        for session in first_two:
            if session_identity(session) not in kept_identities:
                failures.append(
                    f"{name}: completed session on {session['day_date']} was not kept after regeneration."
                )
        combined = list(new_summary["preserved_sessions"]) + list(new_plan)
        again = planner.validate_schedule(combined, hours, new_summary["schedulable_days"], START)
        for problem in over_capacity(again):
            failures.append(f"{name} after regeneration: {problem}")
        after = rank_topics(updated, days_left)
        top_after = next(topic for topic in after if topic["topic"] == top_name)
        if after[0]["topic"] == top_name and not (top_after["priority"] < top["priority"]):
            failures.append(
                f"{name}: {top_name} stayed at rank 1 and its priority did not drop "
                f"({top['priority']} -> {top_after['priority']})."
            )
        rank_after = next(index for index, topic in enumerate(after, start=1) if topic["topic"] == top_name)
        if rank_after > 1:
            rank_drops.append(name)
        shown = sorted(combined, key=lambda session: (str(session["day_date"]), str(session.get("start_time") or "")))
        sections.append("Progress update")
        sections.append(
            f"Raised {top_name} mastery from {int(top['mastery'])} to {int(top_after['mastery'])}."
        )
        for session in first_two:
            sections.append(
                f"Marked complete: {session['day_date']} {session['topic']} — "
                f"{activity_label(str(session['task_type']))}, {int(session['duration_minutes'])} minutes."
            )
        sections.append("Regenerated ranking")
        sections.append(format_ranking(after))
        sections.append("")
        sections.append("What changed")
        sections.append(what_changed(ranked, after))
        sections.append("")
        sections.append("Weekly plan after regeneration")
        sections.append(format_plan(shown))
        sections.append("")
        sections.append("Availability after regeneration (minutes)")
        sections.append(format_availability(again))
        sections.append("")
    if len(rank_drops) < 2:
        failures.append(
            "The top topic's rank got worse in "
            f"{len(rank_drops)} of {len(planner.SAMPLE_PROFILES)} profiles. "
            "Expected at least two, where another topic overtakes it."
        )
    return "\n".join(sections).rstrip() + "\n"


def main() -> None:
    temporary = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
    planner.DB_PATH = Path(temporary.name) / "demo.db"
    planner.init_db()
    failures: list[str] = []
    report = build_report(failures)
    if failures:
        ending = "CHECKS FAILED\n" + "\n".join(f"- {item}" for item in failures) + "\n"
    else:
        ending = "ALL CHECKS PASSED\n"
    full = report + "\n" + ending
    OUTPUT.write_text(full, encoding="utf-8")
    print(full, end="")
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
