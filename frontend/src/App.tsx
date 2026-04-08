import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import { ThemeProvider } from "./context/ThemeContext";
import { ToastProvider } from "./context/ToastContext";
import { AuthProvider } from "./context/AuthContext";
import { ErrorBoundary } from "./components/ErrorBoundary";
import { lazy, Suspense } from "react";
import { Spinner } from "./components/ui/Spinner";
import { ProtectedRoute } from "./components/auth/ProtectedRoute";
import { PermissionGuard } from "./components/auth/PermissionGuard";
import { ProtectedLayout } from "./components/auth/ProtectedLayout";

const DashboardPage = lazy(() => import("./pages/DashboardPage"));
const UniversitiesPage = lazy(() => import("./pages/UniversitiesPage"));
const UniversityDetailPage = lazy(() => import("./pages/UniversityDetailPage"));
const PipelinePage = lazy(() => import("./pages/PipelinePage"));
const ConversationsPage = lazy(() => import("./pages/ConversationsPage"));
const ConversationDetailPage = lazy(
  () => import("./pages/ConversationDetailPage"),
);
const LearningPage = lazy(() => import("./pages/LearningPage"));
const WhatsAppPage = lazy(() => import("./pages/WhatsAppPage"));
const AudiensiQueuePage = lazy(() => import("./pages/AudiensiQueuePage"));
const AudiensiDetailPage = lazy(() => import("./pages/AudiensiDetailPage"));
const KnowledgeBasePage = lazy(() => import("./pages/KnowledgeBasePage"));
const ApiLogsPage = lazy(() => import("./pages/ApiLogsPage"));
const LogsPage = lazy(() => import("./pages/LogsPage"));
const SettingsPage = lazy(() => import("./pages/SettingsPage"));
const BlastCampaignsPage = lazy(() => import("./pages/BlastCampaignsPage"));
const BlastCampaignDetailPage = lazy(
  () => import("./pages/BlastCampaignDetailPage"),
);
const EmailBlastPage = lazy(() => import("./pages/EmailBlastPage"));
const DmsSchedulesPage = lazy(() => import("./pages/DmsSchedulesPage"));
const DmsScheduleDetailPage = lazy(
  () => import("./pages/DmsScheduleDetailPage"),
);
const CrmPage = lazy(() => import("./pages/CrmPage"));
const CrmDetailPage = lazy(() => import("./pages/CrmDetailPage"));
const UniversityGroupsPage = lazy(() => import("./pages/UniversityGroupsPage"));
const MarketingGetContactPage = lazy(
  () => import("./pages/MarketingGetContactPage"),
);
const MarketingClientDetailPage = lazy(
  () => import("./pages/MarketingClientDetailPage"),
);
const MarketingClientPage = lazy(() => import("./pages/MarketingClientPage"));
const MarketingClientsPage = lazy(() => import("./pages/MarketingClientsPage"));
const LoginPage = lazy(() => import("./pages/LoginPage"));

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: false } },
});

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <ThemeProvider>
        <ToastProvider>
          <BrowserRouter
            future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
          >
            <AuthProvider>
              <Suspense
                fallback={
                  <div className="flex h-screen items-center justify-center">
                    <Spinner size="lg" />
                  </div>
                }
              >
                <Routes>
                  <Route
                    path="/login"
                    element={
                      <ErrorBoundary>
                        <LoginPage />
                      </ErrorBoundary>
                    }
                  />
                  <Route element={<ProtectedRoute />}>
                    <Route element={<ProtectedLayout />}>
                      <Route
                        index
                        element={
                          <PermissionGuard permission="dashboard.view">
                            <ErrorBoundary>
                              <DashboardPage />
                            </ErrorBoundary>
                          </PermissionGuard>
                        }
                      />
                      <Route
                        path="universities"
                        element={
                          <PermissionGuard permission="universities.view">
                            <ErrorBoundary>
                              <UniversitiesPage />
                            </ErrorBoundary>
                          </PermissionGuard>
                        }
                      />
                      <Route
                        path="universities/:id"
                        element={
                          <PermissionGuard permission="universities.view">
                            <ErrorBoundary>
                              <UniversityDetailPage />
                            </ErrorBoundary>
                          </PermissionGuard>
                        }
                      />
                      <Route
                        path="pipeline"
                        element={
                          <PermissionGuard permission="pipeline.view">
                            <ErrorBoundary>
                              <PipelinePage />
                            </ErrorBoundary>
                          </PermissionGuard>
                        }
                      />
                      <Route
                        path="conversations"
                        element={
                          <PermissionGuard permission="conversations.view">
                            <ErrorBoundary>
                              <ConversationsPage />
                            </ErrorBoundary>
                          </PermissionGuard>
                        }
                      />
                      <Route
                        path="conversations/:id"
                        element={
                          <PermissionGuard permission="conversations.view">
                            <ErrorBoundary>
                              <ConversationDetailPage />
                            </ErrorBoundary>
                          </PermissionGuard>
                        }
                      />
                      <Route
                        path="learning"
                        element={
                          <PermissionGuard permission="learning.view">
                            <ErrorBoundary>
                              <LearningPage />
                            </ErrorBoundary>
                          </PermissionGuard>
                        }
                      />
                      <Route
                        path="whatsapp"
                        element={
                          <PermissionGuard permission="whatsapp.view">
                            <ErrorBoundary>
                              <WhatsAppPage />
                            </ErrorBoundary>
                          </PermissionGuard>
                        }
                      />
                      <Route
                        path="audiensi"
                        element={
                          <PermissionGuard permission="audiensi.view">
                            <ErrorBoundary>
                              <AudiensiQueuePage />
                            </ErrorBoundary>
                          </PermissionGuard>
                        }
                      />
                      <Route
                        path="audiensi/:id"
                        element={
                          <PermissionGuard permission="audiensi.view">
                            <ErrorBoundary>
                              <AudiensiDetailPage />
                            </ErrorBoundary>
                          </PermissionGuard>
                        }
                      />
                      <Route
                        path="knowledge"
                        element={
                          <PermissionGuard permission="knowledge.view">
                            <ErrorBoundary>
                              <KnowledgeBasePage />
                            </ErrorBoundary>
                          </PermissionGuard>
                        }
                      />
                      <Route
                        path="api-logs"
                        element={
                          <PermissionGuard permission="settings.manage">
                            <ErrorBoundary>
                              <ApiLogsPage />
                            </ErrorBoundary>
                          </PermissionGuard>
                        }
                      />
                      <Route
                        path="logs"
                        element={
                          <PermissionGuard permission="settings.manage">
                            <ErrorBoundary>
                              <LogsPage />
                            </ErrorBoundary>
                          </PermissionGuard>
                        }
                      />
                      <Route
                        path="blast"
                        element={
                          <PermissionGuard permission="blast.view">
                            <ErrorBoundary>
                              <BlastCampaignsPage />
                            </ErrorBoundary>
                          </PermissionGuard>
                        }
                      />
                      <Route
                        path="blast/:id"
                        element={
                          <PermissionGuard permission="blast.view">
                            <ErrorBoundary>
                              <BlastCampaignDetailPage />
                            </ErrorBoundary>
                          </PermissionGuard>
                        }
                      />
                      <Route
                        path="email-blast"
                        element={
                          <PermissionGuard permission="blast.view">
                            <ErrorBoundary>
                              <EmailBlastPage />
                            </ErrorBoundary>
                          </PermissionGuard>
                        }
                      />
                      <Route
                        path="email-blast/:id"
                        element={
                          <PermissionGuard permission="blast.view">
                            <ErrorBoundary>
                              <EmailBlastPage />
                            </ErrorBoundary>
                          </PermissionGuard>
                        }
                      />
                      <Route
                        path="email-blast/inbox"
                        element={
                          <PermissionGuard permission="blast.view">
                            <ErrorBoundary>
                              <EmailBlastPage />
                            </ErrorBoundary>
                          </PermissionGuard>
                        }
                      />
                      <Route
                        path="email-blast/sent"
                        element={
                          <PermissionGuard permission="blast.view">
                            <ErrorBoundary>
                              <EmailBlastPage />
                            </ErrorBoundary>
                          </PermissionGuard>
                        }
                      />
                      <Route
                        path="email-blast/imap-sent"
                        element={
                          <PermissionGuard permission="blast.view">
                            <ErrorBoundary>
                              <EmailBlastPage />
                            </ErrorBoundary>
                          </PermissionGuard>
                        }
                      />
                      <Route
                        path="email-blast/campaigns"
                        element={
                          <PermissionGuard permission="blast.view">
                            <ErrorBoundary>
                              <EmailBlastPage />
                            </ErrorBoundary>
                          </PermissionGuard>
                        }
                      />
                      <Route
                        path="email-blast/campaigns/:id"
                        element={
                          <PermissionGuard permission="blast.view">
                            <ErrorBoundary>
                              <EmailBlastPage />
                            </ErrorBoundary>
                          </PermissionGuard>
                        }
                      />
                      <Route
                        path="email-blast/settings"
                        element={
                          <PermissionGuard permission="blast.view">
                            <ErrorBoundary>
                              <EmailBlastPage />
                            </ErrorBoundary>
                          </PermissionGuard>
                        }
                      />
                      <Route
                        path="email-blast/letter-history"
                        element={
                          <PermissionGuard permission="blast.view">
                            <ErrorBoundary>
                              <EmailBlastPage />
                            </ErrorBoundary>
                          </PermissionGuard>
                        }
                      />
                      <Route
                        path="dms-schedules"
                        element={
                          <PermissionGuard permission="audiensi.view">
                            <ErrorBoundary>
                              <DmsSchedulesPage />
                            </ErrorBoundary>
                          </PermissionGuard>
                        }
                      />
                      <Route
                        path="dms-schedules/:id"
                        element={
                          <PermissionGuard permission="audiensi.view">
                            <ErrorBoundary>
                              <DmsScheduleDetailPage />
                            </ErrorBoundary>
                          </PermissionGuard>
                        }
                      />
                      <Route
                        path="crm"
                        element={
                          <PermissionGuard permission="crm.view">
                            <ErrorBoundary>
                              <CrmPage />
                            </ErrorBoundary>
                          </PermissionGuard>
                        }
                      />
                      <Route
                        path="crm/:id"
                        element={
                          <PermissionGuard permission="crm.view">
                            <ErrorBoundary>
                              <CrmDetailPage />
                            </ErrorBoundary>
                          </PermissionGuard>
                        }
                      />
                      <Route
                        path="university-groups"
                        element={
                          <PermissionGuard permission="universities.view">
                            <ErrorBoundary>
                              <UniversityGroupsPage />
                            </ErrorBoundary>
                          </PermissionGuard>
                        }
                      />
                      <Route
                        path="marketing"
                        element={
                          <PermissionGuard permission="marketing.view">
                            <ErrorBoundary>
                              <MarketingGetContactPage />
                            </ErrorBoundary>
                          </PermissionGuard>
                        }
                      />
                      <Route
                        path="marketing/groups/:id"
                        element={
                          <PermissionGuard permission="marketing.view">
                            <ErrorBoundary>
                              <MarketingClientDetailPage />
                            </ErrorBoundary>
                          </PermissionGuard>
                        }
                      />
                      <Route
                        path="marketing/clients"
                        element={
                          <PermissionGuard permission="marketing.view">
                            <ErrorBoundary>
                              <MarketingClientsPage />
                            </ErrorBoundary>
                          </PermissionGuard>
                        }
                      />
                      <Route
                        path="marketing/clients/:id"
                        element={
                          <PermissionGuard permission="marketing.view">
                            <ErrorBoundary>
                              <MarketingClientPage />
                            </ErrorBoundary>
                          </PermissionGuard>
                        }
                      />
                      <Route
                        path="settings"
                        element={
                          <PermissionGuard permission="settings.instagram">
                            <ErrorBoundary>
                              <SettingsPage />
                            </ErrorBoundary>
                          </PermissionGuard>
                        }
                      />
                    </Route>
                  </Route>
                </Routes>
              </Suspense>
            </AuthProvider>
          </BrowserRouter>
        </ToastProvider>
      </ThemeProvider>
    </QueryClientProvider>
  );
}
