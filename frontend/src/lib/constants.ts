export const STATUS_COLORS: Record<string, { bg: string; text: string }> = {
  pending: { bg: 'bg-gray-100 dark:bg-gray-700', text: 'text-gray-700 dark:text-gray-300' },
  ig_found: { bg: 'bg-blue-100 dark:bg-blue-900/50', text: 'text-blue-700 dark:text-blue-300' },
  ig_scraped: { bg: 'bg-purple-100 dark:bg-purple-900/50', text: 'text-purple-700 dark:text-purple-300' },
  contacted: { bg: 'bg-yellow-100 dark:bg-yellow-900/50', text: 'text-yellow-700 dark:text-yellow-300' },
  got_number: { bg: 'bg-green-100 dark:bg-green-900/50', text: 'text-green-700 dark:text-green-300' },
  failed: { bg: 'bg-red-100 dark:bg-red-900/50', text: 'text-red-700 dark:text-red-300' },
}

export const CONVERSATION_STATE_COLORS: Record<string, { bg: string; text: string }> = {
  PENDING: { bg: 'bg-gray-100 dark:bg-gray-700', text: 'text-gray-700 dark:text-gray-300' },
  INITIAL_SENT: { bg: 'bg-blue-100 dark:bg-blue-900/50', text: 'text-blue-700 dark:text-blue-300' },
  WAITING_REPLY: { bg: 'bg-yellow-100 dark:bg-yellow-900/50', text: 'text-yellow-700 dark:text-yellow-300' },
  REPLIED: { bg: 'bg-indigo-100 dark:bg-indigo-900/50', text: 'text-indigo-700 dark:text-indigo-300' },
  ANALYZING: { bg: 'bg-purple-100 dark:bg-purple-900/50', text: 'text-purple-700 dark:text-purple-300' },
  GOT_NUMBER: { bg: 'bg-green-100 dark:bg-green-900/50', text: 'text-green-700 dark:text-green-300' },
  NEED_MORE: { bg: 'bg-orange-100 dark:bg-orange-900/50', text: 'text-orange-700 dark:text-orange-300' },
  FOLLOWUP_SENT: { bg: 'bg-cyan-100 dark:bg-cyan-900/50', text: 'text-cyan-700 dark:text-cyan-300' },
  REFUSED: { bg: 'bg-red-100 dark:bg-red-900/50', text: 'text-red-700 dark:text-red-300' },
  NO_REPLY: { bg: 'bg-gray-100 dark:bg-gray-700', text: 'text-gray-500 dark:text-gray-400' },
  ABANDONED: { bg: 'bg-gray-100 dark:bg-gray-700', text: 'text-gray-500 dark:text-gray-400' },
  UNDELIVERED: { bg: 'bg-red-100 dark:bg-red-900/50', text: 'text-red-700 dark:text-red-300' },
}

export const PIPELINE_STAGES = [
  { key: 'pending', label: 'Pending', icon: 'Clock' },
  { key: 'ig_found', label: 'IG Found', icon: 'Search' },
  { key: 'ig_scraped', label: 'Scraped', icon: 'Download' },
  { key: 'contacted', label: 'Contacted', icon: 'MessageSquare' },
  { key: 'got_number', label: 'Got Number', icon: 'CheckCircle' },
  { key: 'failed', label: 'Failed', icon: 'XCircle' },
] as const

export const CONVERSATION_STATES = [
  'PENDING',
  'INITIAL_SENT',
  'WAITING_REPLY',
  'REPLIED',
  'ANALYZING',
  'GOT_NUMBER',
  'NEED_MORE',
  'FOLLOWUP_SENT',
  'REFUSED',
  'NO_REPLY',
  'ABANDONED',
  'UNDELIVERED',
] as const

// Trunk: the main linear path
export const TIMELINE_TRUNK = [
  'PENDING', 'INITIAL_SENT', 'WAITING_REPLY', 'REPLIED', 'ANALYZING',
] as const

// Branches from ANALYZING
export const TIMELINE_BRANCHES = [
  { state: 'GOT_NUMBER', color: 'green', label: 'Got Number' },
  { state: 'NEED_MORE', color: 'orange', label: 'Need More',
    next: { state: 'FOLLOWUP_SENT', label: 'Follow-up Sent' } },
  { state: 'REFUSED', color: 'red', label: 'Refused' },
] as const

// Terminal states (can happen from anywhere)
export const TIMELINE_TERMINALS = ['ABANDONED', 'NO_REPLY', 'UNDELIVERED'] as const

export const ITEMS_PER_PAGE = 25
