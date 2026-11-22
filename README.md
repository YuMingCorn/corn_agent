# Corn Agent - AI Agent 循序漸進教學

本專案是一套 AI Agent 的實作教學。每一課都在前一課的基礎上增加一種能力。你可以照著本文件的步驟，從安裝環境開始，一路做到最後一課。

程式使用 **OpenAI 相容的模型端點**（本地端或雲端皆可），並以 **uv** 管理 Python 環境。

---

## 這份教學適合誰

- 會寫基本的 Python（函式、字串、讀寫檔案）。
- 會使用終端機。本文的指令以 **Windows PowerShell** 為例。macOS 或 Linux 使用者只需要改用對應的 shell 語法。
- 能取得一個 OpenAI 相容的模型端點，例如 Ollama 或 Google Gemini 的 OpenAI 相容 API。

## 學習路線總覽

| 順序 | 課程 | 你會學到什麼 |
| :---: | :--- | :--- |
| 1 | [01 本地端模型連線驗證](./docs/01_local_llm_connection.md) | 如何讓程式連上模型，並確認能收到回應。 |
| 2 | [02 工具呼叫與最小 Agent 迴圈](./docs/02_tool_use.md) | 模型如何呼叫工具，程式如何把結果回傳給模型。 |
| 3 | [03 進階工具呼叫](./docs/03_tool_use_advance.md) | 工具參數驗證、工作區路徑限制、多回合對話與詳細日誌。 |
| 4 | [04 權限控制](./docs/04_permission.md) | 硬性規則、風險等級與人工確認，為工具呼叫加上安全閘門。 |
| 5 以後 | 見[練習進度追蹤](#練習進度追蹤) | 上下文管理等後續課程。尚未開始。 |

請依序完成。後面的課程會直接使用前面課程的程式與觀念。

---

## 步驟 1：安裝 uv 與相依套件

1. 依 [uv 官方文件](https://docs.astral.sh/uv/) 安裝 uv。
2. 安裝後重新開啟終端機，確認 uv 可以使用：

   ```powershell
   uv --version
   ```

3. 在專案根目錄執行，安裝所有相依套件：

   ```powershell
   uv sync
   ```

**完成標準**：指令結束後沒有錯誤訊息。`uv` 會自動建立 `.venv/` 虛擬環境，你不需要手動啟用它。

---

## 步驟 2：建立 `.env` 並設定模型端點

`.env` 是你自己的設定檔，裡面會放端點位址、金鑰與模型名稱。它已被 Git 忽略，不會被提交。

1. 從範本複製一份：

   ```powershell
   Copy-Item .env.example .env
   ```

2. 用編輯器打開 `.env`，設定以下三項：

   | 變數 | 說明 | 範例 |
   | :--- | :--- | :--- |
   | `LLM_BASE_URL` | OpenAI 相容端點的位址 | `http://localhost:11434/v1`（Ollama） |
   | `LLM_API_KEY` | 金鑰。本地端通常不驗證，但不能是空字串 | `ollama` |
   | `LLM_MODEL` | 端點上已存在的模型名稱 | `qwen2.5:7b` |

   常見的端點設定：

   | 服務 | 預設 `LLM_BASE_URL` | 範例 `LLM_MODEL` |
   | :--- | :--- | :--- |
   | **Ollama**（本地端） | `http://localhost:11434/v1` | `qwen2.5:7b`、`llama3.1:8b` |
   | **LM Studio**（本地端） | `http://localhost:1234/v1` | 依 LM Studio 載入的模型 ID |
   | **vLLM / llama.cpp**（本地端） | `http://localhost:8000/v1` | 依啟動時指定的模型名稱 |
   | **Google Gemini**（雲端） | `https://generativelanguage.googleapis.com/v1beta/openai/` | 例如 `gemini-flash-lite-latest` |

3. 若要選擇模型，可以先查詢端點的模型清單。模型回應速度差很多，建議用同一個簡單問題比較幾個模型，選最快且穩定的一個。

**注意**：雲端端點需要真正的 API 金鑰，請勿把金鑰寫進程式碼或提交到 Git。

`.env` 其他可選的變數如下：

| 變數 | 預設值 | 說明 |
| :--- | :--- | :--- |
| `LOG_LEVEL` | `INFO` | 日誌等級：`DEBUG` / `INFO` / `WARNING` / `ERROR` / `CRITICAL` |
| `LOG_FILE` | 未設定 | 設定後，日誌也會寫入此檔案（例如 `logs/corn_agent.log`） |
| `LOG_COLOR` | 依終端自動判斷 | 設為 `0`、`false`、`no` 或 `off` 可關閉彩色輸出 |
| `NO_COLOR` | 未設定 | 只要設定此變數（任何值）即關閉彩色輸出 |

---

## 步驟 3：驗證連線（練習 01）

執行：

```powershell
uv run python 01_local_llm_connection/main.py
```

**預期看到**：程式先印出目前的 `Base URL` 與 `Model`，再依序完成「原生 `openai` SDK」與「`langchain-openai`」兩組測試，並印出模型的回應。

**如果失敗**：先看本文件最下方的[常見問題](#常見問題)。大多數問題出在 `.env` 的位址、金鑰或模型名稱。

完成本步驟後，後面所有課程都可以使用同一組設定。

---

## 步驟 4：理解最小 Agent 迴圈（練習 02）

1. 先閱讀 [docs/02_tool_use.md](./docs/02_tool_use.md) 的「系統角色與執行流程圖」。
2. 執行預設任務：

   ```powershell
   uv run python 02_tool_use/main.py
   ```

   或是自己指定任務：

   ```powershell
   uv run python 02_tool_use/main.py "List the files in the current directory and summarize them."
   ```

3. 當模型要執行 shell 指令時，終端會顯示 `Proceed? (y/n)`。輸入 `y` 允許執行，輸入 `n` 拒絕。

**預期看到**：日誌依序出現 `HUMAN`、`HARNESS`、`MODEL` 三種角色的訊息。最後印出 `[Done in N step(s)]` 與最終回答。

**動手試試**：提出一個需要讀取檔案的任務，例如「讀取 `README.md` 前 10 行並說明」，觀察模型先呼叫哪個工具。

---

## 步驟 5：進階工具呼叫（練習 03）

1. 先閱讀 [docs/03_tool_use_advance.md](./docs/03_tool_use_advance.md)，特別是「主流程圖」與「`execute_tool` 執行流程圖」。
2. 啟動互動模式。它會保留前面的對話，直到你輸入 `exit` 或 `quit`：

   ```powershell
   uv run python 03_tool_use_advance/main.py
   ```

3. 依序輸入下列任務，每輸入一個就按 Enter，等待回應後再輸入下一個：

   - `List the files in the workspace folder.`（列出工作區的檔案）
   - `Read the first 5 lines of main.py and explain them.`（讀取 `main.py` 前 5 行並說明）
   - `Read ../README.md.`（嘗試讀取工作區以外的檔案）

4. 輸入 `exit` 結束。

**預期看到**：

- 前兩個任務會正常呼叫 `list_dir`、`read_file`。
- 第三個任務如果讓模型去讀取工作區以外的路徑，程式會擋下，日誌會出現 `路徑超出工作區範圍` 的錯誤，模型會看到這個錯誤並回報給你。模型也可能選擇不嘗試，這時請改用更明確的指令再試一次。

**也可以單次執行**：傳入命令列參數，執行完一個任務就結束：

```powershell
uv run python 03_tool_use_advance/main.py "List the files in the workspace folder."
```

**注意**：03 目前不支援平行工具呼叫，每一步只執行一個工具。

---

## 步驟 6：權限控制（練習 04）

1. 先閱讀 [docs/04_permission.md](./docs/04_permission.md)，特別是「三道閘門」與「執行流程圖」。
2. 啟動互動模式，並依序輸入下列任務。每個任務都會遇到不同等級的檢查：

   - `Create a file named hello.txt containing the text: hi`（新建檔案，風險 `MEDIUM`，出現 `Allow? Type 'y'` 時輸入 `y`）
   - `Show me the contents of the .env file in the parent folder.`（讀取 `..` 的檔案，被硬性規則擋下，不會出現確認提示）
   - `Run the command: dir`（執行指令，風險 `HIGH`，必須輸入 `yes` 才會執行）

3. 輸入 `exit` 結束，然後刪除練習產生的 `hello.txt`。

**預期看到**：
- 第一個任務出現 `[Confirm] tool=write_file risk=MEDIUM`，輸入 `y` 後寫入檔案。
- 第二個任務的 `cat ../.env` 會出現 `hard rule blocked`，這一次不會出現確認提示。之後模型可能改試其他指令。若出現確認提示，輸入 `n`。
- 第三個任務輸入 `yes` 才會執行，其他回答都會被拒絕。

**注意**：`uv run python 04_permission/main.py` 必須在可以互動的終端機執行。用管線傳入任務時，確認會讀到 EOF，被視為拒絕。

---

## 步驟 7：新增下一課

1. 複製 `00_template/` 並以編號命名，例如 `05_context_management/`。
2. 在 `docs/` 新增同名的說明文件，例如 `docs/05_context_management.md`，內容可參考 [docs/00_template.md](./docs/00_template.md)。
3. 撰寫程式。若需要額外套件，執行 `uv add <package-name>`。
4. 更新本檔案的[練習進度追蹤](#練習進度追蹤)表格。

---

## 練習進度追蹤

> 狀態標記：`⬜ 未開始` | `🔄 進行中` | `✅ 已完成`

| 編號 | 練習主題 | 使用工具 / 框架 | 狀態 | 說明文件 |
| :--- | :--- | :--- | :---: | :--- |
| 01 | 本地端模型連線驗證（OpenAI SDK & LangChain） | `openai`, `langchain-openai` | ✅ 已完成 | [01_local_llm_connection](./docs/01_local_llm_connection.md) |
| 02 | 工具呼叫與最小 Agent 迴圈（Tool Use） | `openai` | ✅ 已完成 | [02_tool_use](./docs/02_tool_use.md) |
| 03 | 進階工具呼叫（Tool Use Advance） | `openai` | ✅ 已完成 | [03_tool_use_advance](./docs/03_tool_use_advance.md) |
| 04 | 權限控制（Permission） | `openai` | 🔄 進行中 | [04_permission](./docs/04_permission.md) |
| 05 | 上下文管理（Context Management） | `openai` | ⬜ 未開始 | - |
| 06 | LangGraph 基礎：State、Node、Edge | `langgraph` | ⬜ 未開始 | - |
| 07 | LangGraph 搭配 ToolNode 與條件路由 | `langgraph` | ⬜ 未開始 | - |
| 08 | LangGraph 記憶與 Checkpointer | `langgraph` | ⬜ 未開始 | - |
| 09 | Human-in-the-loop / Multi-Agent 協作 | `langgraph` | ⬜ 未開始 | - |

---

## 專案結構

```text
corn_agent/
├── README.md                    # 教學總覽與操作步驟（本檔案）
├── pyproject.toml               # uv 專案設定與共用相依套件
├── uv.lock                      # uv 鎖定檔
├── .env.example                 # 模型端點設定範本
├── .env                         # 個人設定與金鑰（不進 Git）
├── docs/                        # 所有練習的說明文件
│   ├── 00_template.md           # 新增練習時的說明文件範本
│   ├── 01_local_llm_connection.md
│   ├── 02_tool_use.md
│   ├── 03_tool_use_advance.md
│   └── 04_permission.md
├── utils/                       # 共用工具模組
│   ├── __init__.py              # 統一匯出 get_logger、logger、get_openai_client 等
│   ├── llm.py                   # 讀取 .env，建立 OpenAI / LangChain 用戶端
│   └── logger.py                # 日誌設定（彩色輸出、檔案輪替）
├── 00_template/                 # 新增練習用的程式範本
│   └── main.py
├── 01_local_llm_connection/     # 練習 01：模型連線驗證
│   └── main.py
├── 02_tool_use/                 # 練習 02：工具呼叫與最小 Agent 迴圈
│   ├── main.py
│   └── hello_world.py           # uv 環境檢查用的小範例
├── 03_tool_use_advance/         # 練習 03：進階工具呼叫
│   ├── main.py                  # 互動式 Agent 主程式
│   └── tools.py                 # 工具註冊、參數驗證、路徑限制、輸出截斷
└── 04_permission/               # 練習 04：權限控制（進行中）
    ├── main.py                  # 互動式 Agent 主程式（含權限提示）
    └── tools.py                 # 硬性規則、風險等級、人工確認、工具執行
```

---

## 常見問題

| 現象 | 可能原因與處理方式 |
| :--- | :--- |
| `uv: command not found` | 尚未安裝 uv，或安裝後沒有重新開啟終端機。 |
| `Connection refused` 或連線逾時 | 本地端服務未啟動，或 `LLM_BASE_URL` 的連接埠錯誤。`get_openai_client()` 預設逾時為 60 秒。 |
| `404` 或 `model not found` | `LLM_MODEL` 與端點上的模型名稱不一致。請先查詢端點的模型清單，再修改 `.env`。 |
| `503` 或 `UNAVAILABLE` | 端點上的模型暫時無法使用。請改用其他模型，或稍後再試。 |
| 模型回應很慢 | 換成較小、較快的模型，並用同一個問題比較回應時間。 |
| 找不到 `.env` 的設定，仍使用預設值 | 尚未從 `.env.example` 複製出 `.env`，或檔案不在專案根目錄。 |
| 執行 `run_shell` 時出現 `EOFError`（03） | 這代表程式無法讀取 `y/n` 的確認輸入。請在可以互動的終端機執行，不要用管線（`|`）傳入任務。04 起，無法讀取確認輸入會被視為拒絕，不會出現 `EOFError`。 |
| 用管線傳入 `exit` 沒有結束程式 | PowerShell 管線會在開頭加上 BOM（`﻿`）。直接在終端機輸入 `exit` 即可。 |
| 日誌沒有寫入檔案 | 未設定 `LOG_FILE`，或路徑無法建立。 |
