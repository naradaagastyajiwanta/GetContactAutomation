---
name: react-conventions
description: >
  Standar dan konvensi penulisan kode React/Next.js untuk tim.
  Gunakan setiap kali fe-developer menulis atau memodifikasi
  kode frontend — pages, components, hooks, stores, services,
  dan utilities. Wajib diikuti agar UI konsisten.
---

# React / Next.js Conventions

## Convention Adoption Gate

**Jalankan ini PERTAMA sebelum apply konvensi apapun.**

### Step 1 — Deteksi Project Type
```bash
find src -name "*.jsx" -o -name "*.tsx" -o -name "*.js" 2>/dev/null | wc -l
```
Jika output `0` → **GREENFIELD**. Skip gate, apply konvensi penuh langsung.
Jika output > 0 → **EXISTING PROJECT**. Lanjut ke Step 2.

### Step 2 — Migration Risk Assessment
```bash
# Cek framework + versi
cat package.json 2>/dev/null | grep -E '"react"|"next"|"vite"' | head -3
# Cek TypeScript
ls tsconfig.json 2>/dev/null && echo "HAS_TS" || echo "NO_TS"
# Cek router (Pages vs App)
ls pages/ 2>/dev/null && echo "PAGES_ROUTER" || ls app/ 2>/dev/null && echo "APP_ROUTER" || echo "NOT_NEXTJS"
# Cek test suite
cat package.json 2>/dev/null | grep '"test"' | grep -v "no test\|echo" && echo "HAS_TESTS" || echo "NO_TESTS"
# Jumlah komponen
find src -name "*.jsx" -o -name "*.tsx" 2>/dev/null | wc -l
```

### Step 3 — Hitung Risk Score
```
+40  Pages Router existing dan butuh migrasi ke App Router
+30  Tidak ada test suite
+20  > 20 komponen yang harus diubah
+20  Tidak ada TypeScript dan codebase besar (> 15 file)
+10  Class components masih dipakai
```

### Step 4 — Decision
```
< 40%  → Apply konvensi penuh.
40-79% → STOP. Tampilkan ke programmer:
         "⚠️ Convention migration risk: [N]%
          Impact: [N] components | Reason: [alasan]
          APPROVE → proceed | SKIP → keep existing + catat tech debt"
≥ 80%  → KEEP AS IS. Otomatis tanpa tanya.
         Catat ke .claude/memory/tech-debt.md:
         "[YYYY-MM-DD] React convention migration skipped — risk [N]% ([alasan])"
         Tampilkan: "ℹ️ Convention migration skipped (risk [N]%). Pakai konvensi existing."
```

---

## Prinsip Utama
- Gunakan TypeScript — tidak boleh ada implicit `any`
- Gunakan functional components + hooks, bukan class components
- Gunakan App Router (Next.js 13+), bukan Pages Router
- Pisahkan UI dari logic: komponen tipis, logic di hooks/services
- Server Components by default, Client Components hanya bila perlu

---

## Struktur Folder

```
src/
├── app/                    ← Next.js App Router
│   ├── layout.tsx          ← root layout
│   ├── page.tsx            ← halaman utama
│   ├── (auth)/             ← route group (tidak jadi URL)
│   │   ├── login/
│   │   │   └── page.tsx
│   │   └── register/
│   │       └── page.tsx
│   └── dashboard/
│       ├── layout.tsx
│       └── page.tsx
├── components/
│   ├── ui/                 ← komponen generik (Button, Input, Modal)
│   ├── layout/             ← Navbar, Sidebar, Footer
│   └── features/           ← komponen spesifik fitur
│       └── users/
│           ├── UserCard.tsx
│           ├── UserList.tsx
│           └── UserForm.tsx
├── hooks/                  ← custom hooks
│   ├── useAuth.ts
│   └── useUsers.ts
├── services/               ← API calls
│   └── user.service.ts
├── stores/                 ← Zustand stores
│   └── auth.store.ts
├── types/                  ← TypeScript interfaces
│   └── user.types.ts
├── lib/                    ← konfigurasi library (axios, queryClient)
│   ├── axios.ts
│   └── query-client.ts
└── utils/                  ← helper functions
    └── format.ts
```

---

## Naming Convention

```
Komponen    : PascalCase          → UserCard.tsx, LoginForm.tsx
Hook        : camelCase + use     → useAuth.ts, useUsers.ts
Service     : camelCase + Service → user.service.ts
Store       : camelCase + Store   → auth.store.ts
Type/Interface : PascalCase + I   → IUser, ICreateUserDto
Page file   : page.tsx            → selalu nama ini (Next.js)
Layout file : layout.tsx          → selalu nama ini (Next.js)
```

---

## Komponen — Aturan Dasar

```tsx
// ✅ BENAR — functional component dengan TypeScript
interface UserCardProps {
  user: IUser;
  onDelete?: (id: number) => void;
  className?: string;
}

export function UserCard({ user, onDelete, className }: UserCardProps) {
  return (
    <div className={cn('rounded-lg border p-4', className)}>
      <h3 className="font-semibold">{user.name}</h3>
      <p className="text-sm text-gray-500">{user.email}</p>
      {onDelete && (
        <button onClick={() => onDelete(user.id)}>
          Delete
        </button>
      )}
    </div>
  );
}

// ❌ SALAH — default export tanpa nama (susah debug)
export default function ({ user }) { ... }

// ❌ SALAH — props tanpa type
function UserCard(props) { ... }
```

---

## Server vs Client Component

```tsx
// Server Component (default) — TIDAK ada 'use client'
// Gunakan untuk: data fetching, static content, layout
// src/app/dashboard/page.tsx
import { getUsersAction } from '@/app/actions/user.actions';
import { UserList } from '@/components/features/users/UserList';

export default async function DashboardPage() {
  const users = await getUsersAction(); // fetch di server

  return (
    <main>
      <h1>Dashboard</h1>
      <UserList users={users} />
    </main>
  );
}
```

```tsx
// Client Component — tambah 'use client' di baris pertama
// Gunakan untuk: onClick, useState, useEffect, form input
// src/components/features/users/UserForm.tsx
'use client';

import { useState } from 'react';
import { useCreateUser } from '@/hooks/useUsers';

interface UserFormProps {
  onSuccess?: () => void;
}

export function UserForm({ onSuccess }: UserFormProps) {
  const { mutate: createUser, isPending } = useCreateUser();

  const handleSubmit = (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const formData = new FormData(e.currentTarget);
    createUser(
      {
        name: formData.get('name') as string,
        email: formData.get('email') as string,
      },
      { onSuccess }
    );
  };

  return (
    <form onSubmit={handleSubmit}>
      <input name="name" placeholder="Name" required />
      <input name="email" type="email" placeholder="Email" required />
      <button type="submit" disabled={isPending}>
        {isPending ? 'Saving...' : 'Save'}
      </button>
    </form>
  );
}
```

---

## Custom Hook

```typescript
// src/hooks/useUsers.ts
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { userService } from '@/services/user.service';
import { ICreateUserDto, IUser } from '@/types/user.types';

// Query keys — selalu definisikan sebagai konstanta
export const userKeys = {
  all: ['users'] as const,
  lists: () => [...userKeys.all, 'list'] as const,
  list: (page: number) => [...userKeys.lists(), { page }] as const,
  detail: (id: number) => [...userKeys.all, 'detail', id] as const,
};

export function useUsers(page: number = 1) {
  return useQuery({
    queryKey: userKeys.list(page),
    queryFn: () => userService.getAll(page),
  });
}

export function useUser(id: number) {
  return useQuery({
    queryKey: userKeys.detail(id),
    queryFn: () => userService.getById(id),
    enabled: !!id, // hanya fetch jika id ada
  });
}

export function useCreateUser() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (data: ICreateUserDto) => userService.create(data),
    onSuccess: () => {
      // Invalidate semua list queries setelah create
      queryClient.invalidateQueries({ queryKey: userKeys.lists() });
    },
  });
}

export function useDeleteUser() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (id: number) => userService.delete(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: userKeys.lists() });
    },
  });
}
```

---

## Service (API Calls)

```typescript
// src/services/user.service.ts
import { api } from '@/lib/axios';
import { IUser, ICreateUserDto, IUpdateUserDto } from '@/types/user.types';

interface PaginatedResponse<T> {
  data: T[];
  total: number;
  page: number;
  limit: number;
}

export const userService = {
  async getAll(page = 1, limit = 15): Promise<PaginatedResponse<IUser>> {
    const { data } = await api.get('/users', { params: { page, limit } });
    return data;
  },

  async getById(id: number): Promise<IUser> {
    const { data } = await api.get(`/users/${id}`);
    return data;
  },

  async create(payload: ICreateUserDto): Promise<IUser> {
    const { data } = await api.post('/users', payload);
    return data;
  },

  async update(id: number, payload: IUpdateUserDto): Promise<IUser> {
    const { data } = await api.put(`/users/${id}`, payload);
    return data;
  },

  async delete(id: number): Promise<void> {
    await api.delete(`/users/${id}`);
  },
};
```

---

## Axios Instance

```typescript
// src/lib/axios.ts
import axios from 'axios';

export const api = axios.create({
  baseURL: process.env.NEXT_PUBLIC_API_URL + '/api/v1',
  headers: {
    'Content-Type': 'application/json',
  },
});

// Request interceptor — tambah auth token
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// Response interceptor — handle error global
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      // Redirect ke login
      window.location.href = '/login';
    }
    return Promise.reject(error);
  }
);
```

---

## Store (Zustand)

```typescript
// src/stores/auth.store.ts
import { create } from 'zustand';
import { IUser } from '@/types/user.types';

interface AuthState {
  user: IUser | null;
  token: string | null;
  isAuthenticated: boolean;
  setUser: (user: IUser, token: string) => void;
  logout: () => void;
}

export const useAuthStore = create<AuthState>((set) => ({
  user: null,
  token: null,
  isAuthenticated: false,

  setUser: (user, token) => {
    localStorage.setItem('token', token);
    set({ user, token, isAuthenticated: true });
  },

  logout: () => {
    localStorage.removeItem('token');
    set({ user: null, token: null, isAuthenticated: false });
  },
}));
```

---

## Types

```typescript
// src/types/user.types.ts
export interface IUser {
  id: number;
  name: string;
  email: string;
  isActive: boolean;
  createdAt: string;
}

export interface ICreateUserDto {
  name: string;
  email: string;
  password: string;
}

export interface IUpdateUserDto {
  name?: string;
  email?: string;
  isActive?: boolean;
}
```

---

## Handle States di Komponen

```tsx
// Selalu handle semua state: loading, error, empty, data
export function UserList() {
  const { data, isLoading, isError } = useUsers();

  if (isLoading) return <LoadingSpinner />;
  if (isError) return <ErrorMessage message="Failed to load users" />;
  if (!data?.data.length) return <EmptyState message="No users found" />;

  return (
    <div>
      {data.data.map((user) => (
        <UserCard key={user.id} user={user} />
      ))}
    </div>
  );
}
```

---

## Environment Variables (Next.js)

```
# .env.local
NEXT_PUBLIC_API_URL=http://localhost:8000   ← expose ke browser (prefix NEXT_PUBLIC_)
DATABASE_URL=...                            ← server only (tanpa prefix)
```

```typescript
// Akses di kode
process.env.NEXT_PUBLIC_API_URL  // ✅ bisa di client & server
process.env.DATABASE_URL          // ✅ hanya di server
```

---

## Checklist Sebelum Commit

- [ ] Semua komponen punya TypeScript props interface
- [ ] Tidak ada `any` type yang tidak perlu
- [ ] Client component punya `'use client'` di baris pertama
- [ ] Semua state: loading, error, empty sudah dihandle
- [ ] Tidak ada API call langsung di komponen (pakai service)
- [ ] Tidak ada hardcoded URL API (pakai env var)
- [ ] Tidak ada `console.log` tertinggal
- [ ] Komponen tidak terlalu besar (max ~150 baris, pecah jika lebih)
- [ ] Query keys konsisten menggunakan konstanta
- [ ] Jalankan: `docker compose exec frontend pnpm lint`
- [ ] Jalankan: `docker compose exec frontend pnpm build`
