from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pathlib import Path

from routers import analytics, instruments, experiments

app = FastAPI(title="LabMind Backend", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(analytics.router)
app.include_router(instruments.router)
app.include_router(experiments.router)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/", response_class=HTMLResponse)
def upload_page():
    return """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>LabMind — Upload Experiment</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body { font-family: system-ui, sans-serif; background: #0f0f0f; color: #e0e0e0; min-height: 100vh; display: flex; align-items: center; justify-content: center; }
    .card { background: #1a1a1a; border: 1px solid #2a2a2a; border-radius: 12px; padding: 40px; width: 100%; max-width: 520px; }
    h1 { font-size: 1.4rem; font-weight: 600; margin-bottom: 6px; }
    .subtitle { color: #666; font-size: 0.85rem; margin-bottom: 32px; }
    label { display: block; font-size: 0.8rem; color: #888; margin-bottom: 8px; text-transform: uppercase; letter-spacing: 0.05em; }
    .drop-zone { border: 2px dashed #333; border-radius: 8px; padding: 40px 20px; text-align: center; cursor: pointer; transition: border-color 0.2s; margin-bottom: 24px; }
    .drop-zone:hover, .drop-zone.drag-over { border-color: #76b900; }
    .drop-zone input { display: none; }
    .drop-zone .icon { font-size: 2rem; margin-bottom: 12px; }
    .drop-zone .hint { color: #555; font-size: 0.85rem; margin-top: 6px; }
    .drop-zone .filename { color: #76b900; font-size: 0.9rem; margin-top: 8px; font-weight: 500; }
    button { width: 100%; padding: 12px; background: #76b900; color: #000; font-weight: 600; font-size: 0.95rem; border: none; border-radius: 8px; cursor: pointer; transition: background 0.2s; }
    button:hover:not(:disabled) { background: #89d300; }
    button:disabled { background: #333; color: #555; cursor: not-allowed; }
    .status { margin-top: 20px; padding: 14px 16px; border-radius: 8px; font-size: 0.88rem; display: none; }
    .status.success { background: #0d2200; border: 1px solid #76b900; color: #a8e040; }
    .status.error { background: #220000; border: 1px solid #660000; color: #ff6b6b; }
    .status.pending { background: #1a1400; border: 1px solid #554400; color: #ccaa00; }
    .run-id { font-family: monospace; font-weight: 600; }
    .divider { border: none; border-top: 1px solid #222; margin: 28px 0; }
    .current { font-size: 0.85rem; }
    .current h2 { font-size: 0.8rem; text-transform: uppercase; letter-spacing: 0.05em; color: #555; margin-bottom: 12px; }
    .badge { display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 0.75rem; font-weight: 600; }
    .badge.active { background: #0d2200; color: #76b900; border: 1px solid #76b900; }
    .badge.pending { background: #1a1400; color: #ccaa00; border: 1px solid #554400; }
    .badge.none { color: #444; }
    .openclaw-link { display: block; text-align: center; margin-top: 20px; color: #555; font-size: 0.8rem; text-decoration: none; }
    .openclaw-link:hover { color: #76b900; }
    .format-hint { background: #111; border: 1px solid #222; border-radius: 6px; padding: 12px 14px; font-size: 0.78rem; color: #555; margin-bottom: 24px; font-family: monospace; line-height: 1.6; }
    .format-hint strong { color: #888; display: block; margin-bottom: 6px; font-family: system-ui; }
  </style>
</head>
<body>
  <div class="card">
    <h1>LabMind</h1>
    <p class="subtitle">Upload an experiment document to begin. The agent will assess it and start monitoring.</p>

    <div class="format-hint">
      <strong>Document format (YAML)</strong>
      hypothesis: ...<br>
      instruments: [temp_controller, ph_probe]<br>
      monitoring: { temperature_c: { target: 35, ... } }<br>
      remediation: { temperature_high: { ... } }<br>
      stages: [ { name: ..., hours: ... } ]
    </div>

    <label>Experiment document</label>
    <div class="drop-zone" id="dropZone">
      <div class="icon">📄</div>
      <div>Drop your YAML file here or <strong>click to browse</strong></div>
      <div class="hint">.yaml · .yml · .md · .txt</div>
      <div class="filename" id="fileName"></div>
      <input type="file" id="fileInput" accept=".yaml,.yml,.md,.txt">
    </div>

    <button id="uploadBtn" disabled>Upload &amp; Start</button>

    <div class="status" id="statusBox"></div>

    <hr class="divider">

    <div class="current">
      <h2>Current experiment</h2>
      <div id="currentStatus"><span class="badge none">No active experiment</span></div>
    </div>

    <a class="openclaw-link" href="http://localhost:18789" target="_blank">Open OpenClaw UI →</a>
  </div>

  <script>
    const dropZone = document.getElementById('dropZone');
    const fileInput = document.getElementById('fileInput');
    const uploadBtn = document.getElementById('uploadBtn');
    const fileName = document.getElementById('fileName');
    const statusBox = document.getElementById('statusBox');
    const currentStatus = document.getElementById('currentStatus');
    let selectedFile = null;

    dropZone.addEventListener('click', () => fileInput.click());
    dropZone.addEventListener('dragover', e => { e.preventDefault(); dropZone.classList.add('drag-over'); });
    dropZone.addEventListener('dragleave', () => dropZone.classList.remove('drag-over'));
    dropZone.addEventListener('drop', e => {
      e.preventDefault();
      dropZone.classList.remove('drag-over');
      const f = e.dataTransfer.files[0];
      if (f) selectFile(f);
    });
    fileInput.addEventListener('change', () => { if (fileInput.files[0]) selectFile(fileInput.files[0]); });

    function selectFile(f) {
      selectedFile = f;
      fileName.textContent = f.name;
      uploadBtn.disabled = false;
    }

    uploadBtn.addEventListener('click', async () => {
      if (!selectedFile) return;
      uploadBtn.disabled = true;
      uploadBtn.textContent = 'Uploading…';
      showStatus('', '');

      const form = new FormData();
      form.append('doc', selectedFile);

      try {
        const resp = await fetch('/api/experiments/upload', { method: 'POST', body: form });
        const data = await resp.json();
        if (resp.ok) {
          showStatus('success', `Experiment <span class="run-id">${data.run_id}</span> created. Status: <strong>${data.status}</strong>.<br>The agent is now assessing this run — check the OpenClaw UI for its response.`);
        } else {
          showStatus('error', data.detail || 'Upload failed.');
        }
      } catch (e) {
        showStatus('error', 'Could not reach backend. Is Docker running?');
      }

      uploadBtn.disabled = false;
      uploadBtn.textContent = 'Upload & Start';
      pollCurrent();
    });

    function showStatus(type, html) {
      statusBox.className = 'status ' + type;
      statusBox.innerHTML = html;
      statusBox.style.display = html ? 'block' : 'none';
    }

    async function pollCurrent() {
      try {
        const resp = await fetch('/api/experiments/current');
        const data = await resp.json();
        if (data.status === 'active') {
          currentStatus.innerHTML = `<span class="badge active">Active</span> &nbsp;<span class="run-id">${data.run_id}</span> — ${data.metadata?.hypothesis?.slice(0, 60) || ''}…`;
        } else if (data.status === 'pending') {
          currentStatus.innerHTML = `<span class="badge pending">Pending agent review</span> &nbsp;<span class="run-id">${data.run_id}</span>`;
        } else {
          currentStatus.innerHTML = '<span class="badge none">No active experiment</span>';
        }
      } catch (_) {}
    }

    pollCurrent();
    setInterval(pollCurrent, 10000);
  </script>
</body>
</html>"""
