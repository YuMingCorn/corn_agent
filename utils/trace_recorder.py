"""Record what happens during one run of a lesson, one statement at a time.

Two kinds of records are kept:
- steps: each statement of the lesson's main.py that runs, found with sys.settrace.
  A step keeps the messages list as it was just before that statement ran.
  Recorder calls (recorder.* and logger.*) are not steps.
- events: what each actor does (HUMAN, HARNESS, MODEL, TOOLS) and where in the code.
  An event that main.py records belongs to the next step that runs.
  An event that another file records (for example tools.py) belongs to the step
  that is running at that moment.

The recorder writes two files after every step and every event:
- traces/<lesson>/session-<time>.json   the raw trace
- traces/<lesson>/session-<time>.html   the replay page (see utils/trace_viewer.py)
While the run is going, the page reloads itself. Call finish() at the end.

A failure to write these files only prints a warning. It never stops the agent.
"""

from __future__ import annotations

import ast
import copy
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from .trace_viewer import render_html

PROJECT_ROOT = Path(__file__).resolve().parent.parent
_THIS_FILE = os.path.normcase(os.path.abspath(__file__))
_INSTRUMENT_ROOTS = {"recorder", "logger"}


def _norm(path: str) -> str:
    return os.path.normcase(os.path.abspath(path))


def _say(message: str) -> None:
    """Print a trace message to stderr. A console that cannot show the text must not stop the agent."""
    try:
        print(message, file=sys.stderr)
    except Exception:
        pass


def _write_atomic(path: Path, text: str) -> None:
    """Write to a temporary file first, then replace the target, so readers never see half a file."""
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def _root_name(node: ast.AST) -> str | None:
    while isinstance(node, ast.Attribute):
        node = node.value
    return node.id if isinstance(node, ast.Name) else None


def _statement_map(source: str) -> tuple[dict[int, tuple[int, int, bool]], set[int]]:
    """Map each line to (first line, last line, is_recorder_call) of the statement that owns it.

    A compound statement (if, for, def, try ...) owns only its header lines, so its body
    lines map to the statements inside it. Returns the map and the set of recorder-call lines.
    """
    spans: dict[int, tuple[int, int, bool]] = {}
    instrument: set[int] = set()
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, (ast.stmt, ast.ExceptHandler)):
            continue
        body = getattr(node, "body", None)
        if isinstance(body, list) and body and isinstance(body[0], ast.stmt):
            first, last = node.lineno, max(node.lineno, body[0].lineno - 1)
            is_call = False
        else:
            first = node.lineno
            last = node.end_lineno or node.lineno
            value = node.value if isinstance(node, (ast.Expr, ast.Assign)) else None
            is_call = isinstance(value, ast.Call) and _root_name(value.func) in _INSTRUMENT_ROOTS
        for line in range(first, last + 1):
            spans[line] = (first, last, is_call)  # walk order is outer first, so inner wins
        if is_call:
            instrument.update(range(first, last + 1))
    return spans, instrument


class Recorder:
    def __init__(self, lesson: str, trace_dir: Path | None = None) -> None:
        self.lesson = lesson
        self.started = datetime.now()
        self.name = f"session-{self.started:%Y%m%d-%H%M%S}"
        # Traces sit at the project root, outside every lesson's workspace, so tools cannot read them.
        self.dir = trace_dir if trace_dir is not None else PROJECT_ROOT / "traces" / lesson
        self.events: list[dict[str, Any]] = []
        self.lines: list[dict[str, Any]] = []  # one entry per statement that ran
        self.sources: dict[str, list[str]] = {}
        self.instrument_lines: dict[str, list[int]] = {}
        self.task = 0  # number of the current task; 0 means no task yet
        self.status = "running"
        self._warned = False
        self._announced = False
        self._pending: list[dict[str, Any]] = []  # events waiting for the next step
        self._spans: dict[int, tuple[int, int, bool]] = {}
        self._target: str | None = None  # normalised path of the file being traced
        self._caller_frame: Any = None
        self._last_key: tuple[int, int] | None = None
        self._last_messages_text: str | None = None

    # ----- events -------------------------------------------------------------------

    def _recorded_by_main(self) -> bool:
        """True when the code that called event() or model_input() is the traced main.py."""
        if self._target is None:
            return False
        frame = sys._getframe(1)
        while frame is not None and _norm(frame.f_code.co_filename) == _THIS_FILE:
            frame = frame.f_back
        return frame is not None and _norm(frame.f_code.co_filename) == self._target

    def _add(self, event: dict[str, Any]) -> None:
        event["seq"] = len(self.events) + 1
        event["time"] = datetime.now().isoformat(timespec="seconds")
        event["task"] = self.task
        event["step_seq"] = None
        self.events.append(event)
        if self.lines and not self._recorded_by_main():
            event["step_seq"] = self.lines[-1]["seq"]
        else:
            self._pending.append(event)
        self._flush()

    def start_task(self, task_text: str, code: str) -> None:
        """Mark the start of a new user task. Steps count from 1 inside each task."""
        self.task += 1
        self._add(
            {
                "kind": "task_start",
                "actor": "HUMAN",
                "code": code,
                "action": f"Task {self.task} submitted",
                "step": None,
                "detail": task_text,
                "level": "info",
            }
        )

    def event(
        self,
        actor: str,
        code: str,
        action: str,
        step: int | None = None,
        detail: str | None = None,
        level: str = "info",
    ) -> None:
        """Record one action. `level` is info, warning or error."""
        self._add(
            {
                "kind": "event",
                "actor": actor,
                "code": code,
                "action": action,
                "step": step,
                "detail": detail,
                "level": level,
            }
        )

    def model_input(
        self,
        step: int,
        messages: list[dict[str, Any]],
        tool_schemas: list[dict[str, Any]],
        code: str,
    ) -> None:
        """Record a full copy of the messages and tool schemas sent to the model at this step."""
        self._add(
            {
                "kind": "model_input",
                "actor": "HARNESS",
                "code": code,
                "action": f"Send {len(messages)} message(s) and {len(tool_schemas)} tool schema(s) to model",
                "step": step,
                "tool_schemas": copy.deepcopy(tool_schemas),
                "messages": copy.deepcopy(messages),
                "level": "info",
            }
        )

    # ----- line steps ---------------------------------------------------------------

    def trace_lines(self, source_path: str | Path) -> None:
        """Start recording each statement of this file. Call it at the start of the main loop.

        Does nothing if another tracer (for example an IDE debugger) is already active.
        """
        if self._target is not None or sys.gettrace() is not None:
            return
        try:
            path = Path(source_path)
            text = path.read_text(encoding="utf-8")
            spans, instrument = _statement_map(text)
        except Exception as exc:
            _say(f"[trace] warning: line tracing is off ({type(exc).__name__})")
            return
        self._spans = spans
        self._target = _norm(str(path))
        self.sources[path.name] = text.splitlines()
        self.instrument_lines[path.name] = sorted(instrument)
        self._caller_frame = sys._getframe(1)
        sys.settrace(self._global_trace)
        self._caller_frame.f_trace = self._local_trace

    def _global_trace(self, frame: Any, event: str, arg: Any) -> Any:
        if event == "call" and _norm(frame.f_code.co_filename) == self._target:
            return self._local_trace
        return None

    def _local_trace(self, frame: Any, event: str, arg: Any) -> Any:
        if event == "line":
            try:
                self._on_line(frame)
            except Exception:  # tracing must never break the agent
                pass
        return self._local_trace

    def _on_line(self, frame: Any) -> None:
        if _norm(frame.f_code.co_filename) != self._target:  # the caller may be another file
            return
        first_last = self._spans.get(frame.f_lineno)
        if first_last is None:
            return
        first, last, is_recorder_call = first_last
        if is_recorder_call:
            self._last_key = None  # the next line event starts a new visit, even if it is the same line
            return
        key = (id(frame), first)
        if key == self._last_key:  # a multi-line statement fires several line events
            return
        self._last_key = key
        step: dict[str, Any] = {
            "seq": len(self.lines) + 1,
            "file": os.path.basename(self._target or ""),
            "line": first,
            "end_line": last,
            "func": frame.f_code.co_name,
            "task": self.task,
            "time": datetime.now().isoformat(timespec="seconds"),
        }
        messages = frame.f_locals.get("messages")
        if isinstance(messages, list):
            text = json.dumps(messages, ensure_ascii=False, sort_keys=True, default=str)
            if text != self._last_messages_text:  # store the list only when it changed
                self._last_messages_text = text
                step["messages"] = copy.deepcopy(messages)
        self.lines.append(step)
        for event in self._pending:
            event["step_seq"] = step["seq"]
        self._pending.clear()
        self._flush()

    # ----- finishing and writing ----------------------------------------------------

    def finish(self) -> Path:
        """Stop line tracing, mark the run as finished (the HTML stops reloading), and return the JSON path.

        A failed write here would leave the page reloading forever, so it is retried.
        """
        if self._target is not None:
            sys.settrace(None)
            if self._caller_frame is not None:
                self._caller_frame.f_trace = None
            self._caller_frame = None
            self._target = None
        if self.lines:
            for event in self._pending:
                event["step_seq"] = self.lines[-1]["seq"]
            self._pending.clear()
        self.status = "finished"
        for attempt in range(3):
            if self._try_flush():
                break
            time.sleep(0.3 * (attempt + 1))
        else:
            _say("[trace] warning: the trace page may still show RUNNING (final write failed)")
        return self.dir / f"{self.name}.json"

    def to_dict(self) -> dict[str, Any]:
        return {
            "lesson": self.lesson,
            "name": self.name,
            "status": self.status,
            "started": self.started.isoformat(timespec="seconds"),
            "sources": self.sources,
            "instrument_lines": self.instrument_lines,
            "lines": self.lines,
            "events": self.events,
        }

    def _flush(self) -> None:
        if not self._try_flush() and not self._warned:
            self._warned = True
            _say("[trace] warning: could not write trace files; the run continues")

    def _try_flush(self) -> bool:
        """Write the JSON and HTML files. Return False on failure instead of raising."""
        try:
            self.dir.mkdir(parents=True, exist_ok=True)
            data = self.to_dict()
            json_path = self.dir / f"{self.name}.json"
            html_path = json_path.with_suffix(".html")
            _write_atomic(json_path, json.dumps(data, ensure_ascii=False, indent=2, default=str))
            _write_atomic(html_path, render_html(data))
        except Exception:  # the agent must keep running even if the trace cannot be written
            return False
        if not self._announced:
            self._announced = True
            _say(f"[trace] open in a browser (reloads while running): {html_path}")
        return True
