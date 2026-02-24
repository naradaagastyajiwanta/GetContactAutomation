import { Search, Download, Phone, Users } from 'lucide-react'
import { usePipelineStatus, useTriggerFindHandles, useTriggerDiscoverBem, useTriggerScrapePosts, useTriggerExtractPhones } from '../hooks/usePipeline'
import { Spinner } from '../components/ui/Spinner'
import { PipelineOverview } from '../components/pipeline/PipelineOverview'
import { FunnelChart } from '../components/pipeline/FunnelChart'
import { AgentTriggerCard } from '../components/pipeline/AgentTriggerCard'
import { PddiktiTriggerCard } from '../components/pipeline/PddiktiTriggerCard'
import { PipelineActivityLog } from '../components/pipeline/PipelineActivityLog'

export default function PipelinePage() {
  const { data: status, isLoading } = usePipelineStatus()
  const findHandles = useTriggerFindHandles()
  const discoverBem = useTriggerDiscoverBem()
  const scrapePosts = useTriggerScrapePosts()
  const extractPhones = useTriggerExtractPhones()

  if (isLoading) {
    return (
      <div className="flex h-64 items-center justify-center">
        <Spinner size="lg" />
      </div>
    )
  }

  if (!status) return null

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">
        Pipeline
      </h1>

      <PipelineOverview status={status} />

      <FunnelChart status={status} />

      <div>
        <h2 className="mb-4 text-lg font-semibold text-gray-900 dark:text-gray-100">
          Trigger Agents
        </h2>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
          <PddiktiTriggerCard />
          <AgentTriggerCard
            title="Find IG Handles"
            description="Search for Instagram handles for pending universities."
            defaultLimit={50}
            mutation={findHandles}
            icon={Search}
          />
          <AgentTriggerCard
            title="Discover BEM"
            description="Find BEM accounts and scan their following lists."
            defaultLimit={30}
            mutation={discoverBem}
            icon={Users}
          />
          <AgentTriggerCard
            title="Scrape IG Posts"
            description="Scrape posts from found Instagram handles."
            defaultLimit={20}
            mutation={scrapePosts}
            icon={Download}
          />
          <AgentTriggerCard
            title="Extract Phones"
            description="Extract phone numbers from scraped posts."
            defaultLimit={50}
            mutation={extractPhones}
            icon={Phone}
          />
        </div>
      </div>

      <PipelineActivityLog />
    </div>
  )
}
