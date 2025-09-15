# Gemin Rag/vector_store.py

import os
import shutil
import traceback
from langchain_community.vectorstores import FAISS
from langchain_community.embeddings import HuggingFaceEmbeddings # 為了型別提示
from langchain_core.documents import Document # 為了型別提示

def initialize_vector_store(
    docs_chunks: list[Document],
    embeddings_model: HuggingFaceEmbeddings,
    vector_store_path: str,
    force_rebuild_index: bool
):
    """
    初始化或載入 FAISS 向量資料庫。
    Args:
        docs_chunks (list): 切分後的文件區塊列表。
        embeddings_model (HuggingFaceEmbeddings): 用於嵌入的嵌入模型。
        vector_store_path (str): 向量資料庫的儲存路徑。
        force_rebuild_index (bool): 是否強制重建索引。
    Returns:
        FAISS 或 None: 成功初始化的向量資料庫實例，失敗則返回 None。
    """
    vector_store = None

    if not embeddings_model:
        print("\n--- 向量儲存 (跳過) ---")
        print("嵌入模型未成功初始化，無法創建或載入向量資料庫。")
        return None
    
    index_file_exists = os.path.exists(os.path.join(vector_store_path, "index.faiss"))
    
    # 檢查是否可以載入現有向量庫
    can_load_existing = (
        not force_rebuild_index and 
        os.path.exists(vector_store_path) and 
        index_file_exists
    )

    if not docs_chunks and not can_load_existing:
        print("\n--- 向量儲存 (跳過) ---")
        print("沒有可供嵌入的文件區塊，且未設定載入現有向量庫，無法創建向量資料庫。")
        return None

    print("\n--- 向量儲存 ---")
    if can_load_existing:
        print(f"偵測到已儲存的向量資料庫於 '{vector_store_path}'，正在載入...")
        try:
            vector_store = FAISS.load_local(
                vector_store_path,
                embeddings_model,
                allow_dangerous_deserialization=True
            )
            print("向量資料庫從本機載入成功！")
        except Exception as e:
            print(f"從 '{vector_store_path}' 載入向量資料庫失敗: {e}")
            print("原因可能是檔案損壞、格式不符，或者**更換了嵌入模型或切分方式但未重建索引**。")
            print("將嘗試重新創建向量資料庫...")
            traceback.print_exc()
            vector_store = None

    if vector_store is None:
        if docs_chunks:
            if force_rebuild_index and os.path.exists(vector_store_path):
                 print(f"  因強制重建，正在清理舊的向量資料庫目錄 '{vector_store_path}'...")
                 try:
                     shutil.rmtree(vector_store_path)
                     print("  舊目錄已清理。")
                 except Exception as e:
                     print(f"  清理舊目錄失敗: {e}")
                     print(f"  請手動刪除 '{vector_store_path}' 資料夾後重試。")
                     return None # 清理失敗，無法繼續

            print(f"正在使用 {len(docs_chunks)} 個文件區塊創建新的 FAISS 向量資料庫...")
            try:
                vector_store = FAISS.from_documents(docs_chunks, embeddings_model)
                print("新的向量資料庫創建成功！")
                print(f"正在將新的向量資料庫儲存到 '{vector_store_path}'...")
                if not os.path.exists(vector_store_path):
                    os.makedirs(vector_store_path)
                vector_store.save_local(vector_store_path)
                print(f"向量資料庫已成功儲存到 '{vector_store_path}'。")
            except Exception as e:
                print(f"創建或儲存新的向量資料庫失敗: {e}")
                traceback.print_exc()
                vector_store = None
        else:
            print("沒有可供嵌入的文件區塊，無法創建新的向量資料庫。")
            vector_store = None
            
    return vector_store