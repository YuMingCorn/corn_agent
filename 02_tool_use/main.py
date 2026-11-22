"""02 - Minimal tool-use agent loop using the OpenAI SDK."""

from __future__ import annotations

import json
import subprocess
import sys
from collections.abc import Callable
from typing import Any

from utils import get_logger, get_openai_client
from utils.trace_recorder import Recorder

human_logger = get_logger("HUMAN")
harness_logger = get_logger("HARNESS")
model_logger = get_logger("MODEL")
recorder = Recorder("02_tool_use")

MAX_STEPS = 10
SYSTEM = (
    "You are a helpful coding assistant with access to local tools. "
    "Use the provided tools when needed to inspect files, modify files, or run shell commands, "
    "and respond clearly once the task is complete."
)
DEFAULT_TASK = (
    "List the files in the current directory and summarize what this project does."
)


def _preview(text: str, limit: int = 120) -> str:
    """將多行文字壓縮成單行預覽，方便日誌閱讀。"""
    single_line = " ".join(text.splitlines()).strip()
    if len(single_line) <= limit:
        return single_line
    return f"{single_line[:limit]}..."


def read_file(path: str) -> str:
    with open(path, mode="r", encoding="utf-8") as f:
        return f.read()


def write_file(path: str, content: str) -> str:
    with open(path, mode="w", encoding="utf-8") as f:
        f.write(content)
    return f"Wrote {len(content)} characters to {path}"


def run_shell(command: str) -> str:
    harness_logger.info(f"Requesting human confirmation for shell command: {command}")
    confirm = input(f"\n[Confirm] Run command: {command}\nProceed? (y/n): ")
    if confirm.strip().lower() != "y":
        human_logger.warning(f"Declined shell command: {command}")
        return "Command execution declined by user."
    human_logger.info(f"Approved shell command: {command}")
    try:
        p = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
    except subprocess.TimeoutExpired:
        harness_logger.warning(f"Shell command timed out (60s): {command}")
        return "Command timed out (60s)."
    return (p.stdout + p.stderr)[
        -4000:
    ] or "(no output)"  # Truncate to avoid overflowing context


TOOL_FUNCS: dict[str, Callable[..., str]] = {
    "read_file": read_file,
    "write_file": write_file,
    "run_shell": run_shell,
}


def _tool(name: str, desc: str, props: dict[str, str]) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": desc,
            "parameters": {
                "type": "object",
                "properties": {
                    k: {"type": "string", "description": v} for k, v in props.items()
                },
                "required": list(props),
            },
        },
    }


TOOLS: list[Any] = [
    _tool("read_file", "Read the contents of a file.", {"path": "Path to the file"}),
    _tool(
        "write_file",
        "Write content to a file (overwrites existing content).",
        {"path": "Path to the file", "content": "Full file content"},
    ),
    _tool(
        "run_shell",
        "Execute a shell command and return its output.",
        {"command": "Shell command to execute"},
    ),
]


def main(task: str) -> None:
    code = "main.py:main"
    recorder.trace_lines(__file__)  # record each statement of this file, step by step
    client, model = get_openai_client()
    harness_logger.info(
        f"Starting agent loop (model={model}, max_steps={MAX_STEPS}, tools={list(TOOL_FUNCS)})"
    )
    human_logger.info(f"Submitted task: {task}")
    recorder.start_task(task, code=code)

    messages: list[Any] = [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": task},
    ]

    for step in range(1, MAX_STEPS + 1):
        harness_logger.info(
            f"[Step {step}/{MAX_STEPS}] Sending {len(messages)} message(s) to model"
        )
        recorder.model_input(step, messages, TOOLS, code=code)
        resp = client.chat.completions.create(
            model=model,
            messages=messages,
            tools=TOOLS,
        )
        msg = resp.choices[0].message
        messages.append(msg.model_dump(exclude_none=True))
        recorder.event(
            "MODEL",
            code,
            f"Responded (tool calls={len(msg.tool_calls or [])})",
            step=step,
            detail=msg.content,
        )

        if msg.content:
            model_logger.info(f"[Step {step}] Response: {_preview(msg.content)}")

        # No tool calls means the model considers the task complete
        if not msg.tool_calls:
            model_logger.info(f"[Step {step}] No tool calls -> returning final answer")
            harness_logger.info(f"Agent finished in {step} step(s)")
            recorder.event("HARNESS", code, "Task finished, final answer returned", step=step)
            print(f"\n[Done in {step} step(s)]\n{msg.content}")
            return

        model_logger.info(
            f"[Step {step}] Requested {len(msg.tool_calls)} tool call(s)"
        )

        # Execute each requested tool call and feed the result back as a tool message
        for call in msg.tool_calls:
            if call.type != "function":
                harness_logger.warning(
                    f"[Step {step}] Skipping unsupported tool call type: {call.type}"
                )
                recorder.event(
                    "HARNESS", code,
                    f"Skipped unsupported tool call type {call.type!r}",
                    step=step, level="warning",
                )
                continue
            name = call.function.name
            raw_args = call.function.arguments
            model_logger.info(
                f"[Step {step}] Tool call -> {name}({_preview(raw_args)})"
            )
            recorder.event(
                "MODEL", code, f"Requested tool call {name}",
                step=step, detail=raw_args,
            )
            harness_logger.info(f"[Step {step}] Executing local tool: {name}")
            recorder.event("HARNESS", code, f"Executing local tool {name}", step=step)
            try:
                args = json.loads(raw_args)
                result = TOOL_FUNCS[name](**args)
            except Exception as e:  # noqa: BLE001 - report tool errors back to the model so it can recover
                harness_logger.error(
                    f"[Step {step}] Tool '{name}' failed: {type(e).__name__}: {e}"
                )
                recorder.event(
                    "TOOLS", code, f"Tool '{name}' failed: {type(e).__name__}: {e}",
                    step=step, level="error",
                )
                result = f"Tool execution error: {type(e).__name__}: {e}"
            harness_logger.info(
                f"[Step {step}] Appending tool '{name}' output ({len(result)} chars) to messages: "
                f"{_preview(result)}"
            )
            recorder.event(
                "HARNESS", code,
                f"Appending result of {name} to messages ({len(result)} characters)",
                step=step, detail=result,
            )
            messages.append(
                {"role": "tool", "tool_call_id": call.id, "content": result}
            )

    harness_logger.warning(f"Stopped after reaching the {MAX_STEPS}-step limit")
    recorder.event("HARNESS", code, f"Stopped after {MAX_STEPS}-step limit", level="warning")


if __name__ == "__main__":
    task_arg = sys.argv[1] if len(sys.argv) >= 2 else DEFAULT_TASK
    try:
        main(task_arg)
    finally:
        # Mark the run as finished so the HTML page stops reloading and becomes a replay player.
        json_path = recorder.finish()
        try:
            print(f"Trace view: {json_path.with_suffix('.html')}")
        except Exception:  # a console that cannot show the path must not hide the real result
            pass
