"""01 - 驗證本地端模型連線（OpenAI SDK 與 LangChain ChatOpenAI）。"""

from utils.llm import get_chat_model, get_llm_config, get_openai_client


def test_openai_sdk() -> None:
    print("=== 1. 測試 OpenAI SDK ===")
    client, model = get_openai_client()
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": "你是一個簡潔的 AI 助手，請用繁體中文回答。"},
            {"role": "user", "content": "用一句話介紹什麼是 AI Agent。"},
        ],
        temperature=0.2,
    )
    print(response.choices[0].message.content)


def test_langchain_chat_model() -> None:
    print("\n=== 2. 測試 LangChain ChatOpenAI (LangGraph 用) ===")
    llm = get_chat_model(temperature=0.2)
    result = llm.invoke("用一句話說明 LangGraph 的用途（請用繁體中文）。")
    print(result.content)

    print("\n--- Streaming 輸出 ---")
    for chunk in llm.stream("用一句話說明 LangGraph 的用途（請用繁體中文）。"):
        print(chunk.content, end="", flush=True)
    print()


def main() -> None:
    cfg = get_llm_config()

    print(f"目前設定 -> Base URL: {cfg.base_url} | Model: {cfg.model}\n")
    
    test_openai_sdk()
    test_langchain_chat_model()


if __name__ == "__main__":
    main()
