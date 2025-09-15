# Gemin Rag/llm_model.py

import traceback
from langchain_google_genai import ChatGoogleGenerativeAI

def initialize_llm(google_api_key: str):
    """
    初始化 Gemini LLM。
    Args:
        google_api_key (str): Google API Key。
    Returns:
        ChatGoogleGenerativeAI 或 None: 成功初始化的 LLM 實例，失敗則返回 None。
    """
    llm = None
    if google_api_key:
        print("\n--- LLM 設定 ---")
        print("正在初始化 Gemini LLM (gemini-1.5-flash-latest)...")
        try:
            llm = ChatGoogleGenerativeAI(
                model="gemini-1.5-flash-latest",
                temperature=0.3,
                google_api_key=google_api_key,
            )
            print("Gemini LLM 設定成功！模型：gemini-1.5-flash-latest")
        except Exception as e:
            print(f"初始化 Gemini LLM 失敗: {e}")
            traceback.print_exc()
            print("請確認您的 GOOGLE_API_KEY 有效且有權限使用 Gemini API。")
            llm = None
    else:
        print("\n--- LLM 設定 (跳過) ---")
        print("GOOGLE_API_KEY 未設定，無法初始化 LLM。")
    return llm