"""Dashboard presentation for StudyPilot. CSS and HTML only; no planner logic.

Inject PAGE_STYLE with st.markdown(PAGE_STYLE, unsafe_allow_html=True).
The helpers return HTML for the same call.
"""

from __future__ import annotations

import html

PAGE_STYLE = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,560;9..144,680&family=Outfit:wght@400;500;600&display=swap');
:root {
    --bg: #090A0C;
    --card: #16171B;
    --accent: #E4FF4A;
    --text: #F4F1EA;
    --muted: #A8A49B;
    --line: #5C616B;
    --learn: #5EEAD4;
    --practice: #F5C16C;
    --revise: #C4B5FD;
    --space-1: 4px;
    --space-2: 8px;
    --space-3: 16px;
    --space-4: 24px;
    --space-5: 40px;
    --radius-sm: 8px;
    --radius-md: 14px;
    --radius-lg: 22px;
    --font-display: "Fraunces", Georgia, serif;
    --font-body: "Outfit", sans-serif;
}
html, body, .stApp, [data-testid="stAppViewContainer"], [data-testid="stMain"] {background: var(--bg); color: var(--text); font-family: var(--font-body);}
section[data-testid="stSidebar"] {background: var(--card); border-right: 1px solid var(--line);}
h1, h2, h3, h4, h5, h6, [data-testid="stHeading"], [data-testid="stHeading"] * {font-family: var(--font-display) !important; color: var(--text); letter-spacing: -0.02em;}
p, label, li, .stCaption, [data-testid="stCaptionContainer"], [data-testid="stCaptionContainer"] p {font-family: var(--font-body); font-size: 16px; line-height: 1.5;}
footer, #MainMenu, [data-testid="stDecoration"], [data-testid="stStatusWidget"] {display: none !important; visibility: hidden !important; height: 0 !important;}
header[data-testid="stHeader"] {background: transparent !important; height: 0 !important; min-height: 0 !important; overflow: visible !important;}
header [data-testid="stToolbar"] {height: 0 !important; min-height: 0 !important; overflow: visible !important; background: transparent !important;}
.block-container {padding-top: var(--space-4); padding-bottom: var(--space-5); max-width: 1180px;}
.sp-hero {background: var(--card); border: 1px solid var(--line); border-radius: var(--radius-lg); padding: var(--space-4) var(--space-4) var(--space-2) var(--space-4); margin-bottom: var(--space-3);}
.sp-kicker {margin: 0; color: var(--accent); font-family: var(--font-body); font-size: 0.75rem; font-weight: 600; letter-spacing: 0.08em; text-transform: uppercase;}
.sp-hero h1 {margin: var(--space-1) 0 var(--space-2) 0;}
.sp-hero p {margin-top: 0; color: var(--muted);}
div[data-testid="stMetric"] {background: var(--card); border: 1px solid var(--line); border-radius: var(--radius-md); padding: var(--space-2) var(--space-3);}
div[data-testid="stMetric"] label, div[data-testid="stMetric"] [data-testid="stMetricValue"] {color: var(--text);}
.status-pass, .status-fail, .status-overdue {border-radius: var(--radius-md); padding: var(--space-3) var(--space-4); font-family: var(--font-display); font-size: 1.35rem; font-weight: 680; margin: var(--space-2) 0 var(--space-3) 0;}
.status-pass {background: #14352C; color: #8EEDC7;}
.status-fail {background: #3A1719; color: #F7A8A8;}
.status-overdue {background: #3A2E12; color: var(--accent);}
.sp-day {display: flex; justify-content: space-between; align-items: center; gap: var(--space-3); margin: var(--space-4) 0 var(--space-2) 0;}
.sp-day strong {display: block; color: var(--text); font-family: var(--font-display); font-size: 1.2rem;}
.sp-day span {color: var(--muted); font-size: 0.92rem;}
.sp-pill, .sp-badge {border-radius: 999px; padding: var(--space-1) var(--space-2); font-family: var(--font-body); font-size: 0.75rem; font-weight: 600; letter-spacing: 0.04em;}
.sp-day .sp-pill-pass {background: #14352C; color: #8EEDC7;}
.sp-day .sp-pill-fail {background: #3A1719; color: #F7A8A8;}
.sp-card {background: var(--card); border: 1px solid var(--line); border-radius: var(--radius-lg); padding: var(--space-4); margin-bottom: var(--space-3);}
.sp-card h3 {margin: 0 0 var(--space-2) 0;}
.sp-card-body {color: var(--text);}
.sp-badge-neutral {background: var(--line); color: var(--text);}
.sp-badge-accent {background: var(--accent); color: var(--bg);}
.sp-badge-learn {background: color-mix(in srgb, var(--learn) 18%, var(--card)); color: var(--learn);}
.sp-badge-practice {background: color-mix(in srgb, var(--practice) 18%, var(--card)); color: var(--practice);}
.sp-badge-revise {background: color-mix(in srgb, var(--revise) 18%, var(--card)); color: var(--revise);}
.sp-metric {background: var(--card); border: 1px solid var(--line); border-radius: var(--radius-md); padding: var(--space-3); min-width: 0;}
.sp-metric span {display: block; color: var(--muted); font-size: 0.8rem; line-height: 1.3; overflow-wrap: anywhere;}
.sp-metric strong {display: block; margin-top: var(--space-1); color: var(--text); font-family: var(--font-display); font-size: 1.6rem; line-height: 1.1; overflow-wrap: anywhere;}
.sp-metric-row {display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: var(--space-2); margin: var(--space-2) 0 var(--space-3) 0;}
.sp-ring {display: inline-flex; flex-direction: column; align-items: center; gap: var(--space-1); color: var(--text); font-family: var(--font-body);}
.sp-ring svg {display: block;}
.sp-ring-track {fill: none; stroke: var(--line); stroke-width: 6;}
.sp-ring-value {fill: none; stroke: var(--accent); stroke-width: 6; stroke-linecap: round; transform: rotate(-90deg); transform-origin: 36px 36px;}
.sp-ring small {color: var(--muted);}
.sp-topic-grid {display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: var(--space-3); margin-bottom: var(--space-3);}
.sp-topic-top {display: flex; justify-content: space-between; align-items: flex-start; gap: var(--space-2);}
.sp-topic-why {color: var(--muted); font-size: 0.92rem; margin: var(--space-2) 0;}
.sp-dots {display: flex; gap: 6px; align-items: center; margin: var(--space-2) 0;}
.sp-dot {width: 10px; height: 10px; border-radius: 999px; display: inline-block; background: var(--line);}
.sp-dot-on {background: var(--accent);}
.sp-bar {height: 8px; border-radius: 999px; background: var(--line); overflow: hidden; margin: var(--space-2) 0 var(--space-1) 0;}
.sp-bar > span {display: block; height: 100%; background: var(--accent);}
.sp-bar-label {color: var(--muted); font-size: 0.8rem;}
.sp-formula {display: grid; gap: var(--space-1); margin: var(--space-2) 0;}
.sp-formula div {display: flex; justify-content: space-between; gap: var(--space-2);}
.sp-formula dt {color: var(--muted);}
.sp-formula dd {margin: 0; color: var(--text);}
.sp-card details {margin-top: var(--space-2);}
.sp-card summary {cursor: pointer; color: var(--text); font-weight: 600;}
.sp-week-label {color: var(--muted); margin: 0 0 var(--space-1) 0;}
.sp-day-head {display: flex; justify-content: space-between; align-items: flex-start; gap: var(--space-2);}
.sp-day-head strong {display: block; font-family: var(--font-display); font-size: 1rem; color: var(--text);}
.sp-day-head p, .sp-rest-label {margin: var(--space-1) 0 0 0; color: var(--muted); font-size: 0.82rem;}
.sp-rest-label {letter-spacing: 0.06em; text-transform: uppercase; font-weight: 600;}
.sp-session {border-left: 4px solid var(--learn); border-radius: var(--radius-sm); background: color-mix(in srgb, var(--learn) 12%, var(--card)); padding: var(--space-1) var(--space-2); margin-bottom: var(--space-1);}
.sp-session strong {display: block; color: var(--text); font-size: 0.86rem;}
.sp-session span {color: var(--muted); font-size: 0.78rem;}
.sp-session-practice {border-left-color: var(--practice); background: color-mix(in srgb, var(--practice) 12%, var(--card));}
.sp-session-revise {border-left-color: var(--revise); background: color-mix(in srgb, var(--revise) 12%, var(--card));}
div[data-testid="stHorizontalBlock"]:has(.sp-day-card) {gap: var(--space-2); align-items: stretch; flex-wrap: nowrap !important; overflow-x: auto; padding-bottom: var(--space-2);}
div[data-testid="stHorizontalBlock"]:has(.sp-day-card) > div[data-testid="stColumn"] {min-width: 210px !important; flex: 1 0 210px !important;}
div[data-testid="stColumn"]:has(.sp-day-card) {background: var(--card); border: 1px solid var(--line); border-radius: var(--radius-lg); padding: var(--space-2) var(--space-2) var(--space-3) var(--space-2);}
div[data-testid="stColumn"]:has(.sp-rest) {background: #121316; border-style: dashed;}
.sp-day-card .sp-ring svg {width: 54px; height: 54px;}
.sp-day-card .sp-ring strong {font-size: 0.78rem;}
@media (max-width: 960px) {
div[data-testid="stHorizontalBlock"]:has(.sp-day-card) {flex-direction: column !important; overflow-x: visible;}
div[data-testid="stHorizontalBlock"]:has(.sp-day-card) > div[data-testid="stColumn"] {width: 100% !important; flex: 1 1 100% !important; min-width: 100% !important;}
}
.sp-avail {display: flex; justify-content: space-between; align-items: center; gap: var(--space-3); flex-wrap: wrap;}
.sp-avail-line {margin: 0; color: var(--text); font-size: 1.05rem;}
.sp-avail-bad {color: #F7A8A8;}
.sp-avail-metrics {display: flex; gap: var(--space-2); margin-top: var(--space-2);}
.sp-pass-badge, .sp-fail-badge {font-family: var(--font-display); font-size: 2.6rem; font-weight: 680; letter-spacing: 0.06em; line-height: 1; border-radius: var(--radius-md); padding: var(--space-2) var(--space-4);}
.sp-pass-badge {background: #14352C; color: #8EEDC7;}
.sp-fail-badge {background: #3A1719; color: #F7A8A8;}
.sp-card:has(.sp-pass-badge) {border-color: #245C48;}
.sp-card:has(.sp-fail-badge) {border-color: #7A3034;}
.sp-cap-row {display: grid; grid-template-columns: 158px 1fr 88px; gap: var(--space-2); align-items: center; margin-top: var(--space-3);}
.sp-cap-name {color: var(--text); font-size: 0.92rem;}
.sp-cap-over .sp-cap-name {color: #F7A8A8;}
.sp-cap-nums {color: var(--muted); font-size: 0.8rem; text-align: right;}
.sp-cap-track {position: relative; height: 12px; border-radius: 999px; background: var(--line); overflow: visible;}
.sp-cap-fill {position: absolute; left: 0; top: 0; bottom: 0; border-radius: 999px; background: #8EEDC7; z-index: 1;}
.sp-cap-over .sp-cap-fill {background: #F7A8A8;}
.sp-cap-mark {position: absolute; top: -4px; width: 2px; height: 20px; background: var(--text); transform: translateX(-1px); z-index: 2;}
@media (max-width: 700px) {
.sp-cap-row {grid-template-columns: 1fr auto;}
.sp-cap-track {grid-column: 1 / -1;}
}
.sp-change-list {margin: var(--space-2) 0 var(--space-3) 0; padding-left: 1.1rem; color: var(--text);}
.sp-change-list li {margin: var(--space-1) 0;}
.sp-rank-legend {color: var(--muted); font-size: 0.8rem; margin: 0 0 var(--space-2) 0;}
.sp-rank-move {display: grid; grid-template-columns: 32px 92px 1fr auto; gap: var(--space-2); align-items: center; padding: var(--space-2) 0; border-top: 1px solid var(--line); color: var(--text);}
.sp-rank-up {color: #8EEDC7; font-weight: 700;}
.sp-rank-down {color: #F7A8A8; font-weight: 700;}
.sp-rank-same {color: var(--muted); font-weight: 700;}
.sp-rank-meta {color: var(--muted); font-size: 0.85rem;}
@media (max-width: 700px) {
.sp-rank-move {grid-template-columns: 32px 1fr auto;}
.sp-rank-move strong {grid-column: 2 / -1;}
}
.js-plotly-plot, .js-plotly-plot .plotly, .js-plotly-plot .svg-container {background: transparent !important;}
.js-plotly-plot text {fill: var(--text) !important;}
div[data-testid="stHorizontalBlock"]:has(.sp-insights) {align-items: stretch;}
@media (max-width: 960px) {
div[data-testid="stHorizontalBlock"]:has(.sp-insights) {flex-direction: column !important;}
div[data-testid="stHorizontalBlock"]:has(.sp-insights) > div[data-testid="stColumn"] {width: 100% !important; flex: 1 1 100% !important; min-width: 0 !important;}
}
div[data-testid="stHeading"] {margin-top: var(--space-5); margin-bottom: var(--space-2);}
div[data-testid="stCaptionContainer"], div[data-testid="stCaptionContainer"] p {color: var(--muted) !important;}
div[data-testid="stMetric"] {height: 100%; box-sizing: border-box;}
div[data-testid="stMetricLabel"] p, div[data-testid="stMetricLabel"] label {color: var(--muted) !important;}
div[data-testid="stHorizontalBlock"] {align-items: stretch;}
a:link, a:visited {color: var(--accent); text-underline-offset: 2px;}
a:hover {color: var(--text);}
button[data-testid="stBaseButton-primary"] {color: var(--bg) !important; background-color: var(--accent) !important; border-color: var(--accent) !important; font-weight: 600;}
button[data-testid="stBaseButton-primary"]:hover {background-color: #F6FF9A !important; color: var(--bg) !important; border-color: #F6FF9A !important;}
button[data-testid="stBaseButton-secondary"] {background-color: var(--bg) !important; color: var(--text) !important; border: 1px solid var(--line) !important;}
button[data-testid="stBaseButton-secondary"]:hover {border-color: var(--accent) !important; color: var(--text) !important;}
button[data-testid="stBaseButton-primary"], button[data-testid="stBaseButton-secondary"] {transition: background-color .16s ease, border-color .16s ease;}
.sp-card, div[data-testid="stColumn"]:has(.sp-day-card) {transition: border-color .16s ease, background-color .16s ease;}
div[data-testid="stColumn"]:has(.sp-day-card):hover {border-color: var(--accent);}
.sp-session {transition: background-color .16s ease;}
.sp-session:hover {background-color: color-mix(in srgb, var(--learn) 22%, var(--card));}
.sp-session-practice:hover {background-color: color-mix(in srgb, var(--practice) 22%, var(--card));}
.sp-session-revise:hover {background-color: color-mix(in srgb, var(--revise) 22%, var(--card));}
button:focus-visible, a:focus-visible, input:focus-visible, textarea:focus-visible, select:focus-visible, summary:focus-visible, [role="slider"]:focus-visible, button[data-testid="stBaseButton-primary"]:focus-visible, button[data-testid="stBaseButton-secondary"]:focus-visible, [data-testid="stExpandSidebarButton"]:focus-visible {outline: 2px solid var(--accent) !important; outline-offset: 2px !important; box-shadow: none !important;}
[data-testid="stNumberInput"] [data-baseweb="input"], [data-testid="stDateInput"] [data-baseweb="input"], [data-baseweb="select"] > div {background-color: var(--bg) !important; border-color: var(--line) !important; color: var(--text) !important;}
[data-testid="stExpander"] details {background: var(--card) !important; border: 1px solid var(--line) !important; border-radius: var(--radius-md) !important;}
[data-testid="stExpander"] summary:hover {color: var(--accent);}
div[data-testid="stAlertContainer"] {border-radius: var(--radius-md) !important; color: var(--text) !important;}
div[data-testid="stAlertContainer"]:has([data-testid="stAlertContentWarning"]) {background: #3A2E12 !important; border: 1px solid #6A5A28 !important;}
div[data-testid="stAlertContainer"]:has([data-testid="stAlertContentError"]) {background: #3A1719 !important; border: 1px solid #7A3034 !important;}
div[data-testid="stAlertContainer"]:has([data-testid="stAlertContentSuccess"]) {background: #14352C !important; border: 1px solid #245C48 !important;}
div[data-testid="stAlertContainer"]:has([data-testid="stAlertContentInfo"]) {background: var(--card) !important; border: 1px solid var(--line) !important;}
div[data-testid="stAlertContentWarning"], div[data-testid="stAlertContentError"], div[data-testid="stAlertContentSuccess"], div[data-testid="stAlertContentInfo"] {color: var(--text) !important;}
[data-testid="stDataFrame"], [data-testid="stDataEditor"] {border: 1px solid var(--line); border-radius: var(--radius-md); overflow: hidden; background: var(--bg); color: var(--text);}
[data-testid="stDataEditor"] {--gdg-accent-color: #E4FF4A; --gdg-accent-fg: #090A0C; --gdg-bg-cell: #090A0C; --gdg-bg-cell-medium: #121316; --gdg-bg-header: #16171B; --gdg-bg-header-has-focus: #1C1E24; --gdg-bg-header-hovered: #1C1E24; --gdg-text-dark: #F4F1EA; --gdg-text-medium: #A8A49B; --gdg-text-light: #A8A49B; --gdg-text-header: #F4F1EA; --gdg-text-group-header: #F4F1EA; --gdg-border-color: #5C616B; --gdg-horizontal-border-color: #5C616B; --gdg-bg-icon-header: #16171B; --gdg-fg-icon-header: #A8A49B; --gdg-font-family: Outfit, sans-serif;}
hr, [data-testid="stDivider"] {border-color: var(--line) !important; background-color: var(--line) !important;}
.modebar {background: transparent !important;}
.modebar-btn path {fill: var(--muted) !important;}
[data-testid="stToast"] {background: var(--card) !important; color: var(--text) !important; border: 1px solid var(--line) !important;}
[data-testid="stExpandSidebarButton"] {position: fixed !important; top: 8px; left: 8px; z-index: 1000001; background: var(--card) !important; color: var(--text) !important; border: 1px solid var(--line) !important; border-radius: var(--radius-sm) !important;}
[data-testid="stSidebarHeader"] button {color: var(--text) !important;}
input[type="checkbox"] {accent-color: var(--accent);}
section[data-testid="stSidebar"] [data-testid="stVerticalBlock"] {gap: var(--space-2);}
@media (max-width: 960px) {
header[data-testid="stHeader"] {height: 3rem !important; min-height: 3rem !important; background: var(--bg) !important;}
header [data-testid="stToolbar"] {height: 3rem !important; min-height: 3rem !important;}
[data-testid="stMain"] {scroll-padding-top: 3rem;}
}
@media (max-width: 700px) {
.block-container {padding-left: var(--space-3); padding-right: var(--space-3); padding-top: 3.5rem;}
.sp-hero {padding: var(--space-3);}
.sp-pass-badge, .sp-fail-badge {font-size: 2rem;}
div[data-testid="stHorizontalBlock"]:not(:has(.sp-day-card)):not(:has(.sp-insights)) {flex-direction: column !important;}
div[data-testid="stHorizontalBlock"]:not(:has(.sp-day-card)):not(:has(.sp-insights)) > div[data-testid="stColumn"] {width: 100% !important; flex: 1 1 100% !important; min-width: 0 !important;}
}
.sp-mission {container-type: inline-size;}
.sp-mission h1 {font-size: 2.6rem; margin: var(--space-1) 0 var(--space-3) 0;}
.sp-mission-row {display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: var(--space-3); align-items: stretch;}
.sp-mission-row > .sp-count, .sp-mission-row > .sp-metric, .sp-mission-row > .sp-ring {min-width: 0; height: 100%; box-sizing: border-box; display: flex; flex-direction: column; align-items: flex-start; justify-content: center; background: transparent; border: 1px solid var(--line); border-radius: var(--radius-md); padding: var(--space-3);}
.sp-mission-row > .sp-ring {align-items: center;}
.sp-count strong {display: block; font-family: var(--font-display); font-size: clamp(2.2rem, 10cqi, 4.2rem); line-height: 0.9; color: var(--accent); letter-spacing: -0.04em;}
.sp-count span, .sp-count p {color: var(--muted); font-size: 0.95rem;}
.sp-count p {max-width: 26rem; margin: var(--space-2) 0 0 0; color: var(--text);}
.sp-count-late strong {font-size: 2.4rem; line-height: 1.1;}
.sp-mission-row > .sp-ring svg {width: min(84px, 100%); height: auto;}
.sp-profile {border: 1px solid var(--line); border-radius: var(--radius-md); padding: var(--space-2) var(--space-3); margin-bottom: var(--space-2); background: var(--bg); transition: border-color .16s ease;}
.sp-profile:hover, .sp-profile-on {border-color: var(--accent);}
.sp-profile strong {display: block; color: var(--text); font-family: var(--font-display);}
.sp-profile p {margin: var(--space-1) 0 0 0; color: var(--muted); font-size: 0.85rem;}
.sp-steps {margin: 0; padding-left: 1.2rem; color: var(--text);}
.sp-steps li {margin: var(--space-1) 0;}
@container (max-width: 640px) {
.sp-mission-row {grid-template-columns: repeat(2, minmax(0, 1fr));}
.sp-mission-row .sp-metric strong {font-size: 1.25rem;}
.sp-mission-row .sp-metric span {font-size: 0.72rem;}
}
@media (max-width: 700px) {
.sp-mission-row {grid-template-columns: repeat(2, minmax(0, 1fr));}
.sp-metric-row {grid-template-columns: 1fr;}
.sp-metric strong {font-size: 1.25rem;}
.sp-metric span {font-size: 0.72rem;}
}
.sp-steps-bar {display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: var(--space-3); margin: 0 0 var(--space-4) 0;}
.sp-step {border: 1px solid var(--line); border-radius: var(--radius-md); padding: var(--space-3) var(--space-4); color: var(--muted); background: transparent;}
.sp-step-on {border-color: var(--accent); color: var(--text); background: #1C1E12;}
.sp-step strong {display: block; color: inherit; font-family: var(--font-display); font-size: 1.25rem;}
.sp-today {border: 1px solid var(--line); border-radius: var(--radius-lg); padding: var(--space-4); margin-bottom: var(--space-4);}
.sp-today h2 {margin: 0 0 var(--space-2) 0; font-size: 1.8rem;}
.sp-fit {font-family: var(--font-display); font-size: 2rem; line-height: 1.2; color: var(--text); margin: 0 0 var(--space-2) 0;}
.sp-fit-ok {color: #8EEDC7;}
.sp-week-row {display: flex; flex-wrap: wrap; align-items: center; gap: var(--space-2) var(--space-3); border-bottom: 1px solid var(--line); padding: var(--space-3) 0;}
.sp-week-row strong {min-width: 8rem;}
.sp-chip {display: inline-block; margin: 4px 8px 4px 0; padding: 4px 12px; border-radius: 999px; font-size: 16px;}
.sp-chip-learn {background: #12312C; color: var(--learn);}
.sp-chip-practice {background: #3A2E12; color: var(--practice);}
.sp-chip-revise {background: #2A2140; color: var(--revise);}
.sp-legend {display: flex; flex-wrap: wrap; gap: var(--space-3); margin: var(--space-2) 0 var(--space-3) 0;}
@media (max-width: 700px) {
.sp-steps-bar {grid-template-columns: 1fr;}
.sp-week-row {align-items: flex-start;}
.sp-fit {font-size: 1.5rem;}
}
@media (prefers-reduced-motion: reduce) {
*, *::before, *::after {animation: none !important; transition: none !important;}
}
</style>
"""


def page_style(enter: bool = False) -> str:
    """Full stylesheet. The fade plays once; later reruns omit it so the page does not flicker."""
    if not enter:
        return PAGE_STYLE
    enter_css = (
        "@keyframes sp-fade{from{opacity:0}to{opacity:1}}"
        ".block-container,section[data-testid='stSidebar']{animation:sp-fade .32s ease-out}"
    )
    return PAGE_STYLE.replace("</style>", enter_css + "</style>", 1)


def status_banner(kind: str, title: str) -> str:
    return f"<div class='status-{kind}'>{html.escape(title)}</div>"


def day_heading(when: str, available: str, scheduled: str, remaining: str, result: str) -> str:
    pill = "pass" if result == "PASS" else "fail"
    return (
        "<div class='sp-day'>"
        f"<div><strong>{html.escape(when)}</strong>"
        f"<span>available {html.escape(available)} · scheduled {html.escape(scheduled)} · "
        f"remaining {html.escape(remaining)}</span></div>"
        f"<span class='sp-pill sp-pill-{pill}'>{html.escape(result)}</span>"
        "</div>"
    )


def card(body: str, title: str | None = None) -> str:
    heading = f"<h3>{html.escape(title)}</h3>" if title else ""
    return f"<section class='sp-card'>{heading}<div class='sp-card-body'>{body}</div></section>"


def badge(text: str, kind: str = "neutral") -> str:
    allowed = {"learn", "practice", "revise", "neutral", "accent"}
    tone = kind if kind in allowed else "neutral"
    return f"<span class='sp-badge sp-badge-{tone}'>{html.escape(text)}</span>"


def metric_tile(label: str, value: str) -> str:
    return (
        "<div class='sp-metric'>"
        f"<span>{html.escape(label)}</span>"
        f"<strong>{html.escape(value)}</strong>"
        "</div>"
    )


def progress_ring(value: float, label: str = "", center: str | None = None) -> str:
    """Ring for a fraction from 0 to 1. Numbers above 1 are read as a percent."""
    fraction = float(value)
    if fraction > 1:
        fraction = fraction / 100
    fraction = max(0.0, min(1.0, fraction))
    radius = 28
    circumference = 2 * 3.14159 * radius
    offset = circumference * (1 - fraction)
    shown = html.escape(center) if center is not None else f"{round(fraction * 100)}%"
    caption = f"<small>{html.escape(label)}</small>" if label else ""
    return (
        "<div class='sp-ring'>"
        "<svg viewBox='0 0 72 72' width='72' height='72' aria-hidden='true'>"
        f"<circle class='sp-ring-track' cx='36' cy='36' r='{radius}'></circle>"
        f"<circle class='sp-ring-value' cx='36' cy='36' r='{radius}' "
        f"stroke-dasharray='{circumference:.2f}' stroke-dashoffset='{offset:.2f}'></circle>"
        "</svg>"
        f"<strong>{shown}</strong>"
        f"{caption}"
        "</div>"
    )
