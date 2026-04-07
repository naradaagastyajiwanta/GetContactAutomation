# Code Review Report: Marketing Get Contact Automation

**Date:** 2026-04-02
**Branch:** feature/getcontactcorporate
**Reviewer:** code-reviewer
**User-Sim Report:** docs/user-simulation-report.md (merged)

## Summary
- **Total Issues:** 11
- **Critical:** 3
- **Major:** 5
- **Minor:** 3
- **Confirmed by User-Sim:** 6 flows PASS, 2 PARTIAL

---

## Backend Issues

### [CRITICAL] BE-1 -- client_type enum mismatch (confirmed by user-sim)
**File:** orchestrator/marketing/serializers.py:8
**Type:** BUG / DATA MISMATCH

Backend ClientType enum uses snake_case (lembaga_negara, kementerian, bumn) but Frontend sends readable strings (Lembaga Negara, BUMN). Pydantic rejects with 422.

User-sim confirmed: POST with client_type: "BUMN" returns 422.
Valid values: lembaga_negara, kementerian, bumn, swasta_besar, asosiasi, lpk, lkp

Fix (FE): Add label-to-value mapping in MarketingCreateGroupModal:
  CLIENT_TYPE_MAP = { "BUMN": "bumn", "Lembaga Negara": "lembaga_negara", ... }
OR (BE): Change GroupCreate.client_type to str, bypass enum validation.

---

### [CRITICAL] BE-2 -- No auth on marketing API endpoints
**File:** orchestrator/marketing/__init__.py (entire router)
**Type:** SECURITY

All marketing endpoints have NO authentication checks.
Fix (BE): Add require_permission dependency to all routes.

---

### [CRITICAL] BE-3 -- Route conflict: DELETE /clients/{client_id} after POST /groups/{group_id}/clients
**File:** orchestrator/marketing/__init__.py:71, 89
Fix (BE): Move DELETE route before POST route.

---

### [MAJOR] BE-4 -- is_selected DEFAULT 1 -- user selection semantics broken
**File:** orchestrator/db.py:830
**Type:** LOGIC BUG

DB column: is_selected INTEGER DEFAULT 1. All new contacts auto-selected.
upsert_contact_result (groups.py:227) never sets is_selected on insert.

User-sim confirmed: PATCH {is_selected: false} DOES persist correctly.
Toggle mechanism works -- just default is wrong.

Fix (BE): DEFAULT 0 and add is_selected=0 in upsert_contact_result.

---

### [MAJOR] BE-5 -- search_status returns flat dict, FE expects stats wrapper
**File:** orchestrator/marketing/__init__.py:231

Backend returns {success: True, total, pending, ...} (flat). FE expects data.stats.total.
Fix (BE): return {"success": True, "stats": status} OR (FE): use data?.total directly.

---

### [MAJOR] BE-6 -- get_group_search_status missing approved count
**File:** orchestrator/marketing/groups.py:301

GroupStats.approved always undefined. Stats card shows nothing.
Fix (BE): Add subquery counting is_approved=1 across all group clients.

---

### [MAJOR] BE-7 -- Scraping runs but returns no error visibility
**File:** orchestrator/marketing/search.py
**Type:** UX / DEBUGGABILITY (from user-sim)

User-sim ran scraping on 4 clients: all returned not_found with no error.
Likely cause: missing SERPER_API_KEY, IG credentials, or network restrictions.
No error details surfaced -- just silent not_found.

Fix (BE): Catch exceptions in _search_single_client and store error per-client.
Include error_message in search_status response.

---

### [MINOR] BE-8 -- Unused imports io, json in __init__.py
**File:** orchestrator/marketing/__init__.py:4,5
Fix (BE): Remove unused imports.

---

### [MINOR] BE-9 -- approve_all_in_group uses db.changes() after commit
**File:** orchestrator/marketing/groups.py:294
Fix (BE): Store rowcount before commit.

---

## Frontend Issues

### [CRITICAL] FE-1 -- ContactType mismatch BE vs FE enum values
**File:** frontend/src/api/marketing.ts:16
**Type:** DATA MISMATCH

Frontend: ContactType = "WA" | "Email" | "Telp Kantor" | ...
Backend:  ContactType = "wa_phone" | "email" | "office_phone" | ...

Consequences:
1. CONTACT_ICONS always falls back to Circle for WA contacts
2. MarketingReadyToBlastPanel filter: c.contact_type === "WA" is always FALSE
3. Ready to Blast panel shows 0 WA contacts even when approved contacts exist

Fix (FE): Update ContactType to match backend:
  export type ContactType = "wa_phone" | "email" | "office_phone" | "pic_name" | "pic_title"
Update CONTACT_ICONS keys and labels accordingly.

---

### [CRITICAL] FE-2 -- contact.source undefined (field name mismatch)
**File:** frontend/src/components/marketing/MarketingClientResultsTable.tsx:106
**Type:** RUNTIME ERROR

Template reads contact.source but backend ContactResultOut has source_url.
All rows show dash.
Fix (FE): contact.source_url ?? contact.source_type ?? "-"

---

### [MAJOR] FE-3 -- useSearchStatus data.stats undefined
**File:** frontend/src/pages/MarketingClientDetailPage.tsx:180

Backend returns flat object. FE expects data.stats.total.
Fix (FE): use data?.total, data?.found directly, or wait for BE-5 fix.

---

### [MAJOR] FE-4 -- useBulkApproveGroupContacts missing groupDetail invalidation
**File:** frontend/src/hooks/useMarketing.ts:121

Approved count in stats card does not update after bulk approve.
Fix (FE): Add qc.invalidateQueries({ queryKey: mkKeys.groupDetail(groupId) })

---

### [MAJOR] FE-5 -- useDeleteMarketingClient missing groups list invalidation
**File:** frontend/src/hooks/useMarketing.ts:91

Groups list does not update after deletion.
Fix (FE): Add qc.invalidateQueries({ queryKey: ["marketing", "groups"] })

---

### [MINOR] FE-6 -- Dead code in NotFoundClientForm (unused state)
**File:** frontend/src/components/marketing/MarketingClientResultsTable.tsx:184, 189
Fix (FE): Remove unused state or implement manual contact add.

---

### [MINOR] FE-7 -- ImportPreview.duplicates not in preview response
**File:** frontend/src/api/marketing.ts:63

preview.duplicates always undefined -- duplicate warning never shows.
Fix (BE): Add to preview, or (FE) remove from interface.

---

## User-Sim Confirmed Working Flows

- Add Client Manually: PASS
- Upload Excel Import (preview + commit): PASS
- Review Contacts (approve, uncheck, bulk approve): PASS
- Edit Contact (uses edited_value): PASS
- Export Excel (valid xlsx): PASS
- WA Blast Handoff: PASS
- Email Blast Handoff: PASS
- Delete Group (cascade): PASS
- Handoff endpoint /groups/{id}/handoff with handoff_type body param: PASS

---

## Files LGTM
- orchestrator/marketing/constants.py
- orchestrator/marketing/importer.py
- orchestrator/marketing/search.py
- orchestrator/marketing/groups.py
- orchestrator/marketing/handoff.py
- frontend/src/components/marketing/MarketingHandoffModal.tsx
- frontend/src/App.tsx

---

## Priority Table

| P | ID | Description | Owner | Note |
|---|----|-------------|-------|------|
| P0 | BE-1 | client_type enum mismatch -- group creation broken | FE/BE | User-sim confirmed 422 |
| P0 | BE-2 | No auth on marketing endpoints | BE | Security gap |
| P0 | FE-1 | ContactType mismatch -- WA blast filter broken | FE | Critical UX gap |
| P0 | FE-2 | contact.source undefined | FE | Runtime error |
| P1 | BE-4 | is_selected default 1 | BE | Toggle works, default wrong |
| P1 | BE-5 | search_status flat dict mismatch | BE/FE | BE fix or FE fix |
| P1 | BE-6 | approved count missing from stats | BE | Stats card incomplete |
| P1 | BE-7 | scraping silent failures | BE | User-sim confirmed |
| P1 | FE-3 | searchStatus data.stats undefined | FE | See BE-5 |
| P1 | FE-4 | bulk approve no stats refresh | FE | Stale data |
| P1 | FE-5 | delete client no groups list refresh | FE | Stale data |
| P2 | BE-8 | Unused imports | BE | Cleanup |
| P2 | BE-9 | changes() after commit | BE | Cleanup |
| P2 | FE-6 | Dead code in NotFoundClientForm | FE | Cleanup |
| P2 | FE-7 | preview.duplicates not in response | BE/FE | Cleanup |
