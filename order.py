import datetime
from datetime import timedelta, time, datetime as dt_obj, timezone
from dateutil.relativedelta import relativedelta
from dateutil import parser # 新增：導入 parser
import pytz
import uuid
import re
import traceback

from google.auth import default # 導入 default 函數
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow, Flow # 導入 InstalledAppFlow 和 Flow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import os

SCOPES = ['https://www.googleapis.com/auth/calendar']
TOKEN_FILE = 'token.json'
CREDENTIALS_FILE = 'credentials.json'

def get_calendar_service():
    """
    獲取 Google Calendar API 服務物件。
    優先使用 token.json 憑證，如果不存在或過期則重新認證。
    在 Cloud Run 環境中，這將自動使用服務帳戶憑證作為備用。
    """
    creds = None

    # 嘗試從 token.json 載入憑證
    if os.path.exists(TOKEN_FILE):
        try:
            creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
            print("  [Debug] 憑證從 token.json 載入成功。")
        except Exception as e:
            print(f"  [Debug] 從 token.json 載入憑證失敗: {e}，將嘗試重新認證。")
            creds = None

    # 如果沒有憑證或憑證無效/過期，則進行認證
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            print("  [Debug] 憑證已過期，嘗試刷新。")
            try:
                creds.refresh(Request())
                print("  [Debug] 憑證刷新成功。")
            except Exception as e:
                print(f"  [Debug] 憑證刷新失敗: {e}，將嘗試重新認證。")
                creds = None
        
        if not creds or not creds.valid: # 再次檢查，如果刷新失敗則重新認證
            print("  [Debug] 憑證無效或不存在，將啟動本地認證流程。")
            try:
                flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
                creds = flow.run_local_server(port=0)
                # 將憑證儲存到 token.json
                with open(TOKEN_FILE, 'w') as token:
                    token.write(creds.to_json())
                print("  [Debug] 新憑證已儲存到 token.json。")
            except Exception as e:
                print(f"  [錯誤] 本地認證流程失敗: {e}")
                traceback.print_exc()
                # 如果本地認證失敗，嘗試使用 default() 憑證 (適用於 Cloud Run)
                print("  [Debug] 嘗試使用 google.auth.default() 獲取憑證。")
                try:
                    creds, project = default(scopes=SCOPES)
                    print(f"  [Debug] 憑證獲取成功 (default)。專案: {project}")
                except Exception as default_error:
                    print(f'  [錯誤] 連接 Google 行事曆服務時發生錯誤 (default): {default_error}')
                    traceback.print_exc()
                    return None

    if creds:
        try:
            service = build('calendar', 'v3', credentials=creds)
            print("  [Debug] Google Calendar 服務物件建立成功。")
            return service
        except Exception as error:
            print(f'  [錯誤] 建立 Google Calendar 服務物件時發生錯誤: {error}')
            traceback.print_exc()
            return None
    else:
        print("  [錯誤] 無法獲取 Google Calendar 憑證。")
        return None

def _extract_reservation_id_from_event(event) -> str | None:
    summary = event.get('summary', '')
    description = event.get('description', '')

    if '訂位編號:' in summary:
        parts = summary.split('訂位編號:')
        if len(parts) > 1:
            reservation_id_raw = parts[1].strip().split(' ')[0]
            return reservation_id_raw.upper()

    if '訂位編號:' in description:
        for line in description.split('\n'):
            if '訂位編號:' in line:
                parts = line.split('訂位編號:')
                if len(parts) > 1:
                    return parts[1].strip().upper()
    return None

def get_current_month_events(service, calendar_id: str = 's6663296@gmail.com'):
    taipei_tz = pytz.timezone('Asia/Taipei')
    now_local = dt_obj.now(taipei_tz)

    time_min = now_local
    time_max = now_local + relativedelta(months=1)

    print(f"正在獲取從 {time_min.isoformat()} 到 {time_max.isoformat()} 的事件")

    events_result = service.events().list(calendarId=calendar_id,
                                          timeMin=time_min.isoformat(),
                                          timeMax=time_max.isoformat(),
                                          singleEvents=True,
                                          orderBy='startTime').execute()
    events = events_result.get('items', [])
    return events, time_min, time_max

def find_free_slots_in_month(service, events, time_min, time_max, calendar_id: str = 's6663296@gmail.com', max_bookings: int = 3):
    """
    尋找從 time_min 到 time_max 之間每天早上10點到下午4點之間未安排的時間段。
    Args:
        service: Google Calendar API 服務物件。
        events: 當月的所有事件。
        time_min: 查詢的開始時間。
        time_max: 查詢的結束時間。
    Returns:
        dict: 包含可用時段的字典。
    """
    free_slots_by_date = {}
    current_date = time_min.date()

    taipei_tz = pytz.timezone('Asia/Taipei')

    while current_date <= time_max.date():
        day_start_time_local = taipei_tz.localize(dt_obj.combine(current_date, time(10, 0, 0)))
        day_end_time_local = taipei_tz.localize(dt_obj.combine(current_date, time(16, 0, 0)))

        current_day_free_slots = [(day_start_time_local, day_end_time_local)]

        events_for_current_day = []
        for event in events:
            event_start_str = event['start'].get('dateTime')
            event_end_str = event['end'].get('dateTime')

            if event_start_str:
                try:

                    event_start = parser.isoparse(event_start_str) # 使用 dateutil.parser.isoparse
                    event_end = parser.isoparse(event_end_str) # 使用 dateutil.parser.isoparse

                    event_start = event_start.astimezone(taipei_tz)
                    event_end = event_end.astimezone(taipei_tz)

                    if event_start.date() == current_date or event_end.date() == current_date:
                        events_for_current_day.append((event_start, event_end))
                except ValueError:
                    print(f"警告：無法解析事件時間：{event_start_str} - {event_end_str}")
            else:
                event_date_str = event['start'].get('date')
                event_date = dt_obj.strptime(event_date_str, '%Y-%m-%d').date()
                if event_date == current_date:
                    events_for_current_day.append((day_start_time_local, day_end_time_local))


        events_for_current_day.sort()

        for event_start, event_end in events_for_current_day:
            clipped_event_start = max(event_start, day_start_time_local)
            clipped_event_end = min(event_end, day_end_time_local)

            if clipped_event_start >= clipped_event_end:
                continue

            new_free_slots = []
            
            for free_start, free_end in current_day_free_slots:
                if clipped_event_end <= free_start or clipped_event_start >= free_end:
                    new_free_slots.append((free_start, free_end))
                elif clipped_event_start <= free_start and clipped_event_end >= free_end:
                    pass
                else:
                    if free_start < clipped_event_start:
                        new_free_slots.append((free_start, clipped_event_start))
                    if free_end > clipped_event_end:
                        new_free_slots.append((clipped_event_end, free_end))
            
            current_day_free_slots = new_free_slots

        # 本地計算空閒時段，避免多次API調用
        filtered_slots = []
        max_bookings = 3  # 最大預訂數設定
        
        for slot_start, slot_end in current_day_free_slots:
            if (slot_end - slot_start).total_seconds() > 60:
                # 計算該時段內的重疊事件數
                overlapping_count = 0
                for event_start, event_end in events_for_current_day:
                    if slot_start < event_end and slot_end > event_start:
                        overlapping_count += 1
                
                # 檢查是否小於最大預訂數
                if overlapping_count < max_bookings:
                    filtered_slots.append((slot_start, slot_end))
        
        if filtered_slots:
            free_slots_by_date[current_date] = filtered_slots
        
        current_date += timedelta(days=1)
    
    return free_slots_by_date

def get_formatted_available_slots(calendar_id: str = 's6663296@gmail.com'):
    print("  [訂位模式] 正在連接 Google 行事曆 API...")
    service = get_calendar_service()
    if not service:
        return "無法連接 Google 行事曆服務。請檢查您的憑證和網路連線。"

    print("  [訂位模式] 正在取得行事曆事件...")
    events, time_min_range, time_max_range = get_current_month_events(service, calendar_id=calendar_id)
    
    taipei_tz = pytz.timezone('Asia/Taipei')
    now_local = dt_obj.now(taipei_tz)
    
    response_text = "以下是未來一個月內，早上10點到下午4點之間可供預約的2小時時段：\n"
    available_slots_found = False
    max_bookings_per_slot = 3 # 每個2小時時段的最大預訂組數
    slot_interval_minutes = 30 # 時段檢查粒度：每30分鐘

    # 遍歷未來一個月
    for i in range(30): # 檢查未來30天
        current_date = now_local.date() + timedelta(days=i)
        
        # 排除過去的日期
        if current_date < now_local.date():
            continue

        day_slots = []
        # 生成當天從10:00到14:00的每個30分鐘開始的2小時時段
        # 最晚開始時間是14:00，因為預約持續2小時，結束時間是16:00
        for hour in range(10, 16):
            for minute in range(0, 60, slot_interval_minutes):
                slot_start_time_naive = dt_obj.combine(current_date, time(hour, minute, 0))
                slot_end_time_naive = slot_start_time_naive + timedelta(hours=2)

                # 確保結束時間不超過下午4點
                if slot_end_time_naive.time() > time(16, 0, 0):
                    continue

                slot_start_time = taipei_tz.localize(slot_start_time_naive)
                slot_end_time = taipei_tz.localize(slot_end_time_naive)

                # 檢查時段是否已過
                if slot_end_time <= now_local:
                    continue

                # 計算該2小時時段內的重疊事件數
                overlapping_bookings = 0
                for event in events:
                    event_start_str = event['start'].get('dateTime')
                    event_end_str = event['end'].get('dateTime')

                    if event_start_str and event_end_str:
                        try:
                            event_start = parser.isoparse(event_start_str).astimezone(taipei_tz)
                            event_end = parser.isoparse(event_end_str).astimezone(taipei_tz)

                            # 檢查事件是否與當前2小時時段重疊
                            if slot_start_time < event_end and slot_end_time > event_start:
                                overlapping_bookings += 1
                        except ValueError:
                            print(f"警告：無法解析事件時間：{event_start_str} - {event_end_str}")
                
                print(f"  [Debug] 在 {slot_start_time.strftime('%Y-%m-%d %H:%M')} - {slot_end_time.strftime('%H:%M')} 時段內，已存在 {overlapping_bookings} 個訂位。")

                if overlapping_bookings < max_bookings_per_slot:
                    day_slots.append((slot_start_time, slot_end_time))
                    available_slots_found = True
        
        if day_slots:
            response_text += f"\n日期: {current_date.strftime('%Y年%m月%d日')}\n"
            # 對當天的可用時段進行排序
            day_slots.sort()
            for start, end in day_slots:
                response_text += f"  {start.strftime('%H:%M')} - {end.strftime('%H:%M')}\n"
    
    if not available_slots_found:
        response_text = "此期間早上10點到下午4點之間沒有可供預約的2小時時段。"

    return response_text

def add_calendar_event(name: str, reservation_datetime_str: str, persons: int, phone: str, reservation_id: str, calendar_id: str = 'primary') -> str:
    service = get_calendar_service()
    if not service:
        return "無法連接 Google 行事曆服務，無法新增訂位。"

    try:
        taipei_tz = pytz.timezone('Asia/Taipei')
        # 修正：使用 dateutil.parser.isoparse 處理帶有 'Z' 的 ISO 格式字串
        start_time_naive = parser.isoparse(reservation_datetime_str)
        start_time = taipei_tz.localize(start_time_naive)
        end_time = start_time + timedelta(hours=2)

        event = {
            'summary': f'訂位編號: {reservation_id} - 餐廳訂位: {name} ({persons}人)',
            'location': '您的餐廳地址',
            'description': f'訂位編號: {reservation_id}\n訂位人: {name}\n電話: {phone}\n人數: {persons}',
            'start': {
                'dateTime': start_time.isoformat(),
                'timeZone': 'Asia/Taipei',
            },
            'end': {
                'dateTime': end_time.isoformat(),
                'timeZone': 'Asia/Taipei',
            },
            'reminders': {
                'useDefault': False,
                'overrides': [
                    {'method': 'email', 'minutes': 24 * 60},
                    {'method': 'popup', 'minutes': 60},
                ],
            },
        }

        event = service.events().insert(calendarId=calendar_id, body=event).execute()
        return f"訂位成功！\n訂位編號：{reservation_id}\n訂位人：{name}\n時間：{start_time.strftime('%Y年%m月%d日 %H:%M')}\n人數：{persons}。"

    except HttpError as error:
        print(f'新增 Google 行事曆事件時發生錯誤: {error}')
        return f'新增訂位失敗：{error}'
    except Exception as e:
        print(f'新增訂位時發生未知錯誤: {e}')
        traceback.print_exc()
        return f'新增訂位失敗：{e}'

def check_slot_availability(start_time: dt_obj, end_time: dt_obj, max_bookings: int = 3, calendar_id: str = 's6663296@gmail.com') -> tuple[bool, str]:
    service = get_calendar_service()
    if not service:
        return False, "無法連接 Google 行事曆服務，無法檢查訂位空位。"

    try:
        events_result = service.events().list(calendarId=calendar_id,
                                              timeMin=start_time.isoformat(),
                                              timeMax=end_time.isoformat(),
                                              singleEvents=True,
                                              orderBy='startTime').execute()
        events = events_result.get('items', [])

        overlapping_bookings = 0
        for event in events:
            event_start_str = event['start'].get('dateTime')
            event_end_str = event['end'].get('dateTime')

            if event_start_str and event_end_str:
                event_start = parser.isoparse(event_start_str).astimezone(start_time.tzinfo) # 使用 dateutil.parser.isoparse
                event_end = parser.isoparse(event_end_str).astimezone(end_time.tzinfo) # 使用 dateutil.parser.isoparse

                if start_time < event_end and end_time > event_start:
                    overlapping_bookings += 1
        
        print(f"  [Debug] 在 {start_time.strftime('%Y-%m-%d %H:%M')} - {end_time.strftime('%H:%M')} 時段內，已存在 {overlapping_bookings} 個訂位。")

        if overlapping_bookings >= max_bookings:
            return False, f"該時段 (從 {start_time.strftime('%H:%M')} 到 {end_time.strftime('%H:%M')}) 已有 {overlapping_bookings} 組訂位，已達上限 ({max_bookings} 組)。請選擇其他時間。"
        else:
            return True, ""

    except HttpError as error:
        print(f'檢查 Google 行事曆空位時發生錯誤: {error}')
        return False, f'檢查訂位空位失敗：{error}'
    except Exception as e:
        print(f'檢查訂位空位時發生未知錯誤: {e}')
        traceback.print_exc()
        return False, f'檢查訂位空位失敗：{e}'

def find_bookings_by_phone(service, phone: str, calendar_id: str = 's6663296@gmail.com') -> list[dict]:
    taipei_tz = pytz.timezone('Asia/Taipei')
    now_local = dt_obj.now(taipei_tz)
    time_max = now_local + relativedelta(months=1)

    events_result = service.events().list(calendarId=calendar_id,
                                          timeMin=now_local.isoformat(),
                                          timeMax=time_max.isoformat(),
                                          singleEvents=True,
                                          orderBy='startTime').execute()
    events = events_result.get('items', [])

    matching_bookings = []
    for event in events:
        description = event.get('description', '')
        summary = event.get('summary', '')
        
        if phone in description or phone in summary:
            event_id = event.get('id')
            event_summary = event.get('summary', '無標題')
            event_start = event['start'].get('dateTime', event['start'].get('date'))
            
            name = "未知"
            persons = "未知"
            reservation_code = _extract_reservation_id_from_event(event)
            
            if '餐廳訂位:' in event_summary:
                try:
                    parts = event_summary.split('餐廳訂位:')
                    if len(parts) > 1:
                        name_persons_part = parts[1].strip()
                        name_match = re.search(r'^(.*?)\s*\((\d+)人\)', name_persons_part)
                        if name_match:
                            name = name_match.group(1).strip()
                            persons = int(name_match.group(2))
                        else:
                            name = name_persons_part.split('(')[0].strip()
                except Exception as e:
                    print(f"解析 summary 失敗: {e}")

            if event_start:
                try:
                    if 'T' in event_start:
                        # 修正：使用 dateutil.parser.isoparse 處理帶有 'Z' 的 ISO 格式字串
                        start_dt = parser.isoparse(event_start).astimezone(taipei_tz)
                        date_str = start_dt.strftime('%Y年%m月%d日')
                        time_str = start_dt.strftime('%H:%M')
                    else:
                        start_dt = dt_obj.strptime(event_start, '%Y-%m-%d').date()
                        date_str = start_dt.strftime('%Y年%m月%d日')
                        time_str = "全天"
                except ValueError:
                    date_str = "無法解析日期"
                    time_str = "無法解析時間"
            else:
                date_str = "無日期"
                time_str = "無時間"

            matching_bookings.append({
                'id': event_id,
                'name': name,
                'date': date_str,
                'time': time_str,
                'persons': persons,
                'reservation_code': reservation_code
            })
    return matching_bookings

def find_booking_by_reservation_id(service, reservation_id: str, calendar_id: str = 's6663296@gmail.com') -> dict | None:
    taipei_tz = pytz.timezone('Asia/Taipei')
    now_local = dt_obj.now(taipei_tz)
    time_max = now_local + relativedelta(months=1)

    events_result = service.events().list(calendarId=calendar_id,
                                          timeMin=now_local.isoformat(),
                                          timeMax=time_max.isoformat(),
                                          q=f'"{reservation_id}"',
                                          singleEvents=True,
                                          orderBy='startTime').execute()
    events = events_result.get('items', [])

    for event in events:
        extracted_id = _extract_reservation_id_from_event(event)
        if extracted_id and extracted_id.upper() == reservation_id.upper():
            event_id = event.get('id')
            event_summary = event.get('summary', '無標題')
            event_start = event['start'].get('dateTime', event['start'].get('date'))

            date_str, time_str = "無日期", "無時間"
            if event_start:
                try:
                    # 修正：使用 dateutil.parser.isoparse 處理帶有 'Z' 的 ISO 格式字串
                    start_dt = parser.isoparse(event_start).astimezone(taipei_tz) if 'T' in event_start else dt_obj.strptime(event_start, '%Y-%m-%d').date()
                    date_str = start_dt.strftime('%Y年%m月%d日') if isinstance(start_dt, dt_obj) else start_dt.strftime('%Y年%m月%d日')
                    time_str = start_dt.strftime('%H:%M') if isinstance(start_dt, dt_obj) else "全天"
                except ValueError:
                    pass

            return {
                'id': event_id,
                'name': event_summary.split(' - ')[-1].split('(')[0].strip() if ' - ' in event_summary else '未知',
                'date': date_str,
                'time': time_str,
                'persons': int(re.search(r'\((\d+)人\)', event_summary).group(1)) if re.search(r'\((\d+)人\)', event_summary) else '未知',
                'reservation_code': extracted_id
            }

    return None

def delete_calendar_event(service, event_id: str, calendar_id: str = 's6663296@gmail.com') -> bool:
    try:
        service.events().delete(calendarId=calendar_id, eventId=event_id).execute()
        print(f"事件 {event_id} 已成功刪除。")
        return True
    except HttpError as error:
        if error.resp.status == 404:
            print(f"錯誤：找不到事件 ID {event_id}。")
        else:
            print(f"刪除 Google 行事曆事件時發生錯誤: {error}")
        return False
    except Exception as e:
        print(f"刪除事件時發生未知錯誤: {e}")
        traceback.print_exc()
        return False

def update_calendar_event(service, event_id: str, updated_event_body: dict, calendar_id: str = 's6663296@gmail.com') -> bool:
    try:
        service.events().update(calendarId=calendar_id, eventId=event_id, body=updated_event_body).execute()
        print(f"事件 {event_id} 已成功更新。")
        return True
    except HttpError as error:
        print(f'更新 Google 行事曆事件時發生錯誤: {error}')
        return False
    except Exception as e:
        print(f'更新事件時發生未知錯誤: {e}')
        traceback.print_exc()
        return False