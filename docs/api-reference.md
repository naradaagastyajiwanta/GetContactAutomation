# API Reference - GetContact AI Agent

**Version:** 1.0.0
**Base URL:** `http://localhost:8000` (Development)
**Protocol:** HTTP/REST
**Format:** JSON

---

## Table of Contents

1. [Authentication](#authentication)
2. [Response Format](#response-format)
3. [Dashboard & Stats](#dashboard--stats)
4. [Webhook](#webhook)
5. [Universities](#universities)
6. [PDDIKTI](#pddikti)
7. [Conversations](#conversations)
8. [Pipeline](#pipeline)
9. [Outreach](#outreach)
10. [Control](#control)
11. [Learning](#learning)
12. [WhatsApp Management](#whatsapp-management)
13. [Configuration](#configuration)
14. [Knowledge Base](#knowledge-base)
15. [API Logs](#api-logs)
16. [Audiensi](#audiensi)
17. [Instagram](#instagram)
18. [Health Check](#health-check)
19. [Export](#export)
20. [Error Codes](#error-codes)
21. [Rate Limiting](#rate-limiting)
22. [WebSocket](#websocket)

---

## Authentication

Currently no authentication required. Future versions will implement API keys.

---

## Response Format

### Success Response
```json
{
  "status": "success",
  "data": { ... }
}
```

### Error Response
```json
{
  "detail": "Error message description"
}
```

---

## Dashboard & Stats

### GET /dashboard
Get overall system statistics including university counts, conversation stats, and pipeline status.

**Response 200 OK:**
```json
{
  "universities": {
    "total": 1500,
    "pending": 500,
    "ig_found": 300,
    "posts_scraped": 200,
    "phones_extracted": 100,
    "contacted": 50,
    "got_number": 25,
    "refused": 10,
    "abandoned": 15
  },
  "conversations": {
    "total": 100,
    "active": 45,
    "completed": 55
  },
  "pipeline": {
    "is_running": false,
    "last_run": "2024-01-15T04:00:00Z",
    "next_run": "2024-01-16T04:00:00Z"
  }
}
```

---

### GET /universities
List universities with combined filters and pagination.

**Query Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| status | string | No | - | Filter by status (pending, ig_found, posts_scraped, etc.) |
| search | string | No | - | Search by name or code |
| province | string | No | - | Filter by province |
| has_ig | boolean | No | - | Filter by Instagram handle existence |
| enabled | boolean | No | - | Filter by enabled status |
| limit | integer | No | 25 | Max records to return (1-100) |
| offset | integer | No | 0 | Number of records to skip |

**Response 200 OK:**
```json
{
  "universities": [
    {
      "id": 1,
      "name": "Universitas Indonesia",
      "province": "DKI Jakarta",
      "website": "https://ui.ac.id",
      "ig_handle": "universitas.indonesia",
      "status": "ig_found",
      "enabled": true,
      "secretariat_phone": null,
      "created_at": "2024-01-15T10:30:00Z"
    }
  ],
  "total": 1500,
  "limit": 25,
  "offset": 0
}
```

---

### GET /universities/export-excel
Export contacts (university name, contact name, phone) as Excel (.xlsx) file.

**Query Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| status | string | No | - | Filter by status |
| search | string | No | - | Search by name or code |
| province | string | No | - | Filter by province |
| has_ig | boolean | No | - | Filter by Instagram handle existence |
| enabled | boolean | No | - | Filter by enabled status |
| ids | string | No | - | Comma-separated university IDs |

**Response 200 OK:**
```
Content-Type: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet
Content-Disposition: attachment; filename="contacts_export_20240115_103000.xlsx"

Binary Excel file with columns:
- Nama Universitas
- Nama Contact
- No. WhatsApp
```

---

### POST /universities/match-names
Match a list of university names to existing records.

**Request Body:**
```json
{
  "names": ["Universitas Indonesia", "ITB", "UGM"]
}
```

**Response 200 OK:**
```json
{
  "matches": [
    {
      "id": 1,
      "name": "Universitas Indonesia",
      "matched_query": "Universitas Indonesia"
    },
    {
      "id": 2,
      "name": "Institut Teknologi Bandung",
      "matched_query": "ITB"
    }
  ],
  "total_queries": 3,
  "total_matched": 2
}
```

**Response 400 Bad Request:**
```json
{
  "error": "names must be a non-empty list"
}
```

---

### GET /universities/provinces
Return distinct province values for filter dropdown.

**Response 200 OK:**
```json
[
  "DKI Jakarta",
  "Jawa Barat",
  "Jawa Tengah",
  "D.I. Yogyakarta"
]
```

---

### PATCH /universities/{university_id}/toggle-enabled
Enable or disable a single university for pipeline processing.

**Path Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| university_id | integer | Yes | University ID |

**Query Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| enabled | boolean | No | true | Enable or disable the university |

**Response 200 OK:**
```json
{
  "id": 1,
  "enabled": true
}
```

**Response 404 Not Found:**
```json
{
  "error": "University not found"
}
```

---

### PATCH /universities/bulk-toggle
Enable or disable multiple universities.

**Request Body:**
```json
{
  "ids": [1, 2, 3, 4, 5],
  "enabled": false
}
```

**Response 200 OK:**
```json
{
  "updated": 5,
  "enabled": false
}
```

**Response 400 Bad Request:**
```json
{
  "error": "ids list required"
}
```

---

### POST /universities
Add one or many universities via JSON.

**Request Body (Single):**
```json
{
  "name": "Universitas Gadjah Mada",
  "province": "D.I. Yogyakarta",
  "website": "https://ugm.ac.id"
}
```

**Request Body (Bulk):**
```json
{
  "universities": [
    {
      "name": "Universitas Gadjah Mada",
      "province": "D.I. Yogyakarta",
      "website": "https://ugm.ac.id"
    },
    {
      "name": "Institut Teknologi Bandung",
      "province": "Jawa Barat",
      "website": "https://itb.ac.id"
    }
  ]
}
```

**Response 200 OK:**
```json
{
  "added": 2,
  "skipped": 0
}
```

**Response 422 Unprocessable Entity:**
```json
{
  "detail": "Provide 'name' for a single university or 'universities' array for bulk."
}
```

---

### POST /universities/import
Import universities from CSV or Excel (.xlsx) file.

**Request:** multipart/form-data with file upload

**Supported file formats:**
- CSV (.csv)
- Excel (.xlsx)

**Recognized column names (flexible):**
- Name: `name`, `nama`, `nama universitas`, `nama_universitas`, `university`, `university name`, `university_name`, `institusi`, `perguruan tinggi`
- Province: `province`, `provinsi`, `prov`
- Website: `website`, `web`, `url`, `situs`, `situs web`, `laman`

**Response 200 OK:**
```json
{
  "imported": 150,
  "skipped": 5
}
```

**Response 400 Bad Request:**
```json
{
  "detail": "Excel file has no active sheet"
}
```

---

### GET /universities/{university_id}
Get a single university by ID.

**Path Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| university_id | integer | Yes | University ID |

**Response 200 OK:**
```json
{
  "id": 1,
  "name": "Universitas Indonesia",
  "province": "DKI Jakarta",
  "website": "https://ui.ac.id",
  "ig_handle": "universitas.indonesia",
  "status": "ig_found",
  "enabled": true,
  "secretariat_phone": null,
  "pddikti_id": "001001",
  "created_at": "2024-01-15T10:30:00Z",
  "updated_at": "2024-01-15T10:30:00Z"
}
```

**Response 404 Not Found:**
```json
{
  "detail": "University not found"
}
```

---

### GET /universities/{university_id}/contacts
Get IG contacts for a university.

**Path Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| university_id | integer | Yes | University ID |

**Response 200 OK:**
```json
{
  "contacts": [
    {
      "id": 1,
      "university_id": 1,
      "ig_handle": "universitas.indonesia",
      "relation_type": "main",
      "follower_count": 150000,
      "created_at": "2024-01-15T10:30:00Z"
    }
  ]
}
```

---

### GET /universities/{university_id}/posts
Get IG posts for a university.

**Path Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| university_id | integer | Yes | University ID |

**Response 200 OK:**
```json
{
  "posts": [
    {
      "id": 1,
      "university_id": 1,
      "ig_contact_id": 1,
      "post_shortcode": "Cxyz123",
      "post_url": "https://www.instagram.com/p/Cxyz123/",
      "image_url": "https://instagram.com/...",
      "caption": "Post caption text...",
      "taken_at": "2024-01-10T10:00:00Z",
      "processed": true,
      "phone_extracted": "+6281234567890",
      "created_at": "2024-01-15T10:30:00Z"
    }
  ]
}
```

---

### GET /universities/{university_id}/related-igs
Get related IG accounts (BEM, humas, etc.) for a university.

**Path Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| university_id | integer | Yes | University ID |

**Query Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| relation_type | string | No | - | Filter by relation type (bem, humas, etc.) |

**Response 200 OK:**
```json
{
  "related_igs": [
    {
      "id": 2,
      "university_id": 1,
      "ig_handle": "bem_ui",
      "relation_type": "bem",
      "follower_count": 50000,
      "created_at": "2024-01-15T10:30:00Z"
    }
  ]
}
```

---

## Webhook

### POST /webhook/incoming
Handle incoming WhatsApp message forwarded from Node.js service.

**Request Body:**
```json
{
  "from": "6281234567890",
  "message": "Hello, this is a test message",
  "timestamp": 1705305600,
  "messageId": "3EB0XXXXXXXXX",
  "pushName": "John Doe",
  "msgKey": "3EB0XXXXXXXXX",
  "allMsgKeys": ["3EB0XXXXXXXXX", "3EB0YYYYYYYYY"]
}
```

**Response 200 OK:**
```json
{
  "status": "received"
}
```

---

## PDDIKTI

### GET /pddikti/provinces
Return the list of Indonesian provinces for PDDIKTI search.

**Response 200 OK:**
```json
{
  "provinces": [
    "DKI Jakarta",
    "Jawa Barat",
    "Jawa Tengah",
    "D.I. Yogyakarta",
    "Jawa Timur",
    ...
  ]
}
```

---

### POST /pipeline/collect-universities
Collect universities from PDDIKTI API.

**Query Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| province | string | No | - | Filter by province |
| limit | integer | No | - | Maximum number to collect |

**Response 200 OK:**
```json
{
  "status": "started",
  "message": "Collecting universities from PDDIKTI (province: DKI Jakarta)"
}
```

---

## Conversations

### GET /conversations
List conversations with optional filters.

**Query Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| state | string | No | - | Filter by conversation state |
| university_id | integer | No | - | Filter by university ID |
| is_test | boolean | No | - | Filter test conversations |
| limit | integer | No | 100 | Max records to return |
| offset | integer | No | 0 | Number of records to skip |

**Conversation States:**
- `PENDING` - Initial state
- `INITIAL_SENT` - Initial message sent
- `WAITING_REPLY` - Waiting for response
- `REPLIED` - Received reply
- `ANALYZING` - Analyzing response
- `GOT_NUMBER` - Successfully obtained number
- `REFUSED` - Contact refused
- `ABANDONED` - Conversation abandoned

**Response 200 OK:**
```json
{
  "conversations": [
    {
      "id": 1,
      "university_id": 1,
      "phone": "+6281234567890",
      "state": "REPLIED",
      "is_test": false,
      "last_message_at": "2024-01-15T11:00:00Z",
      "created_at": "2024-01-15T10:30:00Z",
      "university_name": "Universitas Indonesia",
      "linked_audiensi": []
    }
  ],
  "total": 100,
  "limit": 100,
  "offset": 0
}
```

---

### GET /conversations/{conversation_id}
Get a single conversation by ID.

**Path Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| conversation_id | integer | Yes | Conversation ID |

**Response 200 OK:**
```json
{
  "id": 1,
  "university_id": 1,
  "phone": "+6281234567890",
  "state": "REPLIED",
  "is_test": false,
  "message_history": "[{\"role\":\"bot\",\"content\":\"Hello...\",\"timestamp\":\"...\"}]",
  "last_message_at": "2024-01-15T11:00:00Z",
  "created_at": "2024-01-15T10:30:00Z",
  "university_name": "Universitas Indonesia",
  "linked_audiensi": [
    {
      "id": 1,
      "state": "QUEUED",
      "contact_phone": "+6281234567890"
    }
  ]
}
```

**Response 404 Not Found:**
```json
{
  "detail": "Conversation not found"
}
```

---

### POST /conversations/test
Start a test conversation for internal roleplay testing.

**Request Body:**
```json
{
  "phone": "6281234567890",
  "university_name": "Universitas Test",
  "force": false
}
```

**Response 200 OK:**
```json
{
  "id": 101,
  "phone": "+6281234567890",
  "message": "Selamat pagi, saya dari Asosiasi AI Indonesia...",
  "state": "INITIAL_SENT"
}
```

**Response 409 Conflict:**
```json
{
  "detail": "Active conversation already exists for +6281234567890",
  "existing_id": 50,
  "existing_state": "REPLIED"
}
```

**Response 422 Unprocessable Entity:**
```json
{
  "detail": "Invalid phone number: 12345"
}
```

---

## Pipeline

### POST /pipeline/find-ig-handles
Agent 1: Search IG handles for universities in 'pending' status.

**Query Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| limit | integer | No | 50 | Maximum universities to process |

**Response 200 OK:**
```json
{
  "status": "started",
  "message": "Agent 1: searching IG handles for up to 50 universities"
}
```

---

### POST /pipeline/scrape-ig-posts
Agent 2: Scrape IG posts for universities in 'ig_found' status.

**Query Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| limit | integer | No | 20 | Maximum universities to process |

**Response 200 OK:**
```json
{
  "status": "started",
  "message": "Agent 2: scraping posts for up to 20 universities"
}
```

---

### POST /pipeline/extract-phones
Agent 3: Extract phones from unprocessed ig_posts.

**Query Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| limit | integer | No | 50 | Maximum posts to process |

**Response 200 OK:**
```json
{
  "status": "started",
  "message": "Agent 3: extracting phones from up to 50 posts"
}
```

---

### POST /pipeline/discover-bem
Agent 4: Discover BEM handles and scan their following lists.

**Query Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| limit | integer | No | 30 | Maximum universities to process |

**Response 200 OK:**
```json
{
  "status": "started",
  "message": "Agent 4: discovering BEM for up to 30 universities"
}
```

---

### POST /pipeline/run-agent-targeted
Run a pipeline agent on specific universities.

**Request Body:**
```json
{
  "agent_type": "find_handles",
  "university_ids": [1, 2, 3, 4, 5]
}
```

**Agent Types:**
- `find_handles` - Find IG Handles
- `scrape_posts` - Scrape IG Posts
- `extract_phones` - Extract Phones
- `discover_bem` - Discover BEM

**Response 200 OK:**
```json
{
  "status": "started",
  "message": "Find IG Handles: processing 5 universities"
}
```

**Response 400 Bad Request:**
```json
{
  "error": "Invalid agent_type. Must be one of: ['find_handles', 'scrape_posts', 'extract_phones', 'discover_bem']"
}
```

---

### GET /pipeline/status
Return a breakdown of all pipeline stages.

**Response 200 OK:**
```json
{
  "universities_by_status": {
    "pending": 500,
    "ig_found": 300,
    "posts_scraped": 200,
    "phones_extracted": 100,
    "contacted": 50,
    "got_number": 25,
    "refused": 10,
    "abandoned": 15
  },
  "total_universities": 1200
}
```

---

### GET /pipeline/logs
Return paginated pipeline activity logs.

**Query Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| agent_type | string | No | - | Filter by agent type |
| status | string | No | - | Filter by status (completed, failed, running) |
| limit | integer | No | 50 | Max records to return |
| offset | integer | No | 0 | Number of records to skip |

**Response 200 OK:**
```json
{
  "logs": [
    {
      "id": 1,
      "agent_type": "find_handles",
      "trigger_type": "manual",
      "status": "completed",
      "started_at": "2024-01-15T10:00:00Z",
      "completed_at": "2024-01-15T10:05:00Z",
      "summary": {
        "searched": 50,
        "found": 30
      },
      "items_processed": 50,
      "items_success": 30,
      "items_failed": 20,
      "error": null
    }
  ],
  "total": 150
}
```

---

### GET /pipeline/logs/{log_id}
Return a single pipeline log entry with full details.

**Path Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| log_id | integer | Yes | Pipeline log ID |

**Response 200 OK:**
```json
{
  "id": 1,
  "agent_type": "find_handles",
  "trigger_type": "manual",
  "status": "completed",
  "started_at": "2024-01-15T10:00:00Z",
  "completed_at": "2024-01-15T10:05:00Z",
  "summary": {
    "searched": 50,
    "found": 30
  },
  "details": [
    {
      "university_id": 1,
      "university_name": "Universitas Indonesia",
      "status": "found",
      "ig_handle": "universitas.indonesia"
    }
  ],
  "items_processed": 50,
  "items_success": 30,
  "items_failed": 20,
  "error": null
}
```

**Response 404 Not Found:**
```json
{
  "error": "Log not found"
}
```

---

## Outreach

### POST /outreach/start
Manually trigger the outreach loop.

**Response 200 OK:**
```json
{
  "status": "started",
  "message": "Outreach loop triggered"
}
```

---

### POST /outreach/process-followups
Manually trigger follow-up processing.

**Response 200 OK:**
```json
{
  "status": "started",
  "message": "Follow-up processing triggered"
}
```

---

## Control

### POST /control/pause
Pause automated outreach and auto-replies.

**Response 200 OK:**
```json
{
  "paused": true
}
```

---

### POST /control/resume
Resume automated outreach and auto-replies.

**Response 200 OK:**
```json
{
  "paused": false
}
```

---

### GET /control/status
Return current pause state and chatbot toggles.

**Response 200 OK:**
```json
{
  "paused": false,
  "chatbot_enabled": true,
  "audiensi_enabled": true
}
```

---

### POST /control/chatbot/{chatbot_type}
Toggle a chatbot on/off.

**Path Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| chatbot_type | string | Yes | Type: 'agent' or 'audiensi' |

**Request Body:**
```json
{
  "enabled": true
}
```

**Response 200 OK (agent):**
```json
{
  "chatbot_enabled": true
}
```

**Response 200 OK (audiensi):**
```json
{
  "audiensi_enabled": true
}
```

**Response 422 Unprocessable Entity:**
```json
{
  "detail": "chatbot_type must be 'agent' or 'audiensi'"
}
```

---

## Learning

### GET /learning/lessons
Return all active lessons.

**Response 200 OK:**
```json
{
  "lessons": [
    {
      "id": 1,
      "situation_type": "contact_request_forward",
      "pattern": "User asks to forward to secretariat",
      "suggested_response": "Baik, bisa tolong share nomor sekretariat?",
      "created_at": "2024-01-15T10:00:00Z"
    }
  ],
  "total": 25
}
```

---

### GET /learning/analyses
Return unprocessed analyses.

**Query Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| limit | integer | No | 50 | Max records to return |

**Response 200 OK:**
```json
{
  "analyses": [
    {
      "id": 1,
      "conversation_id": 50,
      "situation_type": "refusal_polite",
      "analysis_text": "Contact politely declined...",
      "processed": false,
      "created_at": "2024-01-15T10:00:00Z"
    }
  ],
  "total": 10
}
```

---

### GET /learning/stats
Return summary statistics for the learning system.

**Response 200 OK:**
```json
{
  "total_active_lessons": 25,
  "unprocessed_analyses": 10,
  "lessons_by_situation": {
    "contact_request_forward": 8,
    "refusal_polite": 6,
    "refusal_direct": 5,
    "number_provided": 6
  }
}
```

---

### POST /learning/trigger-reflection
Trigger a reflection cycle in the background.

**Response 200 OK:**
```json
{
  "status": "started",
  "message": "Reflection triggered"
}
```

---

## WhatsApp Management

### GET /wa/qr
Get current QR code for WhatsApp authentication.

**Response 200 OK:**
```json
{
  "connected": false,
  "qr": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAA..."
}
```

**Response 502 Bad Gateway:**
```json
{
  "error": "WA service unavailable: Connection refused",
  "connected": false
}
```

---

### GET /wa/status
Get detailed WhatsApp connection status.

**Response 200 OK:**
```json
{
  "connected": true,
  "phone": "+6281234567890",
  "pushName": "GetContact Bot",
  "profilePictureUrl": "https://...",
  "lastActivity": "2024-01-15T11:00:00Z"
}
```

**Response 502 Bad Gateway:**
```json
{
  "error": "WA service unavailable: Connection refused",
  "connected": false
}
```

---

### POST /wa/send-test
Send a test WhatsApp message.

**Request Body:**
```json
{
  "to": "6281234567890",
  "message": "This is a test message"
}
```

**Response 200 OK:**
```json
{
  "success": true,
  "messageId": "3EB0XXXXXXXXX"
}
```

**Response 502 Bad Gateway:**
```json
{
  "success": false,
  "error": "WA service unavailable: Connection refused"
}
```

---

### POST /wa/logout
Logout from WhatsApp and clear auth session.

**Response 200 OK:**
```json
{
  "success": true,
  "message": "Logged out successfully"
}
```

**Response 502 Bad Gateway:**
```json
{
  "success": false,
  "error": "WA service unavailable: Connection refused"
}
```

---

### POST /wa/restart
Restart WhatsApp connection.

**Response 200 OK:**
```json
{
  "success": true,
  "message": "WhatsApp connection restarted"
}
```

**Response 502 Bad Gateway:**
```json
{
  "success": false,
  "error": "WA service unavailable: Connection refused"
}
```

---

## Configuration

### GET /config/models
Fetch chat-completion-capable models from OpenAI.

**Response 200 OK:**
```json
{
  "models": [
    "gpt-4o",
    "gpt-4o-mini",
    "gpt-4-turbo",
    "gpt-4",
    "o1-mini",
    "o1-preview"
  ]
}
```

**Response 200 OK (with error):**
```json
{
  "models": [],
  "error": "Failed to authenticate"
}
```

---

### GET /config
Return all dynamic settings with metadata.

**Response 200 OK:**
```json
{
  "settings": [
    {
      "key": "OPENAI_API_KEY",
      "value": "········1234",
      "default": "",
      "type": "string",
      "group": "api",
      "label": "OpenAI API Key",
      "description": "API key for OpenAI services",
      "min_value": null,
      "max_value": null,
      "sensitive": true,
      "has_value": true
    },
    {
      "key": "OUTREACH_START_HOUR",
      "value": 9,
      "default": 9,
      "type": "int",
      "group": "outreach",
      "label": "Outreach Start Hour (WIB)",
      "description": "Start hour for automated outreach (WIB timezone)",
      "min_value": 0,
      "max_value": 23,
      "sensitive": false,
      "has_value": null
    }
  ]
}
```

---

### PATCH /config
Update one or more config settings.

**Request Body:**
```json
{
  "settings": {
    "OUTREACH_START_HOUR": 10,
    "OUTREACH_END_HOUR": 17,
    "CHATBOT_ENABLED": true,
    "AGENT_MODEL": "gpt-4o-mini"
  }
}
```

**Response 200 OK:**
```json
{
  "status": "ok",
  "updated": ["OUTREACH_START_HOUR", "OUTREACH_END_HOUR", "CHATBOT_ENABLED", "AGENT_MODEL"]
}
```

**Response 422 Unprocessable Entity:**
```json
{
  "errors": {
    "OUTREACH_START_HOUR": "OUTREACH_START_HOUR must be >= 0",
    "AGENT_MODEL": "Invalid type for AGENT_MODEL: expected string"
  }
}
```

---

### DELETE /config/{key}
Reset a config key to its default value.

**Path Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| key | string | Yes | Config key |

**Response 200 OK:**
```json
{
  "status": "ok",
  "key": "OUTREACH_START_HOUR",
  "value": 9
}
```

**Response 404 Not Found:**
```json
{
  "detail": "Unknown config key: INVALID_KEY"
}
```

---

## Knowledge Base

### GET /knowledge-items
List knowledge items, optionally filtered by chatbot_type.

**Query Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| chatbot_type | string | No | - | Filter by chatbot type ('agent' or 'audiensi') |

**Response 200 OK:**
```json
{
  "items": [
    {
      "id": 1,
      "chatbot_type": "agent",
      "title": "Handle forwarding requests",
      "content": "When user asks to forward to secretariat...",
      "situation_tags": "forward,secretariat",
      "trigger_keywords": "teruskan,forward,sekretariat",
      "is_active": true,
      "created_at": "2024-01-15T10:00:00Z"
    }
  ]
}
```

---

### POST /knowledge-items
Create a new knowledge item.

**Request Body:**
```json
{
  "chatbot_type": "agent",
  "title": "Handle forwarding requests",
  "content": "When user asks to forward to secretariat, respond with...",
  "situation_tags": "forward,secretariat",
  "trigger_keywords": "teruskan,forward,sekretariat"
}
```

**Response 200 OK:**
```json
{
  "id": 10,
  "status": "ok"
}
```

**Response 422 Unprocessable Entity:**
```json
{
  "detail": "chatbot_type must be 'agent' or 'audiensi'"
}
```

---

### PATCH /knowledge-items/{item_id}
Update a knowledge item.

**Path Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| item_id | integer | Yes | Knowledge item ID |

**Request Body:**
```json
{
  "title": "Updated title",
  "content": "Updated content",
  "is_active": false,
  "situation_tags": "updated,tags",
  "trigger_keywords": "updated,keywords"
}
```

**Response 200 OK:**
```json
{
  "status": "ok"
}
```

**Response 422 Unprocessable Entity:**
```json
{
  "detail": "No fields to update"
}
```

---

### DELETE /knowledge-items/{item_id}
Delete a knowledge item.

**Path Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| item_id | integer | Yes | Knowledge item ID |

**Response 200 OK:**
```json
{
  "status": "ok"
}
```

---

### POST /knowledge-items/upload
Upload a file as a knowledge item.

**Request:** multipart/form-data
- `file`: The file to upload
- `chatbot_type`: string (required) - 'agent' or 'audiensi'

**Supported file types:**
- Text files (.txt, .md)
- CSV (.csv)
- Word documents (.docx)
- PDF (.pdf)

**File size limit:** 5MB

**Response 200 OK:**
```json
{
  "id": 15,
  "status": "ok",
  "title": "knowledge_document",
  "content_length": 12345
}
```

**Response 400 Bad Request:**
```json
{
  "detail": "Unsupported file type: .exe. Allowed: .txt, .md, .csv, .docx, .pdf"
}
```

---

## API Logs

### GET /api-logs
List API call logs with optional filters and pagination.

**Query Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| chatbot_type | string | No | - | Filter by chatbot type |
| conversation_id | integer | No | - | Filter by conversation ID |
| call_type | string | No | - | Filter by call type |
| limit | integer | No | 50 | Max records to return |
| offset | integer | No | 0 | Number of records to skip |

**Response 200 OK:**
```json
{
  "logs": [
    {
      "id": 1,
      "chatbot_type": "agent",
      "conversation_id": 50,
      "call_type": "process_incoming",
      "request_payload": "{\"phone\": \"+628...\", \"message\": \"...\"}",
      "response_data": "{\"response_message\": \"...\"}",
      "status_code": 200,
      "duration_ms": 1234,
      "created_at": "2024-01-15T10:00:00Z"
    }
  ]
}
```

---

### GET /api-logs/{log_id}
Get full detail of a single API call log.

**Path Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| log_id | integer | Yes | API log ID |

**Response 200 OK:**
```json
{
  "id": 1,
  "chatbot_type": "agent",
  "conversation_id": 50,
  "call_type": "process_incoming",
  "request_payload": "{\"phone\": \"+628...\", \"message\": \"...\"}",
  "response_data": "{\"response_message\": \"...\"}",
  "status_code": 200,
  "duration_ms": 1234,
  "created_at": "2024-01-15T10:00:00Z"
}
```

**Response 404 Not Found:**
```json
{
  "detail": "API log not found"
}
```

---

## Audiensi

### GET /audiensi
List audiensi conversations with optional state filter.

**Query Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| state | string | No | - | Filter by state |
| limit | integer | No | 100 | Max records to return |
| offset | integer | No | 0 | Number of records to skip |

**Audiensi States:**
- `QUEUED` - Pending approval
- `APPROVED` - Approved, initial message sent
- `INITIAL_SENT` - Initial message sent
- `SCHEDULED` - Zoom scheduled
- `ZOOM_SENT` - Zoom link sent
- `REFUSED` - Refused
- `ABANDONED` - Abandoned

**Response 200 OK:**
```json
{
  "audiensi": [
    {
      "id": 1,
      "source_conversation_id": 50,
      "university_id": 1,
      "university_name": "Universitas Indonesia",
      "contact_phone": "+6281234567890",
      "contact_name": "John Doe",
      "rector_name": "Prof. Dr. Jane Smith",
      "province": "DKI Jakarta",
      "state": "QUEUED",
      "initial_message_draft": "Selamat pagi, saya dari...",
      "pdf_path": "/path/to/document.pdf",
      "zoom_link": null,
      "approved_at": null,
      "created_at": "2024-01-15T10:00:00Z"
    }
  ],
  "total": 25
}
```

---

### GET /audiensi/queue
Get pending approval queue.

**Response 200 OK:**
```json
{
  "queued": [
    {
      "id": 1,
      "university_name": "Universitas Indonesia",
      "contact_name": "John Doe",
      "contact_phone": "+6281234567890",
      "rector_name": "Prof. Dr. Jane Smith",
      "created_at": "2024-01-15T10:00:00Z"
    }
  ]
}
```

---

### GET /audiensi/stats
Get audiensi dashboard stats.

**Response 200 OK:**
```json
{
  "total": 50,
  "queued": 10,
  "approved": 15,
  "scheduled": 8,
  "zoom_sent": 12,
  "refused": 3,
  "abandoned": 2
}
```

---

### GET /audiensi/{aud_id}
Get a single audiensi conversation by ID.

**Path Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| aud_id | integer | Yes | Audiensi conversation ID |

**Response 200 OK:**
```json
{
  "id": 1,
  "source_conversation_id": 50,
  "university_id": 1,
  "university_name": "Universitas Indonesia",
  "contact_phone": "+6281234567890",
  "contact_name": "John Doe",
  "rector_name": "Prof. Dr. Jane Smith",
  "province": "DKI Jakarta",
  "state": "QUEUED",
  "initial_message_draft": "Selamat pagi, saya dari...",
  "pdf_path": "/path/to/document.pdf",
  "zoom_link": null,
  "approved_at": null,
  "created_at": "2024-01-15T10:00:00Z",
  "message_history": "[...]"
}
```

**Response 404 Not Found:**
```json
{
  "detail": "Audiensi not found"
}
```

---

### PUT /audiensi/{aud_id}/rector-name
Edit rector name for an audiensi conversation.

**Path Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| aud_id | integer | Yes | Audiensi conversation ID |

**Request Body:**
```json
{
  "rector_name": "Prof. Dr. Jane Smith"
}
```

**Response 200 OK:**
```json
{
  "status": "ok"
}
```

**Response 404 Not Found:**
```json
{
  "detail": "Audiensi not found"
}
```

---

### PUT /audiensi/{aud_id}/initial-message
Edit initial message draft.

**Path Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| aud_id | integer | Yes | Audiensi conversation ID |

**Request Body:**
```json
{
  "message": "Selamat pagi, saya dari Asosiasi AI Indonesia..."
}
```

**Response 200 OK:**
```json
{
  "status": "ok"
}
```

**Response 404 Not Found:**
```json
{
  "detail": "Audiensi not found"
}
```

---

### POST /audiensi/{aud_id}/regenerate-pdf
Regenerate PDF after edits (rector name, etc.).

**Path Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| aud_id | integer | Yes | Audiensi conversation ID |

**Response 200 OK:**
```json
{
  "status": "ok",
  "pdf_path": "/path/to/new_document.pdf"
}
```

**Response 404 Not Found:**
```json
{
  "detail": "Audiensi not found"
}
```

**Response 500 Internal Server Error:**
```json
{
  "detail": "PDF generation failed: Error details"
}
```

---

### GET /audiensi/{aud_id}/pdf
Download/preview the generated PDF.

**Path Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| aud_id | integer | Yes | Audiensi conversation ID |

**Response 200 OK:**
```
Content-Type: application/octet-stream
Content-Disposition: attachment; filename="document.pdf"

Binary PDF file
```

**Response 404 Not Found:**
```json
{
  "detail": "PDF not found"
}
```

---

### POST /audiensi/{aud_id}/approve
Approve audiensi & send initial message + document.

**Path Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| aud_id | integer | Yes | Audiensi conversation ID |

**Response 200 OK:**
```json
{
  "status": "ok",
  "message": "Audiensi approved, messages being sent"
}
```

**Response 404 Not Found:**
```json
{
  "detail": "Audiensi not found"
}
```

**Response 400 Bad Request:**
```json
{
  "detail": "Cannot approve: state is SCHEDULED"
}
```

---

### POST /audiensi/{aud_id}/reject
Reject/cancel an audiensi.

**Path Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| aud_id | integer | Yes | Audiensi conversation ID |

**Response 200 OK:**
```json
{
  "status": "ok"
}
```

**Response 404 Not Found:**
```json
{
  "detail": "Audiensi not found"
}
```

---

### POST /audiensi/{aud_id}/send-zoom
Manually send zoom link for a scheduled audiensi.

**Path Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| aud_id | integer | Yes | Audiensi conversation ID |

**Response 200 OK:**
```json
{
  "status": "ok",
  "zoom_link": "https://zoom.us/j/123456789"
}
```

**Response 404 Not Found:**
```json
{
  "detail": "Audiensi not found"
}
```

---

### POST /audiensi/template/upload
Upload a new .docx template for audiensi invitations.

**Request:** multipart/form-data with file upload

**Response 200 OK:**
```json
{
  "status": "ok",
  "path": "/path/to/template.docx"
}
```

**Response 400 Bad Request:**
```json
{
  "detail": "Only .docx files allowed"
}
```

---

### GET /audiensi/template/placeholders
List available template placeholders.

**Response 200 OK:**
```json
{
  "placeholders": [
    {
      "key": "{{university_name}}",
      "description": "Nama universitas"
    },
    {
      "key": "{{rector_name}}",
      "description": "Nama rektor"
    },
    {
      "key": "{{province}}",
      "description": "Provinsi"
    },
    {
      "key": "{{date}}",
      "description": "Tanggal surat"
    }
  ]
}
```

---

## Instagram

### POST /instagram/reset-sessions
Reset all IG sessions to healthy state (e.g. after updating session IDs).

**Response 200 OK:**
```json
{
  "success": true,
  "message": "All IG sessions reset to healthy",
  "status": {
    "total_sessions": 5,
    "healthy_sessions": 5,
    "unhealthy_sessions": 0
  }
}
```

---

## Health Check

### GET /health
Health check endpoint with service status.

**Response 200 OK:**
```json
{
  "status": "ok",
  "whatsapp": {
    "connected": true,
    "phone": "+6281234567890",
    "pushName": "GetContact Bot"
  },
  "instagram": {
    "total_sessions": 5,
    "healthy_sessions": 5,
    "unhealthy_sessions": 0
  },
  "api_keys": {
    "serper": {
      "configured": true,
      "working": true
    },
    "apify": {
      "configured": false,
      "working": false
    },
    "scrapingbot": {
      "configured": true,
      "working": true
    }
  }
}
```

---

## Export

### GET /export/csv
Export all universities with contacts as CSV.

**Response 200 OK:**
```
Content-Type: text/csv
Content-Disposition: attachment; filename=universities_export.csv

id,name,province,website,ig_handle,status,secretariat_phone,created_at
1,Universitas Indonesia,DKI Jakarta,https://ui.ac.id,universitas.indonesia,ig_found,,2024-01-15T10:30:00Z
...
```

---

## Error Codes

| Code | Description |
|------|-------------|
| 200 | Success |
| 201 | Created |
| 400 | Bad Request - Invalid input or parameters |
| 404 | Not Found - Resource doesn't exist |
| 409 | Conflict - Resource already exists or operation in progress |
| 422 | Unprocessable Entity - Validation error |
| 500 | Internal Server Error |
| 502 | Bad Gateway - External service unavailable |

---

## Rate Limiting

Currently no rate limiting. Future versions will implement:
- 100 requests per minute per IP
- 1000 requests per hour per IP

---

## WebSocket

### Connection
`ws://localhost:8000/ws/pipeline`

Real-time pipeline updates (planned feature).

**Message Format:**
```json
{
  "type": "phase_update",
  "phase": 3,
  "status": "running",
  "message": "Extracting phone numbers from Instagram posts",
  "progress": 45
}
```

---

## OpenAPI Specification

Full OpenAPI 3.0 specification available at:
```
http://localhost:8000/openapi.json
```

Swagger UI available at:
```
http://localhost:8000/docs
```

ReDoc available at:
```
http://localhost:8000/redoc
```
