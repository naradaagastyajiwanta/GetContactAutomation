---
name: git-operations
description: >
  Operasi Git standar: clone, branch, commit, push,
  dan merge request. Gunakan untuk semua interaksi
  dengan repository GitLab.
allowed-tools: Bash
---

## Variabel Wajib
Semua operasi GitLab membutuhkan variabel berikut dari `.env`:
```bash
GITLAB_TOKEN=glpat-xxxxxxxxxxxx
GITLAB_GROUP=nama-group
GITLAB_REPO_URL=https://gitlab.com/group-name/nama-project.git
```
Jika tidak ada → STOP dan laporkan ke lead.

---

## Helper: Dapatkan Project ID
Project ID dibutuhkan untuk semua GitLab API calls.
Jalankan ini sekali di awal setiap sesi:
```bash
# Load .env
export $(grep -v '^#' .env | xargs)

# Ambil project path dari remote URL
PROJECT_PATH=$(git remote get-url origin \
  | sed 's/https:\/\/oauth2:.*@gitlab.com\///' \
  | sed 's/https:\/\/gitlab.com\///' \
  | sed 's/\.git$//')

# Encode untuk URL
PROJECT_PATH_ENCODED=$(python3 -c \
  "import urllib.parse, sys; print(urllib.parse.quote(sys.stdin.read().strip(), safe=''))" \
  <<< "$PROJECT_PATH")

# Dapatkan Project ID
PROJECT_ID=$(curl --silent \
  --header "PRIVATE-TOKEN: ${GITLAB_TOKEN}" \
  "https://gitlab.com/api/v4/projects/${PROJECT_PATH_ENCODED}" \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")

echo "Project ID: $PROJECT_ID"
```

---

## Operasi Standar

### Clone repository
```bash
export $(grep -v '^#' .env | xargs)
git clone "https://oauth2:${GITLAB_TOKEN}@gitlab.com/${GITLAB_GROUP}/nama-project.git"
cd nama-project
```

### Buat branch baru
```bash
# Feature branch selalu dibuat dari develop
git checkout develop
git pull origin develop
git checkout -b feat/brief-001-nama-fitur

# Fix branch
git checkout -b fix/brief-001-nama-fix
```

### Commit (conventional commits)
```bash
git add <files>
git commit -m "feat(scope): deskripsi singkat"
# Tipe: feat, fix, chore, refactor, test, docs
# Scope contoh: auth, dashboard, api, ui
```

### Cek status sebelum commit
```bash
git status
git diff --staged
```

### Push branch

> ⚠️ PENTING: Token GitLab modern (format `glpat-xxx.01.xxx`) mengandung karakter
> `.` dan `-` yang harus di-URL-encode sebelum dipakai di git HTTPS.
> Jangan pernah set token langsung ke remote URL tanpa encode — akan gagal auth.

```bash
GITLAB_TOKEN=$(grep '^GITLAB_TOKEN=' .env | cut -d= -f2)
ENCODED_TOKEN=$(python3 -c "import urllib.parse; print(urllib.parse.quote('${GITLAB_TOKEN}', safe=''))")
BRANCH=$(git branch --show-current)
REPO_PATH=$(git remote get-url origin | sed 's/https:\/\/.*@gitlab.com\///' | sed 's/https:\/\/gitlab.com\///')
git push "https://oauth2:${ENCODED_TOKEN}@gitlab.com/${REPO_PATH}" "${BRANCH}:${BRANCH}"
```

### Buat Merge Request via GitLab API
```bash
export $(grep -v '^#' .env | xargs)
BRANCH=$(git branch --show-current)
FEATURE_NAME=$(echo $BRANCH | sed 's/feat\///')

curl --request POST \
  --header "PRIVATE-TOKEN: ${GITLAB_TOKEN}" \
  --header "Content-Type: application/json" \
  --data "{
    \"source_branch\": \"${BRANCH}\",
    \"target_branch\": \"develop\",
    \"title\": \"[FEAT] ${FEATURE_NAME}\",
    \"description\": \"$(cat docs/mr-description.md 2>/dev/null || echo 'See commits for details')\",
    \"assignee_id\": null,
    \"remove_source_branch\": true
  }" \
  "https://gitlab.com/api/v4/projects/${PROJECT_ID}/merge_requests"
```

---

## GitLab Setup (Greenfield Only)

### Konfigurasi Credentials
```bash
export $(grep -v '^#' .env | xargs)

# Format remote URL dengan token
REMOTE_URL="https://oauth2:${GITLAB_TOKEN}@gitlab.com/${GITLAB_GROUP}/$(basename $(pwd)).git"
```

### Push Initial Commit
```bash
git init
git add .
git commit -m "chore: initial project structure"
git remote add origin $REMOTE_URL
git push -u origin main
```

### Buat Branch develop
```bash
git checkout -b develop
git push -u origin develop
git checkout main
```

### Set Branch Protection via GitLab API
Jalankan setelah push — butuh PROJECT_ID dari helper di atas.

```bash
export $(grep -v '^#' .env | xargs)

# -- Dapatkan PROJECT_ID dulu --
PROJECT_PATH=$(git remote get-url origin \
  | sed 's/https:\/\/oauth2:.*@gitlab.com\///' \
  | sed 's/\.git$//')
PROJECT_PATH_ENCODED=$(python3 -c \
  "import urllib.parse,sys; print(urllib.parse.quote(sys.stdin.read().strip(),safe=''))" \
  <<< "$PROJECT_PATH")
PROJECT_ID=$(curl --silent \
  --header "PRIVATE-TOKEN: ${GITLAB_TOKEN}" \
  "https://gitlab.com/api/v4/projects/${PROJECT_PATH_ENCODED}" \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")

# -- Protect main: hanya Maintainer yang bisa merge, tidak ada yang bisa push --
curl --request POST \
  --header "PRIVATE-TOKEN: ${GITLAB_TOKEN}" \
  --header "Content-Type: application/json" \
  --data '{
    "name": "main",
    "push_access_level": 0,
    "merge_access_level": 40,
    "allow_force_push": false
  }' \
  "https://gitlab.com/api/v4/projects/${PROJECT_ID}/protected_branches"

# -- Protect develop: Developer bisa push dan merge --
curl --request POST \
  --header "PRIVATE-TOKEN: ${GITLAB_TOKEN}" \
  --header "Content-Type: application/json" \
  --data '{
    "name": "develop",
    "push_access_level": 30,
    "merge_access_level": 30,
    "allow_force_push": false
  }' \
  "https://gitlab.com/api/v4/projects/${PROJECT_ID}/protected_branches"

echo "✅ Branch protection selesai"
```

### Verifikasi Branch Protection
```bash
curl --silent \
  --header "PRIVATE-TOKEN: ${GITLAB_TOKEN}" \
  "https://gitlab.com/api/v4/projects/${PROJECT_ID}/protected_branches" \
  | python3 -c "
import sys, json
branches = json.load(sys.stdin)
for b in branches:
    print(f\"Branch: {b['name']}\")
    print(f\"  Push  : {b['push_access_levels']}\")
    print(f\"  Merge : {b['merge_access_levels']}\")
"
```

---

## Access Level Reference
```
0  = No access        → tidak bisa sama sekali
30 = Developer        → developer biasa
40 = Maintainer       → tech lead / senior
60 = Admin            → owner
```

## Branch Strategy
```
main     → production, hanya Maintainer yang bisa merge
develop  → staging, Developer bisa push & merge
feat/*   → dibuat dari develop, merge back ke develop
fix/*    → hotfix, dibuat dari develop
```