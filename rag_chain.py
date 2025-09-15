
import os
import time
import traceback
import json # 導入 json 模組
import uuid # 導入 uuid 模組，用於生成唯一的訂位編號
from langchain.chains import RetrievalQA, ConversationalRetrievalChain # 導入 ConversationalRetrievalChain
from langchain.retrievers import MultiQueryRetriever
from langchain_core.prompts import ChatPromptTemplate
from langchain.memory import ChatMessageHistory, ConversationBufferWindowMemory # 導入對話記憶相關模組
from langchain.prompts import PromptTemplate
from langchain_google_genai import ChatGoogleGenerativeAI # 為了型別提示
from langchain_community.vectorstores import FAISS # 為了型別提示
import pytz # 導入 pytz 模組
from datetime import datetime as dt_obj, timedelta, time as dt_time # 導入 datetime 模組，並特別引入 timezone 以處理時區
from dateutil.relativedelta import relativedelta # 引入 relativedelta 以便於計算月份的起始和結束日期
from typing import Optional # 導入 Optional 類型提示


import order

def setup_retriever(vector_store: FAISS, retrieval_k: int):
    retriever = None
    if vector_store:
        print("--- 設定基礎檢索器 (將用於 MultiQueryRetriever) ---")
        try:
            retriever = vector_store.as_retriever(
                search_type="similarity",
                search_kwargs={"k": retrieval_k}
            )
            print(f"基礎檢索器設定成功！每個子查詢將檢索最相似的 {retrieval_k} 個文件區塊。")
        except Exception as e:
            print(f"設定基礎檢索器時發生錯誤: {e}")
            traceback.print_exc()
            retriever = None
    else:
        print("--- 基礎檢索器設定 (跳過) ---")
        print("向量資料庫未成功創建或載入，無法設定基礎檢索器。")
    return retriever

def create_rag_chain(retriever, llm: ChatGoogleGenerativeAI, memory_window_size: int = 5, existing_memory: Optional[ConversationBufferWindowMemory] = None):
    qa_chain = None
    if retriever and llm:
        print("--- RAG QA 鏈建立 (使用 MultiQueryRetriever 和對話記憶) ---")

        if existing_memory:
            memory = existing_memory
            print("使用傳入的對話記憶實例。")
        else:
            memory = ConversationBufferWindowMemory(
                memory_key="chat_history",
                return_messages=True,
                output_key="answer",
                k=memory_window_size
            )
            print(f"對話記憶初始化成功！記憶視窗大小：{memory_window_size} 輪。")

        query_gen_prompt = ChatPromptTemplate.from_messages(
            [
                ("system", """你是一個有用的 AI 助理，擅長根據使用者的原始問題生成多個相關的搜索查詢。
                你的目標是從不同的角度思考使用者的原始問題，生成 3-5 個不同的搜索查詢，這些查詢應該能夠幫助檢索系統在文件中找到最相關的背景資訊。
                請根據原始問題生成多個搜索查詢，並將它們以換行符分隔列出。
                例如，如果原始問題是 '如何申請護照？'，你的輸出可以是：
                如何申請護照的步驟
                申請護照所需文件
                護照申請流程
                申請護照費用

                原始問題：{question}
                """),
                ("human", "請提供相關的搜索查詢："),
            ]
        )

        advanced_retriever = None
        try:
            advanced_retriever = MultiQueryRetriever.from_llm(
                retriever=retriever,
                llm=llm,
                prompt=query_gen_prompt
            )
            print("MultiQueryRetriever 設定成功！")
        except Exception as e:
            print(f"設定 MultiQueryRetriever 失敗: {e}")
            traceback.print_exc()
            advanced_retriever = None

        qa_prompt_template = """
        你是一位企業客服，專門回答關於所提供文件內容的問題。
        請運用我接下來提供的「背景資訊」來回答「問題」。
        你的目標是提供清晰、準確且有幫助的答案，並且聽起來像是你自然擁有的知識，請勿讓使用者知道你的知識來自於公司提供的文件!!

        指導方針：
        1.  自然回答：請用流暢、口語化的方式回答，就像你真的了解這些資訊一樣。
        2.  避免提及來源：在你的回答中，**絕對不要**提及「文件」、「知識庫」、「提供的資料」、「上下文」、「背景資訊」或任何類似詞語來指稱你的資訊來源。就當這些知識是你自己的一樣。
        3.  準確性：根據「背景資訊」準確回答。如果「背景資訊」中有直接相關的內容，請用自己的話總結並清晰地回答。
        4.  處理未知：如果「背景資訊」中沒有足夠的資訊來直接回答「問題」，請誠實地說明你目前無法提供確切答案。
            *   你可以說：「關於您的這個問題，我目前沒有找到相關的具體資訊。」
            *   或者：「針對您的情況，我目前無法給出確切的指引。」
            *   或者：「嗯，關於這一點，我暫時沒有足夠的細節可以提供給您。」
            *   **不要說**類似「根據文件...我找不到答案」這樣的話。
        5.  提供相關資訊：如果直接答案沒有，但「背景資訊」中確實有相關主題的內容，你可以嘗試提供，例如：「不過，我可以提供一些關於[相關主題]的一般資訊，也許對您有幫助：...」但前提是這些相關資訊確實存在於「背景資訊」中。
        6.  不要編造：切記，不要編造「背景資訊」中不存在的答案。你的回答必須基於提供的「背景資訊」。

        對話歷史：
        {chat_history}
        背景資訊：
        {context}

        問題：{question}

        AI客服的回答：
        """
        QA_PROMPT = PromptTemplate(
            template=qa_prompt_template, input_variables=["context", "question", "chat_history"]
        )

        if advanced_retriever:
            try:
                qa_chain = ConversationalRetrievalChain.from_llm(
                    llm=llm,
                    retriever=advanced_retriever,
                    memory=memory,
                    combine_docs_chain_kwargs={"prompt": QA_PROMPT},
                    return_source_documents=True,
                )
                print("RAG QA 鏈建立成功！使用 MultiQueryRetriever 和 ConversationalRetrievalChain。")
            except Exception as e:
                print(f"建立 RAG QA 鏈失敗: {e}")
                traceback.print_exc()
                qa_chain = None
        else:
            print("由於 MultiQueryRetriever 設定失敗，無法建立 RAG QA 鏈。")
    return qa_chain

def classify_booking_intent(llm: ChatGoogleGenerativeAI, user_query: str) -> str:
    intent_prompt = ChatPromptTemplate.from_messages(
        [
            ("system", """你是一個意圖分類助理。你的任務是判斷使用者關於訂位的意圖。
            請從以下選項中選擇最符合使用者意圖的類別：
            - '查詢空位'：使用者想知道可用的訂位時間、是否有空位、位子、還有沒有位置、能不能訂位子、查詢空位、還有空位嗎、查空位、空位查詢、預約查詢、查詢預約。
            - '新增訂位'：使用者想預約一個新的訂位。
            - '刪除訂位'：使用者想取消或刪除一個現有的訂位。
            - '其他'：如果意圖不屬於上述任何一項。

             

            例如：

            使用者輸入: "我想訂位"
            輸出: 新增訂位

            使用者輸入: "取消我的訂位"
            輸出: 刪除訂位

            請只輸出分類結果，不要包含任何額外的文字或解釋。

            使用者輸入：{user_input}
            """),
            ("human", "請判斷意圖："),
        ]
    )
    try:
        chain = intent_prompt | llm
        response = chain.invoke({"user_input": user_query})
        intent = response.content.strip().replace("'", "").replace('"', '')
        print(f"  [Debug] 意圖分類結果: {intent}")
        if intent in ['查詢空位', '新增訂位', '刪除訂位']:
            return intent
        else:
            return '其他'
    except Exception as e:
        print(f"意圖分類失敗: {e}")
        traceback.print_exc()
        return '其他'

def create_booking_info_extractor_chain(llm: ChatGoogleGenerativeAI):
    print("--- 建立訂位資訊提取鏈 ---")
    booking_info_prompt = ChatPromptTemplate.from_messages(
        [
            ("system", """你是一個訂位資訊提取助理。你的任務是從使用者提供的文字中，提取以下訂位資訊：
            - 訂位人名稱 (name)
            - 訂位日期 (reservation_date, 格式為 MM-DD 或 YYYY-MM-DD。如果沒有提供年份，請預設為當年。例如 "5月27日" 應提取為當年的 "05-27"。)
            - 訂位時間 (reservation_time, 格式為 HH:MM，例如 10:00。請將所有時間表達轉換為 24 小時制的 HH:MM 格式。例如 "中午12點" 應為 "12:00", "下午兩點半" 應為 "14:30"。)
            - 用餐人數 (persons)
            - 行動電話 (phone)

            如果某項資訊沒有提供，請將其值設為 "None"。
            訂位時間必須是上午10點到下午4點之間。如果使用者提供的時間不在這個範圍內，請將 reservation_time 設為 "Invalid Time"。
            用餐時間固定為2小時。

            請**只**以 JSON 格式輸出結果，**不要**包含任何額外的文字、解釋或 Markdown 程式碼區塊以外的內容。
            你的輸出必須以 ```json 開頭，並以 ``` 結尾。

            例如：
            ```json
            {{
              "name": "王小明",
              "reservation_date": "10-27",
              "reservation_time": "10:00",
              "persons": 4,
              "phone": "0912345678"
            }}
            ```
            或者包含年份：
            ```json
            {{
              "name": "李大華",
              "reservation_date": "2024-06-15",
              "reservation_time": "14:30",
              "persons": 2,
              "phone": "0987654321"
            }}
            ```
            如果使用者只是詢問可訂位時間，而不是要實際訂位，請將所有欄位設為 "None"。
            
            使用者輸入：{user_input}
            """),
            ("human", "請提取訂位資訊："),
        ]
    )
    try:
        booking_info_extractor_chain = booking_info_prompt | llm
        print("訂位資訊提取鏈建立成功！")
        return booking_info_extractor_chain
    except Exception as e:
        print(f"建立訂位資訊提取鏈失敗: {e}")
        traceback.print_exc()
        return None

def ask_question_and_get_answer(query: str, qa_chain: ConversationalRetrievalChain, retriever):
    if not qa_chain:
        print("錯誤：QA 鏈未初始化，無法處理問題。")
        return None

    print(f"--- 您的問題：'{query}' ---")
    print("--- [Debug] 原始檢索器對原始查詢找到的文件區塊 (供參考，可能與 LLM 實際使用的不同) ---")
    retrieved_docs_for_debug = []
    if retriever:
         try:
            retrieved_docs_for_debug = retriever.invoke(query)
            if retrieved_docs_for_debug:
                 for i, doc in enumerate(retrieved_docs_for_debug):
                    source_info = "未知來源"
                    if doc.metadata:
                         source_parts = []
                         if 'source' in doc.metadata:
                             source_file = os.path.basename(doc.metadata['source'])
                             source_parts.append(f"檔案: {source_file}")
                         if 'page' in doc.metadata:
                             source_parts.append(f"頁碼: {doc.metadata['page']}")
                         source_info = ", ".join(source_parts) if source_parts else source_info
                    print(f"  [Debug] 檢索來源 {i+1} ({source_info}):\n{doc.page_content[:200]}...\n")
            else:
                print("  [Debug] 原始檢索器未找到任何相關文件區塊。")
         except Exception as e:
              print(f"  [Debug] 原始檢索器調試時發生錯誤: {e}")
              traceback.print_exc()
    else:
         print("  [Debug] 原始檢索器未成功初始化，無法執行調試檢索。")

    print("--- [Debug] 原始檢索器資訊結束 ---")

    final_answer_text = None
    try:
        print("--- 正在使用 ConversationalRetrievalChain 進行檢索並呼叫 LLM 生成回答 ---")
        result = qa_chain.invoke({"question": query})
        final_answer_text = result.get('answer')

        print("--- [Debug] LLM 生成回答時實際使用的相關原始文件區塊 ---")
        source_documents_from_llm = result.get('source_documents')
        if source_documents_from_llm:
            for i, doc in enumerate(source_documents_from_llm):
                source_info = "未知來源"
                if doc.metadata:
                     source_parts = []
                     if 'source' in doc.metadata:
                         source_file = os.path.basename(doc.metadata['source'])
                         source_parts.append(f"檔案: {source_file}")
                     if 'page' in doc.metadata:
                         source_parts.append(f"頁碼: {doc.metadata['page']}")
                     source_info = ", ".join(source_parts) if source_parts else source_info
                print(f"  [Debug] LLM 使用來源 {i+1} ({source_info}):\n{doc.page_content[:250]}...\n")
        else:
            print("  [Debug] QA 鏈結果中沒有包含 source_documents 或為空。")
        print("--- [Debug] LLM 使用來源資訊結束 ---")

    except Exception as e:
        print(f"處理問題 '{query}' 時發生錯誤: {e}")
        traceback.print_exc()
        print("--------------------------")

    return final_answer_text

def process_booking_request(user_query: str, llm: ChatGoogleGenerativeAI) -> dict:
    booking_extractor = create_booking_info_extractor_chain(llm)
    if not booking_extractor:
        return {"status": "error", "message": "錯誤：訂位資訊提取鏈未能建立，新增訂位功能將無法使用。"}

    extracted_info = {}
    try:
        response = booking_extractor.invoke({"user_input": user_query})
        json_string = response.content.strip()
        if json_string.startswith("```json") and json_string.endswith("```"):
            json_string = json_string[len("```json"): -len("```")].strip()
        
        extracted_info = json.loads(json_string)
        print(f"  [Debug] 提取到的資訊: {extracted_info}")
    except json.JSONDecodeError as e:
        return {"status": "error", "message": f"  [錯誤] 解析訂位資訊時發生 JSON 錯誤: {e}\n  LLM 原始輸出: {response.content}\n  請重新輸入訂位資訊，確保格式正確。"}
    except Exception as e:
        return {"status": "error", "message": f"  [錯誤] 提取訂位資訊時發生未知錯誤: {e}\n  請重新輸入訂位資訊。"}

    # 檢查並清理提取到的資訊
    booking_data = {}
    for key, value in extracted_info.items():
        if isinstance(value, str):
            if value.lower() != 'none' and value.lower() != 'invalid time':
                booking_data[key] = value
        elif value is not None:
            booking_data[key] = value

    if booking_data.get("reservation_date"):
        date_str = booking_data["reservation_date"]
        try:
            parsed_date = dt_obj.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            try:
                current_year = dt_obj.now().year
                parsed_date = dt_obj.strptime(f"{current_year}-{date_str}", '%Y-%m-%d').date()
            except ValueError:
                return {"status": "missing_info", "message": "\n[錯誤] 訂位日期格式不正確。請確保日期為 MM-DD 或 YYYY-MM-DD。請重新提供完整的訂位資訊。"}
        booking_data["reservation_date"] = parsed_date.strftime('%Y-%m-%d')


    required_fields = ["name", "reservation_date", "reservation_time", "persons", "phone"]
    missing_fields = [field for field in required_fields if booking_data.get(field) is None]

    if missing_fields:
        prompt_message = "請確保包含以下資訊："
        if "name" in missing_fields: prompt_message += " 姓名、"
        if "phone" in missing_fields: prompt_message += " 電話、"
        if "persons" in missing_fields: prompt_message += " 人數、"
        if "reservation_date" in missing_fields: prompt_message += " 訂位日期 (ex：MM-DD)、"
        if "reservation_time" in missing_fields: prompt_message += " 訂位時間 (ex：HH:MM)、"
        return {"status": "missing_info", "message": f"{prompt_message.strip('、')}。\n\n範例：'我想訂位，我叫王小明，電話0912345678，2人，訂10月27日早上10點。"}

    try:
        reservation_datetime_str = f"{booking_data['reservation_date']}T{booking_data['reservation_time']}:00"
        
        taipei_tz = pytz.timezone('Asia/Taipei')
        now_local = dt_obj.now(taipei_tz)
        time_max = now_local + relativedelta(months=1)

        proposed_time_naive = dt_obj.fromisoformat(reservation_datetime_str)
        proposed_time = taipei_tz.localize(proposed_time_naive)

        allowed_start_time = dt_time(10, 0, 0)
        allowed_end_time = dt_time(16, 0, 0)
        
        if not (allowed_start_time <= proposed_time.time() < allowed_end_time):
            return {"status": "invalid_time", "message": "\n[錯誤] 訂位時間必須在早上10點到下午4點之間。請重新提供完整的訂位資訊。"}

        if not (now_local <= proposed_time <= time_max):
            return {"status": "invalid_time", "message": f"\n[錯誤] 訂位日期必須在 {now_local.strftime('%Y年%m月%d日 %H:%M')} 到 {time_max.strftime('%Y年%m月%d日 %H:%M')} 之間。請重新提供完整的訂位資訊。"}

    except ValueError:
        return {"status": "error", "message": "\n[錯誤] 訂位日期或時間格式不正確。請確保日期為 YYYY-MM-DD，時間為 HH:MM。請重新提供完整的訂位資訊。"}
    except Exception as e:
        traceback.print_exc()
        return {"status": "error", "message": f"\n[錯誤] 驗證訂位時間時發生未知錯誤: {e}\n請重新提供完整的訂位資訊。"}

    service = order.get_calendar_service()
    if not service:
        return {"status": "error", "message": "無法連接 Google 行事曆服務，無法生成訂位編號。"}
    
    events_in_range, _, _ = order.get_current_month_events(service)
    existing_reservation_ids = {
        order._extract_reservation_id_from_event(event)
        for event in events_in_range
        if order._extract_reservation_id_from_event(event) is not None
    }

    reservation_id = None
    while reservation_id is None or reservation_id in existing_reservation_ids:
        reservation_id = str(uuid.uuid4()).split('-')[0].upper()
        if reservation_id in existing_reservation_ids:
            print(f"  [Debug] 生成的訂位編號 {reservation_id} 已存在，重新生成...")
    
    return {
        "status": "success",
        "message": "請確認以下訂位資訊：",
        "booking_data": booking_data,
        "reservation_id": reservation_id
    }
def add_booking_to_calendar(booking_data: dict, reservation_id: str) -> dict:
    service = order.get_calendar_service()
    if not service:
        return {"status": "error", "message": "無法連接 Google 行事曆服務，無法新增訂位。"}

    try:
        persons_int = int(booking_data["persons"])
        
        taipei_tz = pytz.timezone('Asia/Taipei')
        reservation_datetime_str = f"{booking_data['reservation_date']}T{booking_data['reservation_time']}:00"
        start_time_naive = dt_obj.fromisoformat(reservation_datetime_str)
        start_time = taipei_tz.localize(start_time_naive)
        end_time = start_time + timedelta(hours=2)

        is_available, availability_message = order.check_slot_availability(start_time, end_time)
        if not is_available:
            return {"status": "unavailable", "message": availability_message}

        add_result = order.add_calendar_event(
            name=booking_data["name"],
            reservation_datetime_str=reservation_datetime_str,
            persons=persons_int,
            phone=booking_data["phone"],
            reservation_id=reservation_id,
            calendar_id='s6663296@gmail.com' # 將此替換為您希望寫入的日曆 ID
        )
        return {"status": "success", "message": f"\n{add_result}"}
    except ValueError:
        return {"status": "error", "message": "  [錯誤] 人數格式不正確，請重新提供完整的訂位資訊。"}
    except Exception as e:
        traceback.print_exc()
        return {"status": "error", "message": f"  [錯誤] 新增訂位到 Google 日曆時發生錯誤: {e}\n請重新提供完整的訂位資訊。"}


