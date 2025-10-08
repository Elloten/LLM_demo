# -*- coding: utf-8 -*-
import sys
import io
import re

# 設定輸出編碼為 UTF-8
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
import base64
import email
from email.message import EmailMessage  #  需要確保您有這個 import 
import os
import requests
import json

# 取得讀取、草稿寫入及發送郵件權限
SCOPES = [
    'https://www.googleapis.com/auth/gmail.readonly',  # 查看你的電子郵件和設定
    'https://www.googleapis.com/auth/gmail.compose',   # 管理草稿和傳送電子郵件
    'https://www.googleapis.com/auth/gmail.modify',    # 修改郵件（包含在 token.json 中）
    # 'https://mail.google.com/'                         # 完整 Gmail 存取權限（包含在 token.json 中）
]

# LLM API 配置
LLM_API_BASE_URL = "http://8.218.131.141:2042/v1"
LLM_API_KEY = "EMPTY"

def get_gmail_service():
    creds = None
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    service = build('gmail', 'v1', credentials=creds)
    return service

def list_labels(service):
    """取得所有可用的標籤"""
    results = service.users().labels().list(userId='me').execute()
    labels = results.get('labels', [])
    return labels

def list_messages(service, label_ids=None, max_results=5):
    """取得指定標籤的郵件列表"""
    if label_ids is None:
        label_ids = ['INBOX']
    
    results = service.users().messages().list(
        userId='me', 
        labelIds=label_ids, 
        maxResults=max_results
    ).execute()
    messages = results.get('messages', [])
    return messages

def get_message_detail(service, msg_id):
    msg = service.users().messages().get(userId='me', id=msg_id, format='full').execute()
    payload = msg['payload']
    headers = payload.get('headers', [])

    #  增加 message_id 的初始化 
    subject = sender = message_id = ''
    for header in headers:
        if header['name'] == 'Subject':
            subject = header['value']
        if header['name'] == 'From':
            sender = header['value']
        #  擷取 Message-ID 
        if header['name'] == 'Message-ID': 
            message_id = header['value']

    # 嘗試取得郵件內容
    body = ''
    if 'parts' in payload:
        for part in payload['parts']:
            if part['mimeType'] == 'text/plain':
                data = part['body']['data']
                body = base64.urlsafe_b64decode(data).decode('utf-8')
                break
    elif payload['body'] and 'data' in payload['body']:
        data = payload['body']['data']
        body = base64.urlsafe_b64decode(data).decode('utf-8')

    return {
        'subject': subject,
        'from': sender,
        'message_id': message_id, #  回傳 Message-ID 
        'body': body
    }

def get_messages_by_category(service, label_ids, max_results=5):
    """取得指定標籤的郵件"""
    # 標籤 ID 對應的中文名稱
    label_names = {
        'INBOX': '收件匣',
        'SENT': '已傳送', 
        'DRAFT': '草稿',
        'TRASH': '垃圾桶',
        'SPAM': '垃圾郵件',
        'CATEGORY_PERSONAL': '主要分頁',
        'CATEGORY_PROMOTIONS': '促銷內容分頁',
        'CATEGORY_SOCIAL': '社交網路分頁',
        'CATEGORY_UPDATES': '更新分頁',
        'CATEGORY_FORUMS': '論壇分頁'
    }
    
    # 取得顯示名稱
    first_label = label_ids[0] if label_ids else 'UNKNOWN'
    display_name = label_names.get(first_label, first_label)
    
    print(f"\n🔍 正在取得 {display_name} 的郵件...")
    messages = list_messages(service, label_ids, max_results)
    
    if not messages:
        print(f"❌ {display_name} 中沒有找到郵件")
        return
    
    print(f"📬 找到 {len(messages)} 封 {display_name} 郵件:")
    print("=" * 60)
    
    return messages

def find_label_id(labels, label_name):
    """根據標籤名稱找到對應的 ID"""
    for label in labels:
        if label['name'] == label_name:
            return label['id']
    return None

def extract_reply_content(reply_text):
    """從 reply_text 中提取 <reply> 和 </reply> 標籤之間的內容"""
    reply_text = reply_text.split('<reply>')[-1].split('</reply>')[0]
    return reply_text

def generate_llm_reply(original_subject, original_sender, original_body):
    """使用 LLM 生成智能回覆內容"""
    system_prompt = """
    你是紡織業者的窗口, 工作是與客戶接洽, 你必須根據客戶寄送的email, 進行重點整理, 並擬定草稿。
    規則：
    1. 若是英文的信件, 則使用英文回覆, 否則必須使用繁體中文。
    2. 對email以繁體中文進行重點整理
    3. 擬定草稿
    4. 必須符合台灣當地的用語和習慣, 不要使用不適合的用語, 並保持專業性和禮貌。
    """
    
    user_prompt = f"""
    請分析以下郵件並生成回覆草稿：

    主題: {original_subject}
    寄件人: {original_sender}
    內容: {original_body}

    請提供：
    1. 郵件重點整理（繁體中文）
    2. 專業的回覆草稿, 並以 <reply> 標籤包起來
    """
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {LLM_API_KEY}"
    }
    
    data = {
        "model": "/mnt/model/",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        "max_tokens": 4000,
        "temperature": 0.7,
        "stream": True  # 啟用流式輸出
    }
    
    try:
        print("🤖 正在使用 AI 生成回覆內容...")
        print("💭 AI 思考過程:")
        print("=" * 60)
        
        response = requests.post(f"{LLM_API_BASE_URL}/chat/completions", 
                               headers=headers, 
                               json=data,
                               timeout=60,
                               stream=True)
        
        if response.status_code == 200:
            ai_reply = ""
            
            # 處理流式響應
            for line in response.iter_lines():
                if line:
                    line = line.decode('utf-8')
                    if line.startswith('data: '):
                        data_content = line[6:]
                        
                        if data_content.strip() == '[DONE]':
                            break
                        
                        try:
                            chunk = json.loads(data_content)
                            if 'choices' in chunk and len(chunk['choices']) > 0:
                                delta = chunk['choices'][0].get('delta', {})
                                if 'content' in delta:
                                    content = delta['content']
                                    print(content, end='', flush=True)
                                    ai_reply += content
                        except json.JSONDecodeError:
                            continue
            
            print("\n" + "=" * 60)
            print("✅ AI 回覆內容生成完成")
            return ai_reply
            
        else:
            print(f"❌ LLM API 錯誤: {response.status_code}")
            print(f"響應內容: {response.text}")
            return None
            
    except Exception as e:
        print(f"❌ LLM 請求失敗: {e}")
        return None

def create_reply_draft(service, original_msg_id, reply_text=None):
    """建立回覆信件的草稿（使用 LLM 生成智能回覆內容）"""
    # 取得原始郵件的詳細資訊
    original_msg = service.users().messages().get(userId='me', id=original_msg_id, format='minimal').execute()
    original_detail = get_message_detail(service, original_msg_id)
    
    # 從寄件人資訊中提取電子郵件地址
    from_email = original_detail['from']
    if '<' in from_email and '>' in from_email:
        from_email = from_email.split('<')[1].split('>')[0]
    
    # 建立回覆主題
    reply_subject = original_detail['subject']
    if not reply_subject.startswith('Re: '):
        reply_subject = f"Re: {reply_subject}"
        
    # 確保取得原始郵件的 Message-ID
    original_message_id = original_detail.get('message_id')
    if not original_message_id:
        raise ValueError("無法取得原始郵件的 Message-ID，無法進行標準回覆。")

    # === 使用 LLM 生成智能回覆內容 ===
    if reply_text is None:
        # 使用 LLM 生成回覆內容
        ai_reply = generate_llm_reply(
            original_detail['subject'],
            original_detail['from'],
            original_detail['body']
        )
        
        if ai_reply:
            # 提取 <reply> 標籤之間的內容
            reply_text = extract_reply_content(ai_reply)
            print(f"\n📝 AI 生成的回覆內容:\n{'-' * 50}")
            print(reply_text)
            print(f"{'-' * 50}")
        else:
            # 如果 LLM 失敗，使用預設回覆
            reply_text = "感謝您的來信，我會盡快回覆。"
            print("⚠️ LLM 生成失敗，使用預設回覆內容")
    else:
        # 如果提供了 reply_text，也嘗試提取 <reply> 標籤內容
        reply_text = extract_reply_content(reply_text)
    
    # 1. 建立回覆內容（可以加入原始郵件的引用）
    full_reply_text = f"""
{reply_text}

---
原始郵件：
主題: {original_detail['subject']}
寄件人: {original_detail['from']}
內容摘要: {original_detail['body']}...
"""
    
    reply_message = EmailMessage()
    reply_message.set_content(full_reply_text)
    
    # 2. 設定標準 Headers
    reply_message['To'] = from_email
    reply_message['Subject'] = reply_subject
    
    # 3. 設定讓郵件歸入同一討論串的關鍵 Headers
    # In-Reply-To 設為原始郵件的 Message-ID
    reply_message['In-Reply-To'] = original_message_id
    # References 設為原始郵件的 Message-ID (或整個對話串的 ID 鏈)
    reply_message['References'] = original_message_id
    
    # 4. 取得 Raw 內容並編碼
    encoded_message = base64.urlsafe_b64encode(reply_message.as_bytes()).decode()
    
    # 5. 建立草稿
    draft = service.users().drafts().create(
        userId='me',
        body={
            'message': {
                'raw': encoded_message,
                'threadId': original_msg.get('threadId') # 保持在同一對話串中的關鍵步驟
            }
        }
    ).execute()
    
    return draft

def main():
    # 初始化服務, 固定寫法
    service = get_gmail_service()
    
    # 首先列出所有可用的標籤
    print("🏷️  可用的 Gmail 標籤:")
    labels = list_labels(service)
    for label in labels:
        print(f"  - {label['name']} (ID: {label['id']})")
    
    print("\n" + "=" * 80)
    
    # 取得收件匣的郵件
    inbox_messages = get_messages_by_category(
        service, 
        ["INBOX"], # 這邊可以自己修改ID, 此程式碼執行時可以查看可用的 Gmail 標籤(CHAT, SENT, DRAFT, TRASH, SPAM, CATEGORY_PERSONAL, CATEGORY_PROMOTIONS, CATEGORY_SOCIAL, CATEGORY_UPDATES, CATEGORY_FORUMS)
        max_results=10 # 讀取幾封
    )

    elloten_email = -1
    for i, msg in enumerate(inbox_messages):
        detail = get_message_detail(service, msg['id'])
        print(f"\n📧 [{i}] 主題: {detail['subject']}")
        print(f"👤 寄件人: {detail['from']}")
        print(f"📝 內容摘要:\n{detail['body'][:200]}...")  # 顯示前 200 字
        print('-' * 50)

        if detail['from'].lower().find('elloten')!= -1:
            elloten_email = i


    print("=" * 60)
    
    # 回覆elloten的郵件 (不加則擷取最新的email)
    if elloten_email != -1:
        first_msg = inbox_messages[elloten_email]
        detail = get_message_detail(service, first_msg['id'])
        print(f"\n📧 正在為以下郵件處理回覆:")
        print(f"主題: {detail['subject']}")
        print(f"寄件人: {detail['from']}")
        print(f"內容摘要: {detail['body'][:200]}...")
        
        # 建立回覆草稿（使用 LLM 生成智能回覆）
        draft = create_reply_draft(service, first_msg['id'])
        print(f"✅ 回覆草稿已建立: {draft['id']}")
        print("📝 您可以在 Gmail 中編輯並發送這個草稿")
    else:
        print("❌ 沒有找到elloten的郵件")
                
if __name__ == '__main__':
    main()