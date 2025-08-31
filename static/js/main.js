// Capture keystroke events and compute metrics on the fly
(() => {
  const editor = document.getElementById('editor');
  const liveEls = document.querySelectorAll('#liveMetrics [data-k]');
  const finishBtn = document.getElementById('finishBtn');
  const resetBtn = document.getElementById('resetBtn');
  const timerEl = document.getElementById('timer');
  const exportBtn = document.getElementById('exportBtn'); // ⬅ add this in HTML

  let events = []; // {t: timestamp(ms), k: key}
  let startedAt = null;
  let lastT = null;

  const updateTimer = () => {
    if (!startedAt) return;
    const s = Math.floor((performance.now() - startedAt) / 1000);
    const mm = String(Math.floor(s/60)).padStart(2,'0');
    const ss = String(s%60).padStart(2,'0');
    timerEl.textContent = `${mm}:${ss}`;
  };
  setInterval(updateTimer, 200);

  const computeMetrics = () => {
    if (events.length < 2) {
      return {
        keystrokes: events.length,
        backspace_count: events.filter(e => e.k === 'Backspace').length,
        avg_iki_ms: 0,
        pauses_count: 0,
        avg_pause_ms: 0,
        bursts_count: 0,
        wpm: 0,
        total_time_ms: startedAt ? (performance.now() - startedAt) : 0
      };
    }
    let intervals = [];
    let pauses = [];
    let bursts = 0;
    let currentBurst = 0;
    for (let i=1; i<events.length; i++) {
      const dt = events[i].t - events[i-1].t;
      intervals.push(dt);
      // Pause threshold (heuristic): > 800ms
      if (dt > 800) pauses.push(dt);
      // Burst if fast typing < 120ms
      if (dt < 120) {
        currentBurst++;
      } else {
        if (currentBurst >= 6) bursts++; // at least 7 rapid keys
        currentBurst = 0;
      }
    }
    if (currentBurst >= 6) bursts++;

    const avg = arr => arr.length ? arr.reduce((a,b)=>a+b,0)/arr.length : 0;

    const totalTime = events[events.length-1].t - events[0].t;
    const words = editor.value.trim().length ? editor.value.trim().split(/\s+/).length : 0;
    const minutes = totalTime / 60000;
    const wpm = minutes > 0 ? words / minutes : 0;

    return {
      keystrokes: events.length,
      backspace_count: events.filter(e => e.k === 'Backspace').length,
      avg_iki_ms: Math.round(avg(intervals)),
      pauses_count: pauses.length,
      avg_pause_ms: Math.round(avg(pauses)),
      bursts_count: bursts,
      wpm: Math.round(wpm*10)/10,
      total_time_ms: Math.round(totalTime)
    };
  };

  const renderLive = () => {
    const m = computeMetrics();
    liveEls.forEach(el => {
      const k = el.getAttribute('data-k');
      el.textContent = m[k] ?? 0;
    });
  };

  // Record only meaningful keys
  const meaningful = k => {
    if (k === 'Shift' || k === 'Meta' || k === 'Alt' || k === 'Control') return false;
    if (k === 'CapsLock' || k.startsWith('Arrow')) return false;
    return true;
  };

  const record = k => {
    const t = performance.now();
    if (!startedAt) startedAt = t;
    events.push({t, k});
    lastT = t;
    renderLive();
  };

  editor.addEventListener('keydown', (e) => {
    if (!meaningful(e.key)) return;
    record(e.key);
  });

  resetBtn.addEventListener('click', () => {
    editor.value = '';
    events = [];
    startedAt = null;
    lastT = null;
    renderLive();
    timerEl.textContent = '00:00';
  });

  finishBtn.addEventListener('click', async () => {
    const metrics = computeMetrics();
    const payload = {
      text: editor.value,
      events: events.map(e => ({t: Math.round(e.t), k: e.k})),
      metrics
    };
    const res = await fetch('/submit', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(payload)
    });
    const data = await res.json();
    if (data.ok) {
      window.location.href = `/dashboard/${data.session_id}`;
    }
  });

  // --- Export CSV directly in browser ---
  if (exportBtn) {
    exportBtn.addEventListener('click', () => {
      if (events.length === 0) {
        alert("No keystroke data to export yet!");
        return;
      }
      let csv = "Timestamp(ms),Key\n";
      events.forEach(e => {
        csv += `${e.t},${e.k}\n`;
      });
      const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "typing_session.csv";
      a.click();
      URL.revokeObjectURL(url);
    });
  }

})();
