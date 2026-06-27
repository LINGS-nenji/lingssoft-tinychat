import logging
import os

import httpx
from fastapi import BackgroundTasks, FastAPI, Request

app = FastAPI()
logger = logging.getLogger("tinychat")

POCKETBASE_URL = os.getenv("POCKETBASE_URL", "http://pocketbase:8090").rstrip("/")
AI_MODEL_URL = os.getenv("AI_MODEL_URL", "").strip()
AI_MODEL_TIMEOUT = float(os.getenv("AI_MODEL_TIMEOUT", "30"))
BOT_USER_ID = os.getenv("BOT_USER_ID", "bot_user_id_placeholder")
MESSAGES_COLLECTION = os.getenv("MESSAGES_COLLECTION", "messages")
DOCUMENTS_COLLECTION = os.getenv("DOCUMENTS_COLLECTION", "documents")
ATTACHMENTS_COLLECTION = os.getenv("ATTACHMENTS_COLLECTION", "attachments")


def extract_record(data: dict) -> dict:
    return data.get("record") or {}


def detect_collection_name(data: dict) -> str:
    return (
        data.get("collection")
        or data.get("collectionName")
        or data.get("collection_name")
        or ""
    )


def is_document_event(data: dict, record: dict) -> bool:
    collection_name = detect_collection_name(data).lower()
    if collection_name in {
        DOCUMENTS_COLLECTION.lower(),
        ATTACHMENTS_COLLECTION.lower(),
        "files",
    }:
        return True

    if record.get("document_id") or record.get("file") or record.get("files"):
        return True

    return False


def normalize_file_list(value) -> list[str]:
    if isinstance(value, list):
        return [item for item in value if isinstance(item, str) and item.strip()]
    if isinstance(value, str) and value.strip():
        return [value]
    return []


def build_pocketbase_file_url(collection_name: str, record_id: str, filename: str) -> str:
    return f"{POCKETBASE_URL}/api/files/{collection_name}/{record_id}/{filename}"


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


async def write_chat_message(text: str, room_id: str) -> int:
    payload = {
        "text": text,
        "user_id": BOT_USER_ID,
        "room": room_id,
        "message_type": "bot",
        "processing_status": "completed",
    }
    url = f"{POCKETBASE_URL}/api/collections/{MESSAGES_COLLECTION}/records"

    async with httpx.AsyncClient() as client:
        response = await client.post(url, json=payload)
        response.raise_for_status()
        return response.status_code


async def update_record(collection_name: str, record_id: str, payload: dict) -> int:
    url = f"{POCKETBASE_URL}/api/collections/{collection_name}/records/{record_id}"

    async with httpx.AsyncClient() as client:
        response = await client.patch(url, json=payload)
        response.raise_for_status()
        return response.status_code


def queue_document_ingestion(document_id: str, room_id: str, file_urls: list[str]) -> None:
    logger.info(
        "Document ingestion queued",
        extra={
            "document_id": document_id,
            "room_id": room_id,
            "file_urls": file_urls,
        },
    )


async def handle_message_webhook(data: dict) -> dict:
    record = extract_record(data)
    text = record.get("text", "")
    sender_id = record.get("user_id", "")
    room_id = record.get("room", "general")
    message_type = record.get("message_type", "user")
    processing_status = record.get("processing_status", "pending")

    if sender_id == BOT_USER_ID:
        return {"status": "ignored_bot_message"}

    if message_type != "user":
        return {"status": "ignored_message_type", "message_type": message_type}

    if processing_status not in {"pending", "queued"}:
        return {
            "status": "ignored_processing_status",
            "processing_status": processing_status,
        }

    ai_response = await generate_ai_response(text, sender_id, room_id)

    try:
        status_code = await write_chat_message(ai_response, room_id)
    except Exception as exc:
        return {"status": "error", "detail": str(exc)}

    return {"status": "success", "pocketbase_response": status_code}


async def handle_document_webhook(data: dict, background_tasks: BackgroundTasks) -> dict:
    record = extract_record(data)
    collection_name = detect_collection_name(data) or DOCUMENTS_COLLECTION
    document_id = record.get("id", "")
    room_id = record.get("room", "general")
    processing_status = record.get("processing_status", "pending")
    attachments = normalize_file_list(record.get("attachments"))
    files = normalize_file_list(record.get("file")) + normalize_file_list(record.get("files"))
    files.extend(attachments)
    file_urls = [
        build_pocketbase_file_url(collection_name, document_id, filename)
        for filename in files
    ]

    if processing_status not in {"pending", "queued"}:
        return {
            "status": "ignored_processing_status",
            "processing_status": processing_status,
            "document_id": document_id,
        }

    if collection_name == DOCUMENTS_COLLECTION and document_id:
        try:
            await update_record(
                DOCUMENTS_COLLECTION,
                document_id,
                {"processing_status": "queued"},
            )
        except Exception as exc:
            logger.warning("Failed to update document status: %s", exc)

    background_tasks.add_task(queue_document_ingestion, document_id, room_id, file_urls)
    return {
        "status": "queued",
        "document_id": document_id,
        "room_id": room_id,
        "file_count": len(file_urls),
    }


@app.get("/")
def read_root():
    return {
        "status": "AI Chatbot API Server is running",
        "ai_model_url_configured": bool(AI_MODEL_URL),
    }


@app.post("/webhook")
async def pocketbase_webhook(request: Request, background_tasks: BackgroundTasks):
    """
    Legacy webhook entrypoint. Dispatches to message or document handlers.
    """
    data = await request.json()
    record = extract_record(data)

    if is_document_event(data, record):
        return await handle_document_webhook(data, background_tasks)

    return await handle_message_webhook(data)


@app.post("/webhook/messages")
async def pocketbase_message_webhook(request: Request):
    """
    PocketBase message-created webhook entrypoint.
    """
    data = await request.json()
    return await handle_message_webhook(data)


@app.post("/webhook/documents")
async def pocketbase_document_webhook(request: Request, background_tasks: BackgroundTasks):
    """
    PocketBase document-created webhook entrypoint.
    """
    data = await request.json()
    return await handle_document_webhook(data, background_tasks)
