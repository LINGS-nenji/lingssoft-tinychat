import os
import httpx
from fastapi import FastAPI, Request

app = FastAPI()

POCKETBASE_URL = os.getenv("POCKETBASE_URL", "http://pocketbase:8090")
AI_MODEL_URL = os.getenv("AI_MODEL_URL", "").strip()
AI_MODEL_TIMEOUT = float(os.getenv("AI_MODEL_TIMEOUT", "30"))
BOT_USER_ID = os.getenv("BOT_USER_ID", "bot_user_id_placeholder")


async def generate_ai_response(text: str, sender_id: str, room_id: str) -> str:
    if not AI_MODEL_URL:
        return f"[AI 봇 답변] '{text}'라고 말씀하셨군요. 이 부분에 AI 엔진을 연동하세요."

    payload = {
        "text": text,
        "sender_id": sender_id,
        "room_id": room_id,
    }

    try:
        async with httpx.AsyncClient(timeout=AI_MODEL_TIMEOUT) as client:
            response = await client.post(AI_MODEL_URL, json=payload)
            response.raise_for_status()
            data = response.json()
    except Exception as exc:
        return f"[AI 호출 오류] {exc}"

    if isinstance(data, dict):
        for key in ("response", "text", "answer", "message"):
            value = data.get(key)
            if isinstance(value, str) and value.strip():
                return value

    return "[AI 응답 오류] 모델 서버 응답 형식을 확인하세요."

@app.get("/")
def read_root():
    return {
        "status": "AI Chatbot API Server is running",
        "ai_model_url_configured": bool(AI_MODEL_URL),
    }

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
    if sender_id == BOT_USER_ID:
        return {"status": "ignored_bot_message"}

    ai_response = await generate_ai_response(text, sender_id, room_id)
    
    # PocketBase REST API를 통해 채팅방에 AI 답변 추가
    async with httpx.AsyncClient() as client:
        url = f"{POCKETBASE_URL}/api/collections/messages/records"
        payload = {
            "text": ai_response,
            "user_id": BOT_USER_ID, # PocketBase에 등록한 봇 계정 ID
            "room": room_id
        }
        try:
            response = await client.post(url, json=payload)
            return {"status": "success", "pocketbase_response": response.status_code}
        except Exception as e:
            return {"status": "error", "detail": str(e)}
