# tinyChat

> A lightweight real-time AI chat backend powered by PocketBase and FastAPI.

`tinyChat` is a compact chat backend that separates real-time data handling from AI business logic. PocketBase manages the chat data layer, collections, authentication, and real-time updates, while a Python FastAPI service receives webhooks, generates AI responses, and writes messages back through the PocketBase REST API.

The project is designed to be small, clear, and easy to extend. With a single Docker Compose command, you can run a local development environment and start building chatbot workflows, LLM integrations, RAG pipelines, internal support assistants, or automation-driven chat experiences.

## Architecture

```text
Client / PocketBase UI
        |
        v
PocketBase
  - realtime database
  - auth / collections
  - message records
        |
        | webhook: message created
        v
FastAPI AI Engine
  - webhook receiver
  - AI response logic
  - PocketBase REST write-back
        |
        v
PocketBase messages collection
```

## Tech Stack

| Layer | Technology | Role |
| --- | --- | --- |
| Real-time backend | PocketBase | Chat data, collections, authentication, real-time events |
| AI service | FastAPI | Webhook handling, AI response generation, business logic |
| HTTP client | httpx | PocketBase REST API requests |
| Runtime | Docker Compose | Local service orchestration |
| Python | 3.11 slim | Lightweight AI service runtime |

## Project Structure

```text
tinyChat/
├── docker-compose.yml      # PocketBase + FastAPI service definition
├── chroma_data/            # Local persistent vector store data
├── pb_chatbot/
│   └── main.py             # FastAPI AI webhook server
├── pb_data/                # Local PocketBase data
├── pb_public/              # PocketBase public assets
└── README.md
```

## Quick Start

### 1. Run the services

```bash
docker compose up -d
```

### 2. Open the services

| Service | URL |
| --- | --- |
| PocketBase | http://localhost:8090 |
| FastAPI AI server | http://localhost:8000 |
| FastAPI health check | http://localhost:8000/ |

### 3. Check the server status

```bash
curl http://localhost:8000/
```

Expected response:

```json
{
  "status": "AI Server is running"
}
```

## How It Works

1. A user creates a chat message in the PocketBase `messages` collection.
2. A PocketBase message webhook calls the FastAPI `/webhook/messages` endpoint.
3. FastAPI parses the message text, sender ID, and room ID from the webhook payload.
4. Messages sent by the bot itself are ignored to prevent infinite response loops.
5. The AI service routes chat requests through `chat_with_rag()`, which prepares message context for the model layer and writes the bot response back to the `messages` collection.
6. File or document events can be routed separately to `/webhook/documents`, where `ingest_document()` runs in the background without blocking the chat response path.

If `AI_MODEL_URL` is configured, FastAPI forwards the user message through a provider-aware LLM adapter and uses the returned text as the bot response. Supported modes are `ollama`, `openai`, and `generic`. If `AI_MODEL_URL` is empty, the service falls back to the current placeholder response.

## API

### `GET /`

Returns the FastAPI server status.

```json
{
  "status": "AI Server is running"
}
```

### `POST /webhook`

Legacy compatibility endpoint. It inspects the incoming event and dispatches it to either the message or document handler.

### `POST /webhook/messages`

Receives PocketBase message creation events.

Expected payload shape:

```json
{
  "record": {
    "text": "Hello",
    "user_id": "user_record_id",
    "room": "general"
  }
}
```

Example success response:

```json
{
  "status": "success",
  "pocketbase_response": 200
}
```

### `POST /webhook/documents`

Receives PocketBase document or attachment events and queues ingestion work in the background.

Expected payload shape:

```json
{
  "collection": "documents",
  "record": {
    "id": "document_record_id",
    "room": "general",
    "files": ["example.pdf"]
  }
}
```

Current ingestion behavior:

- marks the document as `processing`
- prepares PocketBase file URLs for later parsers and chunkers
- finalizes the record as `completed` with a placeholder `chunk_count`

This keeps the ingestion lifecycle separate from chat generation so that a later Chroma or embedding step can be added inside `ingest_document()` without changing the webhook contract.

Example queued response:

```json
{
  "status": "queued",
  "document_id": "document_record_id",
  "room_id": "general",
  "file_count": 1
}
```

## Configuration

The FastAPI service uses the following environment variables.

| Variable | Default | Description |
| --- | --- | --- |
| `POCKETBASE_URL` | `http://pocketbase:8090` | Internal PocketBase URL used inside the Docker network |
| `AI_MODEL_URL` | empty | External AI model endpoint URL called by FastAPI |
| `AI_MODEL_TIMEOUT` | `30` | Timeout in seconds for the AI model HTTP request |
| `LLM_PROVIDER` | `auto` | `ollama`, `openai`, or `generic`; `auto` infers from the URL |
| `LLM_MODEL` | empty | Model name used for Ollama or OpenAI-compatible chat requests |
| `LLM_API_KEY` | empty | Bearer token used for OpenAI-compatible APIs |
| `LLM_SYSTEM_PROMPT` | built-in default | System prompt sent to the model provider |
| `LLM_TEMPERATURE` | `0.2` | Sampling temperature |
| `LLM_MAX_TOKENS` | `512` | Output token budget or nearest provider equivalent |
| `BOT_USER_ID` | `bot_user_id_placeholder` | Bot user ID written back to the `messages` collection |
| `CHROMA_PERSIST_DIR` | `/data/chroma` | Persistent local directory for Chroma vector data |
| `PORT` | `8000` | FastAPI container listening port |
| `FASTAPI_HOST_PORT` | `8000` | Host port mapped to the FastAPI container |

The values can be configured in Docker Compose or an `.env` file:

```yaml
environment:
  - POCKETBASE_URL=http://pocketbase:8090
  - AI_MODEL_URL=http://host.docker.internal:11434/api/chat
  - AI_MODEL_TIMEOUT=30
  - LLM_PROVIDER=ollama
  - LLM_MODEL=qwen2.5:7b-instruct
  - BOT_USER_ID=your_bot_user_id
  - CHROMA_PERSIST_DIR=/data/chroma
  - PORT=8000
```

Example `.env` file:

```env
AI_MODEL_URL=http://host.docker.internal:11434/api/chat
AI_MODEL_TIMEOUT=30
LLM_PROVIDER=ollama
LLM_MODEL=qwen2.5:7b-instruct
BOT_USER_ID=your_bot_user_id
CHROMA_PERSIST_DIR=/data/chroma
PORT=8000
FASTAPI_HOST_PORT=8000
```

The FastAPI container mounts `./chroma_data` to `/data/chroma`, so local vector data survives container restarts. This path is now reserved for the upcoming Chroma integration.

### Provider modes

`ollama`

- Typical URL: `http://host.docker.internal:11434/api/chat`
- Requires: `LLM_MODEL`
- Response parsing: `message.content` or `response`

`openai`

- Typical URL: `https://api.openai.com/v1/chat/completions`
- Requires: `LLM_MODEL`
- Usually also requires: `LLM_API_KEY`
- Response parsing: `choices[0].message.content`

`generic`

- Uses the legacy raw payload and looks for `response`, `text`, `answer`, or `message`

The generic request payload looks like this:

```json
{
  "text": "Hello",
  "sender_id": "user_record_id",
  "room_id": "general",
  "document_id": "document_record_id",
  "attachment_ids": ["attachment_record_id"],
  "metadata": {}
}
```

Example OpenAI-compatible `.env` values:

```env
AI_MODEL_URL=https://api.openai.com/v1/chat/completions
LLM_PROVIDER=openai
LLM_MODEL=gpt-4.1-mini
LLM_API_KEY=your_api_key
```

## PocketBase Setup Notes

At minimum, PocketBase should include the following collections.

| Collection | Purpose | Key fields |
| --- | --- | --- |
| `messages` | User and bot chat messages | `text`, `user_id`, `room`, `message_type`, `processing_status`, `document_id`, `attachments` |
| `documents` | Uploaded files and RAG ingestion lifecycle | `title`, `room`, `uploaded_by`, `source_message`, `processing_status`, `file`, `chunk_count`, `last_error` |
| `attachments` | Multiple file references linked to messages and documents | `message_id`, `document_id`, `file`, `file_name`, `mime_type`, `processing_status` |

Detailed field guidance is documented in [pocketbase/schema-reference.md](/Users/nenji/Docker/LINGSSOFT/tinyChat/pocketbase/schema-reference.md).

For the webhook flow used by this project:

- New user messages should be created with `message_type = user` and `processing_status = pending`.
- Bot responses are written by FastAPI with `message_type = bot` and `processing_status = completed`.
- New documents should start with `processing_status = pending`.
- The document webhook moves documents to `queued` before ingestion begins.

The FastAPI service currently uses a placeholder bot account ID:

```python
"user_id": "bot_user_id_placeholder"
```

Before using the service in a real environment, create a bot user or bot record in PocketBase and replace the placeholder with the correct record ID.

## Development

The FastAPI container mounts `pb_chatbot` into `/app` and runs with `uvicorn --reload`. Changes to `pb_chatbot/main.py` are automatically picked up by the development server.

The `chroma_data/` directory is kept out of git and is intended to hold local persisted embeddings and vector index files.

```bash
docker compose logs -f fastapi-ai
```

Stop the services:

```bash
docker compose down
```

To reset local PocketBase data, remove `pb_data/`. This deletes local database state, so back it up first if the data matters.

## Roadmap

- OpenAI or local LLM integration
- Bot user ID configuration through environment variables
- PocketBase admin setup documentation
- Automated `messages` collection schema setup
- Room-specific system prompts
- RAG-based document retrieval responses
- Streaming responses and typing/status events
- Authenticated webhook verification

## License

No license has been specified yet. Add a license that matches your intended usage before publishing or distributing this project.
