"""本地端 LLM 連線設定工具（支援 OpenAI SDK 與 LangChain / LangGraph）。"""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from openai import OpenAI

load_dotenv()


@dataclass(frozen=True)
class LLMConfig:
    base_url: str
    api_key: str
    model: str


def get_llm_config(model: str | None = None) -> LLMConfig:
    """從環境變數讀取本地端模型設定。"""
    return LLMConfig(
        base_url=os.getenv("LLM_BASE_URL", "http://localhost:11434/v1"),
        api_key=os.getenv("LLM_API_KEY", "ollama"),
        model=model or os.getenv("LLM_MODEL", "qwen2.5:7b"),
    )


def get_openai_client(
    model: str | None = None,
    timeout: float = 60.0,
) -> tuple[OpenAI, str]:
    """建立指向本地端 OpenAI 相容端點的 OpenAI Client，並回傳 (client, model)。

    timeout 為等待伺服器回應的秒數，超過時會拋出例外，避免輸入有誤時無限等待。
    """
    cfg = get_llm_config(model=model)
    client = OpenAI(base_url=cfg.base_url, api_key=cfg.api_key, timeout=timeout)
    return client, cfg.model


def get_chat_model(
    model: str | None = None,
    temperature: float = 0.0,
) -> ChatOpenAI:
    """建立供 LangChain / LangGraph 使用的本地端 ChatOpenAI 實例。"""
    cfg = get_llm_config(model=model)
    return ChatOpenAI(
        base_url=cfg.base_url,
        api_key=cfg.api_key,
        model=cfg.model,
        temperature=temperature,
    )
