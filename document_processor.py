# Gemin Rag/document_processor.py

import os
import traceback
import pickle # 新增：用於序列化/反序列化文件區塊
import hashlib # 新增：用於計算文件哈希值
from langchain_community.document_loaders import PyPDFLoader
from langchain_experimental.text_splitter import SemanticChunker
from langchain_community.embeddings import HuggingFaceEmbeddings # 為了型別提示
from langchain_core.documents import Document # 新增：用於型別提示
import config # 新增：導入 config 模組以獲取快取路徑

def load_and_chunk_documents(knowledge_dir: str, embeddings_model: HuggingFaceEmbeddings):
    """
    從指定目錄載入 PDF 文件並進行語義切分。
    Args:
        knowledge_dir (str): 存放 PDF 文件的目錄路徑。
        embeddings_model (HuggingFaceEmbeddings): 用於語義切分的嵌入模型。
    Returns:
        list: 切分後的文件區塊列表。
    """
    documents: list[Document] = []
    docs_chunks: list[Document] = []

    # 1. 檢查快取
    cache_file_path = config.CHUNK_CACHE_PATH
    current_files_hash = ""

    # 計算當前知識庫中所有 PDF 文件的哈希值
    pdf_files_found_list = []
    if os.path.exists(knowledge_dir):
        for root, dirs, files_in_dir in os.walk(knowledge_dir):
            for file_name in files_in_dir:
                if file_name.lower().endswith('.pdf'):
                    pdf_files_found_list.append(os.path.join(root, file_name))
    
    if pdf_files_found_list:
        hasher = hashlib.md5()
        for pdf_path in sorted(pdf_files_found_list): # 確保順序一致
            try:
                with open(pdf_path, 'rb') as f:
                    buf = f.read()
                    hasher.update(buf)
            except Exception as e:
                print(f"計算文件 {pdf_path} 哈希值時發生錯誤: {e}")
                traceback.print_exc()
        current_files_hash = hasher.hexdigest()

    # 嘗試從快取載入
    if os.path.exists(cache_file_path):
        try:
            with open(cache_file_path, 'rb') as f:
                cached_data = pickle.load(f)
                cached_hash = cached_data.get("hash")
                cached_chunks = cached_data.get("chunks")

                if cached_hash == current_files_hash and cached_chunks:
                    print(f"從快取載入文件區塊成功 ({len(cached_chunks)} 個區塊)。")
                    return cached_chunks
                else:
                    print("快取文件已過期或文件內容已變更，將重新切分。")
        except Exception as e:
            print(f"載入快取文件失敗: {e}")
            traceback.print_exc()
            # 如果載入失敗，則繼續執行切分流程

    if not os.path.exists(knowledge_dir):
        os.makedirs(knowledge_dir)
        print(f"已創建知識庫資料夾 '{knowledge_dir}'。請將 PDF 文件放入此資料夾。")

    if not os.path.exists(knowledge_dir):
        print(f"錯誤：找不到指定的知識庫資料夾 '{knowledge_dir}'，且創建失敗。")
    else:
        print(f"偵測到知識庫資料夾 '{knowledge_dir}'，正在掃描其中的 PDF 文件...")
        loaded_count = 0
        pdf_files_found_list = []
        for root, dirs, files_in_dir in os.walk(knowledge_dir):
             for file_name in files_in_dir:
                if file_name.lower().endswith('.pdf'):
                    pdf_files_found_list.append(os.path.join(root, file_name))

        if not pdf_files_found_list:
            print(f"在 '{knowledge_dir}' 中未找到任何 PDF 文件。請添加 PDF 文件到該目錄下以繼續。")
        else:
            for pdf_path in pdf_files_found_list:
                print(f"  載入檔案：{pdf_path}")
                try:
                    loader = PyPDFLoader(pdf_path)
                    pdf_pages_as_documents = loader.load()
                    documents.extend(pdf_pages_as_documents)
                    print(f"    成功載入 {len(pdf_pages_as_documents)} 頁。")
                    loaded_count += 1
                except Exception as e:
                    print(f"    載入 PDF 文件 {pdf_path} 時發生錯誤：{e}")
                    traceback.print_exc()

            print(f"\n總共從資料夾中載入 {loaded_count} 個 PDF 文件，共 {len(documents)} 個 Document (頁面)。")

            if not documents:
                print("未能從指定資料夾中載入任何 PDF 文件內容。無法進行切分。")
                docs_chunks = []
            elif not embeddings_model:
                print("嵌入模型未能初始化，無法進行基於語義的切分。")
                docs_chunks = []
            else:
                print(f"正在使用基於語義的切分器 (SemanticChunker) 進行切分...")
                try:
                    text_splitter = SemanticChunker(
                        embeddings=embeddings_model,
                    )
                    docs_chunks = text_splitter.split_documents(documents)
                    print(f"切分後的區塊總數: {len(docs_chunks)}")
                    if docs_chunks:

                        # 儲存到快取
                        try:
                            with open(cache_file_path, 'wb') as f:
                                pickle.dump({"hash": current_files_hash, "chunks": docs_chunks}, f)
                            print(f"文件區塊已儲存到快取檔案: {cache_file_path}")
                        except Exception as e:
                            print(f"儲存文件區塊到快取失敗: {e}")
                            traceback.print_exc()
                    else:
                        print("雖然載入了文件，但沒有成功切分出文件區塊。")
                except Exception as e:
                    print(f"基於語義切分文件時發生錯誤: {e}")
                    traceback.print_exc()
                    docs_chunks = []
    return docs_chunks