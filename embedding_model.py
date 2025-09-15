# Gemin Rag/embedding_model.py

import os
import traceback
from langchain_community.embeddings import HuggingFaceEmbeddings

def initialize_embedding_model(model_name: str = "intfloat/multilingual-e5-small"):
    """
    初始化 Hugging Face 嵌入模型。
    Args:
        model_name (str): 要載入的嵌入模型名稱。
    Returns:
        HuggingFaceEmbeddings 或 None: 成功初始化的嵌入模型實例，失敗則返回 None。
    """
    embeddings_model = None
    print(f"\n--- 嵌入模型初始化 (用於語義切分和向量儲存) ---")
    print(f"正在初始化 Hugging Face 嵌入模型 ({model_name})...")

    try:
        # 檢查 CUDA 設備是否存在，否則使用 CPU
        device = 'cuda' if os.path.exists('/dev/nvidia0') else 'cpu'
        print(f"  使用設備: {device}")
        embeddings_model = HuggingFaceEmbeddings(
            model_name=model_name,
            model_kwargs={'device': device},
        )
        print(f"Hugging Face 嵌入模型 ({model_name}) 初始化成功。")

    except Exception as e:
        print(f"初始化 Hugging Face 嵌入模型失敗: {e}")
        traceback.print_exc()
        print(f"請確認套件 'sentence-transformers' 已安裝，且您的環境有足夠的記憶體和資源載入 '{model_name}' 模型。")
        embeddings_model = None
    
    return embeddings_model