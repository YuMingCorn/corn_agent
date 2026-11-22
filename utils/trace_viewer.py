"""Render one trace (see utils/trace_recorder.py) as a step-by-step HTML page.

Left: the code of the lesson. The statement that runs now is highlighted.
Right: the messages list as it was just before that statement ran, one card per message.
Bottom: what each actor (HUMAN, HARNESS, MODEL, TOOLS) did during that statement.

While the run is going, the page reloads every 2 seconds and follows the newest step.
If the reader moves to an older step, the page keeps that step (it is stored in the URL hash).
After the run, the controls replay the steps.

Usage: uv run python utils/trace_viewer.py <trace.json>
"""

from __future__ import annotations

import html
import json
import sys
from pathlib import Path

REFRESH_SECONDS = 2

CSS = """
:root {
  --bg: #131417; --panel: #1c1d22; --panel2: #23252b; --line: #2d3038;
  --text: #e7e8ec; --muted: #8e939e; --hl: #3b3517; --hl-bar: #f5b400;
  --human: #a78bfa; --harness: #60a5fa; --model: #fb923c; --tools: #34d399;
  --role-system: #7c6cf0; --role-user: #3b82f6; --role-assistant: #22a06b; --role-tool: #d97706;
  --warn: #f5b400; --err: #f87171;
}
@media (prefers-color-scheme: light) {
  :root:not([data-theme="dark"]) {
    --bg: #f5f6f8; --panel: #ffffff; --panel2: #f0f1f4; --line: #d9dce3;
    --text: #1d2026; --muted: #6b7180; --hl: #fff3c4; --hl-bar: #d99a00;
  }
}
:root[data-theme="light"] {
  --bg: #f5f6f8; --panel: #ffffff; --panel2: #f0f1f4; --line: #d9dce3;
  --text: #1d2026; --muted: #6b7180; --hl: #fff3c4; --hl-bar: #d99a00;
}
* { box-sizing: border-box; }
body { margin: 0; padding: 16px; background: var(--bg); color: var(--text);
  font: 14px/1.5 "Segoe UI", "Microsoft JhengHei", sans-serif; }
h1 { font-size: 18px; margin: 0 0 4px; }
.meta { color: var(--muted); font-size: 13px; }
.status { margin-top: 6px; font-size: 13px; }
.status.running { color: var(--warn); }
.status.finished { color: var(--muted); }
.controls { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; margin: 14px 0; }
.controls button, .controls select { font: inherit; color: var(--text); background: var(--panel);
  border: 1px solid var(--line); border-radius: 6px; padding: 4px 10px; cursor: pointer; }
.controls input[type=range] { flex: 1; min-width: 160px; }
.count { color: var(--muted); font-variant-numeric: tabular-nums; }
.panes { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: 16px; }
@media (max-width: 860px) { .panes { grid-template-columns: 1fr; } }
.pane { background: var(--panel); border: 1px solid var(--line); border-radius: 8px; padding: 10px; min-width: 0; }
.pane-title { font-size: 13px; color: var(--muted); margin-bottom: 8px; display: flex; justify-content: space-between; }
.pane-title b { color: var(--text); font-weight: 600; }
.code-body { position: relative; height: 60vh; overflow: auto; font: 13px/1.6 Consolas, "Courier New", monospace;
  background: var(--panel2); border-radius: 6px; padding: 4px 0; }
.ln { display: flex; white-space: pre; padding-right: 10px; }
.ln .num { width: 44px; flex: none; text-align: right; padding-right: 12px; color: var(--muted); user-select: none; }
.ln .txt { flex: 1; }
.ln.hl { background: var(--hl); box-shadow: inset 3px 0 0 var(--hl-bar); }
.ln.dim { opacity: 0.45; }
.ctx-body { height: 60vh; overflow: auto; }
.card { border-left: 4px solid var(--muted); background: var(--panel2); border-radius: 6px; padding: 6px 10px; margin-bottom: 8px; }
.card.role-system { border-color: var(--role-system); }
.card.role-user { border-color: var(--role-user); }
.card.role-assistant { border-color: var(--role-assistant); }
.card.role-tool { border-color: var(--role-tool); }
.card-head { display: flex; justify-content: space-between; font-size: 12px; color: var(--muted); }
.card-head .role { font-weight: 700; letter-spacing: 0.04em; }
.card.role-system .role { color: var(--role-system); }
.card.role-user .role { color: var(--role-user); }
.card.role-assistant .role { color: var(--role-assistant); }
.card.role-tool .role { color: var(--role-tool); }
pre.body { white-space: pre-wrap; word-break: break-word; margin: 4px 0 0; font: 13px/1.5 Consolas, "Courier New", monospace; }
.explain { margin-top: 16px; background: var(--panel); border: 1px solid var(--line); border-radius: 8px; padding: 10px; }
.explain h2 { font-size: 15px; margin: 0 0 8px; }
.event { display: flex; gap: 10px; align-items: flex-start; padding: 8px 0; border-top: 1px solid var(--line); }
.event:first-of-type { border-top: none; }
.event.warning .event-action { color: var(--warn); }
.event.error .event-action { color: var(--err); }
.event.pending { opacity: 0.75; font-style: italic; }
.event-body { min-width: 0; flex: 1; }
.event-action { font-weight: 600; }
.where { color: var(--muted); font: 12px Consolas, monospace; }
.event details { margin-top: 4px; }
.event summary { cursor: pointer; color: var(--muted); font-size: 12px; }
.badge { display: inline-block; min-width: 72px; text-align: center; padding: 1px 8px; border-radius: 4px;
  color: #111; font-size: 12px; font-weight: 700; flex: none; }
.badge.human { background: var(--human); }
.badge.harness { background: var(--harness); }
.badge.model { background: var(--model); }
.badge.tools { background: var(--tools); }
.empty { color: var(--muted); }
"""

JS = """
(function () {
  "use strict";
  var D = JSON.parse(document.getElementById("trace-data").textContent);
  var RUNNING = D.status === "running";
  var STEPS = D.lines || [];
  var SOURCES = D.sources || {};
  var INSTR = D.instrument_lines || {};
  var TOTAL = STEPS.length;
  var $ = function (id) { return document.getElementById(id); };
  var el = function (tag, cls, text) {
    var n = document.createElement(tag);
    if (cls) { n.className = cls; }
    if (text !== undefined && text !== null) { n.textContent = String(text); }
    return n;
  };

  // Events belong to a step (step_seq); events with no step yet are pending.
  var eventsAt = {};
  var pendingEvents = [];
  (D.events || []).forEach(function (e) {
    if (e.step_seq === null || e.step_seq === undefined) { pendingEvents.push(e); }
    else { (eventsAt[e.step_seq] = eventsAt[e.step_seq] || []).push(e); }
  });

  // The messages list is stored only when it changes, so carry the last one forward.
  // modelCallAt[i] counts the model calls that happened up to step i.
  var contextAt = [];
  var modelCallAt = [];
  var current = [];
  var calls = 0;
  STEPS.forEach(function (s) {
    if (Array.isArray(s.messages)) { current = s.messages; }
    contextAt.push(current);
    (eventsAt[s.seq] || []).forEach(function (e) { if (e.kind === "model_input") { calls += 1; } });
    modelCallAt.push(calls);
  });
  var pendingCall = pendingEvents.some(function (e) { return e.kind === "model_input"; });

  var idx = 0;
  var following = false;
  var timer = null;

  function clamp(i) { return Math.max(0, Math.min(TOTAL - 1, i)); }

  function renderCode() {
    var box = $("code");
    box.textContent = "";
    if (!TOTAL) {
      $("file-name").textContent = "";
      box.appendChild(el("div", "empty", "沒有逐行紀錄。"));
      return;
    }
    var s = STEPS[idx];
    var file = s.file;
    $("file-name").textContent = file;
    var lines = SOURCES[file] || [];
    var dim = {};
    (INSTR[file] || []).forEach(function (n) { dim[n] = true; });
    lines.forEach(function (text, k) {
      var no = k + 1;
      var cls = "ln";
      if (no >= s.line && no <= s.end_line) { cls += " hl"; }
      else if (dim[no]) { cls += " dim"; }
      var row = el("div", cls);
      row.appendChild(el("span", "num", no));
      row.appendChild(el("span", "txt", text));
      box.appendChild(row);
    });
    var hl = box.querySelector(".hl");
    if (hl) { box.scrollTop = Math.max(0, hl.offsetTop - box.clientHeight / 3); }
  }

  function bodyText(m) {
    if (typeof m.content === "string" && m.content !== "") { return m.content; }
    if (Array.isArray(m.tool_calls) && m.tool_calls.length) {
      return m.tool_calls.map(function (c) {
        var f = c.function || {};
        return "請求工具：" + (f.name || "?") + "(" + (f.arguments || "") + ")";
      }).join("\\n");
    }
    return m.content === null || m.content === undefined ? "(無內容)" : JSON.stringify(m.content);
  }

  function renderContext() {
    var box = $("ctx");
    box.textContent = "";
    var s = STEPS[idx];
    var title;
    if (!TOTAL) {
      title = "上下文 / messages（沒有逐行紀錄）";
    } else {
      var here = (eventsAt[s.seq] || []).some(function (e) { return e.kind === "model_input"; });
      if (here) { title = "上下文 / messages → 正在發給模型（第 " + modelCallAt[idx] + " 次）"; }
      else if (idx === TOTAL - 1 && pendingCall) { title = "上下文 / messages → 下一行即將發給模型（第 " + (calls + 1) + " 次）"; }
      else { title = "上下文 / messages（這一行執行前）"; }
    }
    $("ctx-title").textContent = title;
    var msgs = TOTAL ? contextAt[idx] : [];
    msgs.forEach(function (m, k) {
      var role = String(m.role || "?");
      var known = ["system", "user", "assistant", "tool"].indexOf(role) >= 0;
      var card = el("div", "card role-" + (known ? role : "other"));
      var head = el("div", "card-head");
      head.appendChild(el("span", "role", role === "tool" ? "TOOL RESULT" : role.toUpperCase()));
      head.appendChild(el("span", "", "#" + (k + 1) + (m.tool_call_id ? " · " + m.tool_call_id : "")));
      card.appendChild(head);
      card.appendChild(el("pre", "body", bodyText(m)));
      box.appendChild(card);
    });
    if (!msgs.length) { box.appendChild(el("div", "empty", "這一行之前還沒有 messages。")); }
  }

  function eventRow(e, pending) {
    var row = el("div", "event " + (e.level || "info") + (pending ? " pending" : ""));
    row.appendChild(el("span", "badge " + String(e.actor).toLowerCase(), e.actor));
    var body = el("div", "event-body");
    body.appendChild(el("div", "event-action", e.action));
    body.appendChild(el("div", "where", (pending ? "下一行即將執行 · " : "") + (e.code || "")));
    if (e.detail) {
      var d = el("details");
      d.appendChild(el("summary", "", "內容"));
      d.appendChild(el("pre", "body", e.detail));
      body.appendChild(d);
    }
    row.appendChild(body);
    return row;
  }

  function renderExplain() {
    var box = $("explain");
    box.textContent = "";
    var title = $("explain-title");
    if (!TOTAL) {
      title.textContent = "事件";
      (D.events || []).forEach(function (e) { box.appendChild(eventRow(e, false)); });
      return;
    }
    var s = STEPS[idx];
    title.textContent = "第 " + (idx + 1) + " / " + TOTAL + " 步 · " + s.file + " · " + s.func + " · 第 " +
      s.line + (s.end_line > s.line ? "–" + s.end_line : "") + " 行";
    var rows = (eventsAt[s.seq] || []).map(function (e) { return { e: e, pending: false }; });
    if (idx === TOTAL - 1) {
      pendingEvents.forEach(function (e) { rows.push({ e: e, pending: true }); });
    }
    if (!rows.length) { box.appendChild(el("div", "empty", "這一行沒有記錄事件。")); }
    rows.forEach(function (r) { box.appendChild(eventRow(r.e, r.pending)); });
  }

  function updateControls() {
    var p = $("pos");
    p.max = String(Math.max(TOTAL, 1));
    p.value = String(TOTAL ? idx + 1 : 0);
    $("pos-label").textContent = TOTAL ? (idx + 1) + " / " + TOTAL : "0 / 0";
  }

  function writeHash() {
    var h = "step=" + (idx + 1) + (following ? "&follow=1" : "");
    try { history.replaceState(null, "", "#" + h); }
    catch (e) { /* some file pages refuse this; the hash is only a bookmark */ }
  }

  function render() {
    renderCode();
    renderContext();
    renderExplain();
    updateControls();
  }

  function goTo(i) {
    if (!TOTAL) { return; }
    idx = clamp(i);
    following = RUNNING && idx === TOTAL - 1;
    render();
    writeHash();
  }

  function stop() {
    if (timer) { clearInterval(timer); timer = null; }
    $("play").textContent = "▶ 播放";
  }

  function play() {
    if (!TOTAL) { return; }
    if (timer) { stop(); return; }
    $("play").textContent = "⏸ 暫停";
    timer = setInterval(function () {
      if (idx >= TOTAL - 1) { stop(); return; }
      goTo(idx + 1);
    }, Number($("speed").value) || 1000);
  }

  $("first").onclick = function () { stop(); goTo(0); };
  $("prev").onclick = function () { stop(); goTo(idx - 1); };
  $("next").onclick = function () { stop(); goTo(idx + 1); };
  $("last").onclick = function () { stop(); goTo(TOTAL - 1); };
  $("play").onclick = play;
  $("pos").oninput = function () { stop(); goTo(Number(this.value) - 1); };
  $("speed").onchange = function () { if (timer) { stop(); play(); } };

  // Start: while running, follow the newest step unless the URL says the reader stayed on an older step.
  var m = /step=(\\d+)/.exec(location.hash);
  var follow = /follow=1/.test(location.hash);
  if (TOTAL) {
    var wantNewest = RUNNING && (follow || !m);
    idx = wantNewest ? TOTAL - 1 : clamp(m ? Number(m[1]) - 1 : TOTAL - 1);
    following = wantNewest;
    writeHash();
  }
  render();
})();
"""


def _esc(text: object) -> str:
    return html.escape(str(text), quote=True)


def _embed_json(data: dict) -> str:
    """Serialise for a <script> block. Escaping < > & keeps the content from closing the tag."""
    text = json.dumps(data, ensure_ascii=False)
    return text.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")


def render_html(data: dict) -> str:
    running = data.get("status") == "running"
    refresh = f'<meta http-equiv="refresh" content="{REFRESH_SECONDS}">' if running else ""
    status_line = (
        "RUNNING：每 2 秒自動更新；停在較早的步驟時，頁面會留在該步。"
        if running
        else "FINISHED：用上方的控制逐步回放。"
    )
    status_class = "running" if running else "finished"
    lesson = _esc(data.get("lesson", ""))
    steps = len(data.get("lines", []))
    records = len(data.get("events", []))
    title = f"逐行播放 {lesson}"
    return f"""<!doctype html>
<html lang="zh-Hant">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
{refresh}
<style>{CSS}</style>
</head>
<body>
<header>
  <h1>逐行播放：{lesson}</h1>
  <div class="meta">{_esc(data.get("name", ""))} | 開始 {_esc(data.get("started", ""))} | {steps} 步 | {records} 筆事件</div>
  <div class="status {status_class}">{_esc(status_line)}</div>
</header>
<div class="controls">
  <button id="first" title="第一步">⏮ 重來</button>
  <button id="prev" title="上一步">◀ 上一格</button>
  <button id="play">▶ 播放</button>
  <button id="next" title="下一步">下一格 ▶</button>
  <button id="last" title="最新一步">⏭ 最新</button>
  <input type="range" id="pos" min="1" max="1" value="0">
  <span id="pos-label" class="count">0 / 0</span>
  <select id="speed" title="播放速度">
    <option value="2000">慢</option>
    <option value="1000" selected>一般</option>
    <option value="400">快</option>
  </select>
</div>
<div class="panes">
  <section class="pane">
    <div class="pane-title"><b>程式碼</b><span id="file-name"></span></div>
    <div id="code" class="code-body"></div>
  </section>
  <section class="pane">
    <div class="pane-title"><b id="ctx-title">上下文 / messages</b></div>
    <div id="ctx" class="ctx-body"></div>
  </section>
</div>
<section class="explain">
  <h2 id="explain-title">事件</h2>
  <div id="explain"></div>
</section>
<script type="application/json" id="trace-data">{_embed_json(data)}</script>
<script>{JS}</script>
</body>
</html>
"""


def write_html(json_path: Path) -> Path:
    data = json.loads(json_path.read_text(encoding="utf-8"))
    out = json_path.with_suffix(".html")
    out.write_text(render_html(data), encoding="utf-8")
    return out


def main() -> None:
    if len(sys.argv) != 2:
        print("usage: uv run python utils/trace_viewer.py <trace.json>")
        sys.exit(2)
    print(write_html(Path(sys.argv[1])))


if __name__ == "__main__":
    main()
