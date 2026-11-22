# 01 - 本地端模型連線驗證

本章節用於驗證本地端 LLM 服務的連線與基本對話功能，確認 `openai` SDK 與 `langchain-openai`（同步與串流輸出）皆能正常呼叫本地端模型，作為後續 Agent 練習的基礎環境檢查。

## 學習目標

- [x] 確認本地端模型服務（Ollama / LM Studio 等）的 OpenAI 相容 API 可正常連線
- [x] 使用 `openai` 套件完成一次基本對話請求（`client.chat.completions.create`）
- [x] 使用 `langchain-openai`（後續供 `langgraph` 使用）完成同步呼叫（`invoke`）與串流輸出（`stream`）

## 使用環境與套件

- 套件：`openai`、`langchain-openai`、`python-dotenv`
- 共用模組：[utils/llm.py](../utils/llm.py)（`get_llm_config`、`get_openai_client`、`get_chat_model`）
- 設定：專案根目錄 `.env`（參考 `.env.example`）

## 執行方式

```powershell
uv run python 01_local_llm_connection/main.py
```

## 核心概念與實作筆記

1. **OpenAI 相容端點**：本地端推理服務大多提供 OpenAI 相容的 REST API（`/v1/chat/completions`），只要設定 `LLM_BASE_URL` 與已載入的 `LLM_MODEL`，即可無縫銜接 `openai` SDK 與 `langgraph` 生態系。
2. **雙介面驗證**：
   - `test_openai_sdk()`：透過 `get_openai_client()` 驗證原生 OpenAI SDK 對話請求。
   - `test_langchain_chat_model()`：透過 `get_chat_model()` 驗證 `ChatOpenAI` 的一般回應（`invoke`）與即時串流輸出（`stream`）。
3. **共用封裝**：連線設定與初始化邏輯已封裝在 [utils/llm.py](../utils/llm.py)，後續練習可直接匯入使用。
   - `get_openai_client()` 預設等待回應的逾時為 60 秒（`timeout` 參數），避免服務沒有回應時程式無限等待。

## 觀察與心得

- 已完成本地端模型連線驗證，確認 OpenAI SDK 與 LangChain 介面皆可正常運作。
