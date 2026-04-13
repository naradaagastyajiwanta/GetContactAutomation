# Universities Feature - Deep Dive Analysis

## 1. Purpose & Role in System

The **Universities feature** is the core data hub for managing Indonesian university records and their discovery pipeline. It serves as a central repository for:

- **University profiles** (name, province, website, IG handle, contact info, rector data)
- **Contact discovery** (phone numbers extracted from Instagram)
- **Campaign targeting** (email blast, WhatsApp outreach, marketing groups)
- **Pipeline orchestration** (PDDIKTI scraping, IG discovery, agent-driven research)
- **Progress tracking** (status states: pending, ig_handle_found, contacts_found, contacted, converted)

It's the **single source of truth** for all university-related data across the platform.

---

## 2. Frontend Architecture

### 2.1 Main Page Structure
**File:** [frontend/src/pages/UniversitiesPage.tsx](frontend/src/pages/UniversitiesPage.tsx)

The page is a **dashboard with intelligent state management**:

```
┌─────────────────────────────────────────────────────────────┐
│ Header: "Universities" + Action Buttons                      │
│  ├─ [+ Add University]                (if .manage)          │
│  ├─ [Bulk Select]                     (if .manage/.run)    │
│  ├─ [Bulk Update Status]              (if .manage)         │
│  ├─ [Add to Blast] ({n})              (if .manage + selected)
│  ├─ [Export All Contacts]             (all users)          │
│  └─ [Import CSV/Excel]                (if .manage)         │
├─────────────────────────────────────────────────────────────┤
│ Filters: [Search] [Status ▼] [Province ▼] [Has IG ▼] [etc]  │
├─────────────────────────────────────────────────────────────┤
│ Active Filters Bar (dismissible pills) -- only when active   │
├─────────────────────────────────────────────────────────────┤
│ [Running Agents Banner] -- shows active pipeline agents      │
├─────────────────────────────────────────────────────────────┤
│ University Table with Pagination                             │
│ Columns: [checkbox] Name Province Status IG Contacts Count  │
├─────────────────────────────────────────────────────────────┤
│ Pagination: "Page 1 of 3 (showing 1-25 of 75)"              │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 State Management (URL-Synchronized)

The page implements **URL-synced filters** via `useSearchParams()`:

```typescript
// URL: /universities?search=ITB&province=DKI&status=contacts_found&page=2
const initialSearch = searchParams.get("search") || "";
const initialStatus = searchParams.get("status") || "";
const initialProvince = searchParams.get("province") || "";
const initialHasIg = searchParams.get("has_ig") || "";  // "yes"|"no"
const initialEnabled = searchParams.get("enabled") || ""; // "yes"|"no"
const initialSort = searchParams.get("sort") || "";      // "name_asc"|"name_desc"|...
const initialGroupId = searchParams.get("group_id") || "";
const initialPage = Math.max(1, parseInt(searchParams.get("page") || "1"));
```

**Key behaviors:**
- **Persistent filters:** Users can share URLs with pre-applied filters
- **Pagination reset:** Changing any filter resets to page 1
- **URL sync on every change:** `updateUrlParams()` updates the URL bar instantly
- **Auto-refresh:** Every 30 seconds, or on window focus (configurable)
- **Selection state:** `selected: Set<number>` tracks checkbox selections across pages
- **Last updated time:** Tracks the most recent successful refetch

### 2.3 Hook: `useUniversities()`

**File:** [frontend/src/hooks/useUniversities.ts](frontend/src/hooks/useUniversities.ts)

This custom hook encapsulates all query logic:

```typescript
export function useUniversities(params: Record<string, unknown> = {}, autoRefresh = true) {
  return useQuery<PaginatedUniversities>({
    queryKey: queryKeys.universities.list(params),
    queryFn: () => getUniversities(params),
    placeholderData: (prev) => prev,     // Keep prev data while loading next page
    refetchInterval: autoRefresh ? 30000 : false,  // 30-second auto-refresh
  })
}
```

**Features:**
- **Placeholder data:** Smooth pagination (shows old data while new loads)
- **Auto-refetch on focus:** Window focus event triggers refetch
- **Configurable interval:** Can be toggled on/off from the running agents banner

### 2.4 Components (Sub-components)

All components are in [frontend/src/components/universities/](frontend/src/components/universities/):

| Component | Purpose | Key Props |
|-----------|---------|-----------|
| **UniversityTable** | Renders table rows with inline action buttons | `data`, `selected`, `onSelect`, `onToggleEnabled`, `onDelete` |
| **UniversityFilters** | Filter UI: search box, dropdowns | `search`, `status`, `province`, etc., + onChange handlers |
| **UniversityDetail** | Modal: expands single university with contacts/posts tabs | `universityId`, `onClose` |
| **ContactsPanel** | Tab showing IG contacts (phone numbers) discovered from IG | `universityId`, with add/remove actions |
| **PostsPanel** | Tab showing IG posts scraped for this university | `universityId` |
| **RelatedIGsPanel** | Tab showing related/linked IG accounts for enrichment | `universityId` |
| **AddUniversityModal** | Form to manually add a single university | `onAdd`, `onClose` |
| **ImportModal** | Drag-drop or file picker for CSV/Excel import | `onImport`, `onClose` |
| **BulkSelectModal** | Quick select: All, Top N by status, etc. | `selected`, `onApply`, `onClose` |
| **BulkUpdateContactsModal** | Bulk update status (pending→contacted→converted) | `selected`, `onUpdate`, `onClose` |
| **AddToBlastModal** | Add selected universities to email/WA campaign | `selected`, `onAdd`, `onClose` |
| **RunningAgentsBanner** | Shows real-time agent progress (Agent 1, 2, 3) | `autoRefreshEnabled`, `onToggleAutoRefresh` |

### 2.5 Modals Workflow

```
User clicks [Add University]
  ↓
AddUniversityModal opens
  ├─ User enters: Name, Province, Website (optional)
  ├─ Front-end validation
  └─ POST /universities → Backend adds & returns new record
     ↓
     useUniversities query invalidates (React Query)
     ↓
     Table refetches with new entry appended
     
User selects rows + clicks [Export All Contacts]
  ↓
exportUniversitiesExcel({ ids: [1,2,3] }) called
  ├─ Backend: SELECT * from contacts WHERE university_id IN (...)
  └─ Returns: XLSX file download (3 columns: University Name, Contact Name, Phone)

User clicks [Bulk Select] → [Top 10 by "contacts_found"]
  ↓
BulkSelectModal applies selection logic
  ↓
Local state.selected = Set<number>
  ↓
User clicks [Add to Blast ({n})]
  ├─ AddToBlastModal opens
  ├─ User selects: Campaign dropdown
  └─ POST /blast/campaigns/{id}/add-universities → Backend adds recipients
```

---

## 3. Backend Architecture & Endpoints

### 3.1 Database Schema

**File:** [orchestrator/db.py](orchestrator/db.py#L18)

```sql
CREATE TABLE universities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    
    -- Identity
    name TEXT NOT NULL,                 -- "Universitas Indonesia"
    pddikti_id TEXT UNIQUE,             -- Government ID from PDDIKTI
    
    -- Location
    province TEXT,                      -- "DKI Jakarta"
    
    -- Web/Contact
    website TEXT,                       -- "ui.ac.id"
    email_kampus TEXT,                  -- Main university email
    email_source TEXT,                  -- Where email came from
    
    -- Instagram
    ig_handle TEXT,                     -- "@universitasindonesia"
    ig_verified BOOLEAN DEFAULT 0,      -- Verified on Instagram?
    
    -- Secretariat
    secretariat_phone TEXT,             -- Extracted contact number
    rector_name TEXT,                   -- Current rector name
    student_count INTEGER,              -- For sizing/targeting
    
    -- Status Tracking
    status TEXT DEFAULT 'pending',      -- pending|ig_handle_found|contacts_found|contacted|converted
    enabled BOOLEAN DEFAULT 1,          -- Include in pipeline?
    
    -- System
    dms_univ_id INTEGER,                -- DMS sync ID
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE ig_contacts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    university_id INTEGER REFERENCES universities(id),
    phone_number TEXT NOT NULL,         -- "+6281234567890"
    contact_name TEXT,                  -- Name extracted from IG post/bio
    source_post_url TEXT,               -- Which IG post it came from
    source_image_url TEXT,              -- Image URL on S3/GCS
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(university_id, phone_number) -- No duplicates
);

CREATE TABLE ig_posts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    university_id INTEGER NOT NULL REFERENCES universities(id),
    post_url TEXT NOT NULL,             -- Instagram post URL
    image_url TEXT,                     -- Image cached to bucket
    caption TEXT,                       -- Post caption
    post_timestamp TEXT,                -- When posted
    phone_extracted BOOLEAN DEFAULT 0,  -- Processed by Agent 3?
    phones_found INTEGER DEFAULT 0,     -- How many phones in this post
    source_ig_handle TEXT,              -- @handle that posted
    source_ig_type TEXT,                -- official|fan|related
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### 3.2 API Endpoints (Complete List)

**File:** [orchestrator/main.py](orchestrator/main.py#L1263)

#### List & Filter
```
GET /universities
  Query params:
    - search: string (fuzzy match on name)
    - status: string (pending|ig_handle_found|contacts_found|...)
    - province: string exact match
    - has_ig: boolean (filter: has ig_handle or not)
    - enabled: boolean (filter: enabled=1 or enabled=0)
    - limit: int (default 25, max 1000)
    - offset: int (for pagination)
    - sort_by: string (name|province|status|created_at)
    - order: string (asc|desc)
    - group_id: int (filter by university group)
  
  Returns:
    {
      "data": [ {...university...}, ... ],
      "total": 457
    }
```

#### Export to Excel
```
GET /universities/export-excel
  Query params:
    - ids: string (comma-separated IDs, OR use filters below)
    - search, status, province, has_ig, enabled (same as /universities)
  
  Returns:
    File: contacts_export_YYYYMMDD_HHMMSS.xlsx
    Columns: [University Name | Contact Name | Phone Number]
    Format: Green header, auto-filter, frozen panes
```

#### Single Record
```
GET /universities/{university_id}
  Returns: Single university object with all fields

DELETE /universities/{university_id}/ig-handle
  Clears the ig_handle for a university (re-triggers discovery)
  Returns: {"id": X, "ig_handle": null}
```

#### Create & Import
```
POST /universities
  Body: {
    "name": "Universitas Baru",
    "province": "Jawa Barat",
    "website": "unbaru.ac.id", [optional]
    "universities": [ // for bulk create
      {"name": "U1", "province": "P1", "website": "..."},
      ...
    ]
  }
  Returns: {"id": X, "name": "...", ...}

POST /universities/import
  Form Data:
    - file: (multipart) CSV or XLSX with columns: [Name | Province | Website]
  
  Returns: {
    "imported": 50,
    "skipped": [{"row": 2, "name": "ITB", "reason": "duplicate"}],
    "errors": []
  }
```

#### Enable/Disable
```
PATCH /universities/{university_id}/toggle-enabled
  Query params: enabled=true|false
  Returns: {"id": X, "enabled": true|false}

PATCH /universities/bulk-toggle
  Body: {
    "ids": [1, 2, 3],
    "enabled": true
  }
  Returns: {"updated": 3, "enabled": true}
```

#### Contact Data (IG Extracted)
```
GET /universities/{university_id}/contacts
  Returns: [
    {
      "id": 1,
      "phone_number": "+6281234567890",
      "contact_name": "Bagian Admisi",
      "source_post_url": "https://instagram.com/p/ABC123/"
    },
    ...
  ]

GET /universities/{university_id}/posts
  Returns: [
    {
      "id": 1,
      "post_url": "...",
      "image_url": "...",
      "caption": "...",
      "phones_found": 2,
      "created_at": "2026-01-01T10:00:00Z"
    },
    ...
  ]

GET /universities/{university_id}/related-igs
  Returns: [
    {
      "handle": "@ui_inika",
      "type": "fan",
      "follower_count": 50000,
      "relevance_score": 0.95
    },
    ...
  ]
```

#### Groups & Matching
```
GET /university-groups
  Returns: [{"id": 1, "name": "Group A", "university_count": 50}, ...]

POST /university-groups
  Body: {"name": "Group Name", "description": "..."}
  Returns: {"id": X, "name": "..."}

GET /university-groups/{group_id}
  Returns: Single group with member list

DELETE /university-groups/{group_id}

POST /universities/match-names
  Body: {"names": ["ITB", "Universitas Indonesia", ...]}
  Returns: {
    "matches": [
      {"id": 1, "name": "Universitas Indonesia", "matched_query": "Universitas Indonesia"},
      ...
    ]
  }
```

#### Utilities
```
GET /universities/provinces
  Returns: ["DKI Jakarta", "Jawa Barat", ...] (all distinct provinces)

GET /universities/with-emails
  Returns: Universities that have email_kampus (for email blast)
  Query params: province, search, limit, offset
  Returns: {
    "data": [{"id": X, "name": "...", "email": "...", "website": "..."}],
    "total": 150
  }
```

#### PDDIKTI Collection (Pipeline)
```
POST /pipeline/collect-universities
  Query params:
    - province: string (e.g., "Jawa Barat")
    - limit: int (how many to fetch)
  
  Returns: {"status": "started", "message": "Collecting..."}
  
  Background Task:
    1. Scrape PDDIKTI API
    2. Dedup against existing
    3. Add new universities
    4. Broadcast via WebSocket: agent_completed event
```

---

## 4. Permission-Based Access Control

**File:** [orchestrator/main.py](orchestrator/main.py#L553)

Each endpoint requires permissions:

| Endpoint | Permission | Description |
|----------|-----------|-------------|
| `GET /universities` | `universities.view` | View list & filters |
| `POST /universities` | `universities.manage` | Add manual record |
| `POST /universities/import` | `universities.manage` | Bulk import |
| `PATCH /universities/.../toggle-enabled` | `universities.manage` | Enable/disable |
| `PATCH /universities/bulk-toggle` | `universities.manage` | Bulk enable/disable |
| `DELETE /universities/{id}/ig-handle` | `universities.manage` | Clear IG handle |
| `POST /pipeline/collect-universities` | `pipeline.run` | Trigger PDDIKTI scrape |
| `GET /universities/with-emails` | `blast.manage` | For email blast targeting |

**Role hierarchy:**
- **admin** → all permissions
- **operator** → universities.view, universities.manage, pipeline.run, blast.manage
- **viewer** → universities.view, blast.view (read-only)

---

## 5. Key Workflows and Data Flows

### 5.1 Discovery Pipeline (3-Agent Architecture)

The feature integrates tightly with the **Agent-driven discovery pipeline**:

```
┌─────────────────────────────────────────────────────────────────┐
│                    PDDIKTI Scrape (Manual)                      │
│                 POST /pipeline/collect-universities              │
│                     (PDDIKTI API search)                        │
│                                                                  │
│                    universities.status = pending                 │
│                          ig_handle = NULL                        │
└──────────────────────────┬──────────────────────────────────────┘
                           ↓
┌──────────────────────────────────────────────────────────────────┐
│                 AGENT 1: IG Handle Finder                         │
│  Task: Find Instagram handle from university website/Google      │
│  File: orchestrator/agents/ig_handle_finder.py                  │
│                                                                   │
│  Input: universities WHERE ig_handle IS NULL                    │
│  Output: universities.ig_handle = "@universitasindonesia"       │
│  Status: pending → ig_handle_found                               │
└──────────────────────────┬──────────────────────────────────────┘
                           ↓ (can run on schedule or manual)
┌──────────────────────────────────────────────────────────────────┐
│             AGENT 2: IG Post Scraper (Baileys)                   │
│  Task: Scrape recent posts from discovered IG handle            │
│  File: orchestrator/agents/ig_post_scraper.py                   │
│                                                                   │
│  Input: universities.ig_handle                                   │
│  Output: ig_posts table filled with post URLs & images          │
│  Images: Cached to S3/GCS via bucket.py                         │
└──────────────────────────┬──────────────────────────────────────┘
                           ↓
┌──────────────────────────────────────────────────────────────────┐
│          AGENT 3: Phone Extractor (GPT-4o Vision)                │
│  Task: OCR posts to extract phone numbers from images           │
│  File: orchestrator/agents/ig_phone_extractor.py                │
│                                                                   │
│  Input: ig_posts WHERE phone_extracted = 0                      │
│  Process: For each image, GPT-4o vision → extract numbers       │
│  Output: ig_contacts table (university_id, phone_number)        │
│  Status: ig_handle_found → contacts_found                        │
│                                                                   │
│  Phone Dedup: phonenumbers lib validates & normalizes           │
│  WhatsApp Validation: If enabled, checks if phone active on WA  │
└──────────────────────────┬──────────────────────────────────────┘
                           ↓
┌──────────────────────────────────────────────────────────────────┐
│             WhatsApp Outreach (Chatbot 1)                        │
│  Task: Send automated messages to extracted contacts            │
│  File: orchestrator/conversation.py                             │
│                                                                   │
│  Input: ig_contacts WHERE contacted = 0                         │
│  Process:                                                         │
│  1. Send initial: "Hi, we're X. Do you have admin contact?"     │
│  2. Wait for reply (state machine)                               │
│  3. Extract: contact_name, phone of actual secretariat          │
│  4. Save to: ig_contacts (updated) or new contact               │
│  5. Repeat for other contacts                                    │
│                                                                   │
│  States: PENDING → INITIAL_SENT → WAITING_REPLY → REPLIED →    │
│           ANALYZING → GOT_NUMBER → CONVERTED → etc              │
│  Status: contacts_found → contacted → converted                  │
└─────────────────────────────────────────────────────────────────┘
```

### 5.2 User-Initiated Workflows

#### Scenario A: Bulk Import from Government Database
```
User: "We received a list of 200 universities from the Ministry"
↓
1. User clicks [Import CSV/Excel]
2. Drags file or selects: universities.csv
3. Frontend validates: Columns must be [Name, Province, Website (opt)]
4. POST /universities/import with FormData
5. Backend:
   - Parses CSV/XLSX
   - Deduplicates against existing (name + province)
   - Inserts new rows + returns imported count
   - Broadcasts: agent_completed event
6. Frontend refreshes table → new universities appear with status=pending
7. Admin clicks [Bulk Select] → manually starts Agent 1 on these 200
```

#### Scenario B: Manual Targeting for Email Blast
```
1. Admin filters: Province=Jawa Barat, Status=contacts_found
2. Selects top 50 by clicking checkboxes
3. Clicks [Add to Blast]
4. Modal: Choose email campaign dropdown
5. POST /blast/campaigns/{id}/add-universities
   Body: { ids: [1,2,3,...], email_campaign_id: 5 }
6. Backend:
   - Loads universities.email_kampus from selected
   - Adds rows to blast campaign recipients table
   - Returns: {added: 50}
7. Blast admin can now preview & send

Alternative:
- User clicks [Export All Contacts] → Downloads XLSX
- Opens in Excel, manually cleans/enriches phone numbers
- Re-imports with status update: contacted→converted
```

#### Scenario C: OSINT Profile Enrichment (CRM Integration)
```
1. Admin navigates to CRM (separate feature)
2. Selects a university: "Universitas Indonesia"
3. CRM backend triggers osint_researcher agents:
   - Research current rector name, phone
   - Find student council president
   - Profile their social media, interests
4. Results saved to CRM.profile_connections table
5. CRM UI displays: "Rector: Prof. X, Phone: 081xxx, LinkedIn: ..."
6. User can then manually add to audiensi queue (separate feature)
```

---

## 6. Feature Highlights & Advanced Capabilities

### 6.1 Smart Filtering & Sorting

The UI supports **complex multi-filter queries**:

```typescript
// Example: Find all contacts in Jawa Barat that have IG but no email yet
GET /universities?province=Jawa%20Barat&has_ig=true&email_kampus=null&sort_by=name&order=asc

// Result: 23 universities matching all criteria, sorted A→Z
```

**Supported filters:**
- **Search:** Fuzzy name search (contains)
- **Status:** Multi-value: pending|ig_handle_found|contacts_found|contacted|converted
- **Province:** Exact match from dropdown (only provinces that exist)
- **Has IG:** Yes/No (has ig_handle vs. null)
- **Enabled:** Yes/No (enabled=1 vs. enabled=0)
- **Group:** By university group ID
- **Sort:** By any column + direction (asc/desc)

### 6.2 Real-Time Auto-Refresh

The table **auto-refreshes every 30 seconds** when agents are running:

```
User starts Agent 1 on 200 universities
↓
Backend broadcasts via WebSocket: agent_started event
↓
Frontend: RunningAgentsBanner appears, shows: "Agent 1: Processing 3/200"
↓
Every 30 seconds: useUniversities() refetches with same filters
↓
Table updates: Status changes from "pending" → "ig_handle_found"
↓
User can watch progress in real-time without refreshing page
↓
When Agent 1 completes: agent_completed broadcast
  → Toast: "Agent 1 done! 200/200 found IG handles"
  → RunningAgentsBanner hides
  → Auto-refresh stops (manual toggle available)
```

### 6.3 Bulk Operations

**BulkSelectModal** provides smart selection:

```typescript
// Options:
- [ ] All universities
- [ ] Top 10 by: status=contacts_found
- [ ] Top 5 by: created_at (newest)
- [ ] All where has_ig=true
- [ ] All where enabled=false
- [ ] Custom: Select rows manually via checkboxes + Shift-click range
```

Once selected, can:
1. **Export** as XLSX (3 columns: Name, Contact, Phone)
2. **Add to Blast** (WhatsApp or Email campaigns)
3. **Bulk Update Status** (Pending → Contacted → Converted)
4. **Bulk Toggle Enabled** (Exclude or include from pipeline)

### 6.4 Manual Enrichment

**UniversityDetail** modal allows inline editing:

```
Click on a row → UniversityDetail modal opens with 3 tabs:

TAB 1: Basic Info (Editable)
  - Name, Province, Website, Email
  - IG Handle (with a [Verify] button)
  - Rector Name, Student Count
  - Status dropdown
  - Buttons: [Delete IG Handle] [Save]

TAB 2: Contacts
  - List of extracted phone numbers from IG
  - Each row: Phone | Contact Name | Source Post URL
  - Buttons: [+ Add Manual Contact] [Delete] per row

TAB 3: IG Posts
  - List of scraped posts
  - Each row: Post URL | Image Preview | Caption | Phones Found
  - Indicates: { phone_extracted: true/false }

TAB 4: Related IGs
  - Linked accounts (@ui_inika, official accounts, etc)
  - Type: official|fan|related
  - Follower count + relevance score
```

### 6.5 University Groups

Admins can organize universities into **logical groups** for team assignment:

```
POST /university-groups
  Body: { "name": "Region: Jawa Timur", "description": "All East Java unis" }
  Returns: {"id": 3, "name": "...", "university_count": 0}

// Add universities to group (implicit via checkbox when creating)
// or via separate endpoint (not shown in default UI, but available)

// Filter by group in main list
/universities?group_id=3
  Returns: All universities in this group
```

---

## 7. Data Types & Models

### 7.1 University Object (from API)

```typescript
interface University {
  id: number
  name: string                    // "Universitas Indonesia"
  province: string | null         // "DKI Jakarta"
  website: string | null          // "ui.ac.id"
  ig_handle: string | null        // "@universitasindonesia"
  ig_verified: boolean            // true if verified on IG
  
  // Contact info
  secretariat_phone: string | null   // "+62213456789"
  email_kampus: string | null        // "admisi@ui.ac.id"
  email_source: string | null        // "Google Search" or "Manual"
  rector_name: string | null
  student_count: number | null
  
  // Status tracking
  status: 'pending' | 'ig_handle_found' | 'contacts_found' | 'contacted' | 'converted'
  enabled: boolean                // Include in pipeline?
  
  // System
  pddikti_id: string | null       // Government PDDIKTI ID
  dms_univ_id: number | null      // DMS sync ID
  created_at: string              // ISO timestamp
  updated_at: string              // ISO timestamp
  
  // Counts (optional, from views)
  contact_count?: number          // How many phone numbers extracted
  post_count?: number             // How many IG posts scraped
}

interface IgContact {
  id: number
  university_id: number
  phone_number: string            // "+6281234567890"
  contact_name: string | null     // "Bagian Admisi"
  source_post_url: string | null  // "https://instagram.com/p/ABC123/"
  source_image_url: string | null // "https://bucket.com/..."
  created_at: string
}

interface IgPost {
  id: number
  university_id: number
  post_url: string
  image_url: string | null
  caption: string | null
  post_timestamp: string | null
  phone_extracted: boolean        // Has Agent 3 processed it?
  phones_found: number            // Count extracted
  source_ig_handle: string        // @handle that posted
  source_ig_type: 'official' | 'fan' | 'related'
  created_at: string
}

interface RelatedIg {
  handle: string
  type: 'official' | 'fan' | 'related'
  follower_count: number
  relevance_score: number         // 0.0-1.0
}
```

---

## 8. Integration Points with Other Features

The Universities feature integrates with:

| Feature | Integration | Coupling |
|---------|-----------|----------|
| **Pipeline (Agents)** | Agents 1-3 operate on univ table | Tight: status field, ig_posts/contacts tables |
| **Email Blast** | Can target by univ email address | Moderate: looks up email_kampus field |
| **WhatsApp Outreach** | Targets extracted ig_contacts | Tight: uses phone_number from ig_contacts |
| **CRM/OSINT** | Enriches rect/contact data | Moderate: reads univ data, writes to separate tables |
| **Marketing Module** | Groups for segment targeting | Loose: reads university name, ID |
| **Audiensi (Zoom)** | Schedule meetings with universities | Moderate: reads rector_name, phone |
| **Learning System** | Analyzes conversation outcomes | Loose: uses conversation outcomes |
| **DMS Sync** | Two-way sync with external MySQL | Moderate: dms_univ_id field, contact sync |

---

## 9. Performance Characteristics

### 9.1 Query Performance

**Table universities:**
```
Typical size: 500-2000 records (Indonesian universities + manual additions)
Indexes:
  - idx_universities_status (status = 'pending')
  - Contact count: FAST (via ig_contacts GROUP BY university_id)
```

**Typical query: GET /universities with filters**
```
SELECT u.*, COUNT(ic.id) AS contact_count
FROM universities u
LEFT JOIN ig_contacts ic ON u.id = ic.university_id
WHERE u.province = 'Jawa Barat' AND u.status = 'contacts_found'
GROUP BY u.id
LIMIT 25 OFFSET 0;

Execution: ~50-100ms (depends on database size and filters)
```

**Export to XLSX with 1000 rows:**
```
1. SELECT from universities + contacts
2. In-memory workbook creation (openpyxl)
3. Stream to client
Total time: ~500-1000ms
```

### 9.2 Pagination Strategy

- **Page size:** 25 universities per page (configurable: `ITEMS_PER_PAGE`)
- **Method:** Offset-based pagination (not cursor-based)
- **Frontend:** Placeholder data keeps view smooth when fetching next page
- **Max page:** Bounded by total (auto-calculated)

### 9.3 Image Storage (ig_posts)

- **Location:** S3/GCS/R2 (configured via `bucket.py`)
- **Size per image:** ~500KB (IG post screenshots)
- **Lifecycle:** Keep indefinitely (or configurable via bucket policy)
- **Usage:** Loaded on-demand when user opens ContactsPanel tab

---

## 10. Error Handling & Edge Cases

### 10.1 Common Issues

| Issue | Cause | Fix |
|-------|-------|-----|
| Agent 1 can't find IG handle | Website doesn't list IG, or typo in domain | Manually edit ig_handle field |
| Agent 2 finds only 1-2 posts | IG account is private or brand new | Mark ig_verified=false, try different method |
| Agent 3 extracts wrong phones | Image quality poor, phone format ambiguous | Manual review & correction via ContactsPanel |
| Import fails with "Duplicate key" | Name+Province already exists | Check existing records or use different province |
| Export hangs with 5000+ records | XLSX generation is single-threaded | Reduce export size via filters |

### 10.2 Validation Rules

**University creation:**
- `name`: Required, max 255 chars, must be unique (within province)
- `province`: Optional, must be valid Indonesian province
- `website`: Optional, must be valid URL format
- `ig_handle`: Letter+number+underscore only, max 30 chars (Instagram limit)

**Contact import (CSV):**
- Column "Name" required
- Column "Province" required (validates against known provinces)
- Column "Website" optional
- Max file size: 25MB
- Max rows: 5000 (backend limit)

---

## 11. Configuration & Customization

Key environment variables affecting universities feature:

```bash
# Database
DATABASE_PATH=data/getcontact.db              # SQLite location

# IG Scraping
IG_SESSION_ID=...                             # Instagram session
SCRAPINGBOT_API_KEY=...                       # Alternative scraper

# Storage
STORAGE_BACKEND=gcs                           # gcs|s3|r2
GCS_BUCKET_NAME=getcontact-ai-bucket          # Bucket for images

# Pipeline
CHATBOT_ENABLED=true                          # Enable WhatsApp outreach
AUDIENSI_ENABLED=true                         # Enable audiensi feature
LEARNING_ENABLED=true                         # Enable outcome analysis
AGENT_MODEL=gpt-4o-mini                       # LLM model for agents

# Concurrency
AI_SEMAPHORE_SIZE=3                           # Max concurrent AI calls
MESSAGE_QUEUE_BATCH_SIZE=10                   # WA messages per minute
```

---

## 12. Testing & Development

### 12.1 Manual Testing Checklist

- [ ] Add a new university manually via [+ Add University]
- [ ] Import 10 universities via CSV
- [ ] Filter by province, verify pagination works
- [ ] Select 5 universities, export as XLSX
- [ ] Click on a university to open detail modal
- [ ] Add a manual contact to the ContactsPanel
- [ ] Bulk select "All", then [Bulk Update Status]
- [ ] Run Agent 1 on a subset, watch real-time refresh
- [ ] Toggle a university disabled, verify it's excluded from pipelines

### 12.2 Test Data

```sql
-- Seed test universities
INSERT INTO universities (name, province, website, status, enabled)
VALUES
  ('Test University 1', 'DKI Jakarta', 'test1.ac.id', 'pending', 1),
  ('Test University 2', 'Jawa Barat', 'test2.ac.id', 'ig_handle_found', 1),
  ('Test University 3', 'Jawa Timur', 'test3.ac.id', 'contacts_found', 1);

-- Add test contacts
INSERT INTO ig_contacts (university_id, phone_number, contact_name)
VALUES (3, '+6281234567890', 'Admin Admisi');
```

---

## 13. Future Enhancements

Possible additions to strengthen the feature:

1. **Batch Verification:** Verify IG handles + email addresses in bulk
2. **AI-Based Cleansing:** Auto-detect and merge duplicate universities
3. **Rate Limiting per University:** Track messaging rate, avoid spam warnings
4. **Contact Freshness:** Highlight stale contacts (e.g., >3 months old)
5. **Webhook Integrations:** Sync university data from external CRM systems
6. **Analytics Dashboard:** Show conversion funnel (pending → contacted → converted %)
7. **Contact Enrichment API:** Call external API (hunter.io, clearbit, etc.) to find emails
8. **Batch WhatsApp Testing:** Send test message to sample of contacts before full blast

---

## Conclusion

The **Universities feature** is the foundational data layer that powers all outreach, research, and campaign orchestration. It's designed to support:
- **High throughput** (500-5000+ universities)
- **Flexible pipelines** (manual, semi-auto, fully automated)
- **Rich enrichment** (IG, contacts, OSINT, rector research)
- **Targeted campaigns** (filter + select + export + outreach)
- **Permission-driven access** (role-based viewing/editing)

The deep integration with agents, CRM, email/WhatsApp services, and the DMS makes it a **critical system** for the GetContact AI platform's core mission: automated university discovery and outreach at scale.
