import { Card, CardHeader, CardTitle, CardContent } from '../ui/Card'

const configItems = [
  { label: 'Daily Conversation Limit', value: '20' },
  { label: 'Message Gap', value: '5 minutes' },
  { label: 'Outreach Hours', value: '7:00 - 22:00 WIB' },
  { label: 'IG Profiles/Day', value: '200' },
  { label: 'Max Posts/Profile', value: '20' },
]

export function ConfigDisplay() {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Configuration</CardTitle>
      </CardHeader>
      <CardContent>
        <dl className="space-y-3">
          {configItems.map((item) => (
            <div key={item.label} className="flex items-center justify-between">
              <dt className="text-sm text-gray-500 dark:text-gray-400">{item.label}</dt>
              <dd className="text-sm font-medium text-gray-900 dark:text-gray-100">
                {item.value}
              </dd>
            </div>
          ))}
        </dl>
      </CardContent>
    </Card>
  )
}
