import { useState } from 'react'
import type { LucideIcon } from 'lucide-react'
import type { UseMutationResult } from '@tanstack/react-query'
import { Card, CardHeader, CardTitle, CardContent } from '../ui/Card'
import { Button } from '../ui/Button'

interface AgentTriggerCardProps {
  title: string
  description: string
  defaultLimit: number
  mutation: UseMutationResult<unknown, unknown, number | undefined, unknown>
  icon: LucideIcon
}

export function AgentTriggerCard({
  title,
  description,
  defaultLimit,
  mutation,
  icon: Icon,
}: AgentTriggerCardProps) {
  const [limit, setLimit] = useState(defaultLimit)

  const handleTrigger = () => {
    mutation.mutate(limit)
  }

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center gap-3">
          <div className="rounded-lg bg-indigo-100 p-2 dark:bg-indigo-900/50">
            <Icon className="h-5 w-5 text-indigo-600 dark:text-indigo-400" />
          </div>
          <CardTitle>{title}</CardTitle>
        </div>
      </CardHeader>
      <CardContent>
        <p className="mb-4 text-sm text-gray-600 dark:text-gray-400">
          {description}
        </p>
        <div className="flex items-center gap-3">
          <label className="text-sm text-gray-600 dark:text-gray-400">Limit:</label>
          <input
            type="number"
            min={1}
            max={500}
            value={limit}
            onChange={(e) => setLimit(Number(e.target.value) || defaultLimit)}
            className="w-20 rounded-lg border border-gray-300 bg-white px-3 py-1.5 text-sm dark:border-gray-600 dark:bg-gray-800 dark:text-gray-100"
          />
          <Button
            onClick={handleTrigger}
            loading={mutation.isPending}
            size="sm"
          >
            Run
          </Button>
        </div>
      </CardContent>
    </Card>
  )
}
