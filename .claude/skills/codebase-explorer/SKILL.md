# Codebase Explorer Skill

## Purpose
This skill teaches agents how to quickly explore and understand the GetContactAIAgent codebase.

## Quick Exploration Strategy

### Step 1: Understand Structure
```bash
# List top-level directories
ls -la

# Expected output:
orchestrator/    # Python FastAPI backend
whatsapp-service/  # Node.js WhatsApp bridge
frontend/        # React dashboard
data/            # SQLite database
scripts/         # Utility scripts
```

### Step 2: Scan Key Files (Backend)
```bash
# Use Glob to find main Python files
**/main.py        # FastAPI entry point
**/db.py          # Database schema
**/conversation.py # State machine
**/config.py      # Configuration

# Use Read on each to understand patterns
```

### Step 3: Scan Key Files (Frontend)
```bash
# Use Glob to find React structure
**/App.tsx        # Router setup
**/pages/**/*.tsx # Page components
**/components/**/*.tsx  # UI components

# Read a few to understand patterns
```

### Step 4: Find Similar Patterns
When implementing new feature, find existing similar code:

```bash
# Use Grep to search for patterns
grep -r "async def create_" orchestrator/  # Find create functions
grep -r "interface.*Props" frontend/src/   # Find component props
```

## Specific Patterns to Look For

### Backend Patterns

#### API Endpoint Pattern
```python
# In orchestrator/main.py
@router.get("/api/v1/universities")
async def get_universities(
    skip: int = 0,
    limit: int = 100
) -> Dict[str, Any]:
    """Get all universities with pagination."""
    try:
        async with aiosqlite.connect(DATABASE_PATH) as db:
            async with db.execute(
                "SELECT * FROM universities LIMIT ? OFFSET ?",
                (limit, skip)
            ) as cursor:
                rows = await cursor.fetchall()
                return {
                    "status": "success",
                    "data": [dict(row) for row in rows]
                }
    except Exception as e:
        logger.error(f"Error fetching universities: {e}")
        raise HTTPException(status_code=500, detail=str(e))
```

#### Database Query Pattern
```python
# In orchestrator/db.py or services
async with aiosqlite.connect(DATABASE_PATH) as db:
    # Single row
    async with db.execute(
        "SELECT * FROM table WHERE id = ?", (id,)
    ) as cursor:
        row = await cursor.fetchone()
        return dict(row) if row else None

    # Multiple rows
    async with db.execute(
        "SELECT * FROM table WHERE status = ?", (status,)
    ) as cursor:
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    # Insert
    await db.execute(
        "INSERT INTO table (col1, col2) VALUES (?, ?)",
        (val1, val2)
    )
    await db.commit()
```

### Frontend Patterns

#### Component Pattern
```tsx
// In frontend/src/components/ or pages/
import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';

interface ComponentProps {
  id: string;
}

export function Component({ id }: ComponentProps) {
  const { data, isLoading, error } = useQuery({
    queryKey: ['resource', id],
    queryFn: () => fetchResource(id),
  });

  if (isLoading) return <div>Loading...</div>;
  if (error) return <div>Error</div>;

  return <div>{data?.name}</div>;
}
```

#### Service Layer Pattern
```tsx
// In frontend/src/services/
import axios from 'axios';

const API_URL = import.meta.env.VITE_API_URL;

export const resourceService = {
  getAll: async () => {
    const { data } = await axios.get(`${API_URL}/api/v1/resource`);
    return data.data;
  },

  getById: async (id: string) => {
    const { data } = await axios.get(`${API_URL}/api/v1/resource/${id}`);
    return data.data;
  },

  create: async (payload: CreateData) => {
    const { data } = await axios.post(`${API_URL}/api/v1/resource`, payload);
    return data.data;
  },
};
```

## Tools Strategy

### Glob Usage
```bash
# Find all Python files
**/*.py

# Find all React components
**/*.tsx

# Find test files
**/*.test.tsx
**/test_*.py

# Find configuration files
**/config.py
**/vite.config.ts
```

### Grep Usage
```bash
# Find function definitions
grep -r "async def " orchestrator/

# Find interface definitions
grep -r "interface " frontend/src/

# Find TODO comments
grep -r "TODO" .

# Find imports to understand dependencies
grep -r "from fastapi" orchestrator/
grep -r "import.*React" frontend/src/
```

### Read Strategy
1. **Read main entry points first:**
   - `orchestrator/main.py`
   - `frontend/src/App.tsx`
   - `whatsapp-service/src/index.ts`

2. **Read one example of each pattern:**
   - One controller/endpoint
   - One service class
   - One database query
   - One React page
   - One React component

3. **Read files related to the feature being built:**
   - If building university feature: read university-related files
   - If building conversation feature: read conversation.py

## Common Gotchas

### Backend
- **Async/await:** All database operations must use async/await
- **SQL injection:** Never use f-strings in SQL, always use `?` placeholders
- **Error handling:** Always wrap in try-except, log errors, raise HTTPException

### Frontend
- **Type safety:** Avoid `any`, define proper interfaces
- **API URL:** Use `import.meta.env.VITE_API_URL`, don't hardcode
- **Loading states:** Always handle loading and error states in async operations

## Quick Reference Commands

```bash
# Count lines of code (rough estimate)
find orchestrator/ -name "*.py" | xargs wc -l
find frontend/src/ -name "*.tsx" -o -name "*.ts" | xargs wc -l

# Find all routes/endpoints
grep -r "@router\." orchestrator/

# Find all React routes
grep -r "path=" frontend/src/

# Check database schema
grep -r "CREATE TABLE" orchestrator/
```

## Document Findings

After exploration, create/update `docs/codebase-context-report.md` with:

1. **Project structure** - directories and key files
2. **Tech stack confirmation** - frameworks, libraries
3. **Conventions found** - patterns used in codebase
4. **Touch points** - files that need modification for new feature
5. **Reusable components** - existing code that can be reused
6. **Risks** - potential breaking changes
