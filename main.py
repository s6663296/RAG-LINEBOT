import os
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage, FlexSendMessage, BubbleContainer, BoxComponent, TextComponent, ButtonComponent, SeparatorComponent, PostbackAction, MessageAction, URIAction, PostbackEvent
from langchain.memory import ConversationBufferWindowMemory # 導入對話記憶相關模組

import config
import llm_model
import rag_chain
import order
import embedding_model
import document_processor
import vector_store as vector_store_module
import traceback

app = Flask(__name__)

LINE_CHANNEL_SECRET = config.get_line_channel_secret()
LINE_CHANNEL_ACCESS_TOKEN = config.get_line_channel_access_token()

if LINE_CHANNEL_SECRET is None or LINE_CHANNEL_ACCESS_TOKEN is None:
    print("錯誤：Line Channel Secret 或 Channel Access Token 未設定。請檢查 config.py。")
    exit(1)

line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

user_booking_states = {}
delete_booking_states = {}
user_chat_memories = {} # 新增：用於儲存每個用戶的對話記憶體

google_api_key = config.get_google_api_key()

# 全域資源初始化
llm = None
embeddings_model = None
retriever = None
booking_extractor_chain = None


print("正在初始化 Line Bot 全域資源...")
try:
    # 初始化 LLM
    llm = llm_model.initialize_llm(google_api_key)
    if not llm:
        print("LLM 初始化失敗。")
        exit(1)

    # 初始化嵌入模型
    embeddings_model = embedding_model.initialize_embedding_model()
    if not embeddings_model:
        print("嵌入模型初始化失敗。")
        exit(1)

    # 載入並切分文件
    print("--- 文件載入與切分 ---")
    print(f"偵測到知識庫資料夾 '{config.KNOWLEDGE_DIR}'，正在掃描其中的 PDF 文件...")
    docs_chunks = document_processor.load_and_chunk_documents(config.KNOWLEDGE_DIR, embeddings_model)
    if not docs_chunks:
        print("文件載入與切分失敗。這可能導致 RAG 功能受限。")
        # 不退出，讓應用程式在沒有知識庫的情況下也能啟動
        pass
    else:
        print(f"文件切分完成，共 {len(docs_chunks)} 個區塊。")

    # 初始化向量資料庫
    print("--- 向量資料庫初始化 ---")
    print(f"正在初始化向量資料庫 (路徑: {config.VECTOR_STORE_PATH}, 強制重建: {config.FORCE_REBUILD_INDEX})...")
    vector_store_instance = vector_store_module.initialize_vector_store(docs_chunks, embeddings_model, config.VECTOR_STORE_PATH, config.FORCE_REBUILD_INDEX)
    if not vector_store_instance:
        print("向量資料庫初始化失敗。")
        exit(1)
    print("向量資料庫初始化成功。")

    # 設定檢索器
    print("--- 檢索器設定 ---")
    retriever = rag_chain.setup_retriever(vector_store_instance, config.RETRIEVAL_K)
    if not retriever:
        print("檢索器設定失敗。")
        exit(1)
    print("檢索器設定成功。")
    
    # 創建訂位資訊提取鏈
    print("--- 訂位資訊提取鏈設定 ---")
    booking_extractor_chain = rag_chain.create_booking_info_extractor_chain(llm)
    if not booking_extractor_chain:
        print("訂位資訊提取鏈建立失敗。")
        exit(1)
    print("訂位資訊提取鏈建立成功。")

    print("Line Bot 全域資源初始化完成。")
except Exception as e:
    print(f"初始化 Line Bot 全域資源時發生錯誤: {e}")
    traceback.print_exc()
    exit(1)


@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']

    body = request.get_data(as_text=True)
    app.logger.info("Request body: " + body)

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)

    return 'OK'

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_id = event.source.user_id
    user_query = event.message.text

    user_state = delete_booking_states.get(user_id, {"state": None})
    print(f"收到來自用戶 {user_id} 的訊息: {user_query}")

    # 檢查全域資源是否初始化
    if retriever is None or llm is None or booking_extractor_chain is None:
        reply_text = "抱歉，AI 客服系統正在初始化中，請稍後再試。"
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=reply_text)
        )
        return

    # 為每個用戶獲取或創建獨立的對話記憶體
    if user_id not in user_chat_memories:
        memory_window_size = 3 # 可以從 config.py 讀取
        user_chat_memories[user_id] = ConversationBufferWindowMemory(
            memory_key="chat_history",
            return_messages=True,
            output_key="answer",
            k=memory_window_size
        )
        print(f"為用戶 {user_id} 初始化新的對話記憶體。")
    
    # 使用用戶專屬的記憶體創建 qa_chain
    # 注意：這裡每次請求都會創建新的 qa_chain，但底層的 retriever 和 llm 是共享的
    qa_chain_for_user = rag_chain.create_rag_chain(retriever, llm, memory_window_size=3, existing_memory=user_chat_memories[user_id])
    if not qa_chain_for_user:
        reply_text = "抱歉，RAG 鏈未能為您建立，請稍後再試。"
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=reply_text)
        )
        return

    if user_state["state"] == "waiting_for_phone":
        print("--- 刪除訂位流程：等待電話號碼 ---")
        phone_number = user_query.strip()
        if not phone_number:
            reply_text = "請提供您的電話號碼以便查詢訂位。"
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply_text))
            return

        service = order.get_calendar_service()
        if not service:
            reply_text = "無法連接 Google 行事曆服務，無法執行刪除操作。"
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply_text))
            if user_id in delete_booking_states:
                del delete_booking_states[user_id]
            return

        matching_bookings = order.find_bookings_by_phone(service, phone_number)

        if not matching_bookings:
            reply_text = f"未找到電話號碼 {phone_number} 相關的訂位。"
            # 清除狀態
            if user_id in delete_booking_states:
                del delete_booking_states[user_id]
        else:
            delete_booking_states[user_id] = {"state": "waiting_for_reservation_id", "bookings": matching_bookings}
            
            reply_text = f"以下是您電話號碼 {phone_number} 相關的訂位資訊：\n"
            for booking in matching_bookings:
                reply_text += f"\n姓名: {booking.get('name', 'N/A')}\n"
                reply_text += f"日期: {booking.get('date', 'N/A')}\n"
                reply_text += f"時間: {booking.get('time', 'N/A')}\n"
                reply_text += f"人數: {booking.get('persons', 'N/A')}\n"
            reply_text += "\n請輸入您要刪除的訂位編號，或輸入 '取消' 返回。"

        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply_text))
        return

    elif user_state["state"] == "waiting_for_reservation_id":
        print("--- 刪除訂位流程：等待訂位編號 ---")
        reservation_id_to_delete = user_query.strip().upper()

        if reservation_id_to_delete == '取消':
            reply_text = "已取消刪除訂位操作。"
            if user_id in delete_booking_states:
                del delete_booking_states[user_id]
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply_text))
            return

        service = order.get_calendar_service()
        if not service:
            reply_text = "無法連接 Google 行事曆服務，無法執行刪除操作。"
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply_text))
            # 清除狀態
            if user_id in delete_booking_states:
                del delete_booking_states[user_id]
            return

        found_booking = None
        for booking in user_state.get("bookings", []):
            if booking.get('reservation_code') == reservation_id_to_delete:
                found_booking = booking
                break

        if found_booking:
            print(f"找到匹配的訂位: {found_booking}")
            delete_success = order.delete_calendar_event(service, found_booking['id'])
            if delete_success:
                reply_text = f"訂位編號 {found_booking['reservation_code']} ({found_booking['date']} {found_booking['time']}) 已成功刪除。"
            else:
                reply_text = f"刪除訂位編號 {reservation_id_to_delete} 失敗，請稍後再試。"
        else:
            reply_text = f"找不到訂位編號為 {reservation_id_to_delete} 的訂位。請確認您輸入的編號是否正確，或輸入 '取消' 返回。"

        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply_text))
        if found_booking or "找不到訂位編號為" in reply_text:
             if user_id in delete_booking_states:
                 del delete_booking_states[user_id]
        return

    if any(keyword in user_query.lower() for keyword in ["訂位", "預約", "空閒時間", "預約時間", "取消訂位", "刪除訂位", "空位", "查空位", "位子"]):
        print("--- 偵測到訂位相關需求 ---")
        intent = rag_chain.classify_booking_intent(llm, user_query)

        if intent == '查詢空位':
            print("--- 意圖：查詢空位 ---")
            booking_info = order.get_formatted_available_slots()
            reply_text = f"{booking_info}"
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text=reply_text)
            )
        elif intent == '新增訂位':
            print("--- 意圖：新增訂位 ---")
            booking_result = rag_chain.process_booking_request(user_query, llm)
            
            if booking_result["status"] == "success":
                booking_data = booking_result["booking_data"]
                reservation_id = booking_result["reservation_id"]

                user_booking_states[user_id] = {
                    "booking_data": booking_data,
                    "reservation_id": reservation_id
                }

                confirm_message_text = f"請確認以下訂位資訊：\n" \
                                       f"姓名: {booking_data.get('name', 'N/A')}\n" \
                                       f"電話: {booking_data.get('phone', 'N/A')}\n" \
                                       f"人數: {booking_data.get('persons', 'N/A')}\n" \
                                       f"日期: {booking_data.get('reservation_date', 'N/A')}\n" \
                                       f"時間: {booking_data.get('reservation_time', 'N/A')}\n" \
                                       f"訂位編號: {reservation_id}\n" \
                                       f"用餐時間固定2小時。"

                flex_message_content = BubbleContainer(
                    direction='ltr',
                    hero=None,
                    body=BoxComponent(
                        layout='vertical',
                        contents=[
                            TextComponent(text='訂位資訊確認', weight='bold', size='md'),
                            SeparatorComponent(margin='md'),
                            TextComponent(text=confirm_message_text, wrap=True, margin='md'),
                            ButtonComponent(
                                style='primary',
                                height='sm',
                                action=PostbackAction(label='確定訂位', data=f'action=confirm_booking&user_id={user_id}&reservation_id={reservation_id}'),
                                margin='md'
                            ),
                            ButtonComponent(
                                style='secondary',
                                height='sm',
                                action=PostbackAction(label='取消訂位', data=f'action=cancel_booking&user_id={user_id}'),
                                margin='sm'
                            )
                        ]
                    )
                )
                line_bot_api.reply_message(
                    event.reply_token,
                    FlexSendMessage(alt_text="訂位資訊確認", contents=flex_message_content)
                )
            else:
                reply_text = booking_result["message"]
                line_bot_api.reply_message(
                    event.reply_token,
                    TextSendMessage(text=reply_text)
                )
        elif intent == '刪除訂位':
            print("--- 意圖：刪除訂位 ---")
            delete_booking_states[user_id] = {"state": "waiting_for_phone"}
            reply_text = "請提供您當初訂位的電話號碼，以便查詢您的訂位資訊。"
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply_text))
        else:
            print("--- 意圖：其他訂位相關 ---")
            # 將 qa_chain 替換為 qa_chain_for_user
            answer = rag_chain.ask_question_and_get_answer(user_query, qa_chain_for_user, retriever)
            reply_text = answer if answer else "抱歉，我無法理解您的訂位請求，請提供更詳細的資訊。"
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text=reply_text)
            )
    else:
        print("--- 意圖：一般問答 ---")
        # 將 qa_chain 替換為 qa_chain_for_user
        answer = rag_chain.ask_question_and_get_answer(user_query, qa_chain_for_user, retriever)
        reply_text = answer if answer else "抱歉，我無法回答您的問題。請嘗試換個方式提問。"
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=reply_text)
        )

@handler.add(PostbackEvent)
def handle_postback(event):
    user_id = event.source.user_id
    postback_data = event.postback.data
    print(f"收到來自用戶 {user_id} 的 Postback 事件: {postback_data}")

    import urllib.parse
    params = urllib.parse.parse_qs(postback_data)
    action = params.get('action', [None])[0]
    
    if action == 'confirm_booking':
        reservation_id = params.get('reservation_id', [None])[0]
        if user_id in user_booking_states and user_booking_states[user_id]["reservation_id"] == reservation_id:
            booking_data = user_booking_states[user_id]["booking_data"]
            add_result = rag_chain.add_booking_to_calendar(booking_data, reservation_id)
            reply_text = add_result["message"]
            
            del user_booking_states[user_id]
        else:
            reply_text = "訂位資訊已過期或無效，請重新發起訂位請求。"
        
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=reply_text)
        )

    elif action == 'cancel_booking':
        if user_id in user_booking_states:
            del user_booking_states[user_id]
            reply_text = "訂位已取消。感謝您的使用。"
        else:
            reply_text = "沒有待確認的訂位資訊可供取消。"
        
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=reply_text)
        )
    else:
        reply_text = "未知 Postback 動作。"
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=reply_text)
        )

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080))) # 將端口設定為 8080