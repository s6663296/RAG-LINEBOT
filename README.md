# 餐廳 AI 客服

![](RAG範例.png)

## 目錄
- [餐廳 AI 客服](#餐廳-ai-客服)
  - [專案動機](#專案動機)
  - [主要功能](#主要功能)
  - [系統架構](#系統架構)
    - [系統流程圖](#系統流程圖)
    - [技術棧](#技術棧)
  - [功能詳解](#功能詳解)
    - [1. RAG 問答系統](#1-rag-問答系統)
    - [2. 自動化訂位系統](#2-自動化訂位系統)
  - [安裝與執行 (本地端)](#安裝與執行-本地端)
    - [1. 環境設定](#1-環境設定)
    - [2. 安裝依賴](#2-安裝依賴)
    - [3. 建立知識庫](#3-建立知識庫)
    - [4. 啟動應用程式](#4-啟動應用程式)
  - [部署至 Google Cloud Run](#部署至-google-cloud-run)
    - [1. 前置作業](#1-前置作業)
    - [2. 設定 Google Cloud 專案](#2-設定-google-cloud-專案)
    - [3. 建立服務帳戶](#3-建立服務帳戶)
    - [4. 部署應用程式](#4-部署應用程式)
    - [5. 檢查部署狀態與日誌](#5-檢查部署狀態與日誌)

---
## 專案動機

在現今的服務業中，顧客對即時便利的需求日益增高。然而，許多餐廳仍依賴人工處理大量重複的顧客查詢與訂位，這不僅耗費人力，也無法提供 24 小時服務，導致營運效率低落並可能錯失商機。

希望透過這個 AI 客服達成以下目標：

- 提升顧客服務的即時性與自動化程度
- 解決資訊一致性與知識更新困難問題
- 實現與訂位系統的整合自動化流程
- 提供可擴展、低維護成本的智慧客服架構

---

## 主要功能

|**Line Bot 互動**|**RAG 問答系統**|**日曆訂位管理**|**雲端部屬**|
| :--- | :--- | :--- | :--- |
|使用者介面，接收 與回覆訊息|文件檢索、LLM生 成，記憶上下文|自動化訂位，查 詢、新增、刪除|Cloud Run 容器化|

---

## 系統架構

### 系統流程圖
![](Aspose.Words.a3e812dd-1f9e-4df3-b834-0148231fb2ac.001.jpeg)

### 技術棧
| 類別 | 技術 |
| :--- | :--- |
| **語言** | Python |
| **框架** | Flask, LangChain |
| **LLM** | Google Gemini Flash 2.0 |
| **嵌入模型** | `multilingual-e5-small` |
| **向量資料庫** | FAISS |
| **部署** | Docker, Google Cloud Run |
| **其他** | Line Bot SDK, Google Calendar API |

---

## 功能詳解

### 1. RAG 問答系統

![](Aspose.Words.a3e812dd-1f9e-4df3-b834-0148231fb2ac.003.png)

1.  **知識庫處理**:
    *   **資料來源**: 台灣知名連鎖早餐品牌「麥味登」的官方網站資訊 (PDF 格式)。
    *   **語義切分**: 使用 `SemanticChunker` 將 PDF 文件拆解成獨立的知識單元。
    *   **向量化**: 透過 `multilingual-e5-small` 嵌入模型，將知識單元轉換為向量。
    *   **索引**: 將向量化的知識存入 FAISS 向量資料庫，以供快速檢索。
    ![](Aspose.Words.a3e812dd-1f9e-4df3-b834-0148231fb2ac.002.png)

2.  **問答流程**:
    *   當收到使用者問題，系統會先擴展成多個語義相近的問題，並在知識庫中進行多路搜索。
    *   整合對話記憶，理解上下文，讓追問更精準。
    *   將檢索到的知識與問題整合成提示 (Prompt)，提交給 `Gemini Flash 2.0` 模型生成回答。

### 2. 自動化訂位系統

利用 Google 日曆 API 打造全自動訂位系統，包含三大模組：

| 模組 | 功能說明 |
| :--- | :--- |
| **查詢空位** | 1. **API 查詢**: 呼叫 Google 日曆 API，查詢未來可預約的時段。<br>2. **過濾時段**: 每個時段最多接受 3 組預約，過濾已滿的時段。<br>3. **格式化回覆**: 將可預約的日期與時段列表回傳給使用者。 |
| **新增訂位** | 1. **資訊提取**: 使用 LLM 從自然語言中提取姓名、日期、時間、人數、電話等關鍵資訊。<br>2. **規則驗證**: 驗證訂位時間與時段容量。<br>3. **建立日曆活動**: 呼叫 API 在 Google 日曆上建立活動，並產生唯一的訂位編號。 |
| **刪除訂位** | 1. **身份驗證**: 要求使用者提供預約電話號碼。<br>2. **查詢預約**: 根據電話號碼查詢相關訂位紀錄。<br>3. **確認刪除**: 使用者輸入訂位編號進行二次確認後，刪除對應的日曆活動。 |


---

## 安裝與執行 (本地端)

### 1. 環境設定

在執行專案前，請完成以下設定：

*   **Line Bot**:
    *   在 `config.py` 中填入您的 `LINE_CHANNEL_SECRET` 和 `LINE_CHANNEL_ACCESS_TOKEN`。
*   **Google API**:
    *   在 `config.py` 中填入您的 `GOOGLE_API_KEY` (用於 Gemini)。
    *   遵循 [Google Calendar API Python Quickstart](https://developers.google.com/calendar/api/quickstart/python) 指示，產生 `credentials.json` 和 `token.json` 檔案，並放置於專案根目錄。

### 2. 安裝依賴

```bash
pip install -r requirements.txt
```

### 3. 建立知識庫

將您的 PDF 知識庫文件放入 `knowledge_base_pdfs` 資料夾。

**知識庫運作機制說明：**
*   **首次啟動**: 應用程式啟動時，會自動掃描 `knowledge_base_pdfs` 資料夾中的文件，建立向量索引並儲存於 `faiss_index_store`。如果資料夾為空，系統仍會正常啟動，但問答功能將無法使用。
*   **後續載入**: 若 `faiss_index_store` 資料夾已存在，程式會直接載入現有索引以加速啟動，此時不會重新讀取 PDF。
*   **更新知識庫**: 如果您更新或新增了 PDF 檔案，需要手動刪除 `faiss_index_store` 資料夾，或將 `config.py` 中的 `FORCE_REBUILD_INDEX` 設為 `True`，然後重啟應用程式以強制重建索引。

### 4. 啟動應用程式

```bash
python main.py
```
應用程式預設在 `8080` 埠啟動。您需要設定一個公開的 HTTPS URL (可使用 ngrok) 並將其設為 Line Bot 的 Webhook URL。

---

## 部署至 Google Cloud Run

![](Aspose.Words.a3e812dd-1f9e-4df3-b834-0148231fb2ac.004.jpeg)

### 1. 前置作業

確保已安裝並設定好 [Google Cloud SDK](https://cloud.google.com/sdk/docs/install)。

### 2. 設定 Google Cloud 專案

```bash
gcloud auth login
gcloud config set project [YOUR_PROJECT_ID]
```
> 將 `[YOUR_PROJECT_ID]` 替換為您的 Google Cloud 專案 ID。

### 3. 建立服務帳戶

為應用程式建立一個專屬的服務帳戶以存取 Google Calendar API：

```bash
gcloud iam service-accounts create [SERVICE_ACCOUNT_NAME] \
    --display-name "[DISPLAY_NAME]" \
    --project [YOUR_PROJECT_ID]
```
*   `[SERVICE_ACCOUNT_NAME]`: 服務帳戶名稱。
*   `[DISPLAY_NAME]`: 顯示名稱。

> **重要**: 建立後，請至 IAM & Admin 頁面，將 **Google Calendar API 的存取權限**授予此服務帳戶。

### 4. 部署應用程式

在專案根目錄下，執行以下指令：

```bash
gcloud run deploy [SERVICE_NAME] \
  --source . \
  --region [REGION] \
  --allow-unauthenticated \
  --service-account [SERVICE_ACCOUNT_EMAIL] \
  --memory=2Gi --cpu=1 --timeout=800 \
  --set-env-vars LINE_CHANNEL_SECRET="[YOUR_LINE_SECRET]",LINE_CHANNEL_ACCESS_TOKEN="[YOUR_LINE_TOKEN]",GOOGLE_API_KEY="[YOUR_GOOGLE_API_KEY]"
```

**參數說明:**
*   `[SERVICE_NAME]`: Cloud Run 上的服務名稱。
*   `[REGION]`: 部署地區。
*   `[SERVICE_ACCOUNT_EMAIL]`: 上一步建立的服務帳戶 Email。
*   `[YOUR_LINE_SECRET]`, `[YOUR_LINE_TOKEN]`, `[YOUR_GOOGLE_API_KEY]`: 您的 Line Bot 與 Google API 金鑰。

### 5. 檢查部署狀態與日誌

部署完成後，Cloud Run 會提供一個服務 URL，請將此 URL 更新到 Line Bot 的 Webhook 設定。

若需排查問題，可使用以下指令查看日誌：

```bash
gcloud logging read 'resource.type="cloud_run_revision" AND resource.labels.service_name="[SERVICE_NAME]"' \
  --project=[YOUR_PROJECT_ID] \
  --limit=100 \
  --format="value(textPayload)"
