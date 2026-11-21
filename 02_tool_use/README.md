# 02 - 工具呼叫與最小 Agent 迴圈（Tool Use）

## 學習目標

- [x] 定義本地端工具函式（`read_file`、`write_file`、`run_shell`）與 OpenAI Function Calling Schema
- [x] 使用 `openai` SDK 實作最小多步驟 Tool-Use Agent 迴圈（含步數上限與錯誤回饋）
- [x] 在執行 `run_shell` 工具前加入人工確認（Human-in-the-loop）、逾時保護與輸出截斷

## 使用環境與套件

- 套件：`openai`、`python-dotenv`
- 共用模組：[utils/llm.py](../utils/llm.py)（`get_openai_client`）、[utils/logger.py](../utils/logger.py)（`logger`）
- 本地端模型：見根目錄 `.env`（`LLM_MODEL`）

## 執行方式

使用預設任務執行：

```powershell
uv run python 02_tool_use/main.py
```

或是透過命令列傳入自訂任務：

```powershell
uv run python 02_tool_use/main.py "List files in the workspace and summarize the project."
```

## 核心概念與實作筆記

1. **工具定義與 Schema 封裝**：
   - 提供 `read_file`、`write_file`、`run_shell` 三個基礎工具，並以 `_tool()` 輔助函式產生符合 OpenAI Function Calling 格式的 `TOOLS` 清單。
2. **最小 Agent 迴圈**：
   - 每次迭代呼叫 `client.chat.completions.create(..., tools=TOOLS)`，將模型回應加入 `messages`。
   - 若模型未回傳 `tool_calls`，代表任務完成並輸出最終結果；若有 `tool_calls`，則依序執行對應工具，並以 `{"role": "tool", "tool_call_id": ..., "content": ...}` 將結果回饋給模型。
   - 設定 `MAX_STEPS = 10` 防止無窮迴圈。
3. **安全與容錯設計**：
   - `run_shell` 執行前需由使用者輸入 `y` 確認，並設定 60 秒逾時與輸出截斷（僅保留最後 4000 字元避免撐爆上下文）。
   - 工具執行發生例外時不會直接中斷程式，而是將錯誤訊息回傳給模型，讓模型有機會自行修正。

## 觀察與心得

- 已完成實作與本地端執行驗證（包含工具呼叫與檔案操作測試）。
