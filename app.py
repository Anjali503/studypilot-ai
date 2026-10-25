"""StudyPilot AI.

Deterministic study planner for a programming assessment.
"AI" means classical, rule-based AI: a goal-based planning agent with a transparent
heuristic priority score, constraint-based scheduling, and re-planning when progress
changes. It does not use machine learning, a trained model, or a language model.
Scoring and scheduling are pure functions so they can be tested without a browser.
The Streamlit dashboard at the bottom is the demo interface.
No language-model API is used.
"""

from __future__ import annotations

import html
import json
import sqlite3
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from ui_theme import badge, card, metric_tile, page_style, progress_ring, status_banner

APP_DIR = Path(__file__).resolve().parent
DB_PATH = APP_DIR / "studypilot.db"

WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

# Upcoming features. Switch one on only by setting its value here to True.
# With every value False, planner output matches app_baseline.py.
FEATURES = {
    "PREREQUISITES": False,
    "BAYES_MASTERY": False,
    "DURATION_REGRESSION": False,
    "HILL_CLIMB": False,
}

# Explainable priority model. Higher scores need attention sooner.
MASTERY_WEIGHT = 0.55
IMPORTANCE_WEIGHT = 0.45
# urgency = 1 + URGENCY_WEIGHT / max(days_left, 1). Three days left is x1.17.
URGENCY_WEIGHT = 0.5

# 40% learning, 40% coding practice, and the remainder is recall / revision.
LEARN_SHARE = 0.40
PRACTICE_SHARE = 0.40
MAX_SESSION_MINUTES = 60
MIN_PARTIAL_MINUTES = 15
PLANNING_HORIZON_DAYS = 7
DAY_START_MINUTES = 9 * 60  # sessions are packed from 09:00

TASK_LEARN = "Learn / review"
TASK_PRACTICE = "Coding practice"
TASK_RECALL = "Recall / revision"
TASK_ORDER = {TASK_LEARN: 0, TASK_PRACTICE: 1, TASK_RECALL: 2}

# daily_hours is Monday-first. The scheduler maps it onto real calendar dates.
SAMPLE_PROFILES: dict[str, dict[str, Any]] = {
    "Beginner — limited time": {
        "description": (
            "Low mastery and a short week, including Sunday as a rest day. "
            "Foundations and guided practice come first."
        ),
        "daily_hours": [1.0, 1.0, 0.5, 1.0, 1.0, 1.5, 0.0],
        "topics": [
            {"topic": "Arrays & Strings", "mastery": 35, "importance": 5, "hours": 2.0},
            {"topic": "Searching & Sorting", "mastery": 25, "importance": 4, "hours": 2.0},
            {"topic": "Recursion", "mastery": 20, "importance": 4, "hours": 2.0},
            {"topic": "Linked Lists", "mastery": 30, "importance": 3, "hours": 1.5},
            {"topic": "Trees", "mastery": 15, "importance": 5, "hours": 2.5},
            {"topic": "Dynamic Programming", "mastery": 10, "importance": 5, "hours": 3.0},
        ],
    },
    "Intermediate — balanced": {
        "description": (
            "Comfortable with the fundamentals and a balanced week. "
            "Practice is aimed at the topics that are still uneven."
        ),
        "daily_hours": [2.0, 2.0, 2.0, 2.0, 2.0, 2.5, 1.5],
        "topics": [
            {"topic": "Arrays & Strings", "mastery": 70, "importance": 4, "hours": 1.5},
            {"topic": "Searching & Sorting", "mastery": 55, "importance": 5, "hours": 2.0},
            {"topic": "Recursion", "mastery": 45, "importance": 4, "hours": 2.0},
            {"topic": "Linked Lists", "mastery": 60, "importance": 3, "hours": 1.5},
            {"topic": "Trees", "mastery": 40, "importance": 5, "hours": 2.5},
            {"topic": "Dynamic Programming", "mastery": 35, "importance": 5, "hours": 3.0},
        ],
    },
    "Advanced — targeted revision": {
        "description": (
            "High mastery, with time reserved for exam-style problems. "
            "Dynamic programming and trees still need targeted practice."
        ),
        "daily_hours": [3.0, 3.0, 2.5, 3.0, 3.0, 3.5, 2.0],
        "topics": [
            {"topic": "Arrays & Strings", "mastery": 95, "importance": 4, "hours": 1.0},
            {"topic": "Searching & Sorting", "mastery": 85, "importance": 5, "hours": 1.5},
            {"topic": "Recursion", "mastery": 80, "importance": 4, "hours": 1.5},
            {"topic": "Linked Lists", "mastery": 90, "importance": 3, "hours": 1.0},
            {"topic": "Trees", "mastery": 80, "importance": 5, "hours": 2.0},
            {"topic": "Dynamic Programming", "mastery": 70, "importance": 5, "hours": 2.5},
        ],
    },
}


def weekday_name(day: date) -> str:
    return WEEKDAYS[day.weekday()]


def format_day(day: date) -> str:
    return f"{weekday_name(day)} {day.day} {MONTHS[day.month - 1]}"


def format_long(day: date) -> str:
    return f"{day.day} {MONTHS[day.month - 1]} {day.year}"


def format_clock(minutes: int) -> str:
    hour, minute = divmod(int(minutes), 60)
    return f"{hour:02d}:{minute:02d}"


def parse_clock(value: str) -> int:
    hour, minute = str(value).split(":")
    return int(hour) * 60 + int(minute)


def format_minutes(minutes: int) -> str:
    minutes = int(minutes)
    sign = "-" if minutes < 0 else ""
    minutes = abs(minutes)
    hours, mins = divmod(minutes, 60)
    if hours and mins:
        return f"{sign}{hours}h {mins}m"
    if hours:
        return f"{sign}{hours}h"
    return f"{sign}{mins}m"


def canonical_task_type(value: str) -> str:
    legacy = {
        "Revision": TASK_RECALL,
        "Learn / review": TASK_LEARN,
        "Coding practice": TASK_PRACTICE,
        "Recall / revision": TASK_RECALL,
    }
    return legacy.get(str(value), str(value))


def availability_for_window(monday_first_hours: list[float], start: date, days: int = 7) -> list[float]:
    """Map a Monday-first week onto consecutive calendar dates."""
    return [
        float(monday_first_hours[(start + timedelta(days=offset)).weekday()])
        for offset in range(days)
    ]


def schedulable_day_count(start_date: date, deadline: date) -> int:
    days_left = (deadline - start_date).days
    if days_left <= 0:
        return 0
    return min(PLANNING_HORIZON_DAYS, days_left)


def clamp_mastery(mastery: int) -> int:
    return max(0, min(100, int(mastery)))


def clamp_importance(importance: int) -> int:
    return max(1, min(5, int(importance)))


def urgency_multiplier(days_left: int) -> float:
    """Continuous deadline factor. Fewer days left raise the score."""
    return 1 + URGENCY_WEIGHT / max(int(days_left), 1)


def priority_parts(mastery: int, importance: int, days_left: int) -> dict[str, Any]:
    mastery_value = clamp_mastery(mastery)
    importance_value = clamp_importance(importance)
    gap = 1 - mastery_value / 100
    importance_norm = importance_value / 5
    base = 100 * (MASTERY_WEIGHT * gap + IMPORTANCE_WEIGHT * importance_norm)
    urgency = urgency_multiplier(days_left)
    raw = base * urgency
    return {
        "mastery": mastery_value,
        "importance": importance_value,
        "gap": gap,
        "importance_norm": importance_norm,
        "base": base,
        "urgency": urgency,
        "capped": raw > 100,
        "score": round(min(100.0, raw), 1),
    }


def priority_score(mastery: int, importance: int, days_left: int) -> float:
    """Explainable score: 55% mastery gap + 45% importance, then a small urgency factor."""
    return float(priority_parts(mastery, importance, days_left)["score"])


def explain_priority(topic: dict[str, Any], score: float, days_left: int) -> str:
    parts = priority_parts(int(topic["mastery"]), int(topic["importance"]), days_left)
    mastery = parts["mastery"]
    importance = parts["importance"]
    if mastery < 50:
        mastery_text = f"mastery is low ({mastery}%), leaving a large gap"
    elif mastery < 75:
        mastery_text = f"mastery is still developing ({mastery}%)"
    else:
        mastery_text = f"mastery is relatively strong ({mastery}%)"
    day_word = "day" if abs(days_left) == 1 else "days"
    urgency_text = f"{days_left} {day_word} left, urgency x{parts['urgency']:.2f}."
    if days_left < 0:
        urgency_text += " The deadline has passed, so this score is not used to build a schedule."
    elif days_left == 0:
        urgency_text += " The assessment is today, so this score is not used to build a schedule."
    if parts["capped"]:
        urgency_text += " The score is capped at 100."
    shown = parts["score"] if score is None else parts["score"]
    return (
        f"Priority {shown}/100 because {mastery_text} and assessment importance is {importance}/5. "
        f"Score = min(100, 100 x ({MASTERY_WEIGHT:.2f} x mastery gap {parts['gap']:.2f} "
        f"+ {IMPORTANCE_WEIGHT:.2f} x importance {parts['importance_norm']:.2f}) "
        f"x urgency {parts['urgency']:.2f}). {urgency_text}"
    )


def study_activity_minutes(total_minutes: int) -> list[tuple[str, int]]:
    """Split requested minutes into learning, coding practice, and recall.

    Rounding is corrected so the three parts add up to total_minutes.
    Recall receives the remainder, which is the 20% share after rounding.
    """
    total = max(0, int(total_minutes))
    learn = int(round(total * LEARN_SHARE))
    practice = int(round(total * PRACTICE_SHARE))
    if learn + practice > total:
        practice = max(0, total - learn)
    recall = total - learn - practice
    return [(TASK_LEARN, learn), (TASK_PRACTICE, practice), (TASK_RECALL, recall)]


def activity_text(task_type: str, topic_name: str) -> str:
    if task_type == TASK_LEARN:
        return (
            f"Study the core ideas in {topic_name}. "
            "Work one guided example and write a short summary in your own words."
        )
    if task_type == TASK_PRACTICE:
        return (
            f"Solve assessment-style coding problems on {topic_name}. "
            "Test edge cases and note the mistakes to revisit."
        )
    return (
        f"Close the notes and recall the main patterns for {topic_name}, "
        "then review anything that would not come back."
    )


def split_minutes(total_minutes: int, chunk: int = MAX_SESSION_MINUTES) -> list[int]:
    parts: list[int] = []
    remaining = max(0, int(total_minutes))
    while remaining > 0:
        part = min(chunk, remaining)
        parts.append(part)
        remaining -= part
    return parts


def compute_gaps(
    occupied: list[tuple[int, int]], window_start: int, window_end: int
) -> list[tuple[int, int]]:
    cursor = window_start
    gaps: list[tuple[int, int]] = []
    for start, end in sorted(occupied):
        start = max(int(start), window_start)
        end = min(int(end), window_end)
        if end <= window_start or start >= window_end or end <= start:
            continue
        if start > cursor:
            gaps.append((cursor, start))
        cursor = max(cursor, end)
    if cursor < window_end:
        gaps.append((cursor, window_end))
    return gaps


def choose_take(
    occupied: list[tuple[int, int]],
    window_start: int,
    window_end: int,
    remaining: int,
    free_minutes: int,
) -> tuple[int, int] | None:
    """Earliest slot that can take this work without crossing the day's free minutes.

    A larger block is split only when both the piece and the leftover are at least
    MIN_PARTIAL_MINUTES. A short activity is scheduled whole when a gap can hold it.
    """
    if remaining <= 0 or free_minutes <= 0 or window_end <= window_start:
        return None
    gaps = compute_gaps(occupied, window_start, window_end)
    if remaining <= free_minutes:
        for gap_start, gap_end in gaps:
            if gap_end - gap_start >= remaining:
                return gap_start, remaining
    for gap_start, gap_end in gaps:
        available = min(gap_end - gap_start, free_minutes, remaining)
        if available <= 0 or available == remaining:
            continue
        leftover = remaining - available
        if leftover < MIN_PARTIAL_MINUTES:
            take = min(available, remaining - MIN_PARTIAL_MINUTES)
            if take >= MIN_PARTIAL_MINUTES:
                return gap_start, take
            continue
        if available >= MIN_PARTIAL_MINUTES:
            return gap_start, available
    return None


def _empty_summary(message: str, days_left: int, status: str) -> dict[str, Any]:
    return {
        "ok": False,
        "status": status,
        "message": message,
        "days_left": days_left,
        "schedulable_days": 0,
        "total_available_minutes": 0,
        "total_scheduled_minutes": 0,
        "total_requested_minutes": 0,
        "unallocated_minutes": 0,
        "unallocated_tasks": [],
        "preserved_sessions": [],
        "completed_applied_minutes": 0,
        "daily_totals": {},
        "validation": {
            "valid": False,
            "status": "FAIL",
            "errors": [message],
            "daily_totals": {},
            "days": [],
            "overlap_dates": [],
        },
    }


def _new_day_state(capacity: int, day_start_minutes: int) -> dict[str, Any]:
    return {
        "capacity": capacity,
        "free": capacity,
        "window_start": day_start_minutes,
        "window_end": day_start_minutes + capacity,
        "occupied": [],
    }


def _place_preserved_session(session: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
    """Keep a completed session on its original date and block that time."""
    item = dict(session)
    duration = int(item["duration_minutes"])
    choice = choose_take(
        state["occupied"], state["window_start"], state["window_end"], duration, state["free"]
    )
    if choice and choice[1] == duration:
        start_min, take = choice
        end_min = start_min + take
        state["free"] -= take
        state["occupied"].append((start_min, end_min))
    else:
        if item.get("start_time") and item.get("end_time"):
            try:
                start_min = parse_clock(item["start_time"])
                end_min = parse_clock(item["end_time"])
                if end_min - start_min != duration:
                    raise ValueError
            except (TypeError, ValueError):
                start_min = state["window_start"]
                end_min = start_min + duration
        else:
            start_min = state["window_start"]
            end_min = start_min + duration
        state["occupied"].append((start_min, end_min))
        state["free"] = max(0, state["free"] - duration)
    item["start_time"] = format_clock(start_min)
    item["end_time"] = format_clock(end_min)
    item["duration_minutes"] = duration
    item["completed"] = True
    item["day_name"] = weekday_name(date.fromisoformat(str(item["day_date"])))
    item["task_type"] = canonical_task_type(item.get("task_type", TASK_LEARN))
    return item


def generate_plan(
    topics: list[dict[str, Any]],
    daily_hours: list[float],
    start_date: date,
    deadline: date,
    completed_keys: set[tuple[str, str, int]] | list[tuple[str, str, int]] | None = None,
    *,
    completed_sessions: list[dict[str, Any]] | None = None,
    day_start_minutes: int = DAY_START_MINUTES,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Schedule highest-priority work on the earliest day that can hold it.

    Completed sessions stay on their original dates and their minutes are not
    assigned again. Work that cannot fit is returned as unallocated.
    """
    days_left = (deadline - start_date).days
    if days_left < 0:
        return [], _empty_summary(
            "Deadline has passed (overdue). No sessions were generated. Choose a future assessment date.",
            days_left,
            "OVERDUE",
        )
    schedulable = schedulable_day_count(start_date, deadline)
    if schedulable <= 0:
        return [], _empty_summary(
            "The assessment is today, so there is no study day before the deadline. Choose a future date.",
            days_left,
            "OVERDUE",
        )
    if len(daily_hours) < schedulable:
        return [], _empty_summary(
            "Provide an availability value for every day in the planning window.",
            days_left,
            "FAIL",
        )

    ranked: list[dict[str, Any]] = []
    for raw in topics:
        topic = dict(raw)
        topic["topic"] = str(topic.get("topic", "Topic")).strip() or "Topic"
        parts = priority_parts(int(topic.get("mastery", 0)), int(topic.get("importance", 1)), days_left)
        topic["mastery"] = parts["mastery"]
        topic["importance"] = parts["importance"]
        topic["priority"] = parts["score"]
        topic["reason"] = explain_priority(topic, parts["score"], days_left)
        ranked.append(topic)
    ranked.sort(key=lambda item: (-item["priority"], item["topic"]))

    window_dates = [(start_date + timedelta(days=offset)).isoformat() for offset in range(schedulable)]
    day_states = {
        day: _new_day_state(int(round(float(daily_hours[index]) * 60)), day_start_minutes)
        for index, day in enumerate(window_dates)
    }

    completed_minutes: Counter[tuple[str, str]] = Counter()
    preserved_input: list[dict[str, Any]] = []
    if completed_sessions:
        preserved_input = [dict(session) for session in completed_sessions]
        preserved_input.sort(
            key=lambda session: (
                str(session.get("day_date", "")),
                str(session.get("start_time") or "99:99"),
                int(session.get("id") or 0),
            )
        )
        for session in preserved_input:
            task_type = canonical_task_type(session.get("task_type", TASK_LEARN))
            session["task_type"] = task_type
            completed_minutes[(str(session.get("topic")), task_type)] += int(session.get("duration_minutes") or 0)
    elif completed_keys:
        for topic_name, task_type, minutes in completed_keys:
            completed_minutes[(str(topic_name), canonical_task_type(task_type))] += int(minutes)

    tasks: list[dict[str, Any]] = []
    total_requested = 0
    completed_applied = 0
    for topic in ranked:
        requested = max(0, int(round(float(topic.get("hours", 0)) * 60)))
        total_requested += requested
        if requested == 0:
            continue
        for task_type, budget in study_activity_minutes(requested):
            if budget <= 0:
                continue
            key = (topic["topic"], task_type)
            done = min(completed_minutes[key], budget)
            completed_minutes[key] -= done
            completed_applied += done
            text = activity_text(task_type, topic["topic"])
            for chunk in split_minutes(budget - done):
                tasks.append(
                    {
                        "topic": topic["topic"],
                        "task_type": task_type,
                        "task": text,
                        "duration_minutes": chunk,
                        "priority": topic["priority"],
                        "reason": topic["reason"],
                    }
                )
    tasks.sort(key=lambda item: (-item["priority"], TASK_ORDER.get(item["task_type"], 9), item["topic"]))

    normalized_preserved: list[dict[str, Any]] = []
    for session in preserved_input:
        day = str(session.get("day_date", ""))
        if day in day_states:
            normalized_preserved.append(_place_preserved_session(session, day_states[day]))
        else:
            session["task_type"] = canonical_task_type(session.get("task_type", TASK_LEARN))
            normalized_preserved.append(session)

    plan: list[dict[str, Any]] = []
    unallocated: list[dict[str, Any]] = []
    for task in tasks:
        remaining = int(task["duration_minutes"])
        while remaining > 0:
            placed = False
            for day in window_dates:
                state = day_states[day]
                choice = choose_take(
                    state["occupied"],
                    state["window_start"],
                    state["window_end"],
                    remaining,
                    state["free"],
                )
                if not choice:
                    continue
                start_min, take = choice
                end_min = start_min + take
                state["free"] -= take
                state["occupied"].append((start_min, end_min))
                session_date = date.fromisoformat(day)
                plan.append(
                    {
                        "topic": task["topic"],
                        "task_type": task["task_type"],
                        "task": task["task"],
                        "duration_minutes": take,
                        "priority": task["priority"],
                        "reason": task["reason"],
                        "day_date": day,
                        "day_name": weekday_name(session_date),
                        "start_time": format_clock(start_min),
                        "end_time": format_clock(end_min),
                        "completed": False,
                    }
                )
                remaining -= take
                placed = True
                break
            if not placed:
                unallocated.append(
                    {
                        "topic": task["topic"],
                        "task_type": task["task_type"],
                        "task": task["task"],
                        "duration_minutes": remaining,
                        "priority": task["priority"],
                        "reason": task["reason"],
                        "unallocated_reason": (
                            "Not enough daily availability remains before the assessment deadline."
                        ),
                    }
                )
                break

    plan.sort(key=lambda session: (session["day_date"], session["start_time"], TASK_ORDER.get(session["task_type"], 9)))
    in_window_preserved = [session for session in normalized_preserved if session.get("day_date") in day_states]
    validation = validate_schedule(
        in_window_preserved + plan, daily_hours, schedulable, start_date
    )
    new_minutes = sum(int(session["duration_minutes"]) for session in plan)
    preserved_minutes = sum(int(session["duration_minutes"]) for session in in_window_preserved)
    unallocated_minutes = sum(int(task["duration_minutes"]) for task in unallocated)
    total_available = sum(state["capacity"] for state in day_states.values())
    total_scheduled = new_minutes + preserved_minutes

    if not validation["valid"]:
        message = "Schedule failed validation. " + " ".join(validation["errors"])
    elif total_available == 0 and total_requested > 0:
        message = (
            "Daily availability is zero, so nothing was scheduled. "
            "All requested work is listed as unallocated. "
            "Validation PASSes because the plan does not exceed availability."
        )
    elif unallocated_minutes > 0:
        message = (
            "Schedule generated within daily limits. "
            "Some requested work does not fit before the deadline and is listed as unallocated."
        )
    else:
        message = "Schedule generated. All requested study time fits before the deadline."

    summary = {
        "ok": validation["valid"],
        "status": "PASS" if validation["valid"] else "FAIL",
        "message": message,
        "days_left": days_left,
        "schedulable_days": schedulable,
        "total_available_minutes": total_available,
        "total_scheduled_minutes": total_scheduled,
        "total_requested_minutes": total_requested,
        "unallocated_minutes": unallocated_minutes,
        "unallocated_tasks": unallocated,
        "preserved_sessions": normalized_preserved,
        "completed_applied_minutes": completed_applied,
        "daily_totals": validation["daily_totals"],
        "validation": validation,
    }
    return plan, summary


def validate_schedule(
    plan: list[dict[str, Any]],
    daily_hours: list[float],
    schedulable_days: int = 7,
    start_date: date | None = None,
) -> dict[str, Any]:
    """Check each calendar day against that day's own availability.

    Pass start_date. A day with no sessions is still part of the window.
    Inferring the start from the first session is only a fallback, because a
    rest day at the beginning would otherwise shift every later day.
    """
    errors: list[str] = []
    totals: dict[str, int] = {}
    overlap_dates: set[str] = set()
    intervals: dict[str, list[tuple[int, int]]] = defaultdict(list)

    if start_date is None:
        parsed_dates = []
        for session in plan:
            try:
                parsed_dates.append(date.fromisoformat(str(session["day_date"])))
            except (KeyError, TypeError, ValueError):
                continue
        start_date = min(parsed_dates) if parsed_dates else date.today()

    window_count = max(0, min(int(schedulable_days), len(daily_hours)))
    window_dates = [(start_date + timedelta(days=offset)).isoformat() for offset in range(window_count)]
    window_set = set(window_dates)

    for session in plan:
        if "day_date" not in session:
            errors.append("A session is missing a date.")
            continue
        day = str(session["day_date"])
        try:
            duration = int(session["duration_minutes"])
        except (KeyError, TypeError, ValueError):
            errors.append(f"{day}: a session has an invalid duration.")
            continue
        if duration <= 0:
            errors.append(f"{day}: a session has a non-positive duration.")
        totals[day] = totals.get(day, 0) + max(duration, 0)
        start_time = session.get("start_time")
        end_time = session.get("end_time")
        if not start_time or not end_time:
            continue
        try:
            start_min = parse_clock(str(start_time))
            end_min = parse_clock(str(end_time))
        except (TypeError, ValueError):
            errors.append(f"{day}: a session has an invalid clock time.")
            continue
        if end_min - start_min != duration:
            errors.append(
                f"{day}: {start_time}-{end_time} does not match the {duration}-minute duration."
            )
        intervals[day].append((start_min, end_min))

    for day, spans in intervals.items():
        spans.sort()
        for (first_start, first_end), (second_start, second_end) in zip(spans, spans[1:]):
            if first_end > second_start:
                errors.append(
                    f"{day}: overlapping sessions {format_clock(first_start)}-{format_clock(first_end)} "
                    f"and {format_clock(second_start)}-{format_clock(second_end)}."
                )
                overlap_dates.add(day)

    days_report = []
    for index, day in enumerate(window_dates):
        available = int(round(float(daily_hours[index]) * 60))
        scheduled = totals.get(day, 0)
        within_limit = scheduled <= available
        if not within_limit:
            errors.append(
                f"{day}: scheduled {scheduled} minutes, availability is {available} minutes."
            )
        days_report.append(
            {
                "date": day,
                "available": available,
                "scheduled": scheduled,
                "remaining": max(0, available - scheduled),
                "within_limit": within_limit,
                "overlap": day in overlap_dates,
            }
        )

    for day in totals:
        if day not in window_set:
            errors.append(f"{day}: session is outside the planning window.")

    valid = len(errors) == 0
    return {
        "valid": valid,
        "status": "PASS" if valid else "FAIL",
        "errors": errors,
        "daily_totals": totals,
        "days": days_report,
        "overlap_dates": sorted(overlap_dates),
    }


def init_db() -> None:
    with sqlite3.connect(DB_PATH) as con:
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                plan_id TEXT NOT NULL,
                day_date TEXT NOT NULL,
                day_name TEXT NOT NULL,
                start_time TEXT,
                end_time TEXT,
                topic TEXT NOT NULL,
                task_type TEXT NOT NULL,
                task TEXT NOT NULL,
                duration_minutes INTEGER NOT NULL,
                priority REAL NOT NULL,
                reason TEXT NOT NULL,
                completed INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS topic_progress (
                profile_name TEXT NOT NULL,
                topic TEXT NOT NULL,
                mastery INTEGER NOT NULL,
                PRIMARY KEY (profile_name, topic)
            )
            """
        )
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS plan_meta (
                profile_name TEXT PRIMARY KEY,
                summary_json TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        existing = {row[1] for row in con.execute("PRAGMA table_info(sessions)")}
        for column, typedef in (("start_time", "TEXT"), ("end_time", "TEXT")):
            if column not in existing:
                con.execute(f"ALTER TABLE sessions ADD COLUMN {column} {typedef}")
        con.commit()


def _insert_session(con: sqlite3.Connection, profile_name: str, session: dict[str, Any], completed: bool) -> None:
    day = str(session["day_date"])
    con.execute(
        """
        INSERT INTO sessions (
            plan_id, day_date, day_name, start_time, end_time, topic, task_type, task,
            duration_minutes, priority, reason, completed
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            profile_name,
            day,
            session.get("day_name") or weekday_name(date.fromisoformat(day)),
            session.get("start_time"),
            session.get("end_time"),
            session.get("topic") or "Topic",
            canonical_task_type(session.get("task_type", TASK_LEARN)),
            session.get("task") or "",
            int(session.get("duration_minutes") or 0),
            float(session.get("priority") or 0),
            session.get("reason") or "",
            1 if completed else 0,
        ),
    )


def save_plan(
    plan: list[dict[str, Any]],
    profile_name: str,
    preserve_completed: bool = True,
    completed_rows: list[dict[str, Any]] | None = None,
) -> None:
    init_db()
    with sqlite3.connect(DB_PATH) as con:
        con.row_factory = sqlite3.Row
        if not preserve_completed:
            stored_completed: list[dict[str, Any]] = []
        elif completed_rows is not None:
            stored_completed = [dict(row) for row in completed_rows]
        else:
            stored_completed = [
                dict(row)
                for row in con.execute(
                    "SELECT * FROM sessions WHERE plan_id=? AND completed=1",
                    (profile_name,),
                ).fetchall()
            ]
        con.execute("DELETE FROM sessions WHERE plan_id=?", (profile_name,))
        for row in stored_completed:
            _insert_session(con, profile_name, row, True)
        for row in plan:
            _insert_session(con, profile_name, row, False)
        con.commit()


def load_plan(profile_name: str) -> list[dict[str, Any]]:
    init_db()
    with sqlite3.connect(DB_PATH) as con:
        con.row_factory = sqlite3.Row
        rows = con.execute(
            """
            SELECT id, plan_id, day_date, day_name, start_time, end_time, topic, task_type,
                   task, duration_minutes, priority, reason, completed
            FROM sessions
            WHERE plan_id=?
            ORDER BY day_date, COALESCE(start_time, '99:99'), id
            """,
            (profile_name,),
        ).fetchall()
    loaded = []
    for row in rows:
        item = dict(row)
        item["task_type"] = canonical_task_type(item["task_type"])
        item["completed"] = int(item["completed"])
        loaded.append(item)
    return loaded


def set_completed(session_id: int, completed: bool) -> None:
    init_db()
    with sqlite3.connect(DB_PATH) as con:
        con.execute(
            "UPDATE sessions SET completed=? WHERE id=?",
            (1 if completed else 0, int(session_id)),
        )
        con.commit()


def save_mastery(profile_name: str, topics: list[dict[str, Any]]) -> None:
    init_db()
    with sqlite3.connect(DB_PATH) as con:
        for topic in topics:
            con.execute(
                """
                INSERT INTO topic_progress(profile_name, topic, mastery)
                VALUES (?, ?, ?)
                ON CONFLICT(profile_name, topic) DO UPDATE SET mastery=excluded.mastery
                """,
                (profile_name, topic["topic"], int(topic["mastery"])),
            )
        con.commit()


def load_mastery(profile_name: str, topics: list[dict[str, Any]]) -> list[dict[str, Any]]:
    init_db()
    with sqlite3.connect(DB_PATH) as con:
        rows = con.execute(
            "SELECT topic, mastery FROM topic_progress WHERE profile_name=?",
            (profile_name,),
        ).fetchall()
    saved = {topic: mastery for topic, mastery in rows}
    loaded = []
    for topic in topics:
        item = dict(topic)
        if item["topic"] in saved:
            item["mastery"] = int(saved[item["topic"]])
        loaded.append(item)
    return loaded


def save_run(profile_name: str, message: str) -> None:
    init_db()
    payload = json.dumps({"generated": True, "message": message})
    with sqlite3.connect(DB_PATH) as con:
        con.execute(
            """
            INSERT INTO plan_meta(profile_name, summary_json, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(profile_name) DO UPDATE SET
                summary_json=excluded.summary_json,
                updated_at=excluded.updated_at
            """,
            (profile_name, payload, datetime.now().isoformat(timespec="seconds")),
        )
        con.commit()


def has_saved_run(profile_name: str) -> bool:
    init_db()
    with sqlite3.connect(DB_PATH) as con:
        row = con.execute(
            "SELECT profile_name FROM plan_meta WHERE profile_name=?",
            (profile_name,),
        ).fetchone()
    return row is not None


def reset_profile(profile_name: str) -> None:
    init_db()
    with sqlite3.connect(DB_PATH) as con:
        con.execute("DELETE FROM sessions WHERE plan_id=?", (profile_name,))
        con.execute("DELETE FROM topic_progress WHERE profile_name=?", (profile_name,))
        con.execute("DELETE FROM plan_meta WHERE profile_name=?", (profile_name,))
        con.commit()


def clean_topics(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    cleaned = []
    seen: set[str] = set()
    for record in records:
        name = str(record.get("topic", "")).strip()
        if not name or name.lower() == "nan":
            continue
        try:
            mastery = int(round(float(record.get("mastery", 0))))
        except (TypeError, ValueError):
            mastery = 0
        try:
            importance = int(round(float(record.get("importance", 1))))
        except (TypeError, ValueError):
            importance = 1
        try:
            hours = float(record.get("hours", 0))
        except (TypeError, ValueError):
            hours = 0.0
        if name in seen:
            continue
        seen.add(name)
        cleaned.append(
            {
                "topic": name,
                "mastery": max(0, min(100, mastery)),
                "importance": max(1, min(5, importance)),
                "hours": round(max(0.0, min(20.0, hours)), 2),
            }
        )
    return cleaned


def profile_slug(name: str) -> str:
    return "".join(character if character.isalnum() else "_" for character in name)


def algorithm_explanation() -> str:
    return f"""
"AI" here means classical, rule-based AI: a goal-based planning agent that uses a transparent heuristic priority score, constraint-based scheduling and re-planning when progress changes. It does not use machine learning, a trained model or a language model, which keeps every priority explainable and the availability limit guaranteed.

**This is an explainable rule, not a trained model.** No external API is called.

**Priority**

`mastery_gap = 1 - mastery / 100`

`importance_normalised = importance / 5`

`base_priority = 100 * ({MASTERY_WEIGHT:.2f} * mastery_gap + {IMPORTANCE_WEIGHT:.2f} * importance_normalised)`

`urgency = 1 + {URGENCY_WEIGHT:.2f} / max(days_left, 1)`

`priority = min(100, base_priority * urgency)`

Fewer days left raise the multiplier. Three days left is x1.17. A past deadline does not produce a schedule.

A higher score means the topic needs attention sooner. A large mastery gap and a high assessment weight both raise it.

**Time split**

Requested minutes are split into about {LEARN_SHARE:.0%} learning, {PRACTICE_SHARE:.0%} coding practice, and the remainder recall / revision. Rounding is adjusted so the three parts add up to the requested minutes.

**Scheduling rules**

- Sessions are placed only on days before the assessment, for at most {PLANNING_HORIZON_DAYS} days from today.
- Higher-priority work is placed on the earliest day that can hold it.
- Clock times start at 09:00 and run in order. Overlapping sessions are rejected.
- Each piece is at most {MAX_SESSION_MINUTES} minutes.
- A day never receives more minutes than the availability entered for that date.
- Work that cannot fit is listed as unallocated. It is not forced onto the calendar.
- A split must leave at least {MIN_PARTIAL_MINUTES} minutes on both sides, so a day can keep a few unused minutes rather than create a tiny fragment.
- Completed minutes stay completed and are not scheduled again. Regeneration fills only the remaining work.
"""


def _readiness_percent(topics: list[dict[str, Any]]) -> float:
    """Display-only mastery, weighted by importance. Not used for scheduling."""
    weight = sum(int(topic["importance"]) for topic in topics)
    if weight <= 0:
        return 0.0
    weighted = sum(int(topic["mastery"]) * int(topic["importance"]) for topic in topics)
    return weighted / weight


def _mission_hero(
    student_name: str,
    days_left: int,
    overdue: bool,
    hours_planned: float,
    completion: float,
    readiness: float,
) -> str:
    name = student_name.strip() or "Student"
    if overdue:
        countdown = (
            "<div class='sp-count sp-count-late'>"
            "<strong>Overdue</strong>"
            "<p>This deadline has passed. Choose a future date to generate a plan.</p>"
            "</div>"
        )
    else:
        word = "day" if days_left == 1 else "days"
        countdown = (
            "<div class='sp-count'>"
            f"<strong>{max(days_left, 0)}</strong>"
            f"<span>{word} to the exam</span>"
            "</div>"
        )
    hours_label = f"{hours_planned:g} h"
    tiles = metric_tile("Hours in this plan", hours_label) + metric_tile("Finished", f"{completion:.0f}%")
    ring = progress_ring(readiness / 100, "Exam readiness", f"{readiness:.0f}%")
    return (
        "<div class='sp-hero sp-mission'>"
        "<p class='sp-kicker'>Exam Mission Control</p>"
        f"<h1>{html.escape(name)}</h1>"
        f"<div class='sp-mission-row'>{countdown}{tiles}{ring}</div>"
        "</div>"
    )


def _metric_row(pairs: list[tuple[str, str]]) -> None:
    tiles = "".join(metric_tile(label, value) for label, value in pairs)
    st.markdown(f"<div class='sp-metric-row'>{tiles}</div>", unsafe_allow_html=True)


def _status_banner(kind: str, title: str, detail: str) -> None:
    st.markdown(status_banner(kind, title), unsafe_allow_html=True)
    st.write(detail)


def _mastery_on_five(mastery: int) -> str:
    return f"{_mastery_level(mastery)}/5"


def _mastery_level(mastery: int) -> str:
    level = max(0.0, min(5.0, float(mastery) / 20))
    if abs(level - round(level)) < 0.05:
        return str(int(round(level)))
    return f"{level:.1f}"


def _ranking_snapshot(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {"topic": str(row["Topic"]), "rank": int(row["Rank"]), "mastery": int(row["Mastery (%)"])}
        for row in rows
    ]


def _rank_changes(previous: list[dict[str, Any]], current: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Compare the ranking stored before regenerate with the ranking about to be saved."""
    old = {str(item["topic"]): item for item in previous}
    order = [str(item["topic"]) for item in current]
    seen = set(order)
    for item in previous:
        if str(item["topic"]) not in seen:
            order.append(str(item["topic"]))
    changes = []
    for topic in order:
        before = old.get(topic)
        after = next((item for item in current if str(item["topic"]) == topic), None)
        old_rank = int(before["rank"]) if before else None
        new_rank = int(after["rank"]) if after else None
        old_mastery = int(before["mastery"]) if before else None
        new_mastery = int(after["mastery"]) if after else None
        if before is None:
            direction = "new"
        elif after is None:
            direction = "gone"
        elif new_rank is not None and old_rank is not None and new_rank < old_rank:
            direction = "up"
        elif new_rank is not None and old_rank is not None and new_rank > old_rank:
            direction = "down"
        else:
            direction = "same"
        changes.append(
            {
                "topic": topic,
                "old_rank": old_rank,
                "new_rank": new_rank,
                "old_mastery": old_mastery,
                "new_mastery": new_mastery,
                "direction": direction,
            }
        )
    return changes


def _change_sentence(item: dict[str, Any]) -> str | None:
    topic = str(item["topic"])
    old_level = _mastery_level(item["old_mastery"]) if item["old_mastery"] is not None else None
    new_level = _mastery_level(item["new_mastery"]) if item["new_mastery"] is not None else None
    if item["direction"] == "new":
        return f"{topic} entered the ranking at #{item['new_rank']} (mastery {new_level})."
    if item["direction"] == "gone":
        return f"{topic} left the ranking (was #{item['old_rank']})."
    if item["old_rank"] != item["new_rank"]:
        sentence = f"{topic} moved from #{item['old_rank']} to #{item['new_rank']}"
        if item["old_mastery"] != item["new_mastery"]:
            sentence += f" (mastery {old_level} to {new_level})"
        return sentence + "."
    if item["old_mastery"] != item["new_mastery"]:
        return f"{topic} stayed at #{item['new_rank']} (mastery {old_level} to {new_level})."
    return None


def _render_rank_changes(changes: list[dict[str, Any]]) -> None:
    sentences = [html.escape(text) for item in changes if (text := _change_sentence(item))]
    if sentences:
        changed = "<ul class='sp-change-list'>" + "".join(f"<li>{text}</li>" for text in sentences) + "</ul>"
    else:
        changed = "<p class='sp-rank-legend'>Ranks and mastery are unchanged.</p>"
    arrows = {
        "up": ("▲", "sp-rank-up", "moved up"),
        "new": ("▲", "sp-rank-up", "moved up"),
        "down": ("▼", "sp-rank-down", "moved down"),
        "gone": ("▼", "sp-rank-down", "moved down"),
        "same": ("=", "sp-rank-same", "unchanged"),
    }
    rows = []
    for item in changes:
        symbol, css, meaning = arrows[str(item["direction"])]
        old_rank = f"#{item['old_rank']}" if item["old_rank"] is not None else "—"
        new_rank = f"#{item['new_rank']}" if item["new_rank"] is not None else "—"
        if item["old_mastery"] is None:
            mastery = _mastery_level(int(item["new_mastery"]))
        elif item["new_mastery"] is None:
            mastery = _mastery_level(int(item["old_mastery"]))
        else:
            mastery = (
                f"{_mastery_level(int(item['old_mastery']))} → {_mastery_level(int(item['new_mastery']))}"
            )
        rows.append(
            "<div class='sp-rank-move'>"
            f"<span class='{css}' title='{meaning}'>{symbol}</span>"
            f"<span>{html.escape(old_rank)} → {html.escape(new_rank)}</span>"
            f"<strong>{html.escape(str(item['topic']))}</strong>"
            f"<span class='sp-rank-meta'>mastery {html.escape(mastery)}</span>"
            "</div>"
        )
    body = (
        "<p class='sp-kicker'>What changed</p>"
        f"{changed}"
        "<p class='sp-rank-legend'>▲ moved up · ▼ moved down · = unchanged</p>"
        + "".join(rows)
    )
    st.markdown(card(body, "Before and after"), unsafe_allow_html=True)


def _short_reason(reason: str) -> str:
    sentence, _, _rest = reason.partition(". ")
    if sentence and not sentence.endswith("."):
        sentence += "."
    return sentence or reason


def _importance_dots(level: int) -> str:
    marks = []
    for index in range(1, 6):
        state = "sp-dot sp-dot-on" if index <= level else "sp-dot"
        marks.append(f"<i class='{state}'></i>")
    return (
        f"<span class='sp-dots' aria-label='Importance {level} of 5'>"
        + "".join(marks)
        + "</span>"
    )


def _formula_breakdown(parts: dict[str, Any], reason: str) -> str:
    _sentence, _sep, rest = reason.partition(". ")
    detail = (
        "<dl class='sp-formula'>"
        f"<div><dt>Mastery gap</dt><dd>{parts['gap']:.2f}</dd></div>"
        f"<div><dt>Importance</dt><dd>{parts['importance']}/5, normalised {parts['importance_norm']:.2f}</dd></div>"
        f"<div><dt>Urgency multiplier</dt><dd>x{parts['urgency']:.2f}</dd></div>"
        "</dl>"
    )
    if rest:
        detail += f"<p>{html.escape(rest)}</p>"
    return (
        "<details><summary>Formula breakdown</summary>"
        f"{detail}</details>"
    )


def _ranking_cards(rows: list[dict[str, Any]]) -> str:
    top_score = max((float(row["Priority"]) for row in rows), default=1.0) or 1.0
    cards = []
    for row in rows:
        parts = row["parts"]
        share = max(0.0, min(100.0, float(row["Priority"]) / top_score * 100))
        body = (
            "<div class='sp-topic-top'>"
            f"{badge('#' + str(row['Rank']), 'accent')}"
            f"{progress_ring(float(row['Mastery (%)']) / 100, 'Mastery', _mastery_on_five(int(row['Mastery (%)'])))}"
            "</div>"
            f"<p class='sp-topic-why'>{html.escape(_short_reason(row['Why prioritised']))}</p>"
            f"{_importance_dots(int(row['Importance (1-5)']))}"
            "<div class='sp-bar' aria-hidden='true'>"
            f"<span style='width:{share:.1f}%'></span></div>"
            f"<p class='sp-bar-label'>Priority {row['Priority']} of {top_score:g}</p>"
            f"{metric_tile('Allocated', f'{float(row['Estimated hours']):g} h')}"
            f"{_formula_breakdown(parts, row['Why prioritised'])}"
        )
        cards.append(card(body, str(row["Topic"])))
    return "<div class='sp-topic-grid'>" + "".join(cards) + "</div>"


def _chart_theme() -> dict[str, Any]:
    """Dark, transparent Plotly layout shared by every chart."""
    return {
        "paper_bgcolor": "rgba(0,0,0,0)",
        "plot_bgcolor": "rgba(0,0,0,0)",
        "font": {"color": "#F4F1EA", "family": "Outfit, sans-serif"},
        "hoverlabel": {"bgcolor": "#16171B", "bordercolor": "#5C616B", "font": {"color": "#F4F1EA"}},
        "legend": {"orientation": "h", "yanchor": "bottom", "y": 1.02, "x": 0, "font": {"color": "#A8A49B"}},
    }


def _remember_start_mastery(profile_name: str, topics: list[dict[str, Any]]) -> None:
    """Keep the mastery from the first save of this plan. Later edits stay on the other line."""
    stored = st.session_state.setdefault("plan_start_mastery", {})
    if profile_name in stored or not topics:
        return
    stored[profile_name] = {str(topic["topic"]): int(topic["mastery"]) for topic in topics}


def _mastery_radar(topics: list[dict[str, Any]], start: dict[str, int]) -> go.Figure:
    names = [str(topic["topic"]) for topic in topics]
    now = [int(topic["mastery"]) for topic in topics]
    then = [int(start.get(name, value)) for name, value in zip(names, now)]
    figure = go.Figure()
    figure.add_trace(
        go.Scatterpolar(
            r=then,
            theta=names,
            name="At the start",
            fill="toself",
            line={"color": "#A8A49B", "width": 2},
            fillcolor="rgba(168, 164, 155, 0.16)",
            hovertemplate="%{theta}<br>Start %{r}<extra></extra>",
        )
    )
    figure.add_trace(
        go.Scatterpolar(
            r=now,
            theta=names,
            name="Now",
            fill="toself",
            line={"color": "#E4FF4A", "width": 2},
            fillcolor="rgba(228, 255, 74, 0.16)",
            hovertemplate="%{theta}<br>Now %{r}<extra></extra>",
        )
    )
    figure.update_layout(
        **_chart_theme(),
        height=360,
        margin={"l": 56, "r": 56, "t": 48, "b": 24},
        polar={
            "bgcolor": "rgba(0,0,0,0)",
            "radialaxis": {
                "range": [0, 100],
                "gridcolor": "#5C616B",
                "linecolor": "#5C616B",
                "tickfont": {"color": "#A8A49B", "size": 10},
            },
            "angularaxis": {
                "gridcolor": "#5C616B",
                "linecolor": "#5C616B",
                "tickfont": {"color": "#F4F1EA", "size": 11},
            },
        },
    )
    return figure


def _activity_donut(sessions: list[dict[str, Any]]) -> go.Figure:
    totals = {"Learn": 0, "Practice": 0, "Revise": 0}
    colours = {"Learn": "#5EEAD4", "Practice": "#F5C16C", "Revise": "#C4B5FD"}
    for session in sessions:
        kind = _session_kind(str(session.get("task_type", "")))
        label = {"learn": "Learn", "practice": "Practice", "revise": "Revise"}[kind]
        totals[label] += int(session["duration_minutes"])
    labels = [label for label, minutes in totals.items() if minutes > 0]
    values = [totals[label] for label in labels]
    figure = go.Figure(
        go.Pie(
            labels=labels,
            values=values,
            hole=0.62,
            sort=False,
            direction="clockwise",
            marker={"colors": [colours[label] for label in labels], "line": {"color": "#16171B", "width": 2}},
            textinfo="percent",
            hovertemplate="%{label}<br>%{value} min<extra></extra>",
        )
    )
    figure.update_layout(**_chart_theme(), height=360, margin={"l": 8, "r": 8, "t": 48, "b": 8})
    return figure


def _topic_minutes_chart(sessions: list[dict[str, Any]]) -> go.Figure:
    totals: dict[str, int] = defaultdict(int)
    for session in sessions:
        totals[str(session["topic"])] += int(session["duration_minutes"])
    ordered = sorted(totals, key=lambda topic: (-totals[topic], topic))
    figure = go.Figure(
        go.Bar(
            x=ordered,
            y=[totals[topic] for topic in ordered],
            marker_color="#E4FF4A",
            text=[totals[topic] for topic in ordered],
            textposition="outside",
            hovertemplate="%{x}<br>%{y} min<extra></extra>",
        )
    )
    figure.update_layout(
        **_chart_theme(),
        height=360,
        margin={"l": 8, "r": 8, "t": 28, "b": 8},
        showlegend=False,
        yaxis={"title": "Minutes", "gridcolor": "#5C616B", "zerolinecolor": "#5C616B", "automargin": True},
        xaxis={"tickangle": -28, "automargin": True},
    )
    return figure


def _render_insights(
    profile_name: str,
    topics: list[dict[str, Any]],
    sessions: list[dict[str, Any]],
) -> None:
    if not topics:
        st.info("Add a topic, then generate a plan. Charts will show how ready you are and how the week is split.")
        return
    if not sessions:
        st.info("Generate a plan to see these charts. They compare what you knew at the start with this week's study time.")
        return
    _remember_start_mastery(profile_name, topics)
    start = dict(st.session_state.get("plan_start_mastery", {}).get(profile_name, {}))
    st.caption("Each chart answers one question about this week.")
    columns = st.columns(3, gap="small")
    with columns[0]:
        st.markdown("<p class='sp-kicker sp-insights'>How well you know it</p>", unsafe_allow_html=True)
        st.plotly_chart(_mastery_radar(topics, start), width="stretch", config={"displayModeBar": False})
        st.caption("This compares how well you knew each topic at the start with how well you know it now.")
    with columns[1]:
        st.markdown("<p class='sp-kicker sp-insights'>Learn, practice, revise</p>", unsafe_allow_html=True)
        st.plotly_chart(_activity_donut(sessions), width="stretch", config={"displayModeBar": False})
        st.caption("This shows how your study time is split between learning, practice, and revision.")
    with columns[2]:
        st.markdown("<p class='sp-kicker sp-insights'>Minutes per topic</p>", unsafe_allow_html=True)
        st.plotly_chart(_topic_minutes_chart(sessions), width="stretch", config={"displayModeBar": False})
        st.caption("This shows how many minutes each topic gets this week.")


def _priority_chart(ranking: pd.DataFrame) -> None:
    """Draw the ranking scores. The numbers come from priority_score and are not recalculated here."""
    figure = go.Figure(
        go.Bar(
            x=ranking["Priority"],
            y=ranking["Topic"],
            orientation="h",
            marker_color="#E4FF4A",
            text=ranking["Priority"],
            textposition="auto",
            hovertemplate="%{y}<br>Priority %{x}<extra></extra>",
        )
    )
    figure.update_layout(
        xaxis_title="Priority",
        yaxis_title=None,
        xaxis={"range": [0, 100], "gridcolor": "#5C616B", "zerolinecolor": "#5C616B"},
        yaxis={"categoryorder": "array", "categoryarray": list(ranking["Topic"])[::-1]},
        margin={"l": 8, "r": 16, "t": 8, "b": 8},
        height=max(260, 48 * len(ranking) + 60),
        **_chart_theme(),
    )
    st.plotly_chart(figure, width="stretch", config={"displayModeBar": False})


def _paint_status(value: str) -> str:
    if value == "PASS":
        return "background-color: #D1FAE5; color: #065F46; font-weight: 700"
    if value == "FAIL":
        return "background-color: #FEE2E2; color: #991B1B; font-weight: 700"
    return ""


def _join_day_labels(days: list[dict[str, Any]]) -> str:
    labels = [format_day(date.fromisoformat(str(day["date"]))) for day in days]
    if len(labels) <= 1:
        return labels[0] if labels else ""
    if len(labels) == 2:
        return f"{labels[0]} and {labels[1]}"
    return ", ".join(labels[:-1]) + ", and " + labels[-1]


def _availability_statement(
    report: dict[str, Any],
    late_incomplete: list[dict[str, Any]],
) -> tuple[bool, str]:
    """One line for the availability panel. The pass flag follows validate_schedule."""
    over = [day for day in report["days"] if not day["within_limit"]]
    overlap = [day for day in report["days"] if day["overlap"]]
    passed = bool(report["valid"]) and not late_incomplete
    if over:
        names = _join_day_labels(over)
        verb = "exceeds" if len(over) == 1 else "exceed"
        return False, f"{names} {verb} the stated availability."
    if overlap:
        names = _join_day_labels(overlap)
        verb = "has" if len(overlap) == 1 else "have"
        return False, f"{names} {verb} overlapping sessions."
    if late_incomplete:
        labels: list[str] = []
        for session in late_incomplete:
            label = format_day(date.fromisoformat(str(session["day_date"])))
            if label not in labels:
                labels.append(label)
        if len(labels) == 1:
            names = labels[0]
        elif len(labels) == 2:
            names = f"{labels[0]} and {labels[1]}"
        else:
            names = ", ".join(labels[:-1]) + ", and " + labels[-1]
        verb = "has" if len(labels) == 1 else "have"
        return False, f"{names} still {verb} an unfinished session on or after the assessment."
    if not passed:
        errors = list(report.get("errors") or [])
        if errors:
            return False, str(errors[0])
        return False, "The saved plan fails the availability check."
    return True, "No day exceeds the student's stated availability."


def _capacity_row(day: dict[str, Any]) -> str:
    available = int(day["available"])
    scheduled = int(day["scheduled"])
    scale = max(available, scheduled, 1)
    fill = scheduled / scale * 100
    mark = available / scale * 100
    state = "sp-cap-ok" if day["within_limit"] else "sp-cap-over"
    label = format_day(date.fromisoformat(str(day["date"])))
    if available <= 0:
        label = f"{label} · Rest"
    nums = f"{format_minutes(scheduled)} / {format_minutes(available)}"
    return (
        f"<div class='sp-cap-row {state}'>"
        f"<span class='sp-cap-name'>{html.escape(label)}</span>"
        f"<div class='sp-cap-track' role='img' aria-label='{html.escape(nums)}'>"
        f"<span class='sp-cap-fill' style='width:{fill:.2f}%'></span>"
        f"<i class='sp-cap-mark' style='left:{mark:.2f}%'></i>"
        "</div>"
        f"<span class='sp-cap-nums'>{html.escape(nums)}</span>"
        "</div>"
    )


def _render_availability(report: dict[str, Any], late_incomplete: list[dict[str, Any]]) -> None:
    if not report["days"]:
        st.info("There are no study days before this assessment date.")
        return
    passed, statement = _availability_statement(report, late_incomplete)
    badge_class = "sp-pass-badge" if passed else "sp-fail-badge"
    badge_text = "PASS" if passed else "FAIL"
    line_class = "sp-avail-line" if passed else "sp-avail-line sp-avail-bad"
    planned = sum(int(day["scheduled"]) for day in report["days"])
    available = sum(int(day["available"]) for day in report["days"])
    rows = "".join(_capacity_row(day) for day in report["days"])
    body = (
        "<div class='sp-avail'>"
        "<div>"
        f"<p class='{line_class}'>{html.escape(statement)}</p>"
        "<div class='sp-avail-metrics'>"
        f"{metric_tile('Planned', _hours_label(planned))}"
        f"{metric_tile('Available', _hours_label(available))}"
        "</div></div>"
        f"<div class='{badge_class}'>{badge_text}</div>"
        "</div>"
        f"{rows}"
    )
    st.markdown(card(body), unsafe_allow_html=True)


def _show_validation_table(report: dict[str, Any]) -> None:
    table = pd.DataFrame(
        [
            {
                "Date": format_day(date.fromisoformat(day["date"])),
                "Available": format_minutes(day["available"]),
                "Scheduled": format_minutes(day["scheduled"]),
                "Remaining": format_minutes(day["remaining"]),
                "Within limit": "PASS" if day["within_limit"] else "FAIL",
                "Overlap": "FAIL" if day["overlap"] else "PASS",
            }
            for day in report["days"]
        ]
    )
    if table.empty:
        st.info("There are no study days before this assessment date.")
        return
    try:
        styled = table.style.map(_paint_status, subset=["Within limit", "Overlap"])
        st.dataframe(styled, width="stretch", hide_index=True)
    except Exception:
        st.dataframe(table, width="stretch", hide_index=True)


def _persist_plan(
    profile_name: str,
    topics: list[dict[str, Any]],
    plan: list[dict[str, Any]],
    summary: dict[str, Any],
) -> None:
    if not topics:
        st.error("Add at least one topic before generating a plan.")
        return
    if not summary["ok"]:
        st.error(summary["message"])
        return
    save_plan(
        plan,
        profile_name,
        preserve_completed=True,
        completed_rows=summary["preserved_sessions"],
    )
    save_mastery(profile_name, topics)
    save_run(profile_name, summary["message"])
    st.session_state.flash = (
        "Plan saved. Completed sessions were kept, and only the remaining work was scheduled."
    )
    st.rerun()


def _regenerate_plan(
    profile_name: str,
    topics: list[dict[str, Any]],
    plan: list[dict[str, Any]],
    summary: dict[str, Any],
) -> None:
    """Save the plan. The previous ranking is already in session state from the last run."""
    if not topics or not summary["ok"]:
        _persist_plan(profile_name, topics, plan, summary)
        return
    current = [dict(item) for item in st.session_state.get("live_ranking") or []]
    if not st.session_state.get("previous_ranking"):
        st.session_state.previous_ranking = current
    previous = [dict(item) for item in st.session_state.get("previous_ranking") or []]
    st.session_state.rank_comparison = _rank_changes(previous, current)
    st.session_state.show_rank_comparison = True
    st.session_state.previous_ranking = current
    st.session_state.regen_notice = True
    _remember_start_mastery(profile_name, topics)
    _persist_plan(profile_name, topics, plan, summary)


def _session_kind(task_type: str) -> str:
    canonical = canonical_task_type(task_type)
    if canonical == TASK_PRACTICE:
        return "practice"
    if canonical == TASK_RECALL:
        return "revise"
    return "learn"


def _hours_label(minutes: int) -> str:
    return f"{minutes / 60:g} h"


def _render_schedule(
    saved_plan: list[dict[str, Any]],
    daily_hours: list[float],
    start_date: date,
    schedulable: int,
    report: dict[str, Any],
) -> None:
    by_day: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for session in saved_plan:
        by_day[str(session["day_date"])].append(session)
    day_lookup = {day["date"]: day for day in report["days"]}
    pending: list[tuple[int, bool]] = []
    window_dates = [(start_date + timedelta(days=offset)).isoformat() for offset in range(schedulable)]
    window_sessions = [session for day in window_dates for session in by_day.get(day, [])]
    done_count = sum(1 for session in window_sessions if int(session.get("completed") or 0) == 1)
    total_count = len(window_sessions)
    week_share = (done_count / total_count * 100) if total_count else 0
    st.markdown(
        "<p class='sp-week-label'>"
        f"Week progress · {done_count} of {total_count} sessions</p>"
        "<div class='sp-bar'><span style='width:"
        f"{week_share:.1f}%'></span></div>",
        unsafe_allow_html=True,
    )

    if window_dates:
        columns = st.columns(len(window_dates), gap="small")
        for index, day in enumerate(window_dates):
            info = day_lookup.get(day, {})
            available = int(info.get("available", round(float(daily_hours[index]) * 60)))
            sessions = by_day.get(day, [])
            done_today = sum(1 for session in sessions if int(session.get("completed") or 0) == 1)
            current = date.fromisoformat(day)
            rest = available <= 0
            with columns[index]:
                if rest:
                    st.markdown(
                        "<div class='sp-day-card sp-rest'>"
                        "<div class='sp-day-head'><div>"
                        f"<strong>{html.escape(format_day(current))}</strong>"
                        f"<p>{html.escape(_hours_label(available))} available</p>"
                        "<p class='sp-rest-label'>Rest day</p>"
                        "</div></div></div>",
                        unsafe_allow_html=True,
                    )
                else:
                    ring = progress_ring(
                        (done_today / len(sessions)) if sessions else 0,
                        "Done",
                        f"{done_today}/{len(sessions)}",
                    )
                    st.markdown(
                        "<div class='sp-day-card'><div class='sp-day-head'><div>"
                        f"<strong>{html.escape(format_day(current))}</strong>"
                        f"<p>{html.escape(_hours_label(available))} available</p>"
                        f"</div>{ring}</div></div>",
                        unsafe_allow_html=True,
                    )
                if rest and not sessions:
                    continue
                if not sessions:
                    st.caption("No sessions.")
                    continue
                for session in sessions:
                    kind = _session_kind(str(session.get("task_type", TASK_LEARN)))
                    label = {"learn": "Learn", "practice": "Practice", "revise": "Revise"}[kind]
                    minutes = int(session.get("duration_minutes") or 0)
                    st.markdown(
                        f"<div class='sp-session sp-session-{kind}'>"
                        f"{badge(label, kind)}"
                        f"<strong>{html.escape(str(session.get('topic') or 'Topic'))}</strong>"
                        f"<span>{html.escape(format_minutes(minutes))}</span>"
                        "</div>",
                        unsafe_allow_html=True,
                    )
                    if "id" in session:
                        checked = st.checkbox(
                            "Done",
                            value=bool(session["completed"]),
                            key=f"done_{session['id']}",
                        )
                        if checked != bool(session["completed"]):
                            pending.append((int(session["id"]), checked))
                    else:
                        st.caption("Saved")

    outside = [session for session in saved_plan if session["day_date"] not in set(window_dates)]
    if outside:
        with st.expander(f"Saved sessions outside this planning window ({len(outside)})"):
            st.caption(
                "Completed sessions are kept for the record. "
                "Unfinished sessions outside the window are replaced the next time you regenerate."
            )
            for session in outside:
                state = "Done" if session["completed"] else "Not done"
                st.write(
                    f"{session['day_date']} · {session['topic']} · {session['task_type']} · "
                    f"{format_minutes(int(session['duration_minutes']))} · {state}"
                )

    if pending:
        for session_id, checked in pending:
            set_completed(session_id, checked)
        st.rerun()


def _step_bar(current: int) -> str:
    labels = ("1. Tell us about you", "2. See your plan", "3. Update progress")
    cells = []
    for index, label in enumerate(labels, start=1):
        css = "sp-step sp-step-on" if index == current else "sp-step"
        cells.append(f"<div class='{css}'><strong>{html.escape(label)}</strong></div>")
    return "<div class='sp-steps-bar'>" + "".join(cells) + "</div>"


def _study_label(rank: int, mastery: int) -> str:
    if int(mastery) >= 75:
        return "Looking good"
    if int(rank) == 1:
        return "Study first"
    return "Study soon"


def _plain_reason(mastery: int, importance: int) -> str:
    if importance >= 4:
        weight = "It is a big part of the exam."
    elif importance == 3:
        weight = "It is a medium part of the exam."
    else:
        weight = "It is a smaller part of the exam."
    return f"You know about {int(mastery)}% of this. {weight}"


def _plain_update(changes: list[dict[str, Any]]) -> str:
    dropped = next(
        (item for item in changes if item.get("old_rank") == 1 and item.get("direction") == "down"),
        None,
    )
    top = next((item for item in changes if item.get("new_rank") == 1), None)
    parts = ["Your plan was updated."]
    if dropped is not None:
        improved = (
            dropped.get("new_mastery") is not None
            and dropped.get("old_mastery") is not None
            and int(dropped["new_mastery"]) > int(dropped["old_mastery"])
        )
        reason = " (you improved)" if improved else ""
        parts.append(f"{dropped['topic']} moved down{reason}.")
    if top is not None and (dropped is None or top["topic"] != dropped["topic"]):
        parts.append(f"{top['topic']} is now your top topic.")
    return " ".join(parts)


def _edit_topics() -> list[dict[str, Any]]:
    """Simple list, plus the grid the headless test writes into. The grid remains the saved source."""
    nonce = st.session_state.topic_nonce
    editor_key = f"topic_editor_{nonce}"
    stored = [dict(topic) for topic in st.session_state.topics]
    st.caption("How well do you know each topic? Move a slider, then update the plan.")
    with st.expander("Bulk edit"):
        st.caption("Edit mastery here, then regenerate")
        editor = st.data_editor(
            pd.DataFrame(stored),
            num_rows="dynamic",
            width="stretch",
            height=280,
            column_config={
                "topic": st.column_config.TextColumn("Topic", required=True, width=180),
                "mastery": st.column_config.NumberColumn("Mastery (0-100)", min_value=0, max_value=100, step=5, width=150),
                "importance": st.column_config.NumberColumn("Importance (1-5)", min_value=1, max_value=5, step=1, width=160),
                "hours": st.column_config.NumberColumn("Estimated study hours", min_value=0.0, max_value=20.0, step=0.5, width=190),
            },
            key=editor_key,
        )
    current_topics = clean_topics(editor.fillna(0).to_dict(orient="records"))
    raw_names = [
        str(record.get("topic", "")).strip()
        for record in editor.fillna("").to_dict(orient="records")
        if str(record.get("topic", "")).strip()
    ]
    if len(raw_names) != len(set(raw_names)):
        st.warning("Topic names need to be unique. Repeated names are ignored when the plan is built.")
    slider_changed = False
    for index, topic in enumerate(current_topics):
        baseline = stored[index] if index < len(stored) else topic
        know_key = f"know_{nonce}_{index}"
        importance_key = f"imp_{nonce}_{index}"
        if know_key in st.session_state and int(st.session_state[know_key]) != int(baseline["mastery"]):
            topic["mastery"] = int(st.session_state[know_key])
            slider_changed = True
        elif know_key not in st.session_state or int(st.session_state[know_key]) != int(topic["mastery"]):
            st.session_state[know_key] = int(topic["mastery"])
        if importance_key in st.session_state and int(st.session_state[importance_key]) != int(baseline["importance"]):
            topic["importance"] = int(st.session_state[importance_key])
            slider_changed = True
        elif importance_key not in st.session_state or int(st.session_state[importance_key]) != int(topic["importance"]):
            st.session_state[importance_key] = int(topic["importance"])
        st.markdown(f"**{html.escape(str(topic['topic']))}** · {int(topic['mastery'])}%")
        st.slider(
            "How well do you know this? (0-100%)",
            min_value=0,
            max_value=100,
            step=5,
            key=know_key,
            help="0 means you have not studied it. 100 means you can solve it without notes.",
        )
        st.radio(
            "How important is it for the exam?",
            [1, 2, 3, 4, 5],
            horizontal=True,
            key=importance_key,
            help="1 is a small part of the exam. 5 is a large part.",
        )
    if slider_changed:
        st.session_state.topics = current_topics
        st.session_state.topic_nonce += 1
        st.rerun()
    return current_topics


def _mark_done(session: dict[str, Any], pending: list[tuple[int, bool]]) -> None:
    if "id" not in session:
        st.caption("Saved")
        return
    checked = st.checkbox(
        "Done",
        value=bool(session["completed"]),
        key=f"done_{session['id']}",
        help="Tick this when you finish the session. It stays finished when you update the plan.",
    )
    if checked != bool(session["completed"]):
        pending.append((int(session["id"]), checked))


def _apply_done(pending: list[tuple[int, bool]]) -> None:
    if not pending:
        return
    for session_id, checked in pending:
        set_completed(session_id, checked)
    st.rerun()


def _chip(task_type: str, minutes: int) -> str:
    kind = _session_kind(task_type)
    label = {"learn": "Learn", "practice": "Practice", "revise": "Revise"}[kind]
    return f"<span class='sp-chip sp-chip-{kind}'>{html.escape(label)} {html.escape(format_minutes(minutes))}</span>"


def _render_today(
    saved_plan: list[dict[str, Any]],
    daily_hours: list[float],
    start_date: date,
    schedulable: int,
    done_count: int,
    total_count: int,
    pending: list[tuple[int, bool]],
    allow_checks: bool,
) -> None:
    st.markdown(f"**{done_count} of {total_count} sessions done this week**")
    today_hours = float(daily_hours[0]) if schedulable else 0.0
    today_key = start_date.isoformat()
    todays = [session for session in saved_plan if str(session["day_date"]) == today_key]
    if today_hours <= 0:
        next_day = None
        for offset in range(1, schedulable):
            if float(daily_hours[offset]) > 0:
                next_day = start_date + timedelta(days=offset)
                break
        when = format_long(next_day) if next_day else "none left this week"
        st.markdown(
            "<div class='sp-today'><h2>Rest day</h2>"
            f"<p>Rest day. Next study day: {html.escape(when)}.</p></div>",
            unsafe_allow_html=True,
        )
        return
    if not todays:
        st.info("Nothing is scheduled today. Open My week to see the other days, or update the plan.")
        return
    blocks = []
    for session in todays:
        blocks.append(
            "<p><strong>"
            + html.escape(str(session.get("topic") or "Topic"))
            + "</strong> · "
            + html.escape(format_minutes(int(session.get("duration_minutes") or 0)))
            + "</p>"
        )
    st.markdown("<div class='sp-today'><h2>Study this now</h2>" + "".join(blocks) + "</div>", unsafe_allow_html=True)
    if allow_checks:
        for session in todays:
            _mark_done(session, pending)


def _render_week(
    saved_plan: list[dict[str, Any]],
    daily_hours: list[float],
    start_date: date,
    schedulable: int,
    pending: list[tuple[int, bool]],
    allow_checks: bool,
) -> None:
    if schedulable <= 0:
        st.info("There is no day left before this exam. Choose a later exam date to see a week.")
        return
    st.markdown(
        "<div class='sp-legend'>"
        "<span class='sp-chip sp-chip-learn'>Learn = read and understand</span>"
        "<span class='sp-chip sp-chip-practice'>Practice = solve problems</span>"
        "<span class='sp-chip sp-chip-revise'>Revise = recall without notes</span>"
        "</div>",
        unsafe_allow_html=True,
    )
    by_day: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for session in saved_plan:
        by_day[str(session["day_date"])].append(session)
    today_key = start_date.isoformat()
    for offset in range(schedulable):
        day = start_date + timedelta(days=offset)
        key = day.isoformat()
        sessions = by_day.get(key, [])
        hours = float(daily_hours[offset]) if offset < len(daily_hours) else 0.0
        if hours <= 0 and not sessions:
            chips = "<span class='sp-chip'>Rest day</span>"
        elif not sessions:
            chips = "<span>No sessions yet.</span>"
        else:
            chips = "".join(
                _chip(str(session.get("task_type") or TASK_LEARN), int(session.get("duration_minutes") or 0))
                for session in sessions
            )
        st.markdown(
            "<div class='sp-week-row'><strong>"
            + html.escape(format_day(day))
            + f"</strong><span>{hours:g} h</span><div>{chips}</div></div>",
            unsafe_allow_html=True,
        )
        if allow_checks:
            for session in sessions:
                if key == today_key and hours > 0:
                    continue
                _mark_done(session, pending)


def _render_topic_cards(ranking_rows: list[dict[str, Any]], ranking: pd.DataFrame, overdue: bool) -> None:
    if not ranking_rows:
        st.info("Add a topic to see what to study first. Use Tell us about you, then generate a plan.")
        return
    for row in ranking_rows:
        label = _study_label(int(row["Rank"]), int(row["Mastery (%)"]))
        reason = _plain_reason(int(row["Mastery (%)"]), int(row["Importance (1-5)"]))
        st.markdown(
            f"**{int(row['Rank'])}. {html.escape(str(row['Topic']))}** · {html.escape(label)}"
        )
        st.caption(reason)
    with st.expander("Show details"):
        st.caption("These are the numbers behind the labels. The plan uses them. You do not need them to study.")
        st.markdown(_ranking_cards(ranking_rows), unsafe_allow_html=True)
        _priority_chart(ranking)
        if st.toggle("Show raw table", key="show_raw_ranking"):
            st.dataframe(ranking, width="stretch", hide_index=True)
        if overdue:
            st.caption("These scores are informational only. A past or same-day deadline does not produce a timetable.")


def _render_plan_check(
    report: dict[str, Any],
    late_incomplete: list[dict[str, Any]],
    preview_summary: dict[str, Any],
) -> None:
    if not report["days"]:
        st.info("There are no study days before this exam. Choose a later date, then generate a plan.")
        return
    passed, statement = _availability_statement(report, late_incomplete)
    planned = sum(int(day["scheduled"]) for day in report["days"])
    available = sum(int(day["available"]) for day in report["days"])
    if passed:
        st.markdown(
            "<p class='sp-fit sp-fit-ok'>✓ Your plan fits your available time</p>",
            unsafe_allow_html=True,
        )
    else:
        st.markdown("<p class='sp-fit'>Your plan does not fit your available time</p>", unsafe_allow_html=True)
        st.error(statement)
    st.markdown(f"**Planned {format_minutes(planned)} of {format_minutes(available)} available**")
    st.caption(statement)
    if int(preview_summary.get("unallocated_minutes") or 0) > 0:
        st.caption(
            "Not enough time for "
            + format_minutes(int(preview_summary["unallocated_minutes"]))
            + ". Open Show daily details to see it. It is not added to a full day."
        )
    with st.expander("Show daily details"):
        if not passed:
            reasons = list(report["errors"])
            if late_incomplete:
                reasons.append("An unfinished saved session is on or after the exam date. Update the plan to replace it.")
            if reasons:
                st.error("\n\n".join(reasons))
        _show_validation_table(report)
        st.markdown("".join(_capacity_row(day) for day in report["days"]), unsafe_allow_html=True)
        tasks = list(preview_summary.get("unallocated_tasks") or [])
        if tasks:
            st.markdown("**Not enough time for**")
            grouped: dict[tuple[str, str], int] = {}
            for task in tasks:
                key = (str(task["topic"]), str(task["task_type"]))
                grouped[key] = grouped.get(key, 0) + int(task["duration_minutes"])
            for (topic_name, task_type), minutes in grouped.items():
                st.write(f"{topic_name} · {task_type} · {format_minutes(minutes)}")


def main() -> None:
    st.set_page_config(page_title="StudyPilot AI", page_icon="📚", layout="wide")
    init_db()
    st.markdown(page_style(enter=not st.session_state.get("ui_painted")), unsafe_allow_html=True)
    st.session_state.ui_painted = True

    if "profile_name" not in st.session_state:
        st.session_state.profile_name = None
        st.session_state.avail_nonce = 0
        st.session_state.topic_nonce = 0
        st.session_state.topics = []
        st.session_state.flash = ""
        st.session_state.previous_ranking = []
        st.session_state.rank_comparison = []
        st.session_state.show_rank_comparison = False
        st.session_state.regen_notice = False
        st.session_state.plan_start_mastery = {}
    if "student_name" not in st.session_state:
        st.session_state.student_name = "Student"
    if "how_dismissed" not in st.session_state:
        st.session_state.how_dismissed = False
    if "sample_profile" not in st.session_state:
        st.session_state.sample_profile = list(SAMPLE_PROFILES)[0]
    if "assessment_date" not in st.session_state:
        st.session_state.assessment_date = date.today() + timedelta(days=PLANNING_HORIZON_DAYS)

    start_date = date.today()

    with st.sidebar:
        st.header("Tell us about you")
        st.text_input("Your name", key="student_name", help="This name appears at the top of your plan.")
        if st.button("Load demo", width="stretch"):
            demo_name = "Beginner — limited time"
            st.session_state.sample_profile = demo_name
            st.session_state.assessment_date = date(2026, 11, 8)
            st.session_state.topics = [dict(topic) for topic in SAMPLE_PROFILES[demo_name]["topics"]]
            st.session_state.profile_name = demo_name
            st.session_state.avail_nonce += 1
            st.session_state.topic_nonce += 1
            st.session_state.flash = "Demo loaded. Beginner profile, deadline 8 Nov 2026, sample hours."
            st.rerun()
        for full_name, sample in SAMPLE_PROFILES.items():
            short_name = full_name.split(" — ")[0]
            blurb = sample["description"].split(". ")[0].rstrip(".") + "."
            selected = full_name == st.session_state.sample_profile
            card_class = "sp-profile sp-profile-on" if selected else "sp-profile"
            st.markdown(
                f"<div class='{card_class}'><strong>{html.escape(short_name)}</strong>"
                f"<p>{html.escape(blurb)}</p></div>",
                unsafe_allow_html=True,
            )
            if st.button(f"Use {short_name}", key=f"pick_{short_name}", width="stretch"):
                st.session_state.sample_profile = full_name
                st.rerun()
        with st.expander("Profile list"):
            profile_name = st.selectbox("Sample profile", list(SAMPLE_PROFILES), key="sample_profile")
        profile = SAMPLE_PROFILES[profile_name]
        reset_clicked = st.button("Load selected sample profile", width="stretch")
        if reset_clicked or st.session_state.profile_name != profile_name:
            base_topics = [dict(topic) for topic in profile["topics"]]
            if reset_clicked:
                reset_profile(profile_name)
                st.session_state.topics = base_topics
                st.session_state.flash = (
                    f"{profile_name} was reset to the sample mastery, hours, and an empty saved plan."
                )
            else:
                st.session_state.topics = load_mastery(profile_name, base_topics)
            st.session_state.profile_name = profile_name
            st.session_state.avail_nonce += 1
            st.session_state.topic_nonce += 1
            st.session_state.previous_ranking = []
            st.session_state.rank_comparison = []
            st.session_state.show_rank_comparison = False
            st.session_state.regen_notice = False
            starts = st.session_state.setdefault("plan_start_mastery", {})
            if reset_clicked:
                starts.pop(profile_name, None)
            elif has_saved_run(profile_name):
                _remember_start_mastery(profile_name, st.session_state.topics)

        st.divider()
        st.subheader("When is your exam?")
        with st.expander("Demo dates"):
            st.caption("24 Oct 2026 is already in the past. Use it only to see the overdue message.")
            if st.button("Use demo date (7 days ahead)", width="stretch"):
                st.session_state.assessment_date = date.today() + timedelta(days=PLANNING_HORIZON_DAYS)
                st.rerun()
            if st.button("Use 24 Oct 2026 (overdue scenario)", width="stretch"):
                st.session_state.assessment_date = date(2026, 10, 24)
                st.rerun()
        assessment_date = st.date_input(
            "When is your exam?",
            key="assessment_date",
            help="The plan uses the days before this date. The exam day itself is left free.",
        )
        days_left = (assessment_date - start_date).days
        schedulable = schedulable_day_count(start_date, assessment_date)
        if assessment_date <= start_date:
            st.warning("This deadline has passed. Choose a future date to generate a plan.")
        elif days_left > PLANNING_HORIZON_DAYS:
            st.caption(f"Your exam is {days_left} days away. This plan covers the next {PLANNING_HORIZON_DAYS} days.")
        else:
            st.caption(f"{schedulable} study day(s) before {format_long(assessment_date)}.")

        st.divider()
        st.subheader("Hours you can study")
        st.caption("Set each day from Monday to Sunday. Zero hours means a rest day.")
        slug = profile_slug(profile_name)
        monday_first: list[float] = []
        for index, weekday in enumerate(WEEKDAYS):
            monday_first.append(
                float(
                    st.slider(
                        weekday,
                        min_value=0.0,
                        max_value=8.0,
                        value=float(profile["daily_hours"][index]),
                        step=0.5,
                        key=f"avail_{slug}_{st.session_state.avail_nonce}_{weekday}",
                        help="Hours you can study on this weekday. The plan will not go past this.",
                    )
                )
            )
        daily_hours = availability_for_window(monday_first, start_date, PLANNING_HORIZON_DAYS)
        window_bits = [
            f"{format_day(start_date + timedelta(days=offset))} {daily_hours[offset]:g}h"
            for offset in range(schedulable)
        ]
        st.caption("This week: " + ", ".join(window_bits) if window_bits else "No study day falls before this exam.")
        st.caption(f"Hours in this plan: {sum(daily_hours[:schedulable]):g}.")

    if st.session_state.get("flash"):
        st.success(st.session_state.flash)
        st.session_state.flash = ""

    step_slot = st.container()
    hero_slot = st.container()

    saved_plan = load_plan(profile_name)
    completed_sessions = [session for session in saved_plan if int(session["completed"]) == 1]
    generated = has_saved_run(profile_name)
    overdue = assessment_date <= start_date
    window_dates = {(start_date + timedelta(days=offset)).isoformat() for offset in range(schedulable)}
    in_window = [session for session in saved_plan if session["day_date"] in window_dates]
    done_sessions = [session for session in in_window if int(session["completed"]) == 1]
    done_minutes = sum(int(session["duration_minutes"]) for session in done_sessions)
    scheduled_minutes = sum(int(session["duration_minutes"]) for session in in_window)
    completion = (done_minutes / scheduled_minutes * 100) if scheduled_minutes else 0.0

    if not st.session_state.get("how_dismissed"):
        st.info(
            "Pick a sample student and the hours you can study.\n\n"
            "Press the button to build a week that fits those hours.\n\n"
            "Tick what you finish, update how well you know a topic, then update the plan."
        )
        if st.button("Got it"):
            st.session_state.how_dismissed = True
            st.rerun()

    current_topics: list[dict[str, Any]] = []
    preview_plan: list[dict[str, Any]] = []
    preview_summary: dict[str, Any] = _empty_summary("Add a topic first.", days_left, "EMPTY")
    ranking_rows: list[dict[str, Any]] = []
    availability_passed: bool | None = None
    clicked = False

    def _rank_current() -> tuple[list[dict[str, Any]], pd.DataFrame]:
        rows: list[dict[str, Any]] = []
        for topic in current_topics:
            parts = priority_parts(topic["mastery"], topic["importance"], days_left)
            score = float(parts["score"])
            rows.append(
                {
                    "Topic": topic["topic"],
                    "Mastery (%)": topic["mastery"],
                    "Importance (1-5)": topic["importance"],
                    "Estimated hours": topic["hours"],
                    "Priority": score,
                    "Why prioritised": explain_priority(topic, score, days_left),
                    "parts": parts,
                }
            )
        rows.sort(key=lambda row: (-row["Priority"], row["Topic"]))
        for index, row in enumerate(rows, start=1):
            row["Rank"] = index
        frame = pd.DataFrame(
            [{key: value for key, value in row.items() if key != "parts"} for row in rows]
        )
        if not frame.empty:
            frame = frame[
                [
                    "Rank",
                    "Topic",
                    "Mastery (%)",
                    "Importance (1-5)",
                    "Estimated hours",
                    "Priority",
                    "Why prioritised",
                ]
            ]
        return rows, frame

    if not generated:
        st.markdown("Pick a profile, check your hours, press Generate.")
        current_topics = _edit_topics()
        ranking_rows, _ranking = _rank_current()
        st.session_state.live_ranking = _ranking_snapshot(ranking_rows) if ranking_rows else []
        if ranking_rows and not st.session_state.get("previous_ranking"):
            st.session_state.previous_ranking = [dict(item) for item in st.session_state.live_ranking]
        preview_plan, preview_summary = generate_plan(
            current_topics,
            daily_hours,
            start_date,
            assessment_date,
            completed_sessions=completed_sessions,
        )
        clicked = st.button("Generate / regenerate plan", type="primary", width="stretch")
    else:
        if overdue:
            if assessment_date < start_date:
                detail = (
                    f"{format_long(assessment_date)} is before today, {format_long(start_date)}. "
                    "The original scenario date of 24 Oct 2026 is in the past, so StudyPilot explains the overdue "
                    "condition and does not invent sessions for it. Choose a future assessment date, then generate the plan. "
                    "Saved progress for this profile is kept."
                )
            else:
                detail = (
                    f"The assessment is today, {format_long(assessment_date)}. "
                    "Sessions are only placed on earlier days, so there is nothing to schedule. "
                    "Choose a later date for the demo."
                )
            _status_banner("overdue", "DEADLINE OVERDUE", detail)
            st.caption("No timetable is shown for an overdue deadline.")

        today_tab, week_tab, topics_tab, check_tab, insights_tab = st.tabs(
            ["Today", "My week", "Topics", "Plan check", "Insights"]
        )
        pending: list[tuple[int, bool]] = []
        with today_tab:
            if st.session_state.get("show_rank_comparison"):
                changes = list(st.session_state.get("rank_comparison") or [])
                st.success(_plain_update(changes))
                st.caption("▲ moved up · ▼ moved down")
                with st.expander("What changed"):
                    _render_rank_changes(changes)
            if overdue:
                st.info("Choose a later exam date to see what to study today.")
            elif not in_window:
                st.info("Your plan is empty. Press Generate / regenerate plan to fill this week.")
            else:
                _render_today(
                    saved_plan,
                    daily_hours,
                    start_date,
                    schedulable,
                    len(done_sessions),
                    len(in_window),
                    pending,
                    allow_checks=not overdue,
                )
        with week_tab:
            if overdue:
                st.info("No week is shown while the exam date has passed. Choose a future date.")
                st.caption("No timetable is shown for an overdue deadline.")
            elif not in_window:
                st.info("Generate a plan to see one row for each day.")
            else:
                _render_week(saved_plan, daily_hours, start_date, schedulable, pending, allow_checks=not overdue)
        with topics_tab:
            current_topics = _edit_topics()
            preview_plan, preview_summary = generate_plan(
                current_topics,
                daily_hours,
                start_date,
                assessment_date,
                completed_sessions=completed_sessions,
            )
            ranking_rows, ranking = _rank_current()
            st.session_state.live_ranking = _ranking_snapshot(ranking_rows) if ranking_rows else []
            if ranking_rows and not st.session_state.get("previous_ranking"):
                st.session_state.previous_ranking = [dict(item) for item in st.session_state.live_ranking]
            _render_topic_cards(ranking_rows, ranking, overdue)
        with check_tab:
            if overdue:
                st.info("The time check waits until the exam date is in the future.")
            elif not generated and not in_window:
                st.info("Generate a plan to see whether the week fits your hours.")
            else:
                report = validate_schedule(in_window, daily_hours, schedulable, start_date)
                late_incomplete = [
                    session
                    for session in saved_plan
                    if date.fromisoformat(str(session["day_date"])) >= assessment_date and not int(session["completed"])
                ]
                _render_plan_check(report, late_incomplete, preview_summary)
                availability_passed = bool(report["valid"]) and not late_incomplete
        with insights_tab:
            _render_insights(profile_name, current_topics, in_window)
        _apply_done(pending)
        st.markdown("**3. Update progress**")
        st.caption("Finished sessions stay finished. The rest of the week is rebuilt around your hours.")
        clicked = st.button("Generate / regenerate plan", type="primary", width="stretch")

    if not generated and overdue:
        _status_banner(
            "overdue",
            "DEADLINE OVERDUE",
            "This deadline has passed. Choose a future date to generate a plan.",
        )
        st.caption("No timetable is shown for an overdue deadline.")

    if clicked:
        _regenerate_plan(profile_name, current_topics, preview_plan, preview_summary)

    stale = False
    if not overdue:
        for topic in current_topics:
            score = priority_score(topic["mastery"], topic["importance"], days_left)
            stored = [
                session
                for session in in_window
                if session["topic"] == topic["topic"] and not int(session["completed"])
            ]
            if stored and any(abs(float(session["priority"]) - score) > 0.05 for session in stored):
                stale = True
    if generated and stale:
        st.info("You changed a topic or the exam date. Update the plan so the week matches.")

    if st.session_state.get("regen_notice"):
        st.session_state.regen_notice = False
        if availability_passed:
            st.toast("Completed sessions were kept. The availability check still passes.", duration="long")
        elif availability_passed is False:
            st.toast("Completed sessions were kept. The availability check did not pass.", duration="long")

    step = 1
    if generated:
        step = 3 if stale or st.session_state.get("show_rank_comparison") else 2
    with step_slot:
        st.markdown(_step_bar(step), unsafe_allow_html=True)
    with hero_slot:
        st.markdown(
            _mission_hero(
                str(st.session_state.student_name),
                days_left,
                overdue,
                scheduled_minutes / 60,
                completion,
                _readiness_percent(current_topics),
            ),
            unsafe_allow_html=True,
        )

    with st.expander("How the planner makes decisions"):
        st.markdown(algorithm_explanation())


if __name__ == "__main__":
    main()
