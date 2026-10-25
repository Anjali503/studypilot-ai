# StudyPilot AI

"AI" here means classical, rule-based AI: a goal-based planning agent that uses a transparent heuristic priority score, constraint-based scheduling and re-planning when progress changes. It does not use machine learning, a trained model or a language model, which keeps every priority explainable and the availability limit guaranteed.

StudyPilot builds a one-week programming study plan. The student enters mastery (0–100), assessment importance (1–5), and estimated hours for each topic, plus how many hours they can study on each weekday and an assessment date. The planner ranks the topics, splits each topic into learn, practice, and revision, and places that work on the earliest days that still have room.

It is a fixed formula, not a language model. The same inputs always produce the same plan. Nothing is sent to an external API. Progress is stored in a local SQLite file, `studypilot.db`.

The dashboard is the Exam Mission Control screen in `app.py`, styled by `ui_theme.py`. A text-only walkthrough of the same planner is `demo_report.py`.

On screen there are three steps. **1. Tell us about you** is the profile, the exam date, the hours, and a slider per topic labelled "How well do you know this? (0-100%)". **2. See your plan** opens after you generate, on five tabs: Today, My week, Topics, Plan check, and Insights. **3. Update progress** uses the same generate button again: finished sessions stay finished. Scores, the formula, and the per-day table stay behind **Show details** and **Show daily details**. The button label stays **Generate / regenerate plan**.

## Priority formula

For every topic, `days_left = (deadline - start_date).days`:

```text
mastery_gap = 1 - mastery / 100
importance_normalised = importance / 5
base_priority = 100 * (0.55 * mastery_gap + 0.45 * importance_normalised)
urgency = 1 + 0.5 / max(days_left, 1)
priority = min(100, base_priority * urgency)
```

The weights are named constants at the top of `app.py`: mastery `0.55`, importance `0.45`, urgency `0.50`. Fewer days left raise the multiplier continuously. Three days left is ×1.17, seven days left is ×1.07, and one day left is ×1.50. The score is rounded to one decimal and capped at 100. Each topic card shows that score and a sentence with the mastery, the importance, and the days left, for example `14 days left, urgency x1.04`.

A deadline on the start date or earlier does not use this score to build a timetable.

## Learn, practice, and revision

Requested minutes for a topic are split three ways:

- **Learn / review**: 40% of the requested minutes, rounded
- **Coding practice**: 40% of the requested minutes, rounded
- **Recall / revision**: the remainder, so the three parts add up to the request

On screen those activities are labelled Learn, Practice, and Revise, in teal, amber, and lilac. A block longer than 60 minutes is split. A split must leave at least 15 minutes on both sides, so a day can keep a few unused minutes. Higher-priority work is placed first, on the earliest day that can hold it. Clocks start at 09:00 and are not allowed to overlap.

## Per-day availability

Hours are entered Monday to Sunday, then placed on the real dates in the planning window by weekday. A Sunday rest day stays on Sunday. The window is at most the next 7 days, and only dates strictly before the assessment are used.

The scheduler will not put more minutes on a date than that date's availability. Work that cannot fit is listed as unallocated. It is not used to stretch the day. A weekday set to 0 hours gets no sessions.

`validate_schedule` then checks every date in the window, including dates with no sessions:

- scheduled minutes are less than or equal to that date's available minutes
- session clocks match their durations and do not overlap
- each date is PASS or FAIL

The overall result is PASS only when every date passes. `generate_plan` keeps a plan only when this check passes. Section **5. Availability check** shows the same proof: a bar of scheduled minutes, a marker at the day's capacity, planned hours against available hours, and the sentence "No day exceeds the student's stated availability." The detailed table is in the expander. A failure names the day and turns the badge red.

## Update and regenerate

Mastery edits in the topic table and **Done** ticks on sessions are stored in SQLite.

**Regenerate remaining plan** (and **Generate my plan**) does four things:

1. Recalculates every topic's priority from the current mastery, importance, and days left.
2. Keeps each completed session on its original date and treats those minutes as already used.
3. Subtracts completed minutes by topic and activity, then schedules only the remaining learn, practice, and recall time.
4. Runs the per-day availability check again on the completed sessions plus the new ones.

A completed session is not booked a second time. The screen keeps the previous ranking in memory and shows a before/after list: up, down, or unchanged, with the old and new mastery. A toast confirms that completed sessions were kept and whether the availability check still passes.

**Load selected sample profile** replaces that profile's saved mastery and saved sessions. Switching profiles with **Use Beginner**, **Use Intermediate**, or **Use Advanced** keeps mastery already saved for the profile you open.

## Overdue deadlines

The brief's scenario date, **24 October 2026**, is in the past when planning starts on or after 25 October 2026. Demos therefore use a start of **25 October 2026** and a deadline of **8 November 2026** (14 days left). The planner still schedules only the first 7 days, 25–31 October.

- A deadline before the start date returns an empty plan with status `OVERDUE`. No sessions are created.
- A deadline on the start date is also `OVERDUE`. The assessment day is not a study day, so there is nowhere to schedule.
- In the sidebar, today or any earlier date shows: "This deadline has passed. Choose a future date to generate a plan." The hero says **Overdue**. Section 6 says no timetable is shown. Saved progress for the profile is kept.
- **Use 24 Oct 2026 (overdue scenario)** opens that state. **Load demo** pins Beginner and 8 November 2026.

## Run the app, the tests, and the text demo

Python 3.12 in the project virtual environment:

```powershell
cd C:\Users\ANJALI\Downloads\studypilot_ai_starter\studypilot_ai
.\.venv\Scripts\python.exe -m streamlit run app.py
```

Open [http://localhost:8501](http://localhost:8501) if the browser does not open itself. The click path is in `DEMO.md`.

```powershell
.\.venv\Scripts\python.exe -m pytest tests -v
.\.venv\Scripts\python.exe demo_report.py
```

`tests\test_planner.py` checks the formula, the three profiles, availability, overdue dates, explanations, and regeneration. `tests\test_ui.py` loads the dashboard without a browser. Both use a temporary database, so `studypilot.db` is not opened. `demo_report.py` does the same: start 25 October 2026, deadline 8 November 2026, temporary database, and writes `demo_output.txt`. It raises the top topic's mastery by 40 percentage points (capped at 100), marks that topic's first two sessions complete, and prints `ALL CHECKS PASSED` when every day stays within its hours, both completed sessions are kept, and the top topic's rank gets worse in at least two profiles.

To reset one profile inside the app, click **Load selected sample profile**. To reset everything, stop the app and delete `studypilot.db`.

## Sample profiles

Hours below are Monday to Sunday. The availability figures are the minutes in `demo_output.txt` for 25 October–31 October 2026. The update raises Dynamic Programming by 40 percentage points, capped at 100, and marks its first two sessions complete. Every date is PASS before and after. The scheduled total stays the same; the minutes move between days.

| Profile | Mon–Sun hours | Before | After | Rank of Dynamic Programming | Scheduled |
| --- | --- | --- | --- | --- | --- |
| Beginner — limited time | 1, 1, 0.5, 1, 1, 1.5, 0 | PASS | PASS | 1 (97.9, mastery 10) then 5 (75.1, mastery 50). Trees takes rank 1. | 354 of 360. Sunday 25 Oct is 0 available and 0 scheduled. |
| Intermediate — balanced | 2, 2, 2, 2, 2, 2.5, 1.5 | PASS | PASS | 1 (83.6, mastery 35) then 4 (60.8, mastery 75). Trees takes rank 1. | 750 of 840. |
| Advanced — targeted revision | 3, 3, 2.5, 3, 3, 3.5, 2 | PASS | PASS | 1 (63.7, mastery 70) then 4 (46.6, mastery 100). Trees takes rank 1. | 570 of 1,200. The last three days stay at 0 scheduled. |

## Design choices

The score is a formula a person can recompute with a calculator. A model call would make the ranking depend on a network, a prompt, and a hidden set of weights, so two runs of the same student could disagree and a marker could not check the arithmetic. The constants, the 40/40/remainder split, and the per-day cap are named in the source and repeated on the topic card. That is why StudyPilot stays deterministic and explainable, and why it does not call an external model.

## Known limitations

- Only the next 7 days are scheduled. A deadline further away can leave work unallocated even when a later week would have had room.
- Sessions start at 09:00 and run back to back. The app does not ask for a personal timetable such as "only after 18:00".
- The 15-minute split rule is why the beginner demo schedules 354 of 360 available minutes.
- Completed work is recognised by topic and activity type. Changing the estimated hours can change how the remaining minutes are grouped.
- There is one local database and no user accounts.

## Project layout

```text
studypilot_ai\
  app.py                  planner, database, and Streamlit dashboard
  ui_theme.py             colours, type, and HTML helpers for the dashboard
  demo_report.py          text demo of the three profiles; no Streamlit UI
  demo_output.txt         written by demo_report.py
  DEMO.md                 three-minute click path
  requirements.txt
  README.md
  .streamlit\config.toml  local theme; disables the Streamlit usage prompt
  tests\test_planner.py   planner tests
  tests\test_ui.py        headless dashboard tests
  studypilot.db           created on first launch (not part of the source)
```
