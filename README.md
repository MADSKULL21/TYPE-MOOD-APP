# Flask AI‑Lite — Subconscious Typing Pattern Analyzer

**Goal:** Analyze how a user types (speed, pauses, corrections, bursts) and output a heuristic "typing mood" plus suggestions. No ML — pure rules + UX.

## Stack
- Flask, Python, SQLite (via `sqlite3`)
- Tailwind (CDN), Vanilla JS event listeners
- Chart.js for analytics
- Deploy on Render/Heroku; works locally too

## Quickstart (Local)
```bash
python -m venv .venv && source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python app.py
# open http://127.0.0.1:5000
```

## Heuristics
- **Corrections rate** = backspaces / keystrokes.  
  - >12% → *low focus*  
  - 6–12% → *slightly distracted*
- **Thinking mode** if avg pause > 900 ms
- **High confidence** if bursts ≥ 4 and avg pause < 600 ms
- **Cautious** if bursts ≤ 1 and WPM < 25
- **Flow state** if WPM ≥ 45 and corrections < 6%
- Fallback: *balanced*

> Bursts are runs of ≥ 7 keys where inter‑key interval < 120 ms. Long pauses are inter‑key intervals > 800 ms.

### Daily Challenge (bonus)
- Slow WPM → speed drill (3×1min)
- High corrections → accuracy drill (No-Backspace paragraph)
- Long avg pause → warm‑up free typing (30s)
- Else → flow builder (90s on random topic)

## Data Model (SQLite)
Table `sessions`:
- `id`, `created_at`, `text_length`, `total_time_ms`, `avg_iki_ms`, `pauses_count`, `avg_pause_ms`,
- `backspace_count`, `bursts_count`, `wpm`,
- `mood` (computed), `suggestions` (JSON with tips + challenge), `raw_events` (JSON array)

## Routes
- `/` — Editor with live metrics
- `/submit` — POST JSON `{text, events[], metrics{}}`; saves session and redirects to `/dashboard/<id>`
- `/dashboard/<id>` — Charts (timeline + interval histogram) and mood report
- `/history` — Past sessions list
- `/export.csv` — CSV export of sessions

## Frontend Event Capture
We track `keydown` and record meaningful keys only (letters, numbers, space, Enter, Backspace).  
Metrics computed in the browser:
- inter‑key intervals (avg)
- pauses count + avg pause (>800 ms)
- bursts (see heuristic above)
- WPM (words / minutes)
- backspace count

## Deployment
### Render (free/simple)
1. Push this repo to GitHub.
2. On Render: *New + Web Service* → connect repo
3. Build command: `pip install -r requirements.txt`
4. Start command: `gunicorn app:app`
5. Add *SQLite* file persists on disk (Render uses ephemeral disk on free plan; for persistent history, mount a disk).

### Heroku
1. `heroku create`
2. `git push heroku main`
3. Ensure `Procfile` present (`web: gunicorn app:app`)
4. `heroku open`

> For Heroku, add `gunicorn` to requirements or change Procfile to `python app.py` for dev.

## Demo Video (60–90s) Script
1. **Intro (5s):** “This is AI‑Lite Typing Mood. It reads your typing rhythm — not content.”
2. **Typing (20s):** Show typing in editor, live metrics updating.
3. **Analyze (5s):** Click *Finish & Analyze*.
4. **Dashboard (20s):** Show WPM, pauses, backspaces, bursts, charts.
5. **Mood (5s):** Read the mood sentence and suggestions.
6. **History + Export (5–10s):** Open *History*, download CSV.
7. **Wrap (5s):** Mention rules in README, no ML used, link to repo/live demo.

## Notes
- This is a heuristic toy: not medical or psychological assessment.
- Privacy: We save keystroke events timing + which keys (Backspace vs others), and text length, not full text content.
