"""02 - Hello World：驗證 uv 環境與執行路時基礎邏輯."""

from __future__ import annotations


def hello(name: str) -> str:
    return f"Hello, {name}!"


def main() -> None:
    print(hello("World"))
    print(hello("uv"))
    print(hello("corn_agent"))


if __name__ == "__main__":
    main()
