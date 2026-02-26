# Task Breakdown Format

## Purpose
This skill defines the standard format for task breakdown documents in GetContactAIAgent project.

## File Location
`docs/task-breakdown.md`

## Format Template

```markdown
# Task Breakdown: [Feature Name]

**Date:** [YYYY-MM-DD]
**Brief:** [brief file or description]

## Summary
- **Total Tasks:** [N]
- **Backend:** [N] tasks
- **Frontend:** [N] tasks
- **Database:** [N] tasks
- **Integration:** [N] tasks
- **Estimated Time:** [X] hours

## Backend Tasks

### TASK-BE-001: [Task Title]
**File:** `orchestrator/[path]/[file].py`
**Description:**
- [Detail step 1]
- [Detail step 2]
- [Detail step 3]

**Acceptance Criteria:**
- [ ] [Specific, measurable criteria 1]
- [ ] [Specific, measurable criteria 2]
- [ ] [Specific, measurable criteria 3]

**Dependencies:** None or TASK-BE-XXX

**Estimated:** 15-30 min

**Notes:**
[Additional context, considerations, edge cases]

---

### TASK-BE-002: [Task Title]
[Same format as above]

---

## Frontend Tasks

### TASK-FE-001: [Task Title]
**File:** `frontend/src/[path]/[Component].tsx`
**Description:**
- [Detail step 1]
- [Detail step 2]

**Acceptance Criteria:**
- [ ] [Criteria 1]
- [ ] [Criteria 2]

**Dependencies:** None or TASK-FE-XXX

**Estimated:** 20 min

**Props Interface:**
```typescript
interface ComponentProps {
  // prop definitions
}
```

**State:**
- [State variable]: description
- [State variable]: description

---

### TASK-FE-002: [Task Title]
[Same format as above]

---

## Database Tasks (if applicable)

### TASK-DB-001: [Migration Title]
**File:** `orchestrator/migrations/[file].py`
**Description:**
- Create/modify table: [table name]
- Add columns: [list columns]
- Add indexes: [list indexes]

**SQL:**
```sql
CREATE TABLE table_name (
    id TEXT PRIMARY KEY,
    field1 TYPE NOT NULL,
    field2 TYPE NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_table_field ON table_name(field);
```

**Acceptance Criteria:**
- [ ] Migration runs successfully
- [ ] Schema verified
- [ ] No data loss (if modifying existing)

**Dependencies:** None

**Estimated:** 10 min

---

## Integration Tasks

### TASK-INT-001: [Integration Test Title]
**Description:**
- Test flow: [describe end-to-end flow]
- Verify: [what to verify]
- Expected result: [expected outcome]

**Test Steps:**
1. [Step 1]
2. [Step 2]
3. [Step 3]

**Acceptance Criteria:**
- [ ] All steps pass
- [ ] No errors in logs
- [ ] UI displays correctly

**Dependencies:** TASK-BE-XXX, TASK-FE-XXX

**Estimated:** 20 min

---

## Task Dependency Graph

```
TASK-DB-001 (Migration)
    ↓
TASK-BE-001 (Model)
    ↓
TASK-BE-002 (Service) ──→ TASK-BE-003 (Controller)
                              ↓
                         TASK-FE-001 (Service Layer)
                              ↓
                         TASK-FE-002 (Component)
                              ↓
                         TASK-FE-003 (Page)
                              ↓
                         TASK-INT-001 (Integration Test)
```

## Execution Order

### Phase 1: Backend Foundation
1. TASK-DB-001
2. TASK-BE-001
3. TASK-BE-002

### Phase 2: API Layer
4. TASK-BE-003
5. TASK-BE-004

### Phase 3: Frontend Foundation
6. TASK-FE-001 (can run parallel with Phase 2)
7. TASK-FE-002

### Phase 4: Frontend UI
8. TASK-FE-003
9. TASK-FE-004

### Phase 5: Integration & Testing
10. TASK-INT-001

## Notes

### Risks
- [Risk 1]: [Mitigation]
- [Risk 2]: [Mitigation]

### Considerations
- [Consideration 1]
- [Consideration 2]
```

## Task Sizing Guidelines

### Ideal Size
- **15-45 minutes** per task
- If > 60 min: break down further
- If < 10 min: merge with related task

### Granularity Rules
- **Backend:**
  - One task = one endpoint OR one service function OR one migration
  - Database models separate from services
  - Services separate from controllers

- **Frontend:**
  - One task = one component OR one page OR one hook
  - Service layer separate from components
  - Types/interfaces separate from implementation

## Dependency Guidelines

### Marking Dependencies
```markdown
**Dependencies:** TASK-BE-001, TASK-FE-002
```

### Valid Dependencies
- DB migration → Model
- Model → Service
- Service → Controller/Endpoint
- Endpoint → Frontend service layer
- Frontend service → Component

### Invalid Dependencies (indicates need to restructure)
- Frontend task depending on specific backend task (should be API-based)
- Two tasks of same type depending on each other (should be merged)

## Updating Existing Task Breakdown

When adding new features to existing project:

1. **Read existing** `docs/task-breakdown.md`
2. **Continue numbering** from last task
   - If last BE task is TASK-BE-042, next is TASK-BE-043
3. **Append new section** for new feature
4. **Add to dependency graph** if affects existing tasks
5. **DO NOT** remove or modify completed tasks

```markdown
# Task Breakdown: GetContactAIAgent

[... existing tasks ...]

---

## Feature: University Management (Feb 2026)

### TASK-BE-043: Add university CRUD endpoints
[...]
```
