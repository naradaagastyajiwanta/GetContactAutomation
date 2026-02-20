import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { BrowserRouter, Routes, Route } from 'react-router-dom'
import { ThemeProvider } from './context/ThemeContext'
import { ToastProvider } from './context/ToastContext'
import { AppShell } from './components/layout/AppShell'
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
const SettingsPage = lazy(() => import('./pages/SettingsPage'))

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: false } },
})

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <ThemeProvider>
        <ToastProvider>
          <BrowserRouter>
            <Suspense
              fallback={
                <div className="flex h-screen items-center justify-center">
                  <Spinner size="lg" />
                </div>
              }
            >
              <Routes>
                <Route element={<AppShell />}>
                  <Route index element={<DashboardPage />} />
                  <Route path="universities" element={<UniversitiesPage />} />
                  <Route path="universities/:id" element={<UniversityDetailPage />} />
                  <Route path="pipeline" element={<PipelinePage />} />
                  <Route path="conversations" element={<ConversationsPage />} />
                  <Route path="conversations/:id" element={<ConversationDetailPage />} />
                  <Route path="learning" element={<LearningPage />} />
                  <Route path="whatsapp" element={<WhatsAppPage />} />
                  <Route path="settings" element={<SettingsPage />} />
                </Route>
              </Routes>
            </Suspense>
          </BrowserRouter>
        </ToastProvider>
      </ThemeProvider>
    </QueryClientProvider>
  )
}
