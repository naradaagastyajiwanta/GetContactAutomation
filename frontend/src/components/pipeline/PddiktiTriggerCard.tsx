import { useState } from 'react'
import { GraduationCap } from 'lucide-react'
import { Card, CardHeader, CardTitle, CardContent } from '../ui/Card'
import { Button } from '../ui/Button'
import { useProvinces, useTriggerCollectUniversities } from '../../hooks/usePipeline'

export function PddiktiTriggerCard() {
  const [province, setProvince] = useState('')
  const { data: provinces } = useProvinces()
  const collectMutation = useTriggerCollectUniversities()

  const handleTrigger = () => {
    collectMutation.mutate(province || undefined)
  }

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center gap-3">
          <div className="rounded-lg bg-emerald-100 p-2 dark:bg-emerald-900/50">
            <GraduationCap className="h-5 w-5 text-emerald-600 dark:text-emerald-400" />
          </div>
          <CardTitle>Collect Universities</CardTitle>
        </div>
      </CardHeader>
      <CardContent>
        <p className="mb-4 text-sm text-gray-600 dark:text-gray-400">
          Search PDDIKTI for Indonesian universities and add to database.
        </p>
        <div className="flex flex-col gap-3">
          <div className="flex items-center gap-3">
            <label className="text-sm text-gray-600 dark:text-gray-400">Province:</label>
            <select
              value={province}
              onChange={(e) => setProvince(e.target.value)}
              className="flex-1 rounded-lg border border-gray-300 bg-white px-3 py-1.5 text-sm dark:border-gray-600 dark:bg-gray-800 dark:text-gray-100"
            >
              <option value="">All Provinces</option>
              {provinces?.map((p) => (
                <option key={p} value={p}>
                  {p}
                </option>
              ))}
            </select>
          </div>
          <Button
            onClick={handleTrigger}
            loading={collectMutation.isPending}
            size="sm"
            className="w-full"
          >
            Collect from PDDIKTI
          </Button>
        </div>
      </CardContent>
    </Card>
  )
}
