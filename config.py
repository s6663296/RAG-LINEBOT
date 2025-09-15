# Gemin Rag/config.py

import os

# --------------------------------------------------
# 環境變數設定
# --------------------------------------------------
def setup_environment_variables():
    """設定必要的環境變數。"""
    if 'GOOGLE_APPLICATION_CREDENTIALS' in os.environ:
        print("偵測到 GOOGLE_APPLICATION_CREDENTIALS 環境變數，嘗試移除...")
        try:
            del os.environ['GOOGLE_APPLICATION_CREDENTIALS']
            print("GOOGLE_APPLICATION_CREDENTIALS 已移除。")
        except Exception as e:
            print(f"移除 GOOGLE_APPLICATION_CREDENTIALS 失敗: {e}")
    else:
        print("未偵測到 GOOGLE_APPLICATION_CREDENTIALS 環境變數。")

    os.environ['NO_GCE_CHECK'] = 'true'
    print("NO_GCE_CHECK 已設定為 'true'。")

# --------------------------------------------------
# Google API Key 設定
# --------------------------------------------------
def get_google_api_key():
    """獲取 Google API Key。優先從環境變數中讀取。"""
    google_api_key = os.environ.get("GOOGLE_API_KEY")
    if google_api_key:
        print("Google API Key 已從環境變數中準備就緒。(用於 LLM)")
        return google_api_key
    
    # 如果環境變數未設定，則使用程式碼中的預設值 (僅供開發測試用，部署時應透過環境變數設定)
    default_key = "您的_實際_GOOGLE_API_KEY"
    if default_key and default_key != "您的_實際_GOOGLE_API_KEY":
        print("警告：正在使用 config.py 中的預設 Google API Key。建議透過環境變數設定。")
        return default_key
    
    print("警告：Google API Key 未設定。請設定 GOOGLE_API_KEY 環境變數。")
    return None

# --------------------------------------------------
# Line Bot API 設定
# --------------------------------------------------
def get_line_channel_secret():
    """獲取 Line Channel Secret。優先從環境變數中讀取。"""
    line_channel_secret = os.environ.get("LINE_CHANNEL_SECRET")
    if line_channel_secret:
        print("Line Channel Secret 已從環境變數中準備就緒。")
        return line_channel_secret

    # 如果環境變數未設定，則使用程式碼中的預設值 (僅供開發測試用，部署時應透過環境變數設定)
    default_secret = "8bc99a2e64eece0b86c4fc946ade9c50"
    if default_secret and default_secret != "您的_實際_LINE_CHANNEL_SECRET":
        print("警告：正在使用 config.py 中的預設 Line Channel Secret。建議透過環境變數設定。")
        return default_secret

    print("警告：Line Channel Secret 未設定。請設定 LINE_CHANNEL_SECRET 環境變數。")
    return None

def get_line_channel_access_token():
    """獲取 Line Channel Access Token。優先從環境變數中讀取。"""
    line_channel_access_token = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
    if line_channel_access_token:
        print("Line Channel Access Token 已從環境變數中準備就緒。")
        return line_channel_access_token

    # 如果環境變數未設定，則使用程式碼中的預設值 (僅供開發測試用，部署時應透過環境變數設定)
    default_token = "mxMRBVCU7eqTgMA/1UI81mBJ0+J58xVWK5NBqFCNxkU4214+UgWyHdAqUCnX3T51Y4BQLcWF+e1eRAy5J2MchcS6eQ1waF4WBU1P/bsq4lUjSMrty9aF3NyyyK7FXCRKmU56+EzMCor4MiarNdzf3QdB04t89/1O/w1cDnyilFU="
    if default_token and default_token != "您的_實際_LINE_CHANNEL_ACCESS_TOKEN":
        print("警告：正在使用 config.py 中的預設 Line Channel Access Token。建議透過環境變數設定。")
        return default_token

    print("警告：Line Channel Access Token 未設定。請設定 LINE_CHANNEL_ACCESS_TOKEN 環境變數。")
    return None

# --------------------------------------------------
# 路徑和索引設定
# --------------------------------------------------
KNOWLEDGE_DIR = "knowledge_base_pdfs"
VECTOR_STORE_PATH = "faiss_index_store"
CHUNK_CACHE_PATH = "chunk_cache.pkl" # 新增：切分後文件區塊的快取檔案路徑
FORCE_REBUILD_INDEX = False # 設定為 True 會強制重建向量資料庫，即使已存在
RETRIEVAL_K = 5 # 檢索器每次檢索的文件區塊數量