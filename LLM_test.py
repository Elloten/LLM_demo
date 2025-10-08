##################
# LLM簡易測試
##################

import requests
import json
import sys

# vLLM API 服務配置
API_BASE_URL = "http://8.218.131.141:2042/v1"
API_KEY = "EMPTY"

def send_message(system_prompt, user_message):
    """發送訊息並接收回應"""
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message}
    ]
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {API_KEY}"
    }
    
    data = {
        "model": "/mnt/model/",
        "messages": messages,
        "max_tokens": 4000,
        "temperature": 1.2,
        "stream": True
    }
    
    print(f"🤖 AI 回應: ", end="", flush=True)
    
    try:
        response = requests.post(f"{API_BASE_URL}/chat/completions", 
                               headers=headers, 
                               json=data,
                               stream=True)
        
        if response.status_code == 200:
            assistant_response = ""
            
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
                                    assistant_response += content
                        except json.JSONDecodeError:
                            continue
            
            print()  # 換行
            return assistant_response
            
        else:
            print(f"❌ 錯誤: {response.status_code}")
            print(f"響應內容: {response.text}")
            return None
            
    except Exception as e:
        print(f"❌ 請求失敗: {e}")
        return None

def test_api_connection():
    """測試 API 連接"""
    print("🔍 測試 API 連接...")
    try:
        response = requests.get(f"{API_BASE_URL}/models", timeout=5)
        if response.status_code == 200:
            print("✅ API 連接成功！")
            return True
        else:
            print(f"❌ API 連接失敗: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ 無法連接到 API: {e}")
        print("💡 請確認 vLLM 服務是否正在運行")
        return False

if __name__ == "__main__":
    # 測試 API 連接
    if not test_api_connection():
        print("\n❌ 無法連接到 API，程式結束")
        sys.exit(1)
    
    # 硬編碼的 prompt 和使用者輸入
    system_prompt = """
    你是紡織業者的窗口, 工作是與客戶接洽, 你必須根據客戶寄送的email, 進行重點整理, 並擬定草稿。
    規則：
    1. 若是英文的信件, 則使用英文回覆, 否則必須使用繁體中文。
    2. 對email以繁體中文進行重點整理
    3. 擬定草稿
    """

    user_message = """
    客戶來信：
    您好，我們是一家位於台北的服裝製造商，正在尋找優質的棉質布料供應商。
    我們需要以下規格的布料：
    - 100% 純棉
    - 重量：180-200 GSM
    - 顏色：白色、黑色、海軍藍
    - 數量：每月約 5000 碼
    - 交貨期：30 天內
    
    請提供報價和樣品，謝謝。
    """
    
    print("=" * 60)
    print("📧 客戶來信:")
    print("-" * 40)
    print(user_message)
    print("-" * 40)
    
    # 發送訊息並獲取回應
    response = send_message(system_prompt, user_message)
    
    if response:
        print("\n✅ 處理完成！")
    else:
        print("\n❌ 處理失敗！")
