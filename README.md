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
├── pd_chatbot/
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
5. The AI service generates a response and writes it back to the `messages` collection through the PocketBase REST API.
6. File or document events can be routed separately to `/webhook/documents`, where ingestion jobs are queued without blocking the chat response path.

If `AI_MODEL_URL` is configured, FastAPI forwards the user message to that external AI endpoint and uses the returned text as the bot response. If `AI_MODEL_URL` is empty, the service falls back to the current placeholder response.

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
| `BOT_USER_ID` | `bot_user_id_placeholder` | Bot user ID written back to the `messages` collection |
| `PORT` | `8000` | FastAPI container listening port |
| `FASTAPI_HOST_PORT` | `8000` | Host port mapped to the FastAPI container |

The values can be configured in Docker Compose or an `.env` file:

```yaml
environment:
  - POCKETBASE_URL=http://pocketbase:8090
  - AI_MODEL_URL=http://host.docker.internal:11434/api/chat
  - AI_MODEL_TIMEOUT=30
  - BOT_USER_ID=your_bot_user_id
  - PORT=8000
```

Example `.env` file:

```env
AI_MODEL_URL=http://host.docker.internal:11434/api/chat
AI_MODEL_TIMEOUT=30
BOT_USER_ID=your_bot_user_id
PORT=8000
FASTAPI_HOST_PORT=8000
```

The external AI endpoint is expected to accept a JSON body like this:

```json
{
  "text": "Hello",
  "sender_id": "user_record_id",
  "room_id": "general"
}
```

The FastAPI service looks for one of these fields in the AI response JSON:

- `response`
- `text`
- `answer`
- `message`

## PocketBase Setup Notes

At minimum, PocketBase should include a `messages` collection with fields similar to the following.

| Collection | Field | Example |
| --- | --- | --- |
| `messages` | `text` | `"Hello"` |
| `messages` | `user_id` | `"user_record_id"` |
| `messages` | `room` | `"general"` |

The FastAPI service currently uses a placeholder bot account ID:

```python
"user_id": "bot_user_id_placeholder"
```

Before using the service in a real environment, create a bot user or bot record in PocketBase and replace the placeholder with the correct record ID.

## Development

The FastAPI container mounts `pd_chatbot` into `/app` and runs with `uvicorn --reload`. Changes to `pd_chatbot/main.py` are automatically picked up by the development server.

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
