import { useState } from 'react'
import { ClipboardPaste, Search, CheckCircle2, AlertCircle, Loader2 } from 'lucide-react'
import toast from 'react-hot-toast'
import { Modal } from '../ui/Modal'
import { Button } from '../ui/Button'
import { Badge } from '../ui/Badge'
import { matchUniversityNames, type MatchedUniversity } from '../../api/universities'

interface BulkSelectModalProps {
  isOpen: boolean
  onClose: () => void
  currentSelected: Set<number>
  onSelect: (ids: Set<number>) => void
}

export function BulkSelectModal({ isOpen, onClose, currentSelected, onSelect }: BulkSelectModalProps) {
  const [text, setText] = useState('')
  const [loading, setLoading] = useState(false)
  const [matches, setMatches] = useState<MatchedUniversity[] | null>(null)
  const [checkedIds, setCheckedIds] = useState<Set<number>>(new Set())
  const [notMatched, setNotMatched] = useState<string[]>([])

  const reset = () => {
    setText('')
    setMatches(null)
    setCheckedIds(new Set())
    setNotMatched([])
  }

  const handleClose = () => {
    if (!loading) {
      reset()
      onClose()
    }
  }

  const handleMatch = async () => {
    const lines = text
      .split(/[\n,;]+/)
      .map((l) => l.trim())
      .filter(Boolean)

    if (lines.length === 0) {
      toast.error('Paste at least one university name')
      return
    }

    setLoading(true)
    try {
      const result = await matchUniversityNames(lines)
      setMatches(result.matches)
      // Check all matched by default
      setCheckedIds(new Set(result.matches.map((m) => m.id)))

      // Find unmatched queries
      const matchedQueries = new Set(result.matches.map((m) => m.matched_query.toLowerCase()))
      const unmatched = lines.filter((l) => !matchedQueries.has(l.toLowerCase()))
      setNotMatched(unmatched)

      if (result.matches.length === 0) {
        toast.error('No matches found for the provided names')
      }
    } catch {
      toast.error('Failed to match university names')
    } finally {
      setLoading(false)
    }
  }

  const toggleCheck = (id: number) => {
    setCheckedIds((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const toggleAll = () => {
    if (!matches) return
    if (checkedIds.size === matches.length) {
      setCheckedIds(new Set())
    } else {
      setCheckedIds(new Set(matches.map((m) => m.id)))
    }
  }

  const handleApply = () => {
    const merged = new Set(currentSelected)
    checkedIds.forEach((id) => merged.add(id))
    onSelect(merged)
    toast.success(`${checkedIds.size} universit${checkedIds.size === 1 ? 'y' : 'ies'} selected`)
    handleClose()
  }

  return (
    <Modal isOpen={isOpen} onClose={handleClose} title="Bulk Select Universities" size="lg">
      <div className="space-y-4">
        {!matches ? (
          /* Step 1: Paste names */
          <>
            <p className="text-sm text-gray-600 dark:text-gray-400">
              Paste university names below (one per line, or comma/semicolon separated).
              The system will fuzzy-match them against the database.
            </p>
            <textarea
              value={text}
              onChange={(e) => setText(e.target.value)}
              placeholder={`Universitas Indonesia\nInstitut Teknologi Bandung\nUniversitas Gadjah Mada\n...`}
              rows={10}
              className="w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm font-mono text-gray-900 placeholder-gray-400 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 dark:border-gray-600 dark:bg-gray-800 dark:text-gray-100 dark:placeholder-gray-500"
            />
            <div className="flex items-center justify-between text-xs text-gray-500 dark:text-gray-400">
              <span>
                {text.split(/[\n,;]+/).filter((l) => l.trim()).length} name(s) detected
              </span>
              <button
                onClick={async () => {
                  try {
                    const clip = await navigator.clipboard.readText()
                    setText(clip)
                    toast.success('Pasted from clipboard')
                  } catch {
                    toast.error('Cannot read clipboard')
                  }
                }}
                className="inline-flex items-center gap-1 text-indigo-600 hover:text-indigo-800 dark:text-indigo-400 dark:hover:text-indigo-300"
              >
                <ClipboardPaste className="h-3.5 w-3.5" />
                Paste from clipboard
              </button>
            </div>
            <div className="flex justify-end gap-2">
              <Button variant="secondary" onClick={handleClose}>
                Cancel
              </Button>
              <Button onClick={handleMatch} loading={loading} disabled={!text.trim()}>
                <Search className="h-4 w-4" />
                Match Names
              </Button>
            </div>
          </>
        ) : (
          /* Step 2: Review matches */
          <>
            <div className="flex items-center gap-3 text-sm">
              <span className="inline-flex items-center gap-1 text-emerald-700 dark:text-emerald-400">
                <CheckCircle2 className="h-4 w-4" />
                {matches.length} matched
              </span>
              {notMatched.length > 0 && (
                <span className="inline-flex items-center gap-1 text-amber-700 dark:text-amber-400">
                  <AlertCircle className="h-4 w-4" />
                  {notMatched.length} not found
                </span>
              )}
            </div>

            {/* Matched results */}
            {matches.length > 0 && (
              <div className="max-h-72 overflow-y-auto rounded-lg border border-gray-200 dark:border-gray-700">
                <table className="w-full text-sm">
                  <thead className="sticky top-0 bg-gray-50 dark:bg-gray-800">
                    <tr>
                      <th className="w-10 px-3 py-2">
                        <input
                          type="checkbox"
                          checked={checkedIds.size === matches.length}
                          onChange={toggleAll}
                          className="rounded border-gray-300 text-indigo-600 focus:ring-indigo-500"
                        />
                      </th>
                      <th className="px-3 py-2 text-left font-medium text-gray-700 dark:text-gray-300">University</th>
                      <th className="px-3 py-2 text-left font-medium text-gray-700 dark:text-gray-300">Province</th>
                      <th className="px-3 py-2 text-left font-medium text-gray-700 dark:text-gray-300">Match</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-100 dark:divide-gray-700">
                    {matches.map((m) => (
                      <tr
                        key={m.id}
                        className={`cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-800/50 ${
                          checkedIds.has(m.id) ? '' : 'opacity-50'
                        }`}
                        onClick={() => toggleCheck(m.id)}
                      >
                        <td className="px-3 py-1.5">
                          <input
                            type="checkbox"
                            checked={checkedIds.has(m.id)}
                            onChange={() => toggleCheck(m.id)}
                            className="rounded border-gray-300 text-indigo-600 focus:ring-indigo-500"
                          />
                        </td>
                        <td className="px-3 py-1.5">
                          <div className="font-medium text-gray-900 dark:text-gray-100">{m.name}</div>
                          {m.ig_handle && (
                            <div className="text-xs text-gray-500 dark:text-gray-400">@{m.ig_handle}</div>
                          )}
                        </td>
                        <td className="px-3 py-1.5 text-gray-600 dark:text-gray-400">
                          {m.province || '-'}
                        </td>
                        <td className="px-3 py-1.5">
                          <Badge
                            className={
                              m.match_type === 'exact'
                                ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400'
                                : 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400'
                            }
                          >
                            {m.match_type}
                          </Badge>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            {/* Not matched names */}
            {notMatched.length > 0 && (
              <details className="rounded-lg border border-amber-200 bg-amber-50/50 px-3 py-2 dark:border-amber-800 dark:bg-amber-950/20">
                <summary className="cursor-pointer text-sm font-medium text-amber-700 dark:text-amber-400">
                  {notMatched.length} name(s) not found
                </summary>
                <ul className="mt-1 space-y-0.5 text-xs text-amber-600 dark:text-amber-500">
                  {notMatched.map((name, i) => (
                    <li key={i}>• {name}</li>
                  ))}
                </ul>
              </details>
            )}

            <div className="flex items-center justify-between">
              <button
                onClick={() => { setMatches(null); setNotMatched([]) }}
                className="text-sm text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200"
              >
                ← Back to paste
              </button>
              <div className="flex gap-2">
                <Button variant="secondary" onClick={handleClose}>
                  Cancel
                </Button>
                <Button onClick={handleApply} disabled={checkedIds.size === 0}>
                  <CheckCircle2 className="h-4 w-4" />
                  Select {checkedIds.size} Universit{checkedIds.size === 1 ? 'y' : 'ies'}
                </Button>
              </div>
            </div>
          </>
        )}
      </div>
    </Modal>
  )
}
