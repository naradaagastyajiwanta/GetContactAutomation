---
name: python-conventions
description: >
  Standar dan konvensi penulisan kode Python untuk tim.
  Gunakan setiap kali be-developer menulis atau memodifikasi
  kode Python — FastAPI/Flask endpoints, services, repositories,
  models SQLAlchemy, schemas Pydantic, dan utilities.
---

# Python Conventions

## Convention Adoption Gate

**Jalankan ini PERTAMA sebelum apply konvensi apapun.**

### Step 1 — Deteksi Project Type
```bash
find . -name "*.py" -not -path "*/\.*" 2>/dev/null | wc -l
```
Jika output `0` → **GREENFIELD**. Skip gate, apply konvensi penuh langsung.
Jika output > 0 → **EXISTING PROJECT**. Lanjut ke Step 2.

### Step 2 — Migration Risk Assessment
```bash
# Cek framework
cat requirements.txt pyproject.toml 2>/dev/null | grep -E "fastapi|flask|django" | head -3
# Cek typing existing
find . -name "*.py" -not -path "*/\.*" | head -10 | xargs grep -l "from typing\|: str\|: int" 2>/dev/null | wc -l
# Cek test suite
ls tests/ test/ 2>/dev/null && echo "HAS_TESTS" || echo "NO_TESTS"
# Jumlah file terdampak
find . -name "*.py" -not -path "*/\.*" 2>/dev/null | wc -l
# Cek apakah Pydantic sudah dipakai
grep -r "pydantic\|BaseModel" . --include="*.py" 2>/dev/null | wc -l
```

### Step 3 — Hitung Risk Score
```
+40  Framework tidak compatible dengan target pattern (Flask → FastAPI migration)
+30  Tidak ada test suite
+20  > 20 file yang harus diubah
+20  Tidak ada type hints sama sekali di existing code
+10  Tidak ada Pydantic (validation layer perlu ditambahkan)
```

### Step 4 — Decision
```
< 40%  → Apply konvensi penuh.
40-79% → STOP. Tampilkan ke programmer:
         "⚠️ Convention migration risk: [N]%
          Impact: [N] files | Reason: [alasan]
          APPROVE → proceed | SKIP → keep existing + catat tech debt"
≥ 80%  → KEEP AS IS. Otomatis tanpa tanya.
         Catat ke .claude/memory/tech-debt.md:
         "[YYYY-MM-DD] Python convention migration skipped — risk [N]% ([alasan])"
         Tampilkan: "ℹ️ Convention migration skipped (risk [N]%). Pakai konvensi existing."
```

---

## Prinsip Utama
- Ikuti PEP 8 coding style
- Gunakan type hints di semua function signature
- Gunakan Pydantic untuk validation dan serialization
- Gunakan async/await untuk I/O operations (FastAPI)
- Pisahkan concerns: router → controller → service → repository

---

## Struktur Folder (FastAPI)

```
app/
├── main.py               ← entry point
├── core/
│   ├── config.py         ← settings via pydantic-settings
│   └── security.py       ← JWT, password hashing
├── db/
│   ├── base.py           ← SQLAlchemy base
│   ├── session.py        ← database session
│   └── init_db.py        ← initial data
├── api/
│   └── v1/
│       ├── router.py     ← gabungkan semua endpoints
│       └── endpoints/
│           └── users.py  ← route handlers
├── services/             ← business logic
│   └── user_service.py
├── repositories/         ← database queries
│   └── user_repository.py
├── models/               ← SQLAlchemy models
│   └── user.py
├── schemas/              ← Pydantic schemas
│   └── user.py
└── utils/                ← helper functions
    └── response.py
```

---

## Naming Convention

```
File/Module   : snake_case          → user_service.py
Class         : PascalCase          → UserService
Function      : snake_case          → get_user_by_id
Variable      : snake_case          → user_id, order_items
Constant      : UPPER_SNAKE_CASE    → MAX_RETRY_COUNT
Schema Input  : PascalCase + Create/Update → UserCreate, UserUpdate
Schema Output : PascalCase + Response     → UserResponse
```

---

## Config (Pydantic Settings)

```python
# app/core/config.py
from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    APP_NAME: str = "content_automation"
    DEBUG: bool = False
    API_V1_STR: str = "/api/v1"

    DATABASE_URL: str
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    class Config:
        env_file = ".env"
        case_sensitive = True


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
```

---

## Database Session

```python
# app/db/session.py
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from app.core.config import settings

engine = create_async_engine(settings.DATABASE_URL, echo=settings.DEBUG)

AsyncSessionLocal = sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
```

---

## Model (SQLAlchemy)

```python
# app/models/user.py
from sqlalchemy import Boolean, Column, Integer, String, DateTime
from sqlalchemy.sql import func
from app.db.base import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    email = Column(String(255), unique=True, index=True, nullable=False)
    password = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    deleted_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    # orders = relationship("Order", back_populates="user")
```

---

## Schema (Pydantic)

```python
# app/schemas/user.py
from pydantic import BaseModel, EmailStr, Field
from datetime import datetime
from typing import Optional


# Base schema — shared fields
class UserBase(BaseModel):
    name: str = Field(..., min_length=2, max_length=255)
    email: EmailStr


# Create — fields needed saat create
class UserCreate(UserBase):
    password: str = Field(..., min_length=8)


# Update — semua optional saat update
class UserUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=2, max_length=255)
    email: Optional[EmailStr] = None
    is_active: Optional[bool] = None


# Response — yang dikembalikan ke client
class UserResponse(UserBase):
    id: int
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True  # enable ORM mode


# Paginated response
class UserListResponse(BaseModel):
    data: list[UserResponse]
    total: int
    page: int
    limit: int
```

---

## Repository

```python
# app/repositories/user_repository.py
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.models.user import User
from app.schemas.user import UserCreate, UserUpdate
from typing import Optional


class UserRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def find_all(
        self,
        page: int = 1,
        limit: int = 15
    ) -> tuple[list[User], int]:
        offset = (page - 1) * limit

        # Query data
        stmt = (
            select(User)
            .where(User.deleted_at.is_(None))
            .where(User.is_active == True)
            .offset(offset)
            .limit(limit)
            .order_by(User.created_at.desc())
        )
        result = await self.db.execute(stmt)
        users = result.scalars().all()

        # Count total
        count_stmt = (
            select(func.count())
            .select_from(User)
            .where(User.deleted_at.is_(None))
        )
        total = await self.db.scalar(count_stmt)

        return list(users), total or 0

    async def find_by_id(self, user_id: int) -> Optional[User]:
        stmt = select(User).where(
            User.id == user_id,
            User.deleted_at.is_(None)
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def find_by_email(self, email: str) -> Optional[User]:
        stmt = select(User).where(
            User.email == email,
            User.deleted_at.is_(None)
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def create(self, data: UserCreate) -> User:
        user = User(**data.model_dump())
        self.db.add(user)
        await self.db.flush()
        await self.db.refresh(user)
        return user

    async def update(self, user: User, data: UserUpdate) -> User:
        update_data = data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(user, field, value)
        await self.db.flush()
        await self.db.refresh(user)
        return user

    async def soft_delete(self, user: User) -> None:
        from datetime import datetime
        user.deleted_at = datetime.utcnow()
        await self.db.flush()
```

---

## Service

```python
# app/services/user_service.py
from sqlalchemy.ext.asyncio import AsyncSession
from app.repositories.user_repository import UserRepository
from app.schemas.user import UserCreate, UserUpdate, UserResponse
from app.utils.errors import NotFoundError, ConflictError
from app.core.security import hash_password


class UserService:
    def __init__(self, db: AsyncSession):
        self.repository = UserRepository(db)

    async def get_all_paginated(self, page: int, limit: int):
        users, total = await self.repository.find_all(page, limit)
        return {
            "data": users,
            "total": total,
            "page": page,
            "limit": limit,
        }

    async def get_by_id(self, user_id: int):
        user = await self.repository.find_by_id(user_id)
        if not user:
            raise NotFoundError(f"User with ID {user_id} not found")
        return user

    async def create_user(self, data: UserCreate):
        existing = await self.repository.find_by_email(data.email)
        if existing:
            raise ConflictError("Email already registered")

        # Hash password sebelum simpan
        data.password = hash_password(data.password)
        return await self.repository.create(data)

    async def update_user(self, user_id: int, data: UserUpdate):
        user = await self.get_by_id(user_id)
        return await self.repository.update(user, data)

    async def delete_user(self, user_id: int) -> None:
        user = await self.get_by_id(user_id)
        await self.repository.soft_delete(user)
```

---

## Router / Endpoint (FastAPI)

```python
# app/api/v1/endpoints/users.py
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_db
from app.services.user_service import UserService
from app.schemas.user import UserCreate, UserUpdate, UserResponse, UserListResponse

router = APIRouter(prefix="/users", tags=["users"])


def get_user_service(db: AsyncSession = Depends(get_db)) -> UserService:
    return UserService(db)


@router.get("/", response_model=UserListResponse)
async def index(
    page: int = 1,
    limit: int = 15,
    service: UserService = Depends(get_user_service),
):
    return await service.get_all_paginated(page, limit)


@router.get("/{user_id}", response_model=UserResponse)
async def show(
    user_id: int,
    service: UserService = Depends(get_user_service),
):
    return await service.get_by_id(user_id)


@router.post("/", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def store(
    data: UserCreate,
    service: UserService = Depends(get_user_service),
):
    return await service.create_user(data)


@router.put("/{user_id}", response_model=UserResponse)
async def update(
    user_id: int,
    data: UserUpdate,
    service: UserService = Depends(get_user_service),
):
    return await service.update_user(user_id, data)


@router.delete("/{user_id}", status_code=status.HTTP_200_OK)
async def destroy(
    user_id: int,
    service: UserService = Depends(get_user_service),
):
    await service.delete_user(user_id)
    return {"message": "Deleted successfully"}
```

---

## Custom Errors

```python
# app/utils/errors.py
from fastapi import HTTPException


class NotFoundError(HTTPException):
    def __init__(self, detail: str = "Resource not found"):
        super().__init__(status_code=404, detail=detail)


class ConflictError(HTTPException):
    def __init__(self, detail: str = "Resource already exists"):
        super().__init__(status_code=409, detail=detail)


class UnauthorizedError(HTTPException):
    def __init__(self, detail: str = "Unauthorized"):
        super().__init__(status_code=401, detail=detail)
```

---

## Checklist Sebelum Commit

- [ ] Semua function punya type hints
- [ ] Semua input divalidasi via Pydantic schema
- [ ] Tidak ada business logic di endpoint/router
- [ ] Tidak ada query database di service
- [ ] Soft delete dipakai (bukan hard delete) untuk data penting
- [ ] Tidak ada `print()` tertinggal
- [ ] Tidak ada hardcoded credential atau URL
- [ ] Semua config diakses via `settings` object
- [ ] Jalankan: `docker compose exec python pytest`
- [ ] Jalankan: `docker compose exec python flake8 app/`
