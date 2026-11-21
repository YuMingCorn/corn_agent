"""02 - Minimal tool-use agent loop using the OpenAI SDK."""

from __future__ import annotations

import json
import subprocess
import sys
from collections.abc import Callable
from typing import Any

from utils import get_openai_client, logger

MAX_STEPS = 10
SYSTEM = (
    "You are a helpful coding assistant with access to local tools. "
    "Use the provided tools when needed to inspect files, modify files, or run shell commands, "
    "and respond clearly once the task is complete."
)
DEFAULT_TASK = (
    "List the files in the current directory and summarize what this project does."
)


def read_file(path: str) -> str:
    with open(path, mode="r", encoding="utf-8") as f:
        return f.read()


def write_file(path: str, content: str) -> str:
    with open(path, mode="w", encoding="utf-8") as f:
        f.write(content)
    return f"Wrote {len(content)} characters to {path}"


def run_shell(command: str) -> str:
    confirm = input(f"\n[Confirm] Run command: {command}\nProceed? (y/n): ")
    if confirm.strip().lower() != "y":
        return "Command execution declined by user."
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
    client, model = get_openai_client()

    messages: list[Any] = [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": task},
    ]

    for step in range(1, MAX_STEPS + 1):
        resp = client.chat.completions.create(
            model=model,
            messages=messages,
            tools=TOOLS,
        )
        msg = resp.choices[0].message
        messages.append(msg.model_dump(exclude_none=True))

        # No tool calls means the model considers the task complete
        if not msg.tool_calls:
            print(f"\n[Done in {step} step(s)]\n{msg.content}")
            return

        # Execute each requested tool call and feed the result back as a tool message
        for call in msg.tool_calls:
            if call.type != "function":
                continue
            name = call.function.name
            logger.info(f"[Step {step}] {name}({call.function.arguments[:80]})")
            try:
                args = json.loads(call.function.arguments)
                result = TOOL_FUNCS[name](**args)
            except Exception as e:  # noqa: BLE001 - report tool errors back to the model so it can recover
                result = f"Tool execution error: {type(e).__name__}: {e}"
            messages.append(
                {"role": "tool", "tool_call_id": call.id, "content": result}
            )

    logger.info(f"\n[Stopped after reaching the {MAX_STEPS}-step limit]")


if __name__ == "__main__":
    task_arg = sys.argv[1] if len(sys.argv) >= 2 else DEFAULT_TASK
    main(task_arg)
