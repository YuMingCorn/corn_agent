# 01 - 本地端模型連線驗證

## 學習目標

- [x] 確認本地端模型服務（Ollama / LM Studio 等）的 OpenAI 相容 API 可正常連線
- [x] 使用 `openai` 套件完成一次基本對話請求
- [x] 使用 `langchain-openai`（後續供 `langgraph` 使用）完成一次基本對話請求

## 使用環境與套件

- 套件：`openai`、`langchain-openai`、`python-dotenv`
- 設定：專案根目錄 `.env`（參考 `.env.example`）

## 執行方式

```powershell
uv run python 01_local_llm_connection/main.py
```

## 核心概念與實作筆記

本地端推理服務大多提供 OpenAI 相容的 REST API（`/v1/chat/completions`），因此只要設定 `base_url` 與本地端已載入的 `model` 名稱，即可無縫銜接 `openai` SDK 與 `langgraph` 生態系。

共用連線邏輯已封裝在 [utils/llm.py](../utils/llm.py)，後續練習可直接匯入使用。

## 觀察與心得

- （執行後可在此記錄使用的本地端模型、回應速度與注意事項）
