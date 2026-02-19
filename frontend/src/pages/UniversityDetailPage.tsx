import { useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { ArrowLeft } from 'lucide-react'
import { useUniversity, useUniversityContacts, useUniversityPosts } from '../hooks/useUniversities'
import { Button } from '../components/ui/Button'
import { Card } from '../components/ui/Card'
import { Spinner } from '../components/ui/Spinner'
import { UniversityDetail } from '../components/universities/UniversityDetail'
import { ContactsPanel } from '../components/universities/ContactsPanel'
import { PostsPanel } from '../components/universities/PostsPanel'
import { cn } from '../lib/utils'

type Tab = 'contacts' | 'posts'

export default function UniversityDetailPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const [activeTab, setActiveTab] = useState<Tab>('contacts')

  const universityId = Number(id) || 0
  const { data: university, isLoading } = useUniversity(universityId)
  const { data: contacts } = useUniversityContacts(universityId)
  const { data: posts } = useUniversityPosts(universityId)

  if (isLoading) {
    return (
      <div className="flex h-64 items-center justify-center">
        <Spinner size="lg" />
      </div>
    )
  }

  if (!university) {
    return (
      <div className="text-center text-gray-500 dark:text-gray-400">
        University not found.
      </div>
    )
  }

  const tabs: { key: Tab; label: string; count?: number }[] = [
    { key: 'contacts', label: 'Contacts', count: contacts?.length },
    { key: 'posts', label: 'Posts', count: posts?.length },
  ]

  return (
    <div className="space-y-6">
      <Button variant="ghost" size="sm" onClick={() => navigate('/universities')}>
        <ArrowLeft className="h-4 w-4" />
        Back to Universities
      </Button>

      <UniversityDetail university={university} />

      <div>
        <div className="border-b border-gray-200 dark:border-gray-700">
          <nav className="flex gap-4">
            {tabs.map((tab) => (
              <button
                key={tab.key}
                onClick={() => setActiveTab(tab.key)}
                className={cn(
                  'border-b-2 px-1 py-3 text-sm font-medium transition-colors',
                  activeTab === tab.key
                    ? 'border-indigo-500 text-indigo-600 dark:text-indigo-400'
                    : 'border-transparent text-gray-500 hover:border-gray-300 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-300',
                )}
              >
                {tab.label}
                {tab.count !== undefined && (
                  <span className="ml-2 rounded-full bg-gray-100 px-2 py-0.5 text-xs text-gray-600 dark:bg-gray-700 dark:text-gray-300">
                    {tab.count}
                  </span>
                )}
              </button>
            ))}
          </nav>
        </div>

        <Card className="mt-4" padding={false}>
          {activeTab === 'contacts' && (
            <ContactsPanel contacts={contacts || []} />
          )}
          {activeTab === 'posts' && (
            <PostsPanel posts={posts || []} />
          )}
        </Card>
      </div>
    </div>
  )
}
