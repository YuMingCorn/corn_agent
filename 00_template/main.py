"""練習範本進入點。"""

from utils.llm import get_llm_config


def main() -> None:
    cfg = get_llm_config()
    print(f"Base URL: {cfg.base_url}")
    print(f"Model:    {cfg.model}")


if __name__ == "__main__":
    main()
