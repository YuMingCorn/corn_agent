"""Tool registry: tool definitions, argument checks, path limits and output truncation.

Permission checks live in permissions.py. main.py calls them before `execute_tool`.
This file must not import permissions.py.
"""

from __future__ import annotations

import json
import os
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

from utils import get_logger

logger = get_logger("TOOLS")

MAX_OUTPUT = 8000
SHELL_TIMEOUT = 60
# Tools can only reach files under this folder, and shell commands run here.
WORKSPACE_ROOT = Path(__file__).resolve().parent
TOOLS: dict[str, dict[str, Any]] = {}


def tool(
    name: str,
    description: str,
    parameters: dict[str, Any],
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Register a tool. Its risk level is declared in permissions.py."""

    def decorator(func):
        TOOLS[name] = {
            "schema": {
                "type": "function",
                "function": {
                    "name": name,
                    "description": description,
                    "parameters": parameters,
                },
            },
            "func": func,
        }
        return func

    return decorator


def get_schemas():
    return [t["schema"] for t in TOOLS.values()]


def _params(**props):
    return {
        "type": "object",
        "properties": {
            k: {"type": "string", "description": v} for k, v in props.items()
        },
        "required": list(props),
    }


# Names that no tool may read or write. Compared case-insensitively.
DENIED_NAMES = {".git", ".venv"}
DENIED_PREFIX = ".env"  # covers .env, .env.local, and similar files


def is_denied_name(part: str) -> bool:
    lowered = part.casefold()
    return lowered in DENIED_NAMES or lowered.startswith(DENIED_PREFIX)


def safe_path(path: str) -> Path:
    """Resolve a path and check that it stays inside the workspace and avoids denied names."""
    target = (WORKSPACE_ROOT / path).resolve()
    if not target.is_relative_to(WORKSPACE_ROOT):
        raise PermissionError(f"path is outside the workspace: {path}")
    for part in target.relative_to(WORKSPACE_ROOT).parts:
        if is_denied_name(part):
            raise PermissionError(f"protected path is not allowed: {path}")
    return target


def _truncate(text: str) -> str:
    """Cut long output so it does not fill the model's context."""
    if len(text) <= MAX_OUTPUT:
        return text
    omitted = len(text) - MAX_OUTPUT
    return f"{text[:MAX_OUTPUT]}\n...[truncated, {omitted} characters omitted]"


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


@tool(
    "list_dir",
    "List files and subfolders in a directory (read-only)",
    _params(path="dir path, relative to the workspace folder"),
)
def list_dir(path: str):
    p = safe_path(path)
    if not p.is_dir():
        raise NotADirectoryError(f"not a directory: {path}")
    visible = [x for x in p.iterdir() if not is_denied_name(x.name)]
    return (
        "\n".join(sorted(x.name + ("/" if x.is_dir() else "") for x in visible))
        or "empty"
    )


@tool(
    "read_file",
    "Read the text content of a file (read-only)",
    _params(path="file path, relative to the workspace folder"),
)
def read_file(path: str):
    p = safe_path(path)
    if not p.is_file():
        raise FileNotFoundError(f"file not found: {path}")
    return p.read_text(encoding="utf-8")


@tool(
    "write_file",
    "Write a text file. Overwrites existing content.",
    _params(
        path="file path, relative to the workspace folder",
        content="full file content",
    ),
)
def write_file(path: str, content: str):
    p = safe_path(path)
    p.write_text(content, encoding="utf-8")
    return f"wrote {len(content)} characters to {path}"


@tool(
    "run_shell",
    "Run a shell command in the workspace folder. Requires user confirmation.",
    _params(command="shell command to run"),
)
def run_shell(command: str):
    # Remove credentials from the environment so the command cannot read them.
    env = {k: v for k, v in os.environ.items() if not _is_secret_env(k)}
    try:
        p = subprocess.run(
            command,
            shell=True,
            cwd=WORKSPACE_ROOT,
            env=env,
            capture_output=True,
            text=True,
            timeout=SHELL_TIMEOUT,
            check=False,
        )
    except subprocess.TimeoutExpired:
        logger.warning(f"command timed out after {SHELL_TIMEOUT} seconds: {command}")
        return f"command timed out after {SHELL_TIMEOUT} seconds."
    output = (p.stdout + p.stderr) or "(no output)"
    return f"exit code {p.returncode}\n{output}"


def _is_secret_env(key: str) -> bool:
    upper = key.upper()
    return upper.startswith("LLM_") or any(
        s in upper for s in ("KEY", "TOKEN", "SECRET", "PASSWORD")
    )


# ---------------------------------------------------------------------------
# Execution
# ---------------------------------------------------------------------------


def _validate_args(name: str, args: Any) -> str | None:
    """Check arguments against the tool's JSON Schema. Return an error message, or None if valid."""
    params = TOOLS[name]["schema"]["function"]["parameters"]
    if not isinstance(args, dict):
        return "arguments must be a JSON object"
    missing = [k for k in params["required"] if k not in args]
    if missing:
        return f"missing required argument(s): {', '.join(missing)}"
    unknown = [k for k in args if k not in params["properties"]]
    if unknown:
        return f"unknown argument(s): {', '.join(unknown)}"
    for key, value in args.items():
        if params["properties"][key]["type"] == "string" and not isinstance(value, str):
            return f"argument {key} must be a string"
    return None


def parse_args(name: str, raw_args: Any) -> tuple[dict[str, Any], str | None]:
    """Parse and validate the model's arguments. Return (args, None), or ({}, error text)."""
    if name not in TOOLS:
        return {}, f"Tool execution error: unknown tool {name!r}"
    if not isinstance(raw_args, str):
        return {}, "Tool execution error: arguments must be a JSON string"
    try:
        args = json.loads(raw_args or "{}")
    except json.JSONDecodeError as e:
        return {}, f"Tool execution error: arguments are not valid JSON ({e})"
    error = _validate_args(name, args)
    if error:
        logger.warning(f"argument validation failed for {name}: {error}")
        return {}, f"Tool execution error: {error}"
    return args, None


def execute_tool(name: str, args: dict[str, Any]) -> str:
    """Run a registered tool with checked arguments. Call it only after the permission check.
    Errors are returned as text so the model can recover."""
    try:
        result = TOOLS[name]["func"](**args)
    except Exception as e:  # noqa: BLE001 - report to the model so it can recover
        logger.error(f"tool {name} failed: {type(e).__name__}: {e}")
        return f"Tool execution error: {type(e).__name__}: {e}"

    logger.info(f"tool {name} finished ({len(str(result))} characters)")
    return _truncate(str(result))
