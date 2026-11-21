# 03 - 進階工具呼叫（Tool Use Advance）

本章節延續 `02_tool_use` 的最小 Agent 迴圈，進一步探索更貼近實務場景的進階工具呼叫機制（例如更嚴謹的參數驗證、工具安全邊界、多工具協作與錯誤恢復策略）。

## 學習目標

- [ ] 強化工具定義與參數驗證（例如使用更完整的 JSON Schema / Pydantic 驗證）
- [ ] 加入工具安全邊界與權限控制（例如檔案讀寫路徑限制、指令白名單或確認機制）
- [ ] 處理多步驟 / 平行工具呼叫與進階錯誤恢復策略
- [ ] 改善執行過程的可觀測性（日誌記錄、步驟追蹤與上下文長度控管）

## 使用環境與套件

- 套件：`openai`、`python-dotenv`
- 共用模組：[utils/llm.py](../utils/llm.py)（`get_llm_config`、`get_openai_client`）、[utils/logger.py](../utils/logger.py)（`logger`）
- 本地端模型：見根目錄 `.env`（`LLM_MODEL`）

## 執行方式

使用預設任務執行：

```powershell
uv run python 03_tool_use_advance/main.py
```

或是透過命令列傳入自訂任務：

```powershell
uv run python 03_tool_use_advance/main.py "Your task here"
```

## 核心概念與實作筆記

（在此記錄進階工具設計、安全策略、錯誤處理與 Agent 迴圈改進重點）

## 觀察與心得

（在此記錄本地端模型在進階工具呼叫上的表現、踩坑經驗與後續改進方向）
