"""03 - Advanced tool-use agent template."""

from __future__ import annotations

import sys

from utils import get_llm_config, logger

MAX_STEPS = 10
DEFAULT_TASK = "Describe the next advanced tool-use task to implement."


def main(task: str) -> None:
    cfg = get_llm_config()
    logger.info(f"Base URL: {cfg.base_url} | Model: {cfg.model}")
    logger.info(f"Task: {task}")
    # TODO: Implement advanced tool definitions, validation, and agent loop.


if __name__ == "__main__":
    task_arg = sys.argv[1] if len(sys.argv) >= 2 else DEFAULT_TASK
    main(task_arg)
