import { Select } from '../ui/Select'
import { CONVERSATION_STATES } from '../../lib/constants'

interface ConversationFiltersProps {
  state: string
  onStateChange: (state: string) => void
}

const stateOptions = [
  { value: '', label: 'All States' },
  ...CONVERSATION_STATES.map((s) => ({ value: s, label: s.replace(/_/g, ' ') })),
]

export function ConversationFilters({ state, onStateChange }: ConversationFiltersProps) {
  return (
    <div className="flex items-center gap-3">
      <Select
        value={state}
        onChange={onStateChange}
        options={stateOptions}
        className="w-48"
      />
    </div>
  )
}
