# Git Operations Skill

## Branch Strategy

### Branch Naming
```
feat/[brief-number]-[short-feature-name]
fix/brief-[brief-number]-[issue-description]
hotfix/[urgent-issue]
```

Examples:
- `feat/003-university-management`
- `fix/brief-003-api-error`
- `hotfix/login-crash`

### Base Branches
- `main` - Production, protected
- `develop` - Development, integration branch

### Workflow
```bash
# Start new feature
git checkout develop
git pull origin develop
git checkout -b feat/003-university-management

# Work and commit
git add .
git commit -m "feat(be): add university CRUD endpoints"

# Push and create MR
git push -u origin feat/003-university-management
# Then create MR in GitLab/GitHub
```

## Commit Conventions

### Format
```
<type>(<scope>): <description>
```

### Types
- `feat` - New feature
- `fix` - Bug fix
- `refactor` - Code refactoring
- `docs` - Documentation
- `test` - Adding tests
- `chore` - Maintenance tasks

### Scopes
- `be` - Backend (Python/FastAPI)
- `fe` - Frontend (React)
- `db` - Database changes
- `ui` - UI components
- `api` - API endpoints

### Examples
```bash
feat(be): add university CRUD endpoints
feat(fe): add university management page
fix(db): correct index syntax in migration
refactor(ui): extract Button component
test(be): add unit tests for conversation state machine
docs: update setup instructions
chore: upgrade dependencies
```

### Commit Body (optional for complex changes)
```bash
feat(be): add phone extraction agent

- Add ig_phone_extractor.py with GPT-4o vision OCR
- Integrate with pipeline agent system
- Add error handling for API failures

Closes #42
```

## Merge Requests

### MR Title Format
```
[FEAT] University Management System
[FIX] API Error on University Create
[REFACTOR] Extract Reusable UI Components
```

### MR Description Template
```markdown
## Summary
[Brief description of changes]

## Changes
- [Change 1]
- [Change 2]
- [Change 3]

## Technical Details
- **Backend:** [summary of BE changes]
- **Frontend:** [summary of FE changes]
- **Database:** [migration details]

## Testing
- [ ] Unit tests pass
- [ ] Integration tests pass
- [ ] Manual testing completed

## Checklist
- [ ] Code follows conventions
- [ ] Self-review completed
- [ ] Documentation updated
- [ ] No merge conflicts

## Related Issues
Closes #[issue_number]
```

## GitLab API Operations

### Create MR via API
```python
import requests
import os

GITLAB_TOKEN = os.getenv("GITLAB_TOKEN")
GITLAB_URL = "https://gitlab.com/api/v4"

def create_merge_request(project_id: str, source_branch: str, title: str):
    """Create GitLab merge request."""
    headers = {"PRIVATE-TOKEN": GITLAB_TOKEN}
    data = {
        "source_branch": source_branch,
        "target_branch": "develop",
        "title": title,
        "remove_source_branch": True,
    }
    response = requests.post(
        f"{GITLAB_URL}/projects/{project_id}/merge_requests",
        headers=headers,
        json=data
    )
    return response.json()
```

### Protect Branches via API
```python
def protect_branch(project_id: str, branch: str):
    """Protect a branch from direct pushes."""
    headers = {"PRIVATE-TOKEN": GITLAB_TOKEN}
    data = {
        "name": branch,
        "push_access_level": 40,  # Maintainer
        "merge_access_level": 40,  # Maintainer
    }
    response = requests.put(
        f"{GITLAB_URL}/projects/{project_id}/protected_branches",
        headers=headers,
        json=data
    )
    return response.json()

# Protect main and develop
protect_branch(PROJECT_ID, "main")
protect_branch(PROJECT_ID, "develop")
```

## Common Commands

### Check Status
```bash
git status                    # Check working tree status
git log --oneline -10         # Recent commits
git branch -a                 # All branches
```

### Undo Operations
```bash
# Unstage file
git restore --staged <file>

# Discard local changes
git restore <file>

# Undo last commit (keep changes)
git reset --soft HEAD~1

# Undo last commit (discard changes)
git reset --hard HEAD~1
```

### Merge/Rebase
```bash
# Update branch with latest develop
git checkout feat/003-feature
git fetch origin
git rebase origin/develop

# Or merge instead
git merge origin/develop
```

### Stash
```bash
# Stash changes
git stash

# Apply stash
git stash pop

# List stashes
git stash list
```

## Git Flow Summary

```
main (production)
  ↑ merge
develop
  ↑ merge
feat/003-feature
  ↑ commits
  feat(be): add endpoints
  feat(fe): add page
  fix(be): fix bug
```
