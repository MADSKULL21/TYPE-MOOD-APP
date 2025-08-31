import csv
import io
import json
import sqlite3
from datetime import datetime
from pathlib import Path
from flask import Flask, render_template, request, redirect, url_for, send_file, jsonify, Response

app = Flask(__name__)
DB_PATH = Path("typing_mood.db")


def init_db():
    # Use str(DB_PATH) when connecting to avoid any Path/str mismatch
    with sqlite3.connect(str(DB_PATH)) as con:
        cur = con.cursor()
        cur.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            text_length INTEGER,
            total_time_ms INTEGER,
            avg_iki_ms REAL,
            pauses_count INTEGER,
            avg_pause_ms REAL,
            backspace_count INTEGER,
            bursts_count INTEGER,
            wpm REAL,
            mood TEXT,
            suggestions TEXT,
            raw_events TEXT
        );
        """)
        con.commit()


# Initialize DB at startup (Flask 3 removed before_first_request decorator)
with app.app_context():
    init_db()


@app.route("/")
def index():
    return render_template("index.html")


def apply_heuristics(metrics):
    """Return mood label and suggestions given calculated metrics"""
    mood = []
    suggestions = []

    # defensive access - ensure numeric values exist
    keystrokes = metrics.get("keystrokes", 1) or 1
    backspace_count = metrics.get("backspace_count", 0) or 0
    corrections_rate = (backspace_count / max(keystrokes, 1)) * 100
    avg_pause = metrics.get("avg_pause_ms", 0) or 0
    bursts = metrics.get("bursts_count", 0) or 0
    wpm = metrics.get("wpm", 0) or 0

    # Heuristic rules
    if corrections_rate > 12:
        mood.append("low focus")
        suggestions.append("Try a 5-minute 'accuracy first' drill: type slowly without using Backspace.")
    elif corrections_rate > 6:
        mood.append("slightly distracted")
        suggestions.append("Hide other tabs/phone. Aim for smaller corrections in the next run.")

    if avg_pause > 900:
        mood.append("thinking mode")
        suggestions.append("Preview the prompt and outline one sentence in your head before typing.")

    if bursts >= 4 and avg_pause < 600:
        mood.append("high confidence")
    elif bursts <= 1 and wpm < 25:
        mood.append("cautious")
        suggestions.append("Do a 2-minute speed drill: type an easy paragraph continuously.")

    if wpm >= 45 and corrections_rate < 6:
        mood.append("flow state")

    if not mood:
        mood.append("balanced")

    # Bonus daily challenge suggestion
    challenge = None
    if wpm < 25:
        challenge = "Speed drill: 3 rounds of 1-minute typing. Focus on rhythm; don't correct mistakes until the end."
    elif corrections_rate > 10:
        challenge = "Accuracy drill: Type a short paragraph without using Backspace. Review errors after."
    elif avg_pause > 1000:
        challenge = "Warm-up: 30 seconds of free typing to get fingers moving before real writing."
    else:
        challenge = "Flow builder: Pick a random topic and type continuously for 90 seconds."

    return ", ".join(sorted(set(mood))), suggestions, challenge


@app.route("/submit", methods=["POST"])
def submit():
    try:
        payload = request.get_json(force=True)
        if not isinstance(payload, dict):
            return jsonify({"ok": False, "error": "Invalid JSON payload"}), 400
            
        text = payload.get("text", "") or ""
        events = payload.get("events", []) or []
        metrics = payload.get("metrics", {}) or {}
        
        if not isinstance(metrics, dict):
            return jsonify({"ok": False, "error": "Invalid metrics format"}), 400
    except Exception as e:
        return jsonify({"ok": False, "error": f"Failed to process request: {str(e)}"}), 400

    mood, suggestions, challenge = apply_heuristics(metrics)

    # Coerce numeric values to safe defaults (avoid inserting None)
    def safe(val, default=0):
        return default if val is None else val

    record = {
        "created_at": datetime.utcnow().isoformat(),
        "text_length": len(text),
        "total_time_ms": safe(metrics.get("total_time_ms")),
        "avg_iki_ms": safe(metrics.get("avg_iki_ms")),
        "pauses_count": safe(metrics.get("pauses_count")),
        "avg_pause_ms": safe(metrics.get("avg_pause_ms")),
        "backspace_count": safe(metrics.get("backspace_count")),
        "bursts_count": safe(metrics.get("bursts_count")),
        "wpm": safe(metrics.get("wpm")),
        "mood": mood,
        "suggestions": json.dumps({"suggestions": suggestions, "challenge": challenge}),
        "raw_events": json.dumps(events),
    }

    with sqlite3.connect(str(DB_PATH)) as con:
        cur = con.cursor()
        cur.execute("""
            INSERT INTO sessions (created_at, text_length, total_time_ms, avg_iki_ms, pauses_count,
                                  avg_pause_ms, backspace_count, bursts_count, wpm, mood, suggestions, raw_events)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            record["created_at"], record["text_length"], record["total_time_ms"], record["avg_iki_ms"],
            record["pauses_count"], record["avg_pause_ms"], record["backspace_count"], record["bursts_count"],
            record["wpm"], record["mood"], record["suggestions"], record["raw_events"]
        ))
        session_id = cur.lastrowid
        con.commit()

    return jsonify({"ok": True, "session_id": session_id})


@app.route("/dashboard/<int:session_id>")
def dashboard(session_id):
    with sqlite3.connect(str(DB_PATH)) as con:
        cur = con.cursor()
        cur.execute("SELECT * FROM sessions WHERE id=?", (session_id,))
        row = cur.fetchone()

    if not row:
        return "Session not found", 404

    keys = ["id", "created_at", "text_length", "total_time_ms", "avg_iki_ms", "pauses_count", "avg_pause_ms",
            "backspace_count", "bursts_count", "wpm", "mood", "suggestions", "raw_events"]
    data = dict(zip(keys, row))

    # numeric defaults
    for k in ["total_time_ms", "avg_iki_ms", "pauses_count", "avg_pause_ms", "backspace_count", "bursts_count", "wpm"]:
        if data.get(k) is None:
            data[k] = 0

    try:
        sugg = json.loads(data.get("suggestions") or "{}")
    except Exception:
        sugg = {"suggestions": [], "challenge": None}

    try:
        events = json.loads(data.get("raw_events") or "[]")
    except Exception:
        events = []

    # Build keystroke timeline: x = seconds since start, y = cumulative keystrokes
    timeline = []
    if events:
        start_time = events[0].get("t", 0)
        for i, ev in enumerate(events, start=1):
            t = (ev.get("t", 0) - start_time) / 1000.0  # convert ms → seconds
            timeline.append([t, i])

    # Ensure sugg structure
    if isinstance(sugg, dict):
        sugg.setdefault("suggestions", [])
        sugg.setdefault("challenge", None)
    else:
        sugg = {"suggestions": [], "challenge": None}

    return render_template("dashboard.html", data=data, sugg=sugg, events=events, timeline=timeline)


@app.route("/history")
def history():
    with sqlite3.connect(str(DB_PATH)) as con:
        cur = con.cursor()
        cur.execute("""SELECT id, created_at, text_length, wpm, avg_iki_ms, backspace_count, mood
                       FROM sessions ORDER BY id DESC""")
        rows = cur.fetchall()
    sessions = [
        {
            "id": r[0],
            "created_at": r[1],
            "text_length": r[2],
            "wpm": (r[3] or 0),
            "avg_iki_ms": (r[4] or 0),
            "backspace_count": (r[5] or 0),
            "mood": (r[6] or "")
        } for r in rows
    ]
    return render_template("history.html", sessions=sessions)


@app.route("/export.csv")
def export_csv():
    """Stream CSV in-memory to avoid file-permission problems and ensure proper headers."""
    with sqlite3.connect(str(DB_PATH)) as con:
        cur = con.cursor()
        cur.execute("""SELECT id, created_at, text_length, total_time_ms, avg_iki_ms, pauses_count, avg_pause_ms,
                              backspace_count, bursts_count, wpm, mood
                       FROM sessions ORDER BY id ASC""")
        rows = cur.fetchall()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["id", "created_at", "text_length", "total_time_ms", "avg_iki_ms", "pauses_count", "avg_pause_ms",
                     "backspace_count", "bursts_count", "wpm", "mood"])
    for r in rows:
        # Coerce None to empty string for CSV readability
        writer.writerow([("" if c is None else c) for c in r])

    resp = Response(output.getvalue(), mimetype="text/csv")
    resp.headers["Content-Disposition"] = "attachment; filename=typing_mood_history.csv"
    return resp


if __name__ == "__main__":
    # debug=True is fine for local dev; for production use a real WSGI server
    app.run(debug=True)
