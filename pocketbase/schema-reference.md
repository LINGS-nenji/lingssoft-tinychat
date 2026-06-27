# PocketBase Schema Reference

This project now assumes three primary collections for chat and RAG workflows.

## 1. `messages`

Purpose: store user and bot chat messages.

Recommended fields:

| Field | Type | Required | Example | Notes |
| --- | --- | --- | --- | --- |
| `text` | text | yes | `"What does this PDF say?"` | Chat message body |
| `user_id` | relation or text | yes | `user_record_id` | Usually points to `users` |
| `room` | text or relation | yes | `"general"` | Chat room identifier |
| `message_type` | select | yes | `user` | Allowed: `user`, `bot`, `system`, `document_notice` |
| `processing_status` | select | yes | `pending` | Allowed: `pending`, `queued`, `processing`, `completed`, `failed`, `ignored` |
| `document_id` | relation | no | `document_record_id` | Optional link to `documents` |
| `attachments` | relation (multiple) | no | `["attachment_id"]` | Optional related attachment records |
| `metadata` | json | no | `{"source":"webhook"}` | Free-form app metadata |

## 2. `documents`

Purpose: track uploaded source files and ingestion lifecycle for RAG.

Recommended fields:

| Field | Type | Required | Example | Notes |
| --- | --- | --- | --- | --- |
| `title` | text | yes | `"employee-handbook.pdf"` | Display name |
| `room` | text or relation | yes | `"general"` | Scope for retrieval |
| `uploaded_by` | relation or text | yes | `user_record_id` | Uploader |
| `source_message` | relation | no | `message_record_id` | Chat message that introduced the file |
| `processing_status` | select | yes | `pending` | Allowed: `pending`, `queued`, `processing`, `completed`, `failed` |
| `file` | file | yes | `handbook.pdf` | Primary uploaded file |
| `chunk_count` | number | no | `42` | Filled after ingestion |
| `last_error` | text | no | `"PDF parser failed"` | Failure reason |
| `metadata` | json | no | `{"mime_type":"application/pdf"}` | Parser and ingest metadata |

## 3. `attachments`

Purpose: normalize file references when a message may contain multiple files.

Recommended fields:

| Field | Type | Required | Example | Notes |
| --- | --- | --- | --- | --- |
| `message_id` | relation | no | `message_record_id` | Message that owns the file |
| `document_id` | relation | no | `document_record_id` | Linked document record |
| `file` | file | yes | `example.pdf` | Uploaded file |
| `file_name` | text | no | `"example.pdf"` | Original file name |
| `mime_type` | text | no | `"application/pdf"` | Useful for parser choice |
| `processing_status` | select | yes | `pending` | Allowed: `pending`, `queued`, `processing`, `completed`, `failed` |
| `metadata` | json | no | `{"size_bytes":1048576}` | File metadata |

## Workflow expectations

- New user chat messages should be created with `message_type = user` and `processing_status = pending`.
- Bot responses should be written with `message_type = bot` and `processing_status = completed`.
- New documents should be created with `processing_status = pending`.
- The FastAPI document webhook updates documents to `queued` before background ingestion starts.
- After ingestion, later steps should update `documents.processing_status` to `processing`, then `completed` or `failed`.
