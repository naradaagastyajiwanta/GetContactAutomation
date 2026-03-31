import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { BrowserRouter, Routes, Route } from 'react-router-dom'
import { ThemeProvider } from './context/ThemeContext'
import { ToastProvider } from './context/ToastContext'
import { WebSocketProvider } from './context/WebSocketContext'
import { AppShell } from './components/layout/AppShell'
import { ErrorBoundary } from './components/ErrorBoundary'
import { lazy, Suspense } from 'react'
import { Spinner } from './components/ui/Spinner'

const DashboardPage = lazy(() => import('./pages/DashboardPage'))
const UniversitiesPage = lazy(() => import('./pages/UniversitiesPage'))
const UniversityDetailPage = lazy(() => import('./pages/UniversityDetailPage'))
const PipelinePage = lazy(() => import('./pages/PipelinePage'))
const ConversationsPage = lazy(() => import('./pages/ConversationsPage'))
const ConversationDetailPage = lazy(() => import('./pages/ConversationDetailPage'))
const LearningPage = lazy(() => import('./pages/LearningPage'))
const WhatsAppPage = lazy(() => import('./pages/WhatsAppPage'))
const AudiensiQueuePage = lazy(() => import('./pages/AudiensiQueuePage'))
const AudiensiDetailPage = lazy(() => import('./pages/AudiensiDetailPage'))
const KnowledgeBasePage = lazy(() => import('./pages/KnowledgeBasePage'))
const ApiLogsPage = lazy(() => import('./pages/ApiLogsPage'))
const LogsPage = lazy(() => import('./pages/LogsPage'))
const SettingsPage = lazy(() => import('./pages/SettingsPage'))
const BlastCampaignsPage = lazy(() => import('./pages/BlastCampaignsPage'))
const BlastCampaignDetailPage = lazy(() => import('./pages/BlastCampaignDetailPage'))
const EmailBlastPage = lazy(() => import('./pages/EmailBlastPage'))
const DmsSchedulesPage = lazy(() => import('./pages/DmsSchedulesPage'))
const DmsScheduleDetailPage = lazy(() => import('./pages/DmsScheduleDetailPage'))
const CrmPage = lazy(() => import('./pages/CrmPage'))
const CrmDetailPage = lazy(() => import('./pages/CrmDetailPage'))
const UniversityGroupsPage = lazy(() => import('./pages/UniversityGroupsPage'))

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: false } },
})

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <ThemeProvider>
        <ToastProvider>
          <WebSocketProvider>
            <BrowserRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
              <Suspense
                fallback={
                  <div className="flex h-screen items-center justify-center">
                    <Spinner size="lg" />
                  </div>
                }
              >
                <Routes>
                  <Route element={<AppShell />}>
                    <Route index element={<ErrorBoundary><DashboardPage /></ErrorBoundary>} />
                    <Route path="universities" element={<ErrorBoundary><UniversitiesPage /></ErrorBoundary>} />
                    <Route path="universities/:id" element={<ErrorBoundary><UniversityDetailPage /></ErrorBoundary>} />
                    <Route path="pipeline" element={<ErrorBoundary><PipelinePage /></ErrorBoundary>} />
                    <Route path="conversations" element={<ErrorBoundary><ConversationsPage /></ErrorBoundary>} />
                    <Route path="conversations/:id" element={<ErrorBoundary><ConversationDetailPage /></ErrorBoundary>} />
                    <Route path="learning" element={<ErrorBoundary><LearningPage /></ErrorBoundary>} />
                    <Route path="whatsapp" element={<ErrorBoundary><WhatsAppPage /></ErrorBoundary>} />
                    <Route path="audiensi" element={<ErrorBoundary><AudiensiQueuePage /></ErrorBoundary>} />
                    <Route path="audiensi/:id" element={<ErrorBoundary><AudiensiDetailPage /></ErrorBoundary>} />
                    <Route path="knowledge" element={<ErrorBoundary><KnowledgeBasePage /></ErrorBoundary>} />
                    <Route path="api-logs" element={<ErrorBoundary><ApiLogsPage /></ErrorBoundary>} />
                    <Route path="logs" element={<ErrorBoundary><LogsPage /></ErrorBoundary>} />
                    <Route path="blast" element={<ErrorBoundary><BlastCampaignsPage /></ErrorBoundary>} />
                    <Route path="blast/:id" element={<ErrorBoundary><BlastCampaignDetailPage /></ErrorBoundary>} />
                    <Route path="email-blast" element={<ErrorBoundary><EmailBlastPage /></ErrorBoundary>} />
                    <Route path="email-blast/:id" element={<ErrorBoundary><EmailBlastPage /></ErrorBoundary>} />
                    <Route path="email-blast/inbox" element={<ErrorBoundary><EmailBlastPage /></ErrorBoundary>} />
                    <Route path="email-blast/sent" element={<ErrorBoundary><EmailBlastPage /></ErrorBoundary>} />
                    <Route path="email-blast/campaigns" element={<ErrorBoundary><EmailBlastPage /></ErrorBoundary>} />
                    <Route path="email-blast/campaigns/:id" element={<ErrorBoundary><EmailBlastPage /></ErrorBoundary>} />
                    <Route path="email-blast/settings" element={<ErrorBoundary><EmailBlastPage /></ErrorBoundary>} />
                    <Route path="email-blast/letter-history" element={<ErrorBoundary><EmailBlastPage /></ErrorBoundary>} />
                    <Route path="dms-schedules" element={<ErrorBoundary><DmsSchedulesPage /></ErrorBoundary>} />
                    <Route path="dms-schedules/:id" element={<ErrorBoundary><DmsScheduleDetailPage /></ErrorBoundary>} />
                    <Route path="crm" element={<ErrorBoundary><CrmPage /></ErrorBoundary>} />
                    <Route path="crm/:id" element={<ErrorBoundary><CrmDetailPage /></ErrorBoundary>} />
                    <Route path="university-groups" element={<ErrorBoundary><UniversityGroupsPage /></ErrorBoundary>} />
                    <Route path="settings" element={<ErrorBoundary><SettingsPage /></ErrorBoundary>} />
                  </Route>
                </Routes>
              </Suspense>
            </BrowserRouter>
          </WebSocketProvider>
        </ToastProvider>
      </ThemeProvider>
    </QueryClientProvider>
  )
}
