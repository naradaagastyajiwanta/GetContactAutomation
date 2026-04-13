/**
 * EmailBlastPage — Gmail-style email client for blast campaigns.
 * Layout: Left Rail + Content Area
 */

import { useState, useEffect } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { usePageTour } from "../hooks/usePageTour";
import { EMAIL_BLAST_TOUR_STEPS } from "../tours/email-blast.tour";
import { useAuth } from "../context/AuthContext";
import {
  Inbox,
  Send,
  FileText,
  Rocket,
  Pause,
  CheckCircle2,
  XCircle,
  TrendingUp,
  Settings,
  Plus,
  History,
} from "lucide-react";
import { cn } from "../lib/utils";
import {
  useEmailBlastCampaigns,
  useAllInboxEmails,
  useEmailBlastQuota,
} from "../hooks/useEmailBlast";
import { Spinner } from "../components/ui/Spinner";
import { Button } from "../components/ui/Button";
import { Modal } from "../components/ui/Modal";
import { EmailComposeBox } from "../components/emailBlast/EmailComposeBox";
import { EmailInboxView } from "../components/emailBlast/EmailInboxView";
import { EmailSentView } from "../components/emailBlast/EmailSentView";
import { EmailCampaignList } from "../components/emailBlast/EmailCampaignList";
import { EmailCampaignDetail } from "../components/emailBlast/EmailCampaignDetail";
import { EmailSettingsPanel } from "../components/emailBlast/EmailSettingsPanel";
import { EmailLetterHistory } from "../components/emailBlast/EmailLetterHistory";
import type { EmailBlastCampaign } from "../api/emailBlast";

// ─── Types ───────────────────────────────────────────────────────────────────

type View =
  | "inbox"
  | "sent"
  | "campaigns"
  | "settings"
  | "letter-history"
  | "campaign-detail";

interface NavItem {
  id: View;
  label: string;
  icon: React.ElementType;
  badge?: number;
  section?: string;
  status?: string;
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

function useAllStats() {
  const { data: allCampaigns } = useEmailBlastCampaigns();

  const campaigns = allCampaigns?.campaigns ?? [];
  const totalSent = campaigns.reduce((acc, c) => acc + c.sent_count, 0);

  return { campaigns, totalSent };
}

// ─── Left Rail ───────────────────────────────────────────────────────────────

function EmailLeftRail({
  activeView,
  onViewChange,
  stats,
  campaignCounts,
  inboxCount,
  sentCount,
  activeStatusFilter,
  quota,
}: {
  activeView: View;
  onViewChange: (v: View, campaignId?: number, status?: string) => void;
  stats: { totalSent: number };
  campaignCounts: {
    draft: number;
    running: number;
    paused: number;
    completed: number;
    cancelled: number;
  };
  inboxCount: number;
  sentCount: number;
  activeStatusFilter: string;
  quota?: {
    sent_today: number;
    daily_limit: number;
    remaining: number;
    is_exhausted: boolean;
  };
}) {
  const navItems: NavItem[] = [
    {
      id: "inbox",
      label: "Inbox",
      icon: Inbox,
      badge: inboxCount,
      section: "messages",
    },
    {
      id: "sent",
      label: "Sent",
      icon: Send,
      badge: sentCount,
      section: "messages",
    },
    {
      id: "letter-history",
      label: "Riwayat Surat",
      icon: History,
      section: "messages",
    },
  ];

  const campaignItems: NavItem[] = [
    { id: "campaigns", label: "All", icon: FileText, section: "campaigns" },
    {
      id: "campaigns",
      label: "Draft",
      icon: FileText,
      badge: campaignCounts.draft,
      section: "campaigns",
      status: "draft",
    },
    {
      id: "campaigns",
      label: "Active",
      icon: Rocket,
      badge: campaignCounts.running,
      section: "campaigns",
      status: "running",
    },
    {
      id: "campaigns",
      label: "Paused",
      icon: Pause,
      badge: campaignCounts.paused,
      section: "campaigns",
      status: "paused",
    },
    {
      id: "campaigns",
      label: "Completed",
      icon: CheckCircle2,
      badge: campaignCounts.completed,
      section: "campaigns",
      status: "completed",
    },
    {
      id: "campaigns",
      label: "Cancelled",
      icon: XCircle,
      badge: campaignCounts.cancelled,
      section: "campaigns",
      status: "cancelled",
    },
  ];

  return (
    <aside className="flex w-[220px] shrink-0 flex-col bg-white dark:bg-[#111827] border-r border-gray-100 dark:border-gray-800/80">
      {/* New Campaign Button */}
      <div className="p-3">
        <button
          onClick={() => onViewChange("campaign-detail", -1)}
          className="flex w-full items-center justify-center gap-2 rounded-xl bg-indigo-600 px-4 py-2.5 text-sm font-semibold text-white shadow-sm transition-colors hover:bg-indigo-700 active:bg-indigo-800"
        >
          <Plus className="h-4 w-4" />
          New Campaign
        </button>
      </div>

      {/* Navigation */}
      <nav className="flex-1 space-y-0.5 overflow-y-auto px-3 pb-3">
        {/* Messages section */}
        <div className="pt-1">
          <p className="mb-1 px-2 text-[10px] font-semibold uppercase tracking-wider text-gray-400">
            Messages
          </p>
          {navItems.map((item) => {
            const Icon = item.icon;
            const active = activeView === item.id;
            return (
              <button
                key={`${item.id}-${item.label}`}
                onClick={() => onViewChange(item.id)}
                className={cn(
                  "mb-0.5 flex w-full items-center gap-2.5 rounded-lg px-2 py-2 text-[13px] font-medium transition-all duration-150",
                  active
                    ? "bg-indigo-600 text-white"
                    : "text-gray-600 hover:bg-gray-50 hover:text-gray-900 dark:text-gray-400 dark:hover:bg-gray-800/60 dark:hover:text-white",
                )}
              >
                <Icon className="h-4 w-4 shrink-0" />
                <span className="flex-1 text-left">{item.label}</span>
                {item.badge !== undefined && item.badge > 0 && (
                  <span
                    className={cn(
                      "flex h-5 min-w-[20px] items-center justify-center rounded-full px-1.5 text-[10px] font-semibold",
                      active
                        ? "bg-white/20 text-white"
                        : "bg-gray-100 text-gray-500 dark:bg-gray-800 dark:text-gray-400",
                    )}
                  >
                    {item.badge > 99 ? "99+" : item.badge}
                  </span>
                )}
              </button>
            );
          })}
        </div>

        {/* Divider */}
        <div className="my-3 border-t border-gray-100 dark:border-gray-800/80" />

        {/* Campaigns section */}
        <div>
          <button
            onClick={() => onViewChange("campaigns")}
            className={cn(
              "mb-1 flex w-full items-center gap-2 rounded-lg px-2 py-2 text-[11px] font-semibold uppercase tracking-wider transition-colors",
              activeView === "campaigns" || activeView === "campaign-detail"
                ? "text-gray-900 dark:text-white"
                : "text-gray-400 hover:text-gray-600 dark:text-gray-500 dark:hover:text-gray-300",
            )}
          >
            Campaigns
          </button>

          {campaignItems.slice(1).map((item) => {
            const Icon = item.icon;
            const isActive = item.status
              ? activeStatusFilter === item.status
              : !activeStatusFilter;
            return (
              <button
                key={`${item.id}-${item.label}`}
                onClick={() =>
                  onViewChange("campaigns", undefined, item.status)
                }
                className={cn(
                  "mb-0.5 flex w-full items-center gap-2.5 rounded-lg px-2 py-2 text-[13px] font-medium transition-all duration-150",
                  isActive
                    ? "bg-indigo-600 text-white"
                    : "text-gray-500 hover:bg-gray-50 hover:text-gray-900 dark:text-gray-400 dark:hover:bg-gray-800/60 dark:hover:text-white",
                )}
              >
                <div className="flex h-4 w-4 items-center justify-center">
                  <Icon
                    className={cn(
                      "h-3.5 w-3.5",
                      isActive ? "opacity-100" : "opacity-60",
                    )}
                  />
                </div>
                <span className="flex-1 text-left text-[12px]">
                  {item.label}
                </span>
                {item.badge !== undefined && item.badge > 0 && (
                  <span
                    className={cn(
                      "flex h-5 min-w-[20px] items-center justify-center rounded-full px-1.5 text-[10px] font-semibold",
                      isActive
                        ? "bg-white/20 text-white"
                        : "bg-gray-100 text-gray-500 dark:bg-gray-800 dark:text-gray-400",
                    )}
                  >
                    {item.badge}
                  </span>
                )}
              </button>
            );
          })}
        </div>

        {/* Divider */}
        <div className="my-3 border-t border-gray-100 dark:border-gray-800/80" />

        {/* Stats */}
        <div className="rounded-lg bg-gray-50 px-3 py-3 dark:bg-gray-800/40">
          <div className="mb-2 flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wider text-gray-400">
            <TrendingUp className="h-3 w-3" />
            Stats
          </div>
          <div className="space-y-1.5">
            <div className="flex items-center justify-between text-[12px]">
              <span className="text-gray-500 dark:text-gray-400">Sent</span>
              <span className="font-semibold text-gray-700 dark:text-gray-200">
                {stats.totalSent.toLocaleString("id-ID")}
              </span>
            </div>
            <div className="flex items-center justify-between text-[12px]">
              <span className="text-gray-500 dark:text-gray-400">Replies</span>
              <span className="font-semibold text-gray-700 dark:text-gray-200">
                {inboxCount > 0 ? inboxCount.toLocaleString("id-ID") : "—"}
              </span>
            </div>
          </div>

          {/* Daily Quota */}
          {quota && (
            <>
              <div className="mt-3 border-t border-gray-200 dark:border-gray-700/50 pt-3">
                <div className="mb-1.5 flex items-center justify-between">
                  <span className="text-[11px] font-semibold uppercase tracking-wider text-gray-400">
                    Harian
                  </span>
                  {quota.is_exhausted && (
                    <span className="rounded bg-red-100 px-1.5 py-0.5 text-[10px] font-semibold text-red-600 dark:bg-red-900/40 dark:text-red-400">
                      Habis
                    </span>
                  )}
                </div>
                <div className="space-y-1">
                  <div className="flex items-center justify-between text-[12px]">
                    <span className="text-gray-500 dark:text-gray-400">
                      Terpakai
                    </span>
                    <span className="font-semibold text-gray-700 dark:text-gray-200">
                      {quota.sent_today.toLocaleString("id-ID")}
                    </span>
                  </div>
                  <div className="flex items-center justify-between text-[12px]">
                    <span className="text-gray-500 dark:text-gray-400">
                      Sisa
                    </span>
                    <span
                      className={cn(
                        "font-semibold",
                        quota.is_exhausted
                          ? "text-red-500"
                          : quota.remaining < quota.daily_limit * 0.2
                            ? "text-orange-500"
                            : "text-emerald-600 dark:text-emerald-400",
                      )}
                    >
                      {quota.remaining.toLocaleString("id-ID")}
                    </span>
                  </div>
                  {/* Progress bar */}
                  <div className="mt-1.5 h-1.5 w-full overflow-hidden rounded-full bg-gray-200 dark:bg-gray-700">
                    <div
                      className={cn(
                        "h-full rounded-full transition-all",
                        quota.is_exhausted
                          ? "bg-red-500"
                          : quota.sent_today / quota.daily_limit > 0.8
                            ? "bg-orange-400"
                            : "bg-emerald-500",
                      )}
                      style={{
                        width: `${Math.min(100, (quota.sent_today / quota.daily_limit) * 100)}%`,
                      }}
                    />
                  </div>
                  <div className="text-right text-[10px] text-gray-400">
                    dari {quota.daily_limit.toLocaleString("id-ID")}
                  </div>
                </div>
              </div>
            </>
          )}
        </div>

        {/* Settings */}
        <div className="mt-1">
          <button
            onClick={() => onViewChange("settings")}
            className={cn(
              "mb-0.5 flex w-full items-center gap-2.5 rounded-lg px-2 py-2 text-[13px] font-medium transition-all duration-150",
              activeView === "settings"
                ? "bg-indigo-600 text-white"
                : "text-gray-500 hover:bg-gray-50 hover:text-gray-900 dark:text-gray-400 dark:hover:bg-gray-800/60 dark:hover:text-white",
            )}
          >
            <Settings className="h-4 w-4 shrink-0" />
            Settings
          </button>
        </div>
      </nav>
    </aside>
  );
}

// ─── Main Page ────────────────────────────────────────────────────────────────

export default function EmailBlastPage() {
  const navigate = useNavigate();
  const params = useParams();
  const { hasPermission } = useAuth();
  const canManageBlast = hasPermission("blast.manage");

  const campaignIdFromUrl = params.id ? parseInt(params.id) : undefined;

  // Compute initial view from URL directly — no useEffect needed
  const getInitialView = (): View => {
    if (campaignIdFromUrl !== undefined) return "campaign-detail";
    const path = window.location.pathname;
    if (path.includes("/email-blast/inbox")) return "inbox";
    if (path.includes("/email-blast/sent")) return "sent";
    if (path.includes("/email-blast/settings")) return "settings";
    if (path.includes("/email-blast/letter-history")) return "letter-history";
    return "campaigns";
  };

  const [activeView, setActiveView] = useState<View>(getInitialView);
  const [activeCampaignId, setActiveCampaignId] = useState<number | undefined>(
    campaignIdFromUrl,
  );
  const [showCompose, setShowCompose] = useState(false);
  const [statusFilter, setStatusFilter] = useState("");

  usePageTour("email-blast", EMAIL_BLAST_TOUR_STEPS);

  // Sync state with URL when campaignIdFromUrl changes (navigating between campaigns)
  useEffect(() => {
    if (campaignIdFromUrl !== undefined) {
      setActiveView("campaign-detail");
      setActiveCampaignId(campaignIdFromUrl);
    }
  }, [campaignIdFromUrl]);

  // Stats
  const { data: allCampaigns } = useEmailBlastCampaigns();
  // Only fetch inbox when inbox view is active — avoids slow IMAP fetch on page load
  const { data: allInbox } = useAllInboxEmails(1000, activeView === "inbox");
  const { data: quota } = useEmailBlastQuota();

  const campaigns = allCampaigns?.campaigns ?? [];
  const inboxCount = allInbox?.emails?.length ?? 0;
  const totalSent = campaigns.reduce((acc, c) => acc + c.sent_count, 0);

  const campaignCounts = {
    draft: campaigns.filter((c) => c.status === "draft").length,
    running: campaigns.filter((c) => c.status === "running").length,
    paused: campaigns.filter((c) => c.status === "paused").length,
    completed: campaigns.filter((c) => c.status === "completed").length,
    cancelled: campaigns.filter((c) => c.status === "cancelled").length,
  };

  function handleViewChange(view: View, campaignId?: number, status?: string) {
    setActiveView(view);
    if (status !== undefined) {
      setStatusFilter(status);
    }
    if (campaignId === -1) {
      // New campaign
      setActiveCampaignId(undefined);
      setShowCompose(true);
    } else if (campaignId !== undefined) {
      setActiveCampaignId(campaignId);
      navigate(`/email-blast/campaigns/${campaignId}`);
    } else {
      setActiveCampaignId(undefined);
      if (view === "campaigns") navigate("/email-blast/campaigns");
      else if (view === "inbox") navigate("/email-blast/inbox");
      else if (view === "sent") navigate("/email-blast/sent");
      else if (view === "settings") navigate("/email-blast/settings");
      else if (view === "letter-history")
        navigate("/email-blast/letter-history");
    }
  }

  function handleCampaignSelect(campaign: EmailBlastCampaign) {
    setActiveCampaignId(campaign.id);
    setActiveView("campaign-detail");
    navigate(`/email-blast/campaigns/${campaign.id}`);
  }

  function handleNewCampaign() {
    setActiveCampaignId(undefined);
    setShowCompose(true);
    setActiveView("campaign-detail");
  }

  function handleComposeClose() {
    setShowCompose(false);
  }

  // Content area
  function renderContent() {
    if (activeView === "settings") {
      return <EmailSettingsPanel canManage={canManageBlast} />;
    }

    if (activeView === "letter-history") {
      return <EmailLetterHistory />;
    }

    if (activeView === "campaign-detail" || showCompose) {
      return (
        <EmailCampaignDetail
          campaignId={activeCampaignId}
          canManage={canManageBlast}
          onClose={() => {
            setShowCompose(false);
            setActiveCampaignId(undefined);
            setActiveView("campaigns");
            navigate("/email-blast/campaigns");
          }}
          onCompose={() => setShowCompose(true)}
        />
      );
    }

    if (activeView === "inbox") {
      return <EmailInboxView />;
    }

    if (activeView === "sent") {
      return <EmailSentView />;
    }

    // Default: campaigns
    return (
      <EmailCampaignList
        campaigns={campaigns}
        campaignCounts={campaignCounts}
        onSelect={handleCampaignSelect}
        onNew={handleNewCampaign}
        statusFilter={statusFilter}
        onStatusChange={setStatusFilter}
        canManage={canManageBlast}
      />
    );
  }

  return (
    <div className="flex h-full overflow-hidden bg-gray-50 dark:bg-gray-950">
      {/* Left Rail */}
      <div data-tour="email-left-rail">
        <EmailLeftRail
          activeView={activeView}
          onViewChange={handleViewChange}
          stats={{ totalSent }}
          campaignCounts={campaignCounts}
          inboxCount={inboxCount}
          sentCount={totalSent}
          activeStatusFilter={statusFilter}
          quota={quota}
        />
      </div>

      {/* Content Area */}
      <main data-tour="email-content" className="flex-1 overflow-hidden">
        {renderContent()}
      </main>
    </div>
  );
}
