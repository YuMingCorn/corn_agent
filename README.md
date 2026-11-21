# Corn Agent - AI Agent 練習紀錄

本專案用於系統化記錄 AI Agent 的學習與實作練習，使用 **本地端模型（Local LLM）** 搭配 **OpenAI SDK**、**LangGraph** 等工具，並透過 **uv** 管理 Python 環境。

---

## 專案結構

```text
corn_agent/
├── README.md                    # 專案總覽與練習進度追蹤（本檔案）
├── pyproject.toml               # uv 專案設定與共用相依套件
├── uv.lock                      # uv 鎖定檔
├── .env.example                 # 本地端模型連線設定範本
├── .env                         # 個人本機設定（不進 Git）
├── utils/                       # 共用工具模組（本地端 LLM 連線、日誌工具等）
│   ├── llm.py
│   └── logger.py
├── 00_template/                 # 新增練習用的資料夾範本
│   ├── README.md
│   └── main.py
├── 01_local_llm_connection/     # 練習 01：本地端模型連線驗證
│   ├── README.md
│   └── main.py
└── 02_tool_use/                 # 練習 02：工具呼叫與最小 Agent 迴圈
    ├── README.md
    └── main.py
```

---

## 練習進度追蹤

> 狀態標記：`⬜ 未開始` | `🔄 進行中` | `✅ 已完成`

| 編號 | 練習主題 | 使用工具 / 框架 | 狀態 | 資料夾 |
| :--- | :--- | :--- | :---: | :--- |
| 01 | 本地端模型連線驗證（OpenAI SDK & LangChain） | `openai`, `langchain-openai` | ✅ 已完成 | [01_local_llm_connection](./01_local_llm_connection/README.md) |
| 02 | 工具呼叫與最小 Agent 迴圈（Tool Use） | `openai` | ✅ 已完成 | [02_tool_use](./02_tool_use/README.md) |
| 03 | 結構化輸出（Structured Output） | `openai`, `pydantic` | ⬜ 未開始 | - |
| 04 | 手刻 ReAct Agent 迴圈 | `openai` | ⬜ 未開始 | - |
| 05 | LangGraph 基礎：State、Node、Edge | `langgraph` | ⬜ 未開始 | - |
| 06 | LangGraph 搭配 ToolNode 與條件路由 | `langgraph` | ⬜ 未開始 | - |
| 07 | LangGraph 記憶與 Checkpointer | `langgraph` | ⬜ 未開始 | - |
| 08 | Human-in-the-loop / Multi-Agent 協作 | `langgraph` | ⬜ 未開始 | - |

---

## 環境建置與使用方式

### 1. 安裝相依套件

確認已安裝 [uv](https://docs.astral.sh/uv/)，在專案根目錄執行：

```powershell
uv sync
```

### 2. 設定本地端模型

複製 `.env.example` 為 `.env`，並填入本地端推理服務的位址與模型名稱：

```powershell
Copy-Item .env.example .env
```

常見本地端服務的 OpenAI 相容端點：

| 服務 | 預設 `LLM_BASE_URL` | 範例 `LLM_MODEL` |
| :--- | :--- | :--- |
| **Ollama** | `http://localhost:11434/v1` | `qwen2.5:7b`, `llama3.1:8b` |
| **LM Studio** | `http://localhost:1234/v1` | 依 LM Studio 載入的模型 ID |
| **vLLM / llama.cpp** | `http://localhost:8000/v1` | 依啟動時指定的模型名稱 |

### 3. 執行練習

```powershell
uv run python 01_local_llm_connection/main.py
```

### 4. 新增下一次練習

1. 複製 `00_template/` 並以編號命名（例如 `02_structured_output/`）。
2. 填寫該資料夾內的 `README.md` 與程式碼。
3. 更新本檔案的「練習進度追蹤」表格。
4. 若需要額外套件，使用 `uv add <package-name>` 安裝。
