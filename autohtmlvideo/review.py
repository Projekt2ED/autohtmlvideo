from __future__ import annotations

import json
import threading
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from jinja2 import Template

from autohtmlvideo.models import StoryCandidate
from autohtmlvideo.storage import ProjectPaths, load_latest_candidates, save_review_selection


REVIEW_TEMPLATE = Template(
    """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <title>AI 热点审核</title>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <style>
    :root {
      --bg: #0b1220;
      --panel: rgba(8, 15, 28, 0.82);
      --line: rgba(255, 255, 255, 0.12);
      --text: #edf3ff;
      --muted: #94a7c6;
      --accent: #ff7a18;
      --accent-soft: rgba(255, 122, 24, 0.16);
      --ok: #89ffb6;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      min-height: 100vh;
      color: var(--text);
      background:
        radial-gradient(circle at top left, rgba(255,122,24,0.22), transparent 30%),
        radial-gradient(circle at bottom right, rgba(23,92,230,0.28), transparent 30%),
        linear-gradient(160deg, #050913, #0f172a 54%, #08111c);
      font-family: "Microsoft YaHei UI", "PingFang SC", "Noto Sans SC", sans-serif;
    }
    .shell {
      max-width: 1180px;
      margin: 0 auto;
      padding: 28px 22px 40px;
    }
    .hero {
      display: grid;
      gap: 12px;
      padding: 20px 22px;
      border: 1px solid var(--line);
      border-radius: 24px;
      background: linear-gradient(180deg, rgba(255,255,255,0.03), rgba(255,255,255,0.01));
      backdrop-filter: blur(12px);
    }
    .hero h1 { margin: 0; font-size: 28px; }
    .hero p { margin: 0; color: var(--muted); line-height: 1.7; }
    .cards { display: grid; gap: 16px; margin-top: 22px; }
    .card {
      border-radius: 22px;
      border: 1px solid var(--line);
      background: var(--panel);
      overflow: hidden;
    }
    .card-head {
      display: grid;
      gap: 8px;
      padding: 18px 20px 14px;
      background: linear-gradient(135deg, rgba(255,122,24,0.12), transparent 55%);
    }
    .meta {
      display: flex;
      gap: 10px;
      flex-wrap: wrap;
      font-size: 12px;
      color: var(--muted);
      text-transform: uppercase;
      letter-spacing: 0.08em;
    }
    .badge {
      width: fit-content;
      padding: 6px 10px;
      border-radius: 999px;
      background: var(--accent-soft);
      color: #ffd8b3;
      font-size: 12px;
    }
    .card h2 {
      margin: 0;
      font-size: 22px;
      line-height: 1.35;
    }
    .body {
      display: grid;
      gap: 14px;
      padding: 0 20px 20px;
    }
    .sources, .urls { display: grid; gap: 8px; }
    .source-row {
      display: grid;
      gap: 4px;
      padding: 10px 12px;
      border-radius: 16px;
      background: rgba(255,255,255,0.03);
      border: 1px solid rgba(255,255,255,0.06);
    }
    .source-row small { color: var(--muted); }
    a { color: #9ed0ff; word-break: break-all; }
    button {
      width: fit-content;
      padding: 12px 18px;
      border: 0;
      border-radius: 999px;
      cursor: pointer;
      color: #1f1308;
      font-weight: 700;
      background: linear-gradient(135deg, #ffb347, #ff7a18);
      box-shadow: 0 12px 36px rgba(255,122,24,0.22);
    }
    .status {
      min-height: 22px;
      color: var(--ok);
      font-size: 14px;
    }
  </style>
</head>
<body>
  <div class="shell">
    <section class="hero">
      <div class="badge">Review Mode</div>
      <h1>今日 AI 热点候选</h1>
      <p>从最新候选池中手动确认 1 条热点进入生成。审核通过后会在本地写入选中记录，随后直接运行 <code>autohtmlvideo build &lt;story_id&gt;</code>。</p>
      <div id="status" class="status"></div>
    </section>
    <section class="cards">
      {% for candidate in candidates %}
      <article class="card">
        <div class="card-head">
          <div class="meta">
            <span>#{{ loop.index }}</span>
            <span>{{ candidate["id"] }}</span>
            <span>score {{ "%.2f"|format(candidate["rank_score"]) }}</span>
          </div>
          <h2>{{ candidate["merged_topic"] }}</h2>
          <p>{{ candidate["why_hot"] }}</p>
        </div>
        <div class="body">
          <div class="sources">
            {% for item in candidate["items"] %}
            <div class="source-row">
              <strong>{{ item["source"] }}</strong>
              <small>{{ item["published_at"] }}</small>
              <div>{{ item["title"] }}</div>
              {% if item["summary"] %}<small>{{ item["summary"] }}</small>{% endif %}
              <a href="{{ item["url"] }}" target="_blank" rel="noreferrer">{{ item["url"] }}</a>
            </div>
            {% endfor %}
          </div>
          <button data-id="{{ candidate["id"] }}">批准并进入生成</button>
        </div>
      </article>
      {% endfor %}
    </section>
  </div>
  <script>
    const status = document.getElementById('status');
    for (const button of document.querySelectorAll('button[data-id]')) {
      button.addEventListener('click', async () => {
        const candidateId = button.getAttribute('data-id');
        button.disabled = true;
        status.textContent = `正在保存 ${candidateId} ...`;
        const response = await fetch('/api/approve', {
          method: 'POST',
          headers: { 'content-type': 'application/json' },
          body: JSON.stringify({ candidate_id: candidateId }),
        });
        const payload = await response.json();
        status.textContent = payload.message || payload.error || '';
        button.disabled = false;
      });
    }
  </script>
</body>
</html>"""
)


def run_review_server(paths: ProjectPaths, host: str, port: int) -> None:
    bundle = load_latest_candidates(paths)
    candidates = bundle.candidates
    candidates_by_id = {candidate.id: candidate for candidate in candidates}

    class ReviewHandler(BaseHTTPRequestHandler):
        def _send_json(self, payload: dict, status: int = 200) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:  # noqa: N802
            if self.path != "/":
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            body = REVIEW_TEMPLATE.render(candidates=[candidate.model_dump(mode="json") for candidate in candidates]).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self) -> None:  # noqa: N802
            if self.path != "/api/approve":
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            candidate_id = payload.get("candidate_id")
            candidate = candidates_by_id.get(candidate_id)
            if candidate is None:
                self._send_json({"error": f"Unknown candidate: {candidate_id}"}, status=400)
                return
            save_review_selection(paths, candidate)
            self._send_json({"message": f"已批准 {candidate_id}。下一步运行：autohtmlvideo build {candidate_id}"})

        def log_message(self, fmt: str, *args) -> None:  # noqa: A003
            return

    server = ThreadingHTTPServer((host, port), ReviewHandler)
    url = f"http://{host}:{port}/"
    thread = threading.Thread(target=webbrowser.open, args=(url,), daemon=True)
    thread.start()
    print(f"Review server listening on {url}")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
