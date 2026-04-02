---
name: nodejs-conventions
description: >
  Standar dan konvensi penulisan kode Node.js/Express untuk tim.
  Gunakan setiap kali be-developer menulis atau memodifikasi
  kode Node.js — routes, controllers, services, middleware,
  models (Prisma/Sequelize), dan utility functions.
---

# Node.js / Express Conventions

## Convention Adoption Gate

**Jalankan ini PERTAMA sebelum apply konvensi apapun.**

### Step 1 — Deteksi Project Type
```bash
find src -name "*.js" -o -name "*.ts" 2>/dev/null | wc -l
```
Jika output `0` → **GREENFIELD**. Skip gate, apply konvensi penuh langsung.
Jika output > 0 → **EXISTING PROJECT**. Lanjut ke Step 2.

### Step 2 — Migration Risk Assessment
```bash
# Cek module system
head -3 src/index.js src/app.js 2>/dev/null | grep "require(" && echo "COMMONJS" || echo "ESM_OR_EMPTY"
# Cek TypeScript
ls tsconfig.json 2>/dev/null && echo "HAS_TS" || echo "NO_TS"
# Cek test suite
cat package.json 2>/dev/null | grep '"test"' | grep -v "no test\|echo" && echo "HAS_TESTS" || echo "NO_TESTS"
# Core libraries yang incompatible dengan ESM
cat package.json 2>/dev/null | grep -E '"whatsapp-web|"puppeteer|"electron' && echo "ESM_INCOMPATIBLE_CORE" || echo "OK"
# Jumlah file terdampak
find src -name "*.js" -o -name "*.ts" 2>/dev/null | wc -l
```

### Step 3 — Hitung Risk Score
```
+40  Core library tidak support ESM (whatsapp-web.js, puppeteer, electron, dll)
+30  Tidak ada test suite
+20  > 20 file yang harus diubah
+20  Mixed: sebagian require(), sebagian import
+10  Tidak ada TypeScript
```

### Step 4 — Decision
```
< 40%  → Apply konvensi penuh. Catat di file header: migrated [YYYY-MM-DD]
40-79% → STOP. Tampilkan ke programmer:
         "⚠️ Convention migration risk: [N]%
          Impact: [N] files | Reason: [alasan]
          APPROVE → proceed | SKIP → keep existing + catat tech debt"
≥ 80%  → KEEP AS IS. Otomatis tanpa tanya.
         Catat ke .claude/memory/tech-debt.md:
         "[YYYY-MM-DD] Node.js convention migration skipped — risk [N]% ([alasan])"
         Lanjut dengan konvensi existing. Tampilkan:
         "ℹ️ Convention migration skipped (risk [N]%). Pakai konvensi existing."
```

Setelah gate: konvensi di bawah berlaku untuk **kode baru** jika migration di-skip,
atau untuk **semua kode** jika migration disetujui/greenfield.

---

## Prinsip Utama
- Gunakan ES Modules (import/export), bukan CommonJS (require)
- Gunakan async/await, bukan callback atau .then()
- Gunakan TypeScript jika project sudah setup TS
- Pisahkan concerns: routes → controllers → services → repositories
- Semua error handling via middleware terpusat

---

## Struktur Folder

```
src/
├── config/           ← konfigurasi app, db, dll
│   ├── database.ts
│   └── app.ts
├── routes/           ← definisi endpoint saja
│   ├── index.ts      ← gabungkan semua routes
│   └── user.routes.ts
├── controllers/      ← handle request & response
│   └── user.controller.ts
├── services/         ← business logic
│   └── user.service.ts
├── repositories/     ← query database
│   └── user.repository.ts
├── middleware/       ← auth, validation, error handler
│   ├── auth.middleware.ts
│   ├── validate.middleware.ts
│   └── error.middleware.ts
├── models/           ← Prisma schema atau Sequelize models
├── types/            ← TypeScript interfaces & types
│   └── user.types.ts
├── utils/            ← helper functions
│   └── response.util.ts
└── main.ts           ← entry point
```

---

## Naming Convention

```
File        : kebab-case          → user.controller.ts
Class       : PascalCase          → UserController
Function    : camelCase           → getUserById
Variable    : camelCase           → userId, orderItems
Constant    : UPPER_SNAKE_CASE    → MAX_RETRY_COUNT
Interface   : PascalCase + I      → IUser, ICreateUserDto
Type        : PascalCase          → UserResponse
Enum        : PascalCase          → UserStatus
```

---

## Entry Point

```typescript
// src/main.ts
import express from 'express';
import cors from 'cors';
import helmet from 'helmet';
import morgan from 'morgan';
import { router } from './routes';
import { errorMiddleware } from './middleware/error.middleware';

const app = express();
const PORT = process.env.PORT || 3000;

// Middleware
app.use(helmet());
app.use(cors());
app.use(morgan('dev'));
app.use(express.json());
app.use(express.urlencoded({ extended: true }));

// Routes
app.use('/api/v1', router);

// Error handler — selalu taruh paling akhir
app.use(errorMiddleware);

app.listen(PORT, () => {
  console.log(`Server running on port ${PORT}`);
});

export default app;
```

---

## Routes

```typescript
// src/routes/user.routes.ts
import { Router } from 'express';
import { UserController } from '../controllers/user.controller';
import { authMiddleware } from '../middleware/auth.middleware';
import { validate } from '../middleware/validate.middleware';
import { createUserSchema, updateUserSchema } from '../validators/user.validator';

const router = Router();
const userController = new UserController();

// Public
router.post('/auth/login', userController.login);
router.post('/auth/register',
  validate(createUserSchema),
  userController.register
);

// Protected
router.use(authMiddleware);
router.get('/', userController.index);
router.get('/:id', userController.show);
router.post('/', validate(createUserSchema), userController.store);
router.put('/:id', validate(updateUserSchema), userController.update);
router.delete('/:id', userController.destroy);

export { router as userRouter };
```

```typescript
// src/routes/index.ts
import { Router } from 'express';
import { userRouter } from './user.routes';

const router = Router();

router.use('/users', userRouter);
// tambahkan router lain di sini

export { router };
```

---

## Controller

```typescript
// src/controllers/user.controller.ts
import { Request, Response, NextFunction } from 'express';
import { UserService } from '../services/user.service';
import { sendSuccess, sendCreated } from '../utils/response.util';

export class UserController {
  private userService: UserService;

  constructor() {
    this.userService = new UserService();
  }

  index = async (req: Request, res: Response, next: NextFunction) => {
    try {
      const { page = 1, limit = 15 } = req.query;
      const users = await this.userService.getAllPaginated(
        Number(page),
        Number(limit)
      );
      sendSuccess(res, users);
    } catch (error) {
      next(error); // selalu pass error ke next()
    }
  };

  show = async (req: Request, res: Response, next: NextFunction) => {
    try {
      const user = await this.userService.findById(Number(req.params.id));
      sendSuccess(res, user);
    } catch (error) {
      next(error);
    }
  };

  store = async (req: Request, res: Response, next: NextFunction) => {
    try {
      const user = await this.userService.createUser(req.body);
      sendCreated(res, user);
    } catch (error) {
      next(error);
    }
  };

  update = async (req: Request, res: Response, next: NextFunction) => {
    try {
      const user = await this.userService.updateUser(
        Number(req.params.id),
        req.body
      );
      sendSuccess(res, user);
    } catch (error) {
      next(error);
    }
  };

  destroy = async (req: Request, res: Response, next: NextFunction) => {
    try {
      await this.userService.deleteUser(Number(req.params.id));
      sendSuccess(res, null, 'Deleted successfully');
    } catch (error) {
      next(error);
    }
  };
}
```

---

## Service

```typescript
// src/services/user.service.ts
import { UserRepository } from '../repositories/user.repository';
import { ICreateUserDto, IUpdateUserDto, IUser } from '../types/user.types';
import { NotFoundError, ConflictError } from '../utils/errors';

export class UserService {
  private userRepository: UserRepository;

  constructor() {
    this.userRepository = new UserRepository();
  }

  async getAllPaginated(page: number, limit: number) {
    const offset = (page - 1) * limit;
    return this.userRepository.findAll({ limit, offset });
  }

  async findById(id: number): Promise<IUser> {
    const user = await this.userRepository.findById(id);
    if (!user) {
      throw new NotFoundError(`User with ID ${id} not found`);
    }
    return user;
  }

  async createUser(data: ICreateUserDto): Promise<IUser> {
    const existing = await this.userRepository.findByEmail(data.email);
    if (existing) {
      throw new ConflictError('Email already registered');
    }
    return this.userRepository.create(data);
  }

  async updateUser(id: number, data: IUpdateUserDto): Promise<IUser> {
    await this.findById(id); // throws if not found
    return this.userRepository.update(id, data);
  }

  async deleteUser(id: number): Promise<void> {
    await this.findById(id); // throws if not found
    await this.userRepository.delete(id);
  }
}
```

---

## Repository (dengan Prisma)

```typescript
// src/repositories/user.repository.ts
import { prisma } from '../config/database';
import { ICreateUserDto, IUpdateUserDto } from '../types/user.types';

export class UserRepository {
  async findAll(options: { limit: number; offset: number }) {
    const [data, total] = await Promise.all([
      prisma.user.findMany({
        where: { deletedAt: null },
        skip: options.offset,
        take: options.limit,
        orderBy: { createdAt: 'desc' },
      }),
      prisma.user.count({ where: { deletedAt: null } }),
    ]);
    return { data, total };
  }

  async findById(id: number) {
    return prisma.user.findFirst({
      where: { id, deletedAt: null },
    });
  }

  async findByEmail(email: string) {
    return prisma.user.findFirst({
      where: { email, deletedAt: null },
    });
  }

  async create(data: ICreateUserDto) {
    return prisma.user.create({ data });
  }

  async update(id: number, data: IUpdateUserDto) {
    return prisma.user.update({ where: { id }, data });
  }

  async delete(id: number) {
    // Soft delete
    return prisma.user.update({
      where: { id },
      data: { deletedAt: new Date() },
    });
  }
}
```

---

## Error Middleware (Terpusat)

```typescript
// src/middleware/error.middleware.ts
import { Request, Response, NextFunction } from 'express';
import { AppError } from '../utils/errors';

export const errorMiddleware = (
  err: Error,
  req: Request,
  res: Response,
  next: NextFunction
) => {
  if (err instanceof AppError) {
    return res.status(err.statusCode).json({
      success: false,
      message: err.message,
    });
  }

  // Unexpected error
  console.error('Unexpected error:', err);
  return res.status(500).json({
    success: false,
    message: 'Internal server error',
  });
};
```

```typescript
// src/utils/errors.ts
export class AppError extends Error {
  constructor(
    message: string,
    public statusCode: number = 500
  ) {
    super(message);
    this.name = this.constructor.name;
  }
}

export class NotFoundError extends AppError {
  constructor(message = 'Resource not found') {
    super(message, 404);
  }
}

export class ConflictError extends AppError {
  constructor(message = 'Resource already exists') {
    super(message, 409);
  }
}

export class UnauthorizedError extends AppError {
  constructor(message = 'Unauthorized') {
    super(message, 401);
  }
}
```

---

## Response Utility

```typescript
// src/utils/response.util.ts
import { Response } from 'express';

export const sendSuccess = (
  res: Response,
  data: any,
  message = 'Success',
  statusCode = 200
) => {
  res.status(statusCode).json({ success: true, message, data });
};

export const sendCreated = (res: Response, data: any) => {
  sendSuccess(res, data, 'Created successfully', 201);
};
```

---

## Environment Config

```typescript
// src/config/app.ts
// Selalu validasi env vars saat startup
export const config = {
  port: process.env.PORT || 3000,
  nodeEnv: process.env.NODE_ENV || 'development',
  jwtSecret: process.env.JWT_SECRET!,  // ! = wajib ada
  dbUrl: process.env.DATABASE_URL!,
};

// Validasi saat startup
const required = ['JWT_SECRET', 'DATABASE_URL'];
for (const key of required) {
  if (!process.env[key]) {
    throw new Error(`Missing required environment variable: ${key}`);
  }
}
```

---

## Checklist Sebelum Commit

- [ ] Semua async function pakai try/catch dan pass ke next()
- [ ] Tidak ada business logic di controller
- [ ] Tidak ada query database di service/controller
- [ ] Error pakai custom AppError class
- [ ] Tidak ada console.log tertinggal (pakai logger)
- [ ] Tidak ada hardcoded URL, secret, atau credential
- [ ] Semua env var diakses via config object
- [ ] TypeScript tidak ada type `any` yang tidak perlu
- [ ] Jalankan: `docker compose exec node pnpm test`
- [ ] Jalankan: `docker compose exec node pnpm lint`
