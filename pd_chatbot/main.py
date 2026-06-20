from fastapi import FastAPI, Request
import httpx
import os

app = FastAPI()

POCKETBASE_URL = os.getenv("POCKETBASE_URL", "http://pocketbase:8090")

@app.get("/")
def read_root():
    return {"status": "AI Chatbot API Server is running"}

@app.post("/webhook")
async def pocketbase_webhook(request: Request):
    """
    PocketBase에서 메시지가 생성되면 호출되는 웹훅 엔드포인트
    """
    data = await request.json()
    
    # PocketBase의 웹훅 데이터 구조에 따라 파싱 (버전에 따라 상이할 수 있음)
    record = data.get("record", {})
    text = record.get("text", "")
    sender_id = record.get("user_id", "")
    room_id = record.get("room", "general")
    
    # 무한 루프 방지: 만약 발신자가 봇(Bot) 자신이라면 응답하지 않음
    if sender_id == "bot_user_id_placeholder":
        return {"status": "ignored_bot_message"}
        
    # [AI 처리 영역] 여기에 LLM 모델 호출 로직을 넣으시면 됩니다.
    ai_response = f"[AI 봇 답변] '{text}'라고 말씀하셨군요. 이 부분에 AI 엔진을 연동하세요."
    
    # PocketBase REST API를 통해 채팅방에 AI 답변 추가
    async with httpx.AsyncClient() as client:
        url = f"{POCKETBASE_URL}/api/collections/messages/records"
        payload = {
            "text": ai_response,
            "user_id": "bot_user_id_placeholder", # PocketBase에 등록한 봇 계정 ID
            "room": room_id
        }
        try:
            response = await client.post(url, json=payload)
            return {"status": "success", "pocketbase_response": response.status_code}
        except Exception as e:
            return {"status": "error", "detail": str(e)}
