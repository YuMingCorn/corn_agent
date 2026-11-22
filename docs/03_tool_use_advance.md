# 03 - 進階工具呼叫（Tool Use Advance）

本章節延續 `02_tool_use` 的最小 Agent 迴圈，加入工具參數驗證、工作區路徑邊界、輸出截斷與多回合對話。模型仍透過原生 `openai` SDK 呼叫，但工具的註冊與執行邏輯集中在 `tools.py`。

## 學習目標

- [x] 強化工具定義與參數驗證（以工具的 JSON Schema 檢查必要參數、未知參數與字串型別）
- [x] 加入工具安全邊界與權限控制（檔案路徑限制在工作區內、禁止存取 `.git` / `.env` / `.venv`、`run_shell` 需使用者確認）
- [ ] 處理多步驟 / 平行工具呼叫與進階錯誤恢復策略（多步驟與錯誤回報已完成；平行工具呼叫尚未實作）
- [x] 改善執行過程的可觀測性（`HUMAN`、`HARNESS`、`MODEL`、`TOOLS` 四組日誌與 token 用量）

## 使用環境與套件

- 套件：`openai`、`python-dotenv`
- 共用模組：[utils/llm.py](../utils/llm.py)（`get_openai_client`）、[utils/logger.py](../utils/logger.py)（`get_logger`）
- 工具模組：`03_tool_use_advance/tools.py`（工具註冊、參數驗證、路徑檢查、輸出截斷）
- 本地端模型：見根目錄 `.env`（`LLM_MODEL`）

## 執行方式

進入互動模式，可以連續輸入多個任務，模型會保留前面的對話內容。輸入 `exit` 或 `quit` 結束：

```powershell
uv run python 03_tool_use_advance/main.py
```

或是只傳入一個任務，執行完後直接結束：

```powershell
uv run python 03_tool_use_advance/main.py "List the files in the workspace folder and summarize them."
```

## 工具清單

| 工具名稱 | 說明 | 參數 | 安全限制 |
| :--- | :--- | :--- | :--- |
| `list_dir` | 列出目錄內的檔案與子目錄 | `path` | 只能存取工作區內的目錄，隱藏 `.git` / `.env` / `.venv` |
| `read_file` | 讀取文字檔內容 | `path` | 同上，且必須是既有檔案 |
| `write_file` | 寫入文字檔（覆寫既有內容） | `path`、`content` | 同上 |
| `run_shell` | 在工作區目錄執行 shell 指令 | `command` | 執行前需輸入 `y` 確認，60 秒逾時 |

工作區是 `tools.py` 所在的資料夾（`03_tool_use_advance/`）。所有路徑都以此資料夾為基準解析。

## 系統角色與執行流程圖

模型本身不會直接讀寫檔案或執行指令。外層的 **Harness** 負責維護對話紀錄、送出請求、執行工具並回傳結果。高風險的 shell 指令則由 **Human** 確認。

| 角色（Logger 名稱） | 負責工作 |
| :--- | :--- |
| **`HUMAN`**（人類） | 輸入任務，或以命令列傳入任務；在 `run_shell` 執行前輸入 `y` / `n` 確認。 |
| **`HARNESS`**（Agent 外層迴圈） | 維護 `messages`、控制 `MAX_STEPS = 10` 上限、送出 API 請求、依序執行 `tool_calls`，並把結果以 `role: "tool"` 回傳給模型。 |
| **`MODEL`**（本地端 LLM） | 決定要呼叫哪個工具與參數（`tool_calls`），或在資訊足夠時產出最終回答。 |
| **`TOOLS`**（工具層） | 檢查工具名稱與參數、執行路徑檢查、執行工具、截斷過長輸出，並記錄失敗原因。 |

### 主流程圖（對話與 Agent 迴圈）

```mermaid
flowchart TD
    Start(["啟動 main()"]) --> Init["建立 OpenAI client，建立 system 訊息"]
    Init --> Mode{"命令列有傳入任務？"}
    Mode -- "是" --> Once["run_task：執行單一任務"]
    Mode -- "否" --> Prompt["等待 User input"]
    Prompt --> Quit{"輸入 exit 或 quit？"}
    Quit -- "是" --> End(["結束 Session"])
    Quit -- "否" --> Empty{"輸入為空？"}
    Empty -- "是" --> Prompt
    Empty -- "否" --> Once
    Once --> Append["把 user 訊息加入 messages"]
    Append --> Step["HARNESS：送出 messages 與工具 schema"]
    Step --> Resp["MODEL：回傳 assistant 訊息"]
    Resp --> Save["把 assistant 訊息加入 messages"]
    Save --> HasTools{"有 tool_calls？"}
    HasTools -- "否" --> Answer["回傳最終回答"]
    Answer --> Mode2{"互動模式？"}
    Mode2 -- "是" --> Prompt
    Mode2 -- "否（單次任務）" --> End
    HasTools -- "是" --> Loop["逐一處理每個 tool_call"]
    Loop --> IsFunc{"type 是 function？"}
    IsFunc -- "否" --> ErrMsg["加入錯誤的 tool 訊息"]
    IsFunc -- "是" --> Exec["呼叫 execute_tool（見下方流程圖）"]
    Exec --> ToolMsg["把結果加入 messages（role = tool）"]
    ErrMsg --> More{"還有下一個 tool_call？"}
    ToolMsg --> More
    More -- "是" --> Loop
    More -- "否" --> Limit{"已達 MAX_STEPS？"}
    Limit -- "否" --> Step
    Limit -- "是" --> Stop["回傳步數上限訊息"]
    Stop --> Mode2
```

### `execute_tool` 執行流程圖

```mermaid
flowchart TD
    A(["execute_tool(name, raw_args)"]) --> B{"工具名稱已註冊？"}
    B -- "否" --> E1["回傳 Tool execution error：未知工具"]
    B -- "是" --> C{"raw_args 是合法 JSON？"}
    C -- "否" --> E2["回傳 Tool execution error：JSON 解析失敗"]
    C -- "是" --> D{"_validate_args 通過？"}
    D -- "否" --> E3["回傳錯誤：缺少參數、未知參數或型別錯誤"]
    D -- "是" --> F["呼叫工具函式"]
    F --> G{"檔案工具：_safe_path 通過？"}
    G -- "否" --> E4["拋出 PermissionError，回傳錯誤文字"]
    G -- "是" --> H{"工具為 run_shell？"}
    H -- "是" --> I{"使用者輸入 y？"}
    I -- "否" --> R1["回傳：使用者拒絕執行此指令"]
    I -- "是" --> J["在工作區執行指令（60 秒逾時）"]
    H -- "否" --> K["執行讀取、列出或寫入"]
    F -. "任何例外" .-> E5["回傳 Tool execution error：例外類型與訊息"]
    J --> L["_truncate：超過 8000 字元時截斷"]
    K --> L
    L --> M(["回傳結果給 HARNESS"])
    E1 --> M
    E2 --> M
    E3 --> M
    E4 --> M
    E5 --> M
    R1 --> M
```

### 時序圖（誰在什麼時候做什麼）

```mermaid
sequenceDiagram
    actor Human as HUMAN (人類)
    participant Harness as HARNESS (Agent 迴圈)
    participant Model as MODEL (本地端 LLM)
    participant Tools as TOOLS (execute_tool)

    Human->>Harness: 輸入任務（互動模式或命令列參數）

    loop 最多 MAX_STEPS = 10 步
        Harness->>Model: 傳送 messages + 工具 schema
        Model-->>Harness: 回傳 assistant 訊息

        alt 模型回傳 tool_calls
            loop 逐一處理每個 tool_call
                Harness->>Tools: execute_tool(name, raw_args)
                Tools->>Tools: 檢查名稱、解析 JSON、驗證參數
                opt 工具為 run_shell
                    Tools->>Human: 顯示 [Confirm] 指令並詢問「確認執行？(y/n)」
                    Human-->>Tools: 核准 (y) 或拒絕 (n)
                end
                Tools-->>Harness: 回傳結果或錯誤文字（截斷至 8000 字元）
                Harness->>Harness: 將結果加入 messages（role = tool）
            end
        else 無 tool_calls（任務完成）
            Harness->>Human: 輸出最終回答，等待下一個任務
        end
    end
```

### 日誌閱讀方式

程式內建四組 Logger。下方是實際執行 `"List the files in the workspace folder, then read the first 5 lines of main.py..."` 的日誌節錄（時間戳與長行已省略）：

```text
HARNESS | Agent ready (model=gemini-4-hydrogen, max_steps=10, tools=['list_dir', 'read_file', 'write_file', 'run_shell'])
HUMAN   | Submitted task: List the files in the workspace folder, then read the first 5 lines of main.py...
HARNESS | [Step 1/10] Sending 2 message(s) to model
MODEL   | [Step 1] finish_reason=tool_calls
MODEL   | [Step 1] Tokens: prompt=383, completion=22
MODEL   | [Step 1] Requested 1 tool call(s)
MODEL   | [Step 1] Tool call -> list_dir({"path":"."})
HARNESS | [Step 1] Executing local tool: list_dir
TOOLS   | 工具 list_dir 執行完成（29 字元）
HARNESS | [Step 1] Appending tool 'list_dir' output (29 chars) to messages: __pycache__/ main.py tools.py
HARNESS | [Step 2/10] Sending 4 message(s) to model
MODEL   | [Step 2] Tool call -> read_file({"path":"main.py"})
HARNESS | [Step 2] Executing local tool: read_file
TOOLS   | 工具 read_file 執行完成（4974 字元）
HARNESS | [Step 3/10] Sending 6 message(s) to model
MODEL   | [Step 3] finish_reason=stop
MODEL   | [Step 3] No tool calls -> returning final answer
HARNESS | Task finished in 3 step(s)
```

`TOOLS` 這組日誌目前仍是 `tools.py` 中的中文訊息。`main.py` 的訊息已改為英文。

## 核心概念與實作筆記

1. **工具註冊與 Schema 封裝**：
   - `tools.py` 用 `@tool(...)` 裝飾器把工具登記在 `TOOLS` 字典中，`get_schemas()` 會把所有工具轉成 OpenAI Function Calling 格式。
   - 新增工具只需要寫一個函式並加上裝飾器，`main.py` 不必修改。
2. **多回合 Agent 迴圈**：
   - `messages` 在互動模式中跨任務保留，因此後續任務可以參考前面的內容。
   - 若模型沒有回傳 `tool_calls`，代表任務完成；若有，則逐一執行並以 `role: "tool"` 回傳結果，每個 `tool_call_id` 都必須有對應的 tool 訊息，否則 API 會拒絕下一次請求。
   - `MAX_STEPS = 10` 防止無窮迴圈。達到上限時，回傳提示訊息並等待下一個任務。
3. **安全邊界**：
   - `_safe_path` 把路徑解析為絕對路徑，確認它位於工作區內，並拒絕 `.git`、`.env`、`.venv`。
   - `run_shell` 在工作區目錄執行，執行前需使用者輸入 `y`，並有 60 秒逾時保護。
4. **錯誤回報與輸出控管**：
   - 工具發生錯誤時，錯誤文字會回傳給模型，讓模型自行修正。
   - 工具輸出超過 8000 字元時會截斷，並標示省略的字元數，避免撐爆上下文。
   - 目前沒有裁剪舊的對話紀錄，長對話仍會累積上下文。

## 觀察與心得

- 已用本地端模型完成一次端到端測試：模型依序呼叫 `list_dir` 與 `read_file`，共 3 步完成，最終回答正確列出檔案並說明 `main.py` 的用途。
- 以 PowerShell 管線傳入 `exit` 時，輸入會帶有 BOM（`﻿`），導致無法辨識為結束指令。直接在終端機輸入 `exit` 不會發生這個問題。
- 尚未實作：平行工具呼叫、對話紀錄裁剪，以及把 `tools.py` 的中文日誌與錯誤訊息改為英文。

## 執行紀錄與 HTML 頁面

本課的主迴圈也會寫執行紀錄，並產生可在瀏覽器打開的 HTML 頁面。執行中頁面每 2 秒更新，結束後可以回放。紀錄放在專案根目錄的 `traces/<課名>/`。說明見 [04 的執行紀錄章節](./04_permission.md#執行紀錄與視覺化)。

