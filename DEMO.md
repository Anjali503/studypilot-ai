# Three-minute demo

Start the app with `.\.venv\Scripts\python.exe -m streamlit run app.py` and open http://localhost:8501. The path below assumes today is 25 October 2026. **Load demo** pins Beginner and a deadline of 8 November 2026.

| Time | Click | What to say |
| --- | --- | --- |
| 0:00 | **Load demo** | Beginner is selected, Sunday is 0 hours, and the deadline is 8 Nov 2026. |
| 0:20 | Read the three steps, then press **Generate / regenerate plan** | The line says to pick a profile, check the hours, and press Generate. One button builds the week. |
| 0:45 | **Today** | Sunday is a rest day, with the next study day named. The line says how many sessions are done this week. |
| 1:10 | **My week** | One row per day. Chips say Learn, Practice, and Revise, with the legend under the tab. |
| 1:30 | **Topics**, then **Show details** | Dynamic Programming is rank 1 and labelled Study first, with a plain reason. The score and formula are inside Show details. |
| 1:50 | **Plan check** | The large line says the plan fits, with planned time against available time. The daily table is under Show daily details. |
| 2:10 | **Topics**: move Dynamic Programming from 10 to 50. On **My week**, tick **Done** on two sessions. | The percent updates. The ticks are stored. |
| 2:30 | **Generate / regenerate plan** again, then **Today** | The summary says the plan was updated and names the topic that moved down and the new top topic. **What changed** holds the before/after list. Plan check still fits. |

## Where each requirement appears

- Priority from mastery, importance, and days left: **Topics**, the plain reason, and the formula inside **Show details**. The hero counts the days to the exam.
- A written reason for the rank: the one-line reason under each topic. The full sentence is inside **Show details**.
- Learn, practice, and revision: the chips on **My week**, the legend on that tab, and the chart on **Insights**.
- A weekly plan that respects each day's hours: **My week**. Sunday is a rest day when that weekday is 0 hours.
- A check that no day is overfilled: **Plan check**. The daily table is under **Show daily details**.
- Three different students: the Beginner, Intermediate, and Advanced cards in the sidebar.
- Update mastery and keep finished work: the topic slider, the **Done** boxes, and **Generate / regenerate plan**.
- The rank change after that update: the sentence at the top of **Today**, and **What changed**. For Beginner, Dynamic Programming moves from rank 1 to rank 5 and Trees takes rank 1.
- The brief date 24 Oct 2026 is overdue: **Use 24 Oct 2026 (overdue scenario)** shows the overdue hero and no timetable. Demos use **Load demo** and 8 Nov 2026 instead.
- No external model: **How the planner makes decisions** at the bottom of the page states that no API is called. The same inputs always rebuild the same week.
