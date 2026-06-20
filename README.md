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
2. A PocketBase webhook calls the FastAPI `/webhook` endpoint.
3. FastAPI parses the message text, sender ID, and room ID from the webhook payload.
4. Messages sent by the bot itself are ignored to prevent infinite response loops.
5. The AI service generates a response and writes it back to the `messages` collection through the PocketBase REST API.

The current AI response is a placeholder. For production use, connect your preferred AI layer in `pd_chatbot/main.py`, such as the OpenAI API, a local LLM, a RAG pipeline, or an internal knowledge base.

## API

### `GET /`

Returns the FastAPI server status.

```json
{
  "status": "AI Server is running"
}
```

### `POST /webhook`

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

## Configuration

The FastAPI service uses the following environment variable.

| Variable | Default | Description |
| --- | --- | --- |
| `POCKETBASE_URL` | `http://pocketbase:8090` | Internal PocketBase URL used inside the Docker network |

The value is already configured in Docker Compose:

```yaml
environment:
  - POCKETBASE_URL=http://pocketbase:8090
```

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
