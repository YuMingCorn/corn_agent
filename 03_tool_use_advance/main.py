"""03 - Advanced tool-use agent with a multi-turn chat loop using the OpenAI SDK."""

from __future__ import annotations

import sys
from typing import Any

from tools import TOOLS, execute_tool, get_schemas
from utils import get_logger, get_openai_client

human_logger = get_logger("HUMAN")
harness_logger = get_logger("HARNESS")
model_logger = get_logger("MODEL")

MAX_STEPS = 10
SYSTEM_PROMPT = (
    "You are a helpful assistant with access to local tools. "
    "Use the tools when you need to list, read, or write files, or run shell commands. "
    "All file paths are relative to the workspace folder. "
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
    human_logger.info(f"Submitted task: {task}")
    messages.append({"role": "user", "content": task})
    tool_schemas = get_schemas()

    for step in range(1, MAX_STEPS + 1):
        harness_logger.info(
            f"[Step {step}/{MAX_STEPS}] Sending {len(messages)} message(s) to model"
        )
        resp = client.chat.completions.create(
            model=model,
            messages=messages,
            tools=tool_schemas,
        )
        choice = resp.choices[0]
        msg = choice.message
        messages.append(msg.model_dump(exclude_none=True))

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
            return msg.content or ""

        model_logger.info(f"[Step {step}] Requested {len(msg.tool_calls)} tool call(s)")

        # Every tool call needs a matching "tool" message, or the API rejects the next request
        for call in msg.tool_calls:
            if call.type != "function":
                harness_logger.warning(
                    f"[Step {step}] Skipping unsupported tool call type: {call.type}"
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
            harness_logger.info(f"[Step {step}] Executing local tool: {name}")
            result = execute_tool(name, raw_args)
            harness_logger.info(
                f"[Step {step}] Appending tool '{name}' output ({len(result)} chars) to messages: "
                f"{_preview(result)}"
            )
            messages.append(
                {"role": "tool", "tool_call_id": call.id, "content": result}
            )

    harness_logger.warning(f"Stopped after reaching the {MAX_STEPS}-step limit")
    return f"(Stopped after reaching the {MAX_STEPS}-step limit.)"


def main() -> None:
    client, model = get_openai_client()
    harness_logger.info(
        f"Agent ready (model={model}, max_steps={MAX_STEPS}, tools={list(TOOLS)})"
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


if __name__ == "__main__":
    main()
