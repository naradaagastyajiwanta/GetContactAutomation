# User Guide - GetContact AI Agent

**Version:** 1.0.0
**Last Updated:** 2025-02-25

---

## Table of Contents

1. [Dashboard Overview](#dashboard-overview)
2. [Managing Universities](#managing-universities)
3. [Monitoring Pipeline](#monitoring-pipeline)
4. [WhatsApp Management](#whatsapp-management)
5. [Conversations](#conversations)
6. [Learning & Knowledge Base](#learning--knowledge-base)
7. [Settings & Configuration](#settings--configuration)
8. [Interpreting Conversation States](#interpreting-conversation-states)
9. [Best Practices](#best-practices)
10. [FAQ](#faq)

---

## Dashboard Overview

### Accessing the Dashboard

**URL:** http://localhost:5173 (development) or your domain (production)

**Login:** Currently no authentication required (future versions will add login)

### Main Dashboard

The dashboard provides an at-a-glance view of your system status and progress.

#### Key Components

**1. Stats Grid (Top Cards)**

```
┌─────────────────┬─────────────────┬─────────────────┐
│  Total          │  IG Scraped     │  Got Numbers    │
│  Universities   │                 │                 │
│  1,234          │  567            │  89             │
└─────────────────┴─────────────────┴─────────────────┘
```

- **Total Universities:** Count of all universities in database
- **IG Scraped:** Universities with Instagram data collected
- **Got Numbers:** Successful secretariat phone number collection
- **Today's Conversations:** Conversations started today
- **Today's Messages:** Messages sent today
- **Active Agents:** Number of pipeline agents currently running

**2. Pipeline Funnel**

Visual representation of universities through the pipeline stages:

```
pending → ig_found → ig_scraped → contacted → got_number
  456   →   389    →    234     →    123    →     89
```

**3. Today's Quota**

Shows daily usage vs. limits:

- **Conversations Started:** 15 / 50 (30%)
- **Messages Sent:** 45 / 150 (30%)
- **IG Profiles Scraped:** 80 / 300 (27%)

**4. System Status**

- **Orchestrator:** Running / Stopped
- **WhatsApp Service:** Connected / Disconnected
- **Current Time:** WIB timezone display
- **Outreach Hours:** Active / Inactive (based on schedule)

**5. Recent Activity**

Timeline of recent system events:
- Pipeline agent completions
- New conversations started
- Phone numbers collected
- Errors or warnings

---

## Managing Universities

### Universities Page

**Navigation:** Sidebar → Universities

The Universities page is your main interface for managing the target university database.

#### University Table

**Columns:**
- **Select:** Checkbox for bulk operations
- **Name:** University name (clickable for details)
- **Province:** Indonesian province
- **IG Handle:** Instagram handle (if found)
- **Status:** Pipeline status badge
- **Enabled:** Toggle switch for inclusion in pipeline

**Status Badges:**
- `gray` - Pending: Not yet processed
- `blue` - IG Found: Instagram handle discovered
- `purple` - IG Scraped: Posts scraped for phone numbers
- `yellow` - Contacted: Initial message sent
- `green` - Got Number: Successfully obtained secretariat phone
- `red` - Failed: Max follow-ups reached, no response

#### Filtering and Search

**Search Bar:**
- Search by university name
- Real-time filtering as you type

**Filters Panel:**
- **Status:** Filter by pipeline status
- **Province:** Filter by Indonesian province
- **Enabled:** Show enabled/disabled only

**Apply Filters:** Click "Apply" to activate filters
**Clear Filters:** Click "Reset" to clear all filters

#### Pagination

- **Per Page:** 10, 25, 50, 100 rows
- **Navigation:** Previous/Next buttons
- **Page Info:** "Showing 1-25 of 1,234"

#### Bulk Operations

**1. Selection:**
- Click checkboxes to select universities
- Use "Select All" for current page

**2. Bulk Actions Dropdown:**
- **Enable Selected:** Include in pipeline
- **Disable Selected:** Exclude from pipeline
- **Export Selected:** Download CSV/Excel

#### Adding Universities

**Option 1: Add Single University**

1. Click "Add University" button (top right)
2. Fill in form:
   - **Name** (required): University name
   - **Province** (optional): Select from dropdown
   - **Website** (optional): University website URL
   - **PDDIKTI ID** (optional): PDDIKTI database ID
3. Click "Add University"

**Option 2: Import from CSV**

1. Click "Import" button
2. Download template (optional)
3. Prepare CSV with columns: `name`, `province`, `website`, `pddikti_id`
4. Upload CSV file
5. Review import preview
6. Click "Import" to process

**Option 3: Import from PDDIKTI**

1. Navigate to Pipeline page
2. Find "PDDIKTI Import" section
3. Select province and limit
4. Click "Scrape Universities"
5. Monitor progress in activity log

#### University Detail Page

Click any university name to view details.

**Tabs:**

**1. Overview Tab**
- Basic information
- Current pipeline status
- Related statistics

**2. Contacts Tab**
- Phone numbers extracted from Instagram
- Contact names (if available)
- Source post links
- Source images

**3. Posts Tab**
- Instagram posts scraped
- Post captions
- Images
- Phone extraction status

**4. Related IGs Tab**
- BEM (Student Council) accounts
- Other related Instagram handles
- Discovery date

**Actions:**
- **Edit:** Update university details
- **Delete:** Remove university (soft delete)
- **Retry Agent:** Re-run pipeline agent for this university
- **View Conversations:** See all conversations with this university

---

## Monitoring Pipeline

### Pipeline Page

**Navigation:** Sidebar → Pipeline

The Pipeline page shows the automated data collection and outreach process.

#### Pipeline Overview

**Visual Funnel Chart:**

```
┌─────────────────────────────────────────┐
│         Pipeline Progress               │
├─────────────────────────────────────────┤
│ pending    ████████████ 456            │
│ ig_found   ██████████  389            │
│ ig_scraped ████████    234            │
│ contacted  █████       123            │
│ got_number ██          89             │
└─────────────────────────────────────────┘
```

#### Agent Trigger Cards

**Agent 1: Find IG Handles**
- **Purpose:** Discover Instagram accounts for universities
- **Trigger:** Automatic (every 2 hours) or Manual
- **Status:** Running / Idle / Last run: 2 hours ago
- **Action:** Click "Run Now" to trigger manually

**Agent 2: Scrape IG Posts**
- **Purpose:** Collect recent posts from found accounts
- **Trigger:** Automatic (every 3 hours) or Manual
- **Status:** Running / Idle / Last run: 3 hours ago
- **Action:** Click "Run Now" to trigger manually

**Agent 3: Extract Phones**
- **Purpose:** Use AI to find phone numbers in post images
- **Trigger:** Automatic (every hour) or Manual
- **Status:** Running / Idle / Last run: 1 hour ago
- **Action:** Click "Run Now" to trigger manually

**Agent 4: Discover BEM**
- **Purpose:** Find Student Council Instagram accounts
- **Trigger:** Automatic (every 4 hours) or Manual
- **Status:** Running / Idle / Last run: 4 hours ago
- **Action:** Click "Run Now" to trigger manually

**PDDIKTI Scraper**
- **Purpose:** Import universities from PDDIKTI database
- **Trigger:** Manual only
- **Configuration:**
  - Select province(s)
  - Set limit (number of universities)
- **Action:** Click "Scrape Universities" to run

#### Pipeline Activity Log

**Real-time log of pipeline activities:**

```
2025-02-25 14:30 [Agent 1] Found 12 IG handles (searched: 50)
2025-02-25 14:25 [Agent 3] Extracted 8 phone numbers (processed: 45)
2025-02-25 14:20 [Agent 2] Scraped 234 posts from 12 profiles
2025-02-25 14:15 [Outreach] Started 5 conversations
```

**Features:**
- Auto-refresh every 30 seconds
- Filter by agent type
- View details for each log entry
- Download full log as CSV

#### Pipeline Status

**Current State:**
- **Is Running:** Yes/No
- **Current Phase:** Agent name or "Idle"
- **Last Run:** Timestamp
- **Next Run:** Scheduled time

---

## WhatsApp Management

### WhatsApp Page

**Navigation:** Sidebar → WhatsApp

Manage WhatsApp connection and view connection status.

#### Connection Status

**Status Badge:**
- **Green (Connected):** Ready to send/receive messages
- **Red (Disconnected):** Not connected, needs pairing
- **Yellow (Connecting):** Attempting to connect

**Information Display:**
- **Phone Number:** Connected WhatsApp number
- **Reconnect Attempts:** Current attempt count
- **Connection Time:** How long connected

#### QR Code Pairing

**When Disconnected:**

1. QR code displays automatically
2. Open WhatsApp on your phone
3. Tap menu → Linked Devices
4. Tap "Link a Device"
5. Scan QR code with phone camera

**Tips:**
- QR code refreshes every 60 seconds
- Connection persists after restart
- Use dedicated account (not personal)

#### Connection Controls

**Buttons:**

**Restart Connection:**
- Use if connection is unstable
- Attempts graceful reconnect
- Preserves session

**Logout:**
- Clears all credentials
- Requires re-pairing
- Use when switching accounts

#### Test Message

**Send Test Message:**
1. Enter phone number (format: 628...)
2. Type test message
3. Click "Send Test"
4. Verify delivery

---

## Conversations

### Conversations Page

**Navigation:** Sidebar → Conversations

View and manage all WhatsApp conversations with university contacts.

#### Conversation List

**Columns:**
- **University:** University name (clickable)
- **Contact Phone:** Phone number
- **State:** Conversation state badge
- **Last Message:** Date/time of last activity
- **Messages Count:** Total message count

**Conversation States:**
- `PENDING` - Not yet started
- `INITIAL_SENT` - First message sent
- `WAITING_REPLY` - Awaiting response
- `REPLIED` - Received response
- `ANALYZING` - AI analyzing response
- `GOT_NUMBER` - Successfully extracted phone
- `NEED_MORE` - Needs follow-up
- `FOLLOWUP_SENT` - Follow-up sent
- `REFUSED` - Contact refused
- `NO_REPLY` - No response after follow-ups
- `ABANDONED` - Max follow-ups reached
- `UNDELIVERED` - Message delivery failed

#### Filtering

**Filter Options:**
- **State:** Select conversation state
- **University:** Search by university name
- **Date Range:** Filter by last message date

#### Conversation Detail

Click any conversation to view details.

**Chat Bubbles:**
- **Right (Blue):** Bot messages
- **Left (Gray):** Contact messages
- **Timestamps:** Each message shows time

**State Timeline:**

```
[INITIAL_SENT] 2025-02-25 09:00
       ↓
[WAITING_REPLY] 2025-02-25 09:00
       ↓
[REPLIED] 2025-02-25 10:30
       ↓
[ANALYZING] 2025-02-25 10:31
       ↓
[GOT_NUMBER] 2025-02-25 10:32
```

**Actions:**
- **Send Manual Message:** Send custom message
- **Mark as Complete:** Manually set state
- **View University:** Go to university detail

#### Manual Message Sending

**1. Click "Send Message" button**
**2. Type your message**
**3. Click "Send"**

**Note:** Manual messages bypass the AI but are logged in conversation history.

---

## Learning & Knowledge Base

### Learning Page

**Navigation:** Sidebar → Learning

View AI-learned lessons from conversations.

#### Lessons List

**Columns:**
- **Created:** Date lesson was learned
- **Source:** Conversation ID
- **Pattern:** Detected pattern
- **Lesson:** Learned lesson
- **Success Rate:** Confidence score

#### Lesson Details

Click a lesson to view:
- **Conversation Context:** Original conversation
- **Pattern Analysis:** What AI detected
- **Lesson Learned:** What AI concluded
- **Application:** How to apply

**Actions:**
- **Activate:** Enable lesson in future conversations
- **Deactivate:** Disable lesson
- **Delete:** Remove lesson

### Knowledge Base Page

**Navigation:** Sidebar → Knowledge Base

Manage curated knowledge items for AI context.

#### Knowledge Items

**List shows:**
- **Title:** Knowledge item title
- **Category:** Item category
- **Tags:** Associated tags
- **Active:** Enable/disable status
- **Updated:** Last update time

#### Adding Knowledge

**1. Click "Add Knowledge"**
**2. Fill form:**
   - **Title** (required)
   - **Content** (required): Knowledge text
   - **Category:** Select category
   - **Tags:** Add tags (comma-separated)
   - **Active:** Toggle to enable/disable
**3. Click "Save"**

#### Editing Knowledge

**1. Click knowledge item**
**2. Edit fields**
**3. Click "Update"**

**Actions:**
- **Edit:** Modify knowledge item
- **Delete:** Remove item
- **Toggle Active:** Enable/disable without deleting

---

## Settings & Configuration

### Settings Page

**Navigation:** Sidebar → Settings

Configure system behavior and limits.

#### Control Panel

**Pause/Resume Bot:**
- **Pause:** Stop all automated outreach
- **Resume:** Restart automated outreach

**Current Status:**
- Bot state (paused/running)
- Current time (WIB)
- Outreach hours status

#### Configuration Sections

**Rate Limiting:**

```
MAX_DAILY_CONVERSATIONS: 50
  └─ Maximum new conversations per day

MIN_MESSAGE_GAP_SECONDS: 300
  └─ Minimum seconds between messages

MAX_IG_PROFILES_PER_DAY: 300
  └─ Maximum Instagram profiles to scrape daily

IG_REQUEST_DELAY_SECONDS: 10
  └─ Delay between Instagram requests
```

**Outreach Hours:**

```
OUTREACH_START_HOUR: 8
  └─ Start hour (WIB timezone)

OUTREACH_END_HOUR: 21
  └─ End hour (WIB timezone)
```

**AI Settings:**

```
AGENT_MODEL: gpt-4o-mini
  └─ OpenAI model to use

AGENT_TEMPERATURE: 0.1
  └─ Creativity (0.0 - 1.0)

AGENT_MAX_TOKENS: 500
  └─ Maximum response length

MAX_AI_CONCURRENT: 5
  └─ Parallel AI requests

SEND_INTERVAL_MS: 3000
  └─ Delay between messages (ms)
```

**Feature Flags:**

```
CHATBOT_ENABLED: true
  └─ Enable contact finder chatbot

LEARNING_ENABLED: true
  └─ Enable AI learning system

AUDIENSI_ENABLED: false
  └─ Enable rector outreach pipeline

USE_AGENTIC_REPLIES: true
  └─ Use AI for conversation replies

USE_AGENTIC_INITIAL: true
  └─ Use AI for initial messages

USE_AGENTIC_FOLLOWUPS: true
  └─ Use AI for follow-up messages
```

#### Updating Configuration

**1. Find setting to change**
**2. Click edit button**
**3. Enter new value**
**4. Click "Save"**

**Note:** Changes take effect immediately (no restart required).

#### Export Section

**Export Options:**
- **Universities:** CSV export of all universities
- **Conversations:** Export conversation history
- **Results:** Export successfully collected phone numbers

**Filters:**
- Filter by status before export
- Filter by date range
- Select specific universities

**Export Formats:**
- CSV
- Excel (XLSX)
- JSON

---

## Interpreting Conversation States

### State Meanings

**Active States (In Progress):**

`PENDING`
- Conversation created but not started
- Awaiting initial message

`INITIAL_SENT`
- First outreach message sent
- Waiting for contact response

`WAITING_REPLY`
- No response received yet
- Within follow-up window

`REPLIED`
- Contact has responded
- Analysis in progress

`ANALYZING`
- AI analyzing response
- Determining next action

`NEED_MORE`
- Response unclear
- Follow-up sent
- Awaiting clarification

`FOLLOWUP_SENT`
- Follow-up message sent
- Waiting for response

**Terminal States (Completed):**

`GOT_NUMBER`
- Success! Phone number extracted
- University updated with secretariat phone
- Audiensi conversation auto-queued (if enabled)

`REFUSED`
- Contact declined to provide information
- Polite closing message sent
- No further action

`NO_REPLY`
- No response after max follow-ups
- Conversation abandoned
- University marked as "failed"

`ABANDONED`
- Max follow-up attempts reached
- No useful information obtained
- University marked as "failed"

`UNDELIVERED`
- Message delivery failed
- Phone number may be invalid
- University marked as "failed"

### State Transitions

```
PENDING
  ↓ (send initial)
INITIAL_SENT
  ↓ (receive reply)
WAITING_REPLY
  ↓ (reply received)
REPLIED
  ↓ (AI analysis)
ANALYZING
  ├─→ GOT_NUMBER (success)
  ├─→ REFUSED (declined)
  ├─→ NEED_MORE (unclear)
  └─→ NEED_MORE (follow-up needed)
       ↓ (send follow-up)
FOLLOWUP_SENT
  ↓ (no response after timeout)
  └─→ ABANDONED (max attempts)
```

### Timeline Example

**Successful Conversation:**

```
[Feb 25 09:00] INITIAL_SENT
  Bot: "Selamat pagi, Izin saya Ali..."

[Feb 25 10:15] REPLIED
  Contact: "Boleh, hubungi 08123456789"

[Feb 25 10:15] ANALYZING
  AI: "action: got_number, extracted_number: 08123456789"

[Feb 25 10:16] GOT_NUMBER
  Bot: "Terima kasih banyak atas informasinya!"
```

**Failed Conversation:**

```
[Feb 25 09:00] INITIAL_SENT
  Bot: "Selamat pagi, Izin saya Ali..."

[Feb 26 09:00] FOLLOWUP_SENT
  Bot: "Menindaklanjuti chat sebelumnya..."

[Feb 27 09:00] FOLLOWUP_SENT
  Bot: "Mohon info kontak yang dapat kami hubungi..."

[Feb 28 09:00] ABANDONED
  System: "Max follow-ups reached"
```

---

## Best Practices

### University Management

**1. Start Small:**
- Import 10-50 universities first
- Test pipeline flow
- Gradually increase volume

**2. Quality Over Quantity:**
- Focus on universities with active Instagram
- Verify IG handles are official
- Disable universities with no IG presence

**3. Province Targeting:**
- Start with one province
- Expand gradually
- Monitor success rates by province

### Pipeline Management

**1. Let Agents Run Automatically:**
- Agents run on schedule
- Manual triggers for testing only
- Monitor activity log

**2. Check Quota Daily:**
- Monitor daily quota usage
- Adjust limits if needed
- Best times: Morning (WIB)

**3. Handle Errors Promptly:**
- Check activity log for failures
- Restart stuck agents
- Review error messages

### Conversation Management

**1. Monitor Active Conversations:**
- Check conversations page daily
- Respond to urgent inquiries
- Review AI analysis

**2. Manual Intervention:**
- Use manual messaging for complex cases
- Override AI decisions when needed
- Provide feedback to improve AI

**3. Learn from Patterns:**
- Review learning page regularly
- Identify successful approaches
- Apply lessons to future conversations

### WhatsApp Connection

**1. Use Dedicated Account:**
- Separate business account
- Not your personal WhatsApp
- Reduces risk of main account ban

**2. Maintain Connection:**
- Keep service running
- Monitor connection status
- Restart if disconnected

**3. Respect Rate Limits:**
- Don't decrease gaps too much
- Human-like behavior is key
- Avoid spam detection

---

## FAQ

### General Questions

**Q: What does this system do?**
A: It automates WhatsApp outreach to Indonesian universities to collect secretariat contact information using AI.

**Q: How does the AI work?**
A: The system uses GPT-4o for vision OCR (to read phone numbers from images) and GPT-4o-mini for conversational AI (to understand responses and generate messages).

**Q: Is this legal?**
A: The system only contacts publicly available information from universities. Always comply with WhatsApp Terms of Service and local regulations.

### Technical Questions

**Q: Why use SQLite?**
A: SQLite is simple, reliable, and sufficient for single-instance deployments. Future versions may support PostgreSQL for scaling.

**Q: Can I use multiple WhatsApp numbers?**
A: Not currently, but this is planned for future versions to increase throughput.

**Q: What happens if WhatsApp disconnects?**
A: The system automatically attempts to reconnect with exponential backoff. Check the WhatsApp page for status.

**Q: How do I increase daily limits?**
A: Adjust `MAX_DAILY_CONVERSATIONS` in Settings. Be conservative to avoid WhatsApp spam detection.

### Troubleshooting

**Q: Universities stuck in "pending" status**
A: Trigger Agent 1 (Find IG Handles) manually from the Pipeline page.

**Q: No phone numbers being extracted**
A:
1. Check if posts are scraped (Agent 2)
2. Trigger Agent 3 (Extract Phones) manually
3. Verify OpenAI API key is valid

**Q: Messages not sending**
A:
1. Check WhatsApp connection status
2. Verify outreach hours (WIB timezone)
3. Check daily quota not exceeded
4. Review error logs

**Q: AI not responding appropriately**
A:
1. Check AGENT_MODEL setting
2. Verify OpenAI API key has credits
3. Review temperature setting (lower = more focused)

### Best Practices

**Q: How often should I check the dashboard?**
A: At least once daily for production use. Monitor quota, active conversations, and pipeline status.

**Q: Should I use manual or automatic mode?**
A: Use automatic mode for routine operation. Use manual triggers for testing or handling special cases.

**Q: How do I improve success rates?**
A:
1. Focus on universities with active Instagram
2. Review learning page regularly
3. Provide feedback via knowledge base
4. Monitor and adjust timing

---

## Summary

This user guide covers:

- **Dashboard navigation** and key metrics
- **University management** (add, import, filter)
- **Pipeline monitoring** and agent triggers
- **WhatsApp management** and connection
- **Conversation tracking** and state interpretation
- **Learning system** and knowledge base
- **Configuration** and settings
- **Best practices** for effective use

For technical details, see [developer-guide.md](developer-guide.md).
For deployment instructions, see [deployment.md](deployment.md).
For architecture details, see [architecture.md](architecture.md).

---

## Support

**Documentation:** See `/docs` folder
**API Reference:** `docs/api-reference.md`
**Issues:** Report via GitHub issues (if available)

**Key Contacts:**
- Technical issues: Check troubleshooting section
- Feature requests: Submit via issue tracker
- Questions: Review FAQ and documentation
