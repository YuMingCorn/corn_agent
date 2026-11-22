"""Tool registry with a permission layer.

Every tool call goes through three gates in `execute_tool`:
1. Hard rules: fixed blocks. A human cannot override them.
2. Risk level: LOW runs directly. MEDIUM and HIGH need a human answer.
3. Human confirmation: shows the full arguments and reads the answer.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

from utils import get_logger

logger = get_logger("TOOLS")
human_logger = get_logger("HUMAN")

MAX_OUTPUT = 8000
SHELL_TIMEOUT = 60
# Tools can only reach files under this folder, and shell commands run here.
WORKSPACE_ROOT = Path(__file__).resolve().parent
TOOLS: dict[str, dict[str, Any]] = {}

# Risk levels
LOW = "LOW"  # runs without asking
MEDIUM = "MEDIUM"  # asks the user to type "y"
HIGH = "HIGH"  # asks the user to type "yes"

# A risk is either a fixed level, or a function that decides the level from the arguments.
RiskSpec = str | Callable[[dict[str, Any]], str]


def tool(
    name: str,
    description: str,
    parameters: dict[str, Any],
    risk: RiskSpec = HIGH,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Register a tool. A tool without a declared risk defaults to HIGH."""

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
            "risk": risk,
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
# Source files of this lesson. Tools may read them but never change them.
PROTECTED_FILES = {"main.py", "tools.py"}


def _is_denied_name(part: str) -> bool:
    lowered = part.casefold()
    return lowered in DENIED_NAMES or lowered.startswith(DENIED_PREFIX)


def _safe_path(path: str) -> Path:
    """Resolve a path and check that it stays inside the workspace and avoids denied names."""
    target = (WORKSPACE_ROOT / path).resolve()
    if not target.is_relative_to(WORKSPACE_ROOT):
        raise PermissionError(f"path is outside the workspace: {path}")
    for part in target.relative_to(WORKSPACE_ROOT).parts:
        if _is_denied_name(part):
            raise PermissionError(f"protected path is not allowed: {path}")
    return target


def _truncate(text: str) -> str:
    """Cut long output so it does not fill the model's context."""
    if len(text) <= MAX_OUTPUT:
        return text
    omitted = len(text) - MAX_OUTPUT
    return f"{text[:MAX_OUTPUT]}\n...[truncated, {omitted} characters omitted]"


# ---------------------------------------------------------------------------
# Hard rules: checked before any risk level or prompt. They cannot be confirmed.
# This is a set of pattern checks, not a sandbox. It blocks common dangerous forms only.
# ---------------------------------------------------------------------------

_SHELL_RULES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\.\."), "parent-directory reference (..)"),
    (
        re.compile(r"\.env\b|\.git\b|\.venv\b", re.IGNORECASE),
        "protected name (.env, .git, .venv)",
    ),
    (
        re.compile(
            r"llm_|api[_-]?key|(?<![a-z])(token|secret|password)(?![a-z])",
            re.IGNORECASE,
        ),
        "credential-related name",
    ),
    (
        re.compile(r"\benv:|(^|[&|;])\s*(set|env|printenv)\s*($|[&|;])", re.IGNORECASE),
        "environment variable dump",
    ),
    (
        re.compile(
            r"\b(del|erase|rd|rmdir)\b.*/[sq]\b"
            r"|\brm\b.*\s-[a-z]*r"
            r"|remove-item.*-recurse"
            r"|\bformat\s+[a-z]:"
            r"|\breg\s+delete\b"
            r"|\bdiskpart\b"
            r"|\bshutdown\b",
            re.IGNORECASE,
        ),
        "destructive command",
    ),
]
_PROTECTED_FILE_RE = re.compile(r"\b(main|tools)\.py\b", re.IGNORECASE)
_WRITE_RE = re.compile(
    r">|\b(del|erase|move|copy|ren|rename|remove-item|set-content|out-file|"
    r"add-content|tee|sed|mv|cp|rm|clear-content)\b",
    re.IGNORECASE,
)


def _hard_rule(name: str, args: dict[str, Any]) -> str | None:
    """Return the reason to block this call, or None if no hard rule applies."""
    if name == "run_shell":
        command = args["command"]
        for pattern, reason in _SHELL_RULES:
            if pattern.search(command):
                return f"command blocked by hard rule: {reason}"
        if _PROTECTED_FILE_RE.search(command) and _WRITE_RE.search(command):
            return "command would change a protected source file (main.py or tools.py)"
        return None

    if name in ("list_dir", "read_file", "write_file"):
        try:
            target = _safe_path(args["path"])
        except PermissionError as e:
            return str(e)
        if (
            name == "write_file"
            and target.parent == WORKSPACE_ROOT
            and target.name.casefold() in PROTECTED_FILES
        ):
            return f"writing {target.name} is not allowed (protected source file)"
    return None


# ---------------------------------------------------------------------------
# Risk levels
# ---------------------------------------------------------------------------


def _write_risk(args: dict[str, Any]) -> str:
    """Creating a new file is MEDIUM. Overwriting an existing file is HIGH.
    A new .py file in the workspace root is HIGH, because Python may import it from there."""
    target = _safe_path(args["path"])
    if target.parent == WORKSPACE_ROOT and target.suffix.casefold() == ".py":
        return HIGH
    return HIGH if target.exists() else MEDIUM


def _risk_of(name: str, args: dict[str, Any]) -> str:
    risk = TOOLS[name]["risk"]
    return risk(args) if callable(risk) else risk


# ---------------------------------------------------------------------------
# Human confirmation
# ---------------------------------------------------------------------------


def _describe(name: str, args: dict[str, Any]) -> str:
    """Build the full text shown to the user. Nothing is cut off."""
    if name == "write_file":
        exists = _safe_path(args["path"]).exists()
        note = "overwrites an existing file" if exists else "creates a new file"
        return (
            f"write_file: {args['path']} ({note}, {len(args['content'])} characters)\n"
            f"--- content start ---\n{args['content']}\n--- content end ---"
        )
    if name == "run_shell":
        return f"run_shell: {args['command']}"
    return f"{name}: {json.dumps(args, ensure_ascii=False)}"


def _confirm(name: str, args: dict[str, Any], risk: str) -> bool:
    """Ask the user. EOF and Ctrl-C count as a denial."""
    expected = "yes" if risk == HIGH else "y"
    hint = (
        "Type 'yes' to allow, anything else denies"
        if risk == HIGH
        else "Allow? Type 'y' to allow, anything else denies"
    )
    print(f"\n[Confirm] tool={name} risk={risk}\n{_describe(name, args)}")
    try:
        answer = input(f"{hint}: ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print()
        answer = ""

    approved = answer == expected
    if approved:
        human_logger.info(f"Approved {name} (risk={risk})")
    else:
        human_logger.warning(f"Denied {name} (risk={risk})")
    return approved


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


@tool(
    "list_dir",
    "List files and subfolders in a directory (read-only)",
    _params(path="dir path, relative to the workspace folder"),
    risk=LOW,
)
def list_dir(path: str):
    p = _safe_path(path)
    if not p.is_dir():
        raise NotADirectoryError(f"not a directory: {path}")
    visible = [x for x in p.iterdir() if not _is_denied_name(x.name)]
    return "\n".join(sorted(x.name + ("/" if x.is_dir() else "") for x in visible)) or "empty"


@tool(
    "read_file",
    "Read the text content of a file (read-only)",
    _params(path="file path, relative to the workspace folder"),
    risk=LOW,
)
def read_file(path: str):
    p = _safe_path(path)
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
    risk=_write_risk,
)
def write_file(path: str, content: str):
    p = _safe_path(path)
    p.write_text(content, encoding="utf-8")
    return f"wrote {len(content)} characters to {path}"


@tool(
    "run_shell",
    "Run a shell command in the workspace folder. Requires user confirmation.",
    _params(command="shell command to run"),
    risk=HIGH,
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


DENIED_MESSAGE = (
    "The user denied this action. Do not retry the same action. "
    "Ask the user, or try a different approach that does not need it."
)


def execute_tool(name: str, raw_args: str) -> str:
    """Run a registered tool after the permission gates. Errors are returned as text so the model can recover."""
    if name not in TOOLS:
        return f"Tool execution error: unknown tool {name!r}"
    if not isinstance(raw_args, str):
        return "Tool execution error: arguments must be a JSON string"
    try:
        args = json.loads(raw_args or "{}")
    except json.JSONDecodeError as e:
        return f"Tool execution error: arguments are not valid JSON ({e})"

    error = _validate_args(name, args)
    if error:
        logger.warning(f"argument validation failed for {name}: {error}")
        return f"Tool execution error: {error}"

    # Gates 1 to 3 run inside the try block. If any check fails, the action is denied, never run.
    try:
        # Gate 1: hard rules. Checked before any prompt.
        blocked = _hard_rule(name, args)
        if blocked:
            logger.warning(f"hard rule blocked {name}: {blocked}")
            return (
                f"Tool execution error: {blocked}. "
                "This action is not allowed. Do not retry it."
            )

        # Gates 2 and 3: risk level, then human confirmation when needed.
        risk = _risk_of(name, args)
        if risk != LOW and not _confirm(name, args, risk):
            return DENIED_MESSAGE
    except Exception as e:  # noqa: BLE001 - fail closed
        logger.error(f"permission check failed for {name}: {type(e).__name__}: {e}")
        return (
            f"Tool execution error: could not check permission ({type(e).__name__}: {e}). "
            "The action was not run. Do not retry the same action."
        )

    try:
        result = TOOLS[name]["func"](**args)
    except Exception as e:  # noqa: BLE001 - report to the model so it can recover
        logger.error(f"tool {name} failed: {type(e).__name__}: {e}")
        return f"Tool execution error: {type(e).__name__}: {e}"

    logger.info(f"tool {name} finished ({len(str(result))} characters)")
    return _truncate(str(result))
