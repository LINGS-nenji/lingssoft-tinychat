import logging
import os
from typing import Any

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
CHROMA_PERSIST_DIR = os.getenv("CHROMA_PERSIST_DIR", "/data/chroma")


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


def build_ai_payload(
    text: str,
    sender_id: str,
    room_id: str,
    document_id: str = "",
    attachment_ids: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "text": text,
        "sender_id": sender_id,
        "room_id": room_id,
        "document_id": document_id,
        "attachment_ids": attachment_ids or [],
        "metadata": metadata or {},
    }


async def call_ai_model(payload: dict[str, Any]) -> str:
    if not AI_MODEL_URL:
        text = payload.get("text", "")
        return f"[AI 봇 답변] '{text}'라고 말씀하셨군요. 이 부분에 AI 엔진을 연동하세요."

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


async def create_record(collection_name: str, payload: dict[str, Any]) -> int:
    url = f"{POCKETBASE_URL}/api/collections/{collection_name}/records"

    async with httpx.AsyncClient() as client:
        response = await client.post(url, json=payload)
        response.raise_for_status()
        return response.status_code


async def write_chat_message(
    text: str,
    room_id: str,
    document_id: str = "",
    attachments: list[str] | None = None,
) -> int:
    payload = {
        "text": text,
        "user_id": BOT_USER_ID,
        "room": room_id,
        "message_type": "bot",
        "processing_status": "completed",
        "document_id": document_id or None,
        "attachments": attachments or [],
    }
    return await create_record(MESSAGES_COLLECTION, payload)


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


async def chat_with_rag(record: dict[str, Any]) -> dict[str, Any]:
    text = record.get("text", "")
    sender_id = record.get("user_id", "")
    room_id = record.get("room", "general")
    document_id = record.get("document_id", "")
    attachments = normalize_file_list(record.get("attachments"))
    metadata = record.get("metadata")
    message_id = record.get("id", "")

    if message_id:
        try:
            await update_record(
                MESSAGES_COLLECTION,
                message_id,
                {"processing_status": "processing"},
            )
        except Exception as exc:
            logger.warning("Failed to update message status: %s", exc)

    payload = build_ai_payload(
        text=text,
        sender_id=sender_id,
        room_id=room_id,
        document_id=document_id,
        attachment_ids=attachments,
        metadata=metadata if isinstance(metadata, dict) else {},
    )
    ai_response = await call_ai_model(payload)
    status_code = await write_chat_message(
        ai_response,
        room_id,
        document_id=document_id,
        attachments=attachments,
    )

    if message_id:
        try:
            await update_record(
                MESSAGES_COLLECTION,
                message_id,
                {"processing_status": "completed"},
            )
        except Exception as exc:
            logger.warning("Failed to finalize message status: %s", exc)

    return {
        "status": "success",
        "pocketbase_response": status_code,
        "message_id": message_id,
    }


async def ingest_document(collection_name: str, record: dict[str, Any]) -> dict[str, Any]:
    document_id = record.get("id", "")
    room_id = record.get("room", "general")
    attachments = normalize_file_list(record.get("attachments"))
    files = normalize_file_list(record.get("file")) + normalize_file_list(record.get("files"))
    files.extend(attachments)
    file_urls = [
        build_pocketbase_file_url(collection_name, document_id, filename)
        for filename in files
    ]

    if collection_name == DOCUMENTS_COLLECTION and document_id:
        await update_record(
            DOCUMENTS_COLLECTION,
            document_id,
            {
                "processing_status": "processing",
                "chunk_count": 0,
                "last_error": "",
            },
        )

    logger.info(
        "Document ingestion started",
        extra={
            "collection_name": collection_name,
            "document_id": document_id,
            "room_id": room_id,
            "file_urls": file_urls,
            "chroma_persist_dir": CHROMA_PERSIST_DIR,
        },
    )

    if collection_name == DOCUMENTS_COLLECTION and document_id:
        await update_record(
            DOCUMENTS_COLLECTION,
            document_id,
            {
                "processing_status": "completed",
                "chunk_count": len(file_urls),
                "last_error": "",
            },
        )

    return {
        "status": "completed",
        "document_id": document_id,
        "room_id": room_id,
        "file_count": len(file_urls),
    }


async def run_document_ingestion_task(collection_name: str, record: dict[str, Any]) -> None:
    document_id = record.get("id", "")
    try:
        await ingest_document(collection_name, record)
    except Exception as exc:
        logger.exception("Document ingestion failed: %s", exc)
        if collection_name == DOCUMENTS_COLLECTION and document_id:
            try:
                await update_record(
                    DOCUMENTS_COLLECTION,
                    document_id,
                    {
                        "processing_status": "failed",
                        "last_error": str(exc),
                    },
                )
            except Exception as nested_exc:
                logger.warning("Failed to persist document failure: %s", nested_exc)


async def handle_message_webhook(data: dict) -> dict:
    record = extract_record(data)
    sender_id = record.get("user_id", "")
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

    try:
        return await chat_with_rag(record)
    except Exception as exc:
        message_id = record.get("id", "")
        if message_id:
            try:
                await update_record(
                    MESSAGES_COLLECTION,
                    message_id,
                    {"processing_status": "failed"},
                )
            except Exception as nested_exc:
                logger.warning("Failed to persist message failure: %s", nested_exc)
        return {"status": "error", "detail": str(exc)}


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

    queue_document_ingestion(document_id, room_id, file_urls)
    background_tasks.add_task(run_document_ingestion_task, collection_name, record)
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
        "chroma_persist_dir": CHROMA_PERSIST_DIR,
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
