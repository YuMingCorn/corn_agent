"""Permission layer. Every tool call passes three gates before it runs.

1. Hard rules: fixed blocks. A human cannot override them.
2. Risk level: SAFE runs directly. DENY is always blocked. CONFIRM goes to gate 3.
3. Human confirmation: shows the full arguments and reads the answer (y / n / a).

Import direction is main -> permissions -> tools. tools.py must not import this file.
"""

from __future__ import annotations

import fnmatch
import json
import re
import sys
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from typing import Any

from tools import WORKSPACE_ROOT, safe_path

from utils import get_logger

logger = get_logger("PERMS")
human_logger = get_logger("HUMAN")


class Risk(Enum):
    SAFE = "safe"  # runs without asking
    CONFIRM = "confirm"  # asks the user first
    DENY = "deny"  # never runs


# A tool that is not in this table is treated as CONFIRM.
TOOL_RISK: dict[str, Risk] = {
    "list_dir": Risk.SAFE,
    "read_file": Risk.SAFE,
    "write_file": Risk.CONFIRM,
    "run_shell": Risk.CONFIRM,
}

# Tools for which the answer "a" (always allow for this session) is offered.
REMEMBERABLE = {"write_file"}

# Source files of this lesson. Tools may read them but never change them.
PROTECTED_FILES = {"main.py", "tools.py", "permissions.py"}


@dataclass
class Decision:
    allowed: bool
    reason: str = ""


# ask(name, args) -> (answer, note). answer is "y", "n" or "a". note is an optional reason.
AskFunc = Callable[[str, dict[str, Any]], tuple[str, str]]


# ---------------------------------------------------------------------------
# Gate 1: hard rules. They are checked before any risk level or prompt.
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
            r"|\bshutdown\b"
            r"|\bsudo\b"
            r"|\bmkfs\b"
            r"|\bdd\s+if="
            r"|:\(\)\s*\{"  # fork bomb
            r"|\b(curl|wget|iwr|invoke-webrequest)\b.*\|\s*(sh|bash|iex|invoke-expression)\b",
            re.IGNORECASE,
        ),
        "destructive command",
    ),
]
_PROTECTED_FILE_RE = re.compile(r"\b(main|tools|permissions)\.py\b", re.IGNORECASE)
_WRITE_RE = re.compile(
    r">|\b(del|erase|move|copy|ren|rename|remove-item|set-content|out-file|"
    r"add-content|tee|sed|mv|cp|rm|clear-content|"
    r"python|open|write_text|write_bytes)\b"
    r"|(^|[\s;&|])py\s",  # the py launcher, but not the .py in "main.py"
    re.IGNORECASE,
)
# A wildcard such as mai[n].py or *.py can name a protected file without spelling it out.
_WILDCARD_RE = re.compile(r"[*?\[]")


def _real_name(name: str) -> str:
    """Windows drops trailing dots and spaces from file names, so "main.py." is saved as
    "main.py". Compare names in that form, so the rules cannot be bypassed this way."""
    return name.rstrip(". ").casefold()


def _wildcard_hits_protected(command: str) -> bool:
    """True if a word with a wildcard could match a protected file name, such as *.py or
    mai[n].py. Words like 2*3 in python -c "print(2*3)" do not match, so they pass."""
    for word in re.split(r"[\s;&|<>()'\"=,]+", command):
        if _WILDCARD_RE.search(word):
            pattern = word.replace("\\", "/").rsplit("/", 1)[-1].casefold()
            if any(fnmatch.fnmatchcase(f, pattern) for f in PROTECTED_FILES):
                return True
    return False


def _hard_rule(name: str, args: dict[str, Any]) -> str | None:
    """Return the reason to block this call, or None if no hard rule applies."""
    if name == "run_shell":
        command = args["command"]
        for pattern, reason in _SHELL_RULES:
            if pattern.search(command):
                return f"command blocked by hard rule: {reason}"
        if _WRITE_RE.search(command) and (
            _PROTECTED_FILE_RE.search(command) or _wildcard_hits_protected(command)
        ):
            return "command could change a protected source file"
        return None

    if name in ("list_dir", "read_file", "write_file"):
        try:
            target = safe_path(args["path"])
        except PermissionError as e:
            return str(e)
        if (
            name == "write_file"
            and target.parent == WORKSPACE_ROOT
            and _real_name(target.name) in PROTECTED_FILES
        ):
            return f"writing {target.name} is not allowed (protected source file)"
    return None


def _is_root_python_file(name: str, args: dict[str, Any]) -> bool:
    """A .py file in the workspace root can shadow a module that main.py imports.
    Writing one always asks, even after the user chose "a"."""
    if name != "write_file":
        return False
    target = safe_path(args["path"])
    return target.parent == WORKSPACE_ROOT and _real_name(target.name).endswith(".py")


# ---------------------------------------------------------------------------
# Gate 3: what the user sees
# ---------------------------------------------------------------------------


def render_call(name: str, args: dict[str, Any]) -> str:
    """Show the real arguments, not the model's description of them. Nothing is cut off,
    so a dangerous part at the end of a long file cannot hide from the user."""
    if name == "run_shell":
        return f"  $ {args['command']}"
    if name == "write_file":
        exists = safe_path(args["path"]).exists()
        note = "overwrites an existing file" if exists else "creates a new file"
        return (
            f"  path: {args['path']} ({note}, {len(args['content'])} characters)\n"
            f"--- content start ---\n{args['content']}\n--- content end ---"
        )
    return f"  {json.dumps(args, ensure_ascii=False)}"


def ask_terminal(name: str, args: dict[str, Any]) -> tuple[str, str]:
    """Ask in the terminal. No terminal, EOF and Ctrl-C all count as a denial."""
    if not sys.stdin.isatty():
        return "n", "no interactive terminal, so nobody can confirm"
    allow_always = name in REMEMBERABLE and not _is_root_python_file(name, args)
    options = "[y] allow / [n] deny" + (
        " / [a] always allow this session" if allow_always else ""
    )
    try:
        print(f"\n[Confirm] The agent wants to run: {name}")
        print(render_call(name, args))
        while True:
            answer = input(f"{options} > ").strip().lower()
            if answer in ("y", "n") or (answer == "a" and allow_always):
                break
        note = (
            input("Reason for denial (optional, Enter to skip) > ").strip()
            if answer == "n"
            else ""
        )
    except (EOFError, KeyboardInterrupt):
        print()
        return "n", ""
    return answer, note


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


class PermissionManager:
    def __init__(self, ask: AskFunc | None = None) -> None:
        # Tools the user chose "a" for. Only lasts for this session.
        self.always_allowed: set[str] = set()
        # ask can be replaced, for example by a test that answers automatically.
        self.ask: AskFunc = ask or ask_terminal

    def check(self, name: str, args: dict[str, Any]) -> Decision:
        """Run the three gates. If any check raises an error, the call is denied."""
        try:
            decision = self._check(name, args)
        # KeyboardInterrupt is not an Exception, so name it too: Ctrl-C must deny, not crash.
        except (Exception, KeyboardInterrupt) as e:  # noqa: BLE001 - fail closed
            logger.error(f"permission check failed for {name}: {type(e).__name__}: {e}")
            return Decision(
                False,
                f"could not check permission ({type(e).__name__}: {e}). "
                "The action was not run. Do not retry the same action.",
            )
        if not decision.allowed:
            logger.warning(f"denied {name}: {decision.reason}")
        return decision

    def _check(self, name: str, args: dict[str, Any]) -> Decision:
        # Gate 1: hard rules. A human cannot override them, so nobody is asked.
        blocked = _hard_rule(name, args)
        if blocked:
            return Decision(
                False, f"{blocked}. This action is not allowed. Do not retry it."
            )

        # Gate 2: risk level.
        risk = TOOL_RISK.get(name, Risk.CONFIRM)
        if risk is Risk.DENY:
            return Decision(False, f"tool {name} is disabled by policy.")
        if risk is Risk.SAFE:
            return Decision(True)
        if name in self.always_allowed and not _is_root_python_file(name, args):
            human_logger.info(f"Auto-approved {name} (always allowed this session)")
            return Decision(True)

        # Gate 3: human confirmation.
        return self._confirm(name, args)

    def _confirm(self, name: str, args: dict[str, Any]) -> Decision:
        answer, note = self.ask(name, args)
        if (
            answer == "a"
            and name in REMEMBERABLE
            and not _is_root_python_file(name, args)
        ):
            self.always_allowed.add(name)
            human_logger.info(f"Approved {name} and every later {name} in this session")
            return Decision(True)
        if answer == "y":
            human_logger.info(f"Approved {name}")
            return Decision(True)
        human_logger.warning(f"Denied {name}" + (f" (reason: {note})" if note else ""))
        message = "The user denied this action."
        if note:
            message += f" Reason: {note}."
        message += (
            " Do not retry the same action. Try a different approach, "
            "or tell the user what you want to do and why."
        )
        return Decision(False, message)
