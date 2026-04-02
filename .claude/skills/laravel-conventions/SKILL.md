---
name: laravel-conventions
description: >
  Standar dan konvensi penulisan kode Laravel/PHP untuk tim.
  Gunakan setiap kali be-developer menulis atau memodifikasi
  kode PHP/Laravel — controller, model, service, migration,
  route, middleware, dll. Wajib diikuti agar kode konsisten.
---

# Laravel / PHP Conventions

## Convention Adoption Gate

**Jalankan ini PERTAMA sebelum apply konvensi apapun.**

### Step 1 — Deteksi Project Type
```bash
find app -name "*.php" 2>/dev/null | wc -l
```
Jika output `0` → **GREENFIELD**. Skip gate, apply konvensi penuh langsung.
Jika output > 0 → **EXISTING PROJECT**. Lanjut ke Step 2.

### Step 2 — Migration Risk Assessment
```bash
# Cek versi Laravel
cat composer.json 2>/dev/null | grep '"laravel/framework"' | head -1
# Cek struktur existing
ls app/Http/Controllers/ 2>/dev/null | wc -l
# Cek test suite
ls tests/ 2>/dev/null && echo "HAS_TESTS" || echo "NO_TESTS"
# Jumlah file terdampak
find app -name "*.php" 2>/dev/null | wc -l
# Cek apakah sudah pakai Service-Repository atau masih fat controller
grep -r "Repository" app/ 2>/dev/null | wc -l
```

### Step 3 — Hitung Risk Score
```
+40  Versi Laravel < 9 (konvensi modern tidak backward-compatible)
+30  Tidak ada test suite
+20  > 30 file yang harus diubah
+20  Fat controllers existing (refactor ke Service-Repository = besar)
+10  Tidak ada type hints di existing code
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
         "[YYYY-MM-DD] Laravel convention migration skipped — risk [N]% ([alasan])"
         Tampilkan: "ℹ️ Convention migration skipped (risk [N]%). Pakai konvensi existing."
```

---

## Prinsip Utama
- Ikuti PSR-12 coding standard
- Gunakan Service-Repository pattern untuk business logic
- Controller hanya boleh menerima request dan return response
- Semua business logic masuk ke Service layer
- Semua query database masuk ke Repository layer

---

## Struktur Layer

```
Request → Controller → Service → Repository → Model → Database
                ↓
            Resource (API response)
```

### Yang Boleh Ada di Setiap Layer

**Controller** — hanya boleh:
- Validate request (atau delegate ke FormRequest)
- Panggil Service
- Return response / Resource

**Service** — boleh:
- Business logic
- Panggil Repository
- Panggil Service lain
- Throw custom Exception

**Repository** — hanya boleh:
- Query database via Eloquent
- Tidak boleh ada business logic

**Model** — hanya boleh:
- Define relationships
- Define casts, fillable, hidden
- Scope queries sederhana
- Mutators / Accessors

---

## Naming Convention

### File & Class
```
Controller  : UserController.php          PascalCase + Controller
Model       : User.php                    PascalCase, singular
Service     : UserService.php             PascalCase + Service
Repository  : UserRepository.php          PascalCase + Repository
Interface   : UserRepositoryInterface.php PascalCase + Interface
FormRequest : StoreUserRequest.php        PascalCase, deskriptif
Resource    : UserResource.php            PascalCase + Resource
Migration   : 2024_01_01_create_users_table.php
Seeder      : UserSeeder.php
Factory     : UserFactory.php
```

### Method
```php
// Controller methods — ikuti REST convention
index()     // GET    /users
show()      // GET    /users/{id}
store()     // POST   /users
update()    // PUT    /users/{id}
destroy()   // DELETE /users/{id}

// Service methods — gunakan kata kerja deskriptif
createUser()
updateUserProfile()
deactivateUser()
sendWelcomeEmail()

// Repository methods — deskriptif query-nya
findById()
findByEmail()
getAllActive()
getPaginated()
```

### Variable & Parameter
```php
// camelCase untuk variable
$userId
$orderItems
$isActive

// snake_case untuk array keys (sesuai DB)
$data['first_name']
$data['created_at']
```

---

## Controller

```php
<?php

namespace App\Http\Controllers\Api\V1;

use App\Http\Controllers\Controller;
use App\Http\Requests\StoreUserRequest;
use App\Http\Requests\UpdateUserRequest;
use App\Http\Resources\UserResource;
use App\Services\UserService;
use Illuminate\Http\JsonResponse;

class UserController extends Controller
{
    public function __construct(
        private readonly UserService $userService
    ) {}

    public function index(): JsonResponse
    {
        $users = $this->userService->getAllPaginated();

        return UserResource::collection($users)
            ->response()
            ->setStatusCode(200);
    }

    public function store(StoreUserRequest $request): JsonResponse
    {
        $user = $this->userService->createUser($request->validated());

        return (new UserResource($user))
            ->response()
            ->setStatusCode(201);
    }

    public function show(int $id): JsonResponse
    {
        $user = $this->userService->findById($id);

        return (new UserResource($user))
            ->response()
            ->setStatusCode(200);
    }

    public function update(UpdateUserRequest $request, int $id): JsonResponse
    {
        $user = $this->userService->updateUser($id, $request->validated());

        return (new UserResource($user))
            ->response()
            ->setStatusCode(200);
    }

    public function destroy(int $id): JsonResponse
    {
        $this->userService->deleteUser($id);

        return response()->json(['message' => 'Deleted successfully'], 200);
    }
}
```

---

## Model

```php
<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Factories\HasFactory;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\SoftDeletes;
use Illuminate\Database\Eloquent\Relations\HasMany;

class User extends Model
{
    use HasFactory, SoftDeletes;

    // Selalu definisikan fillable (bukan guarded)
    protected $fillable = [
        'name',
        'email',
        'password',
        'is_active',
    ];

    // Sembunyikan field sensitif
    protected $hidden = [
        'password',
        'remember_token',
    ];

    // Cast tipe data
    protected $casts = [
        'is_active'         => 'boolean',
        'email_verified_at' => 'datetime',
        'password'          => 'hashed',
    ];

    // Relationships
    public function orders(): HasMany
    {
        return $this->hasMany(Order::class);
    }

    // Scope — untuk query yang sering dipakai
    public function scopeActive($query)
    {
        return $query->where('is_active', true);
    }
}
```

---

## Service

```php
<?php

namespace App\Services;

use App\Models\User;
use App\Repositories\UserRepository;
use App\Exceptions\UserNotFoundException;
use Illuminate\Pagination\LengthAwarePaginator;

class UserService
{
    public function __construct(
        private readonly UserRepository $userRepository
    ) {}

    public function getAllPaginated(int $perPage = 15): LengthAwarePaginator
    {
        return $this->userRepository->getPaginated($perPage);
    }

    public function findById(int $id): User
    {
        $user = $this->userRepository->findById($id);

        if (!$user) {
            throw new UserNotFoundException("User with ID {$id} not found");
        }

        return $user;
    }

    public function createUser(array $data): User
    {
        return $this->userRepository->create($data);
    }

    public function updateUser(int $id, array $data): User
    {
        $user = $this->findById($id);

        return $this->userRepository->update($user, $data);
    }

    public function deleteUser(int $id): void
    {
        $user = $this->findById($id);
        $this->userRepository->delete($user);
    }
}
```

---

## Repository

```php
<?php

namespace App\Repositories;

use App\Models\User;
use Illuminate\Pagination\LengthAwarePaginator;

class UserRepository
{
    public function getPaginated(int $perPage = 15): LengthAwarePaginator
    {
        return User::active()
            ->latest()
            ->paginate($perPage);
    }

    public function findById(int $id): ?User
    {
        return User::find($id);
    }

    public function findByEmail(string $email): ?User
    {
        return User::where('email', $email)->first();
    }

    public function create(array $data): User
    {
        return User::create($data);
    }

    public function update(User $user, array $data): User
    {
        $user->update($data);
        return $user->fresh();
    }

    public function delete(User $user): void
    {
        $user->delete();
    }
}
```

---

## API Resource

```php
<?php

namespace App\Http\Resources;

use Illuminate\Http\Resources\Json\JsonResource;

class UserResource extends JsonResource
{
    public function toArray($request): array
    {
        return [
            'id'         => $this->id,
            'name'       => $this->name,
            'email'      => $this->email,
            'is_active'  => $this->is_active,
            'created_at' => $this->created_at?->toISOString(),

            // Conditional relationship — hanya load jika di-load
            'orders'     => OrderResource::collection(
                                $this->whenLoaded('orders')
                            ),
        ];
    }
}
```

---

## FormRequest

```php
<?php

namespace App\Http\Requests;

use Illuminate\Foundation\Http\FormRequest;

class StoreUserRequest extends FormRequest
{
    public function authorize(): bool
    {
        return true; // atau cek permission spesifik
    }

    public function rules(): array
    {
        return [
            'name'     => ['required', 'string', 'max:255'],
            'email'    => ['required', 'email', 'unique:users,email'],
            'password' => ['required', 'string', 'min:8', 'confirmed'],
        ];
    }

    public function messages(): array
    {
        return [
            'email.unique' => 'Email sudah terdaftar.',
        ];
    }
}
```

---

## Migration

```php
<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        Schema::create('users', function (Blueprint $table) {
            $table->id();
            $table->string('name');
            $table->string('email')->unique();
            $table->string('password');
            $table->boolean('is_active')->default(true);
            $table->timestamp('email_verified_at')->nullable();
            $table->rememberToken();
            $table->timestamps();
            $table->softDeletes();

            // Index
            $table->index('is_active');
        });
    }

    public function down(): void
    {
        Schema::dropIfExists('users');
    }
};
```

---

## Routes (API)

```php
// routes/api.php

use App\Http\Controllers\Api\V1\UserController;

Route::prefix('v1')->group(function () {

    // Public routes
    Route::post('auth/login', [AuthController::class, 'login']);
    Route::post('auth/register', [AuthController::class, 'register']);

    // Protected routes
    Route::middleware('auth:sanctum')->group(function () {
        Route::apiResource('users', UserController::class);
        // Menghasilkan: index, store, show, update, destroy
    });
});
```

---

## Error Handling

```php
// app/Exceptions/Handler.php atau custom exception
// Selalu gunakan custom exception untuk error yang spesifik

// app/Exceptions/UserNotFoundException.php
class UserNotFoundException extends \RuntimeException
{
    public function __construct(string $message = "User not found")
    {
        parent::__construct($message, 404);
    }
}
```

---

## Standar Response API

```php
// Selalu konsisten:
// Success dengan data    → 200, data di key 'data'
// Created                → 201
// No content / deleted   → 200 dengan message
// Validation error       → 422 (otomatis dari FormRequest)
// Not found              → 404
// Unauthorized           → 401
// Forbidden              → 403
// Server error           → 500
```

---

## Checklist Sebelum Commit

- [ ] Controller tidak mengandung business logic
- [ ] Semua query ada di Repository
- [ ] Semua business logic ada di Service
- [ ] Semua input divalidasi via FormRequest
- [ ] Response menggunakan API Resource
- [ ] Tidak ada `dd()`, `var_dump()`, atau `print_r()` tertinggal
- [ ] Tidak ada hardcoded string yang harusnya di config/env
- [ ] Migration bisa rollback (`down()` method benar)
- [ ] Relationship sudah didefinisikan di Model
- [ ] Jalankan: `docker compose exec php php artisan test`
