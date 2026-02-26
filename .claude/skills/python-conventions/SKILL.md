# Python FastAPI Conventions

## Stack
- Python 3.x
- FastAPI
- aiosqlite (async SQLite)
- OpenAI GPT-4o
- APScheduler

## File Structure
```
orchestrator/
├── main.py           # FastAPI app, routes, lifespan
├── config.py         # Env vars, logging setup
├── db.py             # Database schema, connection
├── conversation.py   # State machine, GPT integration
├── message_queue.py  # Queue management
├── scheduler.py      # APScheduler setup
└── agents/
    ├── base_agent.py
    ├── ig_handle_finder.py
    ├── ig_post_scraper.py
    └── ig_phone_extractor.py
```

## Code Style

### Function Definitions
```python
async def function_name(
    param1: str,
    param2: Optional[int] = None,
    **kwargs: Any
) -> Dict[str, Any]:
    """
    Brief description.

    Args:
        param1: Description
        param2: Description (optional)

    Returns:
        Dict with keys: key1, key2, ...

    Raises:
        ValueError: If invalid input
    """
    pass
```

### Database Operations (aiosqlite)
```python
# Safe: parameterized query
async with aiosqlite.connect(db_path) as db:
    async with db.execute(
        "SELECT * FROM table WHERE id = ?", (id,)
    ) as cursor:
        row = await cursor.fetchone()
        return dict(row) if row else None

# NEVER: string interpolation (SQL injection risk)
# async with db.execute(f"SELECT * FROM table WHERE id = '{id}'")
```

### API Response Format
```python
# Success response
return {
    "status": "success",
    "data": {"key": "value"}
}

# Error response
raise HTTPException(
    status_code=404,
    detail={"status": "error", "message": "Not found"}
)
```

### Error Handling
```python
try:
    result = await operation()
except Exception as e:
    logger.error(f"Operation failed: {e}")
    raise HTTPException(status_code=500, detail=str(e))
```

### Logging
```python
import logging
logger = logging.getLogger(__name__)

logger.info("Info message")
logger.warning("Warning message")
logger.error("Error message")
```

## Type Hints
```python
from typing import Dict, List, Optional, Any, AsyncIterator

def sync_func(x: int) -> str:
    return str(x)

async def async_func(x: str) -> Optional[Dict]:
    return {"key": x}
```

## Environment Variables
```python
# In config.py
import os
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("OPENAI_API_KEY")
DB_PATH = os.getenv("DATABASE_PATH", "data/getcontact.db")

# NEVER hardcode:
# API_KEY = "sk-..."  # ❌
```

## OpenAI Integration
```python
from openai import AsyncOpenAI

client = AsyncOpenAI(api_key=API_KEY)

async def get_completion(prompt: str) -> str:
    response = await client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7
    )
    return response.choices[0].message.content
```

## Testing (pytest + httpx)
```python
# tests/test_main.py
import pytest
from httpx import AsyncClient
from main import app

@pytest.mark.asyncio
async def test_endpoint():
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get("/api/v1/test")
        assert response.status_code == 200
        assert response.json()["status"] == "success"
```
