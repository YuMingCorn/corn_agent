"""進階工具定義：註冊、參數驗證、路徑與指令安全邊界、輸出截斷。"""

from __future__ import annotations

import json
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

from utils import get_logger

logger = get_logger("TOOLS")

MAX_OUTPUT = 8000
SHELL_TIMEOUT = 60
# 工具只能存取 main.py 所在目錄（工作區）以內的檔案，指令也在此目錄執行
WORKSPACE_ROOT = Path(__file__).resolve().parent
TOOLS: dict[str, dict[str, Any]] = {}


def tool(
    name: str, description: str, parameters: dict[str, Any]
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """decorater"""

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


DENIED_NAMES = {".git", ".env", ".venv"}


def _safe_path(path: str) -> Path:
    """將路徑解析為絕對路徑，並確認它位於工作區內且不含禁止的名稱。"""
    target = (WORKSPACE_ROOT / path).resolve()
    if not target.is_relative_to(WORKSPACE_ROOT):
        raise PermissionError(f"路徑超出工作區範圍：{path}")
    relative_parts = target.relative_to(WORKSPACE_ROOT).parts
    if DENIED_NAMES.intersection(relative_parts):
        raise PermissionError(f"禁止存取受保護的路徑：{path}")
    return target


def _truncate(text: str) -> str:
    """把過長的輸出截斷，避免撐爆模型的上下文。"""
    if len(text) <= MAX_OUTPUT:
        return text
    omitted = len(text) - MAX_OUTPUT
    return f"{text[:MAX_OUTPUT]}\n...[已截斷，省略 {omitted} 個字元]"


@tool(
    "list_dir",
    "列出目錄底下文件與子目錄",
    _params(path="dir path, relative to the workspace folder"),
)
def list_dir(path: str):
    p = _safe_path(path)
    if not p.is_dir():
        raise NotADirectoryError(f"不是目錄：{path}")
    visible = [x for x in p.iterdir() if x.name not in DENIED_NAMES]
    return "\n".join(sorted(x.name + ("/" if x.is_dir() else "") for x in visible)) or "empty"


@tool(
    "read_file",
    "讀取文字檔內容",
    _params(path="file path, relative to the workspace folder"),
)
def read_file(path: str):
    p = _safe_path(path)
    if not p.is_file():
        raise FileNotFoundError(f"找不到檔案：{path}")
    return p.read_text(encoding="utf-8")


@tool(
    "write_file",
    "寫入文字檔（會覆寫既有內容）",
    _params(
        path="file path, relative to the workspace folder",
        content="full file content",
    ),
)
def write_file(path: str, content: str):
    p = _safe_path(path)
    p.write_text(content, encoding="utf-8")
    return f"已寫入 {len(content)} 個字元到 {path}"


@tool(
    "run_shell",
    "在工作區目錄執行 shell 指令（需使用者確認）",
    _params(command="shell command to run"),
)
def run_shell(command: str):
    logger.warning(f"請求執行 shell 指令：{command}")
    answer = input(f"\n[Confirm] 執行指令：{command}\n確認執行？(y/n): ")
    if answer.strip().lower() != "y":
        logger.warning(f"使用者拒絕執行指令：{command}")
        return "使用者拒絕執行此指令。"
    try:
        p = subprocess.run(
            command,
            shell=True,
            cwd=WORKSPACE_ROOT,
            capture_output=True,
            text=True,
            timeout=SHELL_TIMEOUT,
            check=False,
        )
    except subprocess.TimeoutExpired:
        logger.warning(f"指令逾時（{SHELL_TIMEOUT} 秒）：{command}")
        return f"指令逾時（{SHELL_TIMEOUT} 秒）。"
    output = (p.stdout + p.stderr) or "(no output)"
    return f"exit code {p.returncode}\n{output}"


def _validate_args(name: str, args: Any) -> str | None:
    """依工具的 JSON Schema 檢查參數，回傳錯誤訊息；通過則回傳 None。"""
    params = TOOLS[name]["schema"]["function"]["parameters"]
    if not isinstance(args, dict):
        return "參數必須是 JSON 物件"
    missing = [k for k in params["required"] if k not in args]
    if missing:
        return f"缺少必要參數：{', '.join(missing)}"
    unknown = [k for k in args if k not in params["properties"]]
    if unknown:
        return f"未知參數：{', '.join(unknown)}"
    for key, value in args.items():
        if params["properties"][key]["type"] == "string" and not isinstance(value, str):
            return f"參數 {key} 必須是字串"
    return None


def execute_tool(name: str, raw_args: str) -> str:
    """依名稱執行已註冊的工具。所有錯誤都轉成文字回傳，讓模型可以自行修正。"""
    if name not in TOOLS:
        return f"Tool execution error: 未知工具 {name!r}"
    if not isinstance(raw_args, str):
        return "Tool execution error: 參數必須是 JSON 字串"
    try:
        args = json.loads(raw_args or "{}")
    except json.JSONDecodeError as e:
        return f"Tool execution error: 參數不是合法 JSON（{e}）"

    error = _validate_args(name, args)
    if error:
        logger.warning(f"工具 {name} 參數驗證失敗：{error}")
        return f"Tool execution error: {error}"

    try:
        result = TOOLS[name]["func"](**args)
    except Exception as e:  # noqa: BLE001 - 回報給模型，讓它可以恢復
        logger.error(f"工具 {name} 執行失敗：{type(e).__name__}: {e}")
        return f"Tool execution error: {type(e).__name__}: {e}"

    logger.info(f"工具 {name} 執行完成（{len(str(result))} 字元）")
    return _truncate(str(result))
