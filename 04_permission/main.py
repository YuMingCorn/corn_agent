"""04 - Tool-use agent with a permission layer (hard rules, risk levels, human confirmation)."""

from __future__ import annotations

import sys
from typing import Any

from tools import TOOLS, execute_tool, get_schemas, recorder
from utils import get_logger, get_openai_client

human_logger = get_logger("HUMAN")
harness_logger = get_logger("HARNESS")
model_logger = get_logger("MODEL")

MAX_STEPS = 10
SYSTEM_PROMPT = (
    "You are a helpful assistant with access to local tools. "
    "Use the tools when you need to list, read, or write files, or run shell commands. "
    "All file paths are relative to the workspace folder. "
    "If a tool result says an action was blocked or denied, do not retry the same action. "
    "When the task is complete, reply with a clear final answer."
)


def _preview(text: str | None, limit: int = 120) -> str:
    """Compress multi-line text into a single-line preview for readable logs."""
    single_line = " ".join((text or "").splitlines()).strip()
    if len(single_line) <= limit:
        return single_line
    return f"{single_line[:limit]}..."


def run_task(
    client: Any, model: str, task: str, messages: list[dict[str, Any]]
) -> str:
    """Run the agent loop for one user task.

    `messages` holds the whole conversation and is updated in place,
    so later turns can refer to earlier ones.
    """
    code = "main.py:run_task"
    human_logger.info(f"Submitted task: {task}")
    recorder.start_task(task, code=code)
    messages.append({"role": "user", "content": task})
    tool_schemas = get_schemas()

    for step in range(1, MAX_STEPS + 1):
        harness_logger.info(
            f"[Step {step}/{MAX_STEPS}] Sending {len(messages)} message(s) to model"
        )
        recorder.model_input(step, messages, tool_schemas, code=code)
        resp = client.chat.completions.create(
            model=model,
            messages=messages,
            tools=tool_schemas,
        )
        choice = resp.choices[0]
        msg = choice.message
        messages.append(msg.model_dump(exclude_none=True))
        recorder.event(
            "MODEL",
            code,
            f"Responded (finish_reason={choice.finish_reason}, "
            f"tool calls={len(msg.tool_calls or [])})",
            step=step,
            detail=msg.content,
        )

        model_logger.info(f"[Step {step}] finish_reason={choice.finish_reason}")
        if resp.usage is not None:
            model_logger.info(
                f"[Step {step}] Tokens: prompt={resp.usage.prompt_tokens}, "
                f"completion={resp.usage.completion_tokens}"
            )
        if msg.content:
            model_logger.info(f"[Step {step}] Response: {_preview(msg.content)}")

        # No tool calls means the model considers the task complete
        if not msg.tool_calls:
            model_logger.info(f"[Step {step}] No tool calls -> returning final answer")
            harness_logger.info(f"Task finished in {step} step(s)")
            recorder.event("HARNESS", code, "Task finished, final answer returned", step=step)
            return msg.content or ""

        model_logger.info(f"[Step {step}] Requested {len(msg.tool_calls)} tool call(s)")

        # Every tool call needs a matching "tool" message, or the API rejects the next request
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
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.id,
                        "content": f"Tool execution error: unsupported tool call type {call.type!r}",
                    }
                )
                continue

            name = call.function.name
            raw_args = call.function.arguments or "{}"
            model_logger.info(f"[Step {step}] Tool call -> {name}({_preview(raw_args)})")
            recorder.event(
                "MODEL", code, f"Requested tool call {name}",
                step=step, detail=raw_args,
            )
            harness_logger.info(f"[Step {step}] Executing local tool: {name}")
            recorder.event("HARNESS", code, f"Executing tool {name} through execute_tool", step=step)
            result = execute_tool(name, raw_args)
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
    return f"(Stopped after reaching the {MAX_STEPS}-step limit.)"


def main() -> None:
    recorder.trace_lines(__file__)  # record each statement of this file, step by step
    try:
        _run_session()
    finally:
        # Mark the run as finished so the HTML page stops reloading and becomes a replay player.
        json_path = recorder.finish()
        try:
            print(f"Trace view: {json_path.with_suffix('.html')}")
        except Exception:  # a console that cannot show the path must not hide the real result
            pass


def _run_session() -> None:
    client, model = get_openai_client()
    harness_logger.info(
        f"Agent ready (model={model}, max_steps={MAX_STEPS}, tools={list(TOOLS)})"
    )
    recorder.event(
        "HARNESS", "main.py:_run_session",
        f"Agent ready (model={model}, max_steps={MAX_STEPS}, tools={list(TOOLS)})",
    )
    messages: list[dict[str, Any]] = [{"role": "system", "content": SYSTEM_PROMPT}]

    # One-shot mode: pass a task on the command line, then exit
    if len(sys.argv) >= 2:
        print(run_task(client, model, sys.argv[1], messages))
        return

    # Interactive mode: keep the conversation until the user types exit or quit
    while True:
        try:
            question = input("\nUser input: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if question.lower() in ("exit", "quit"):
            break
        if not question:
            continue
        answer = run_task(client, model, question, messages)
        print(f"\nAssistant: {answer}")

    harness_logger.info("Session ended")
    recorder.event("HARNESS", "main.py:_run_session", "Session ended")


if __name__ == "__main__":
    main()
