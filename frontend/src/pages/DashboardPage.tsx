import { Link } from "react-router-dom";
import {
  Video,
  Building2,
  Phone,
  MessageSquare,
  CheckCircle,
  Wifi,
  Bot,
  Lightbulb,
  ArrowRight,
} from "lucide-react";
import { useDashboard } from "../hooks/useDashboard";
import { usePipelineStatus } from "../hooks/usePipeline";
import { useLearningStats } from "../hooks/useLearning";
import { useAudiensiStats } from "../hooks/useAudiensi";
import { usePageTour } from "../hooks/usePageTour";
import { DASHBOARD_TOUR_STEPS } from "../tours/dashboard.tour";
import { Spinner } from "../components/ui/Spinner";
import { formatNumber } from "../lib/utils";
import type { DashboardStats } from "../lib/types";
import type { PipelineStatus } from "../lib/types";

// ─── Stat Card ───────────────────────────────────────────────────────────────
function StatCard({
  icon,
  label,
  value,
  sub,
  accent,
}: {
  icon: React.ReactNode;
  label: string;
  value: number;
  sub?: string;
  accent?: boolean;
}) {
  return (
    <div className="flex items-center gap-4 rounded-xl border border-gray-200 bg-white px-5 py-4 dark:border-gray-700 dark:bg-gray-800">
      <div
        className={`flex h-11 w-11 shrink-0 items-center justify-center rounded-xl ${accent ? "bg-indigo-50 dark:bg-indigo-950/50" : "bg-gray-50 dark:bg-gray-700"}`}
      >
        {icon}
      </div>
      <div>
        <p className="text-2xl font-bold text-gray-900 dark:text-white">
          {formatNumber(value)}
        </p>
        <p className="text-xs font-medium text-gray-500 dark:text-gray-400">
          {label}
        </p>
        {sub && (
          <p className="text-[11px] text-gray-400 dark:text-gray-500">{sub}</p>
        )}
      </div>
    </div>
  );
}

// ─── Pipeline Card ────────────────────────────────────────────────────────
function PipelineCard({ status }: { status: PipelineStatus }) {
  const stages = [
    { key: "pending", label: "Pending" },
    { key: "ig_found", label: "IG Found" },
    { key: "ig_scraped", label: "IG Scraped" },
    { key: "contacted", label: "Contacted" },
    { key: "got_number", label: "Got Number" },
  ];
  const maxCount = Math.max(
    ...stages.map(
      (s) => (status[s.key as keyof PipelineStatus] as number) || 0,
    ),
    1,
  );
  const total = stages.reduce(
    (s, st) => s + ((status[st.key as keyof PipelineStatus] as number) || 0),
    0,
  );

  return (
    <div className="rounded-xl border border-gray-200 bg-white dark:border-gray-700 dark:bg-gray-800">
      <div className="border-b border-gray-100 px-5 py-4 dark:border-gray-700">
        <h3 className="text-sm font-semibold text-gray-900 dark:text-white">
          Pipeline
        </h3>
        <p className="text-xs text-gray-500 dark:text-gray-400">
          {formatNumber(total)} total
        </p>
      </div>
      <div className="p-5">
        <div className="space-y-3">
          {stages.map((stage) => {
            const count =
              (status[stage.key as keyof PipelineStatus] as number) || 0;
            const pct = maxCount > 0 ? (count / maxCount) * 100 : 0;
            const isActive = stage.key === "got_number";
            return (
              <div key={stage.key} className="flex items-center gap-3">
                <span className="w-24 shrink-0 text-xs font-medium text-gray-500 dark:text-gray-400">
                  {stage.label}
                </span>
                <div className="flex-1 h-7 overflow-hidden rounded-md bg-gray-100 dark:bg-gray-700">
                  <div
                    className={`flex h-full items-center justify-end rounded-md px-2 transition-all duration-500 ${
                      isActive
                        ? "bg-indigo-500"
                        : "bg-indigo-100 dark:bg-indigo-950"
                    }`}
                    style={{ width: `${Math.max(pct, count > 0 ? 8 : 0)}%` }}
                  >
                    <span
                      className={`text-xs font-bold ${isActive ? "text-white" : "text-indigo-600 dark:text-indigo-300"}`}
                    >
                      {count > 0 ? formatNumber(count) : ""}
                    </span>
                  </div>
                </div>
                <span className="w-8 text-right text-xs text-gray-400 dark:text-gray-500">
                  {pct.toFixed(0)}%
                </span>
              </div>
            );
          })}
        </div>
        <div className="mt-4 flex items-center justify-between rounded-lg bg-gray-50 px-4 py-2.5 dark:bg-gray-700/50">
          <span className="text-xs text-gray-500 dark:text-gray-400">
            Failed
          </span>
          <span className="text-sm font-bold text-gray-700 dark:text-gray-200">
            {formatNumber(status.failed)}
          </span>
        </div>
      </div>
    </div>
  );
}

// ─── System Status Card ────────────────────────────────────────────────
function StatusCard({ stats }: { stats: DashboardStats }) {
  const items = [
    {
      icon: <Building2 className="h-4 w-4" />,
      label: "Universities",
      value: stats.total_universities,
    },
    {
      icon: <Phone className="h-4 w-4" />,
      label: "IG Contacts",
      value: stats.total_contacts,
    },
    {
      icon: <MessageSquare className="h-4 w-4" />,
      label: "Total Conv.",
      value: stats.total_conversations,
    },
    {
      icon: <CheckCircle className="h-4 w-4" />,
      label: "Got Numbers",
      value: stats.successful_conversations,
    },
  ];

  return (
    <div className="rounded-xl border border-gray-200 bg-white dark:border-gray-700 dark:bg-gray-800">
      <div className="border-b border-gray-100 px-5 py-4 dark:border-gray-700">
        <h3 className="text-sm font-semibold text-gray-900 dark:text-white">
          Overview
        </h3>
      </div>
      <div className="p-5">
        <div className="grid grid-cols-2 gap-4">
          {items.map((item) => (
            <div key={item.label} className="flex items-center gap-3">
              <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-indigo-50 text-indigo-600 dark:bg-indigo-950/50 dark:text-indigo-400">
                {item.icon}
              </div>
              <div>
                <p className="text-base font-bold text-gray-900 dark:text-white">
                  {formatNumber(item.value)}
                </p>
                <p className="text-[10px] text-gray-400 dark:text-gray-500">
                  {item.label}
                </p>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

// ─── Quota Card ──────────────────────────────────────────────────────────
function QuotaCard({ stats }: { stats: DashboardStats }) {
  const limit = stats.daily_conversation_limit || 20;
  const used = stats.today_conversations_started;
  const pct = Math.min((used / limit) * 100, 100);
  const remaining = Math.max(limit - used, 0);
  const r = 28;
  const c = 2 * Math.PI * r;
  const dashOffset = c - (pct / 100) * c;

  return (
    <div className="rounded-xl border border-gray-200 bg-white dark:border-gray-700 dark:bg-gray-800">
      <div className="border-b border-gray-100 px-5 py-4 dark:border-gray-700">
        <h3 className="text-sm font-semibold text-gray-900 dark:text-white">
          Today's Quota
        </h3>
      </div>
      <div className="flex items-center gap-4 p-5">
        <svg width="72" height="72" className="shrink-0 -rotate-90">
          <circle
            cx="36"
            cy="36"
            r={r}
            fill="none"
            stroke="currentColor"
            strokeWidth="4"
            className="text-gray-100 dark:text-gray-700"
          />
          <circle
            cx="36"
            cy="36"
            r={r}
            fill="none"
            stroke="#6366f1"
            strokeWidth="4"
            strokeLinecap="round"
            strokeDasharray={c}
            strokeDashoffset={dashOffset}
            className="transition-all duration-700"
          />
        </svg>
        <div className="flex-1 space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-xs text-gray-500 dark:text-gray-400">
              Used
            </span>
            <span className="text-sm font-bold text-gray-900 dark:text-white">
              {used}/{limit}
            </span>
          </div>
          <div className="flex items-center justify-between">
            <span className="text-xs text-gray-500 dark:text-gray-400">
              Remaining
            </span>
            <span className="text-sm font-bold text-indigo-600 dark:text-indigo-400">
              {remaining}
            </span>
          </div>
          <div className="flex items-center justify-between">
            <span className="text-xs text-gray-500 dark:text-gray-400">
              Messages
            </span>
            <span className="text-sm font-bold text-gray-900 dark:text-white">
              {formatNumber(stats.today_messages_sent)}
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}

// ─── Aux Card (Audiensi / Learning) ──────────────────────────────────
function AuxCard({
  icon,
  title,
  link,
  children,
}: {
  icon: React.ReactNode;
  title: string;
  link: string;
  children: React.ReactNode;
}) {
  return (
    <div className="rounded-xl border border-gray-200 bg-white dark:border-gray-700 dark:bg-gray-800">
      <div className="flex items-center justify-between border-b border-gray-100 px-5 py-3 dark:border-gray-700">
        <div className="flex items-center gap-2">
          <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-gray-100 text-gray-500 dark:bg-gray-700 dark:text-gray-400">
            {icon}
          </div>
          <span className="text-xs font-semibold text-gray-700 dark:text-gray-200">
            {title}
          </span>
        </div>
        <Link
          to={link}
          className="flex items-center gap-0.5 text-[10px] font-medium text-indigo-600 hover:text-indigo-800 dark:text-indigo-400"
        >
          View <ArrowRight className="h-3 w-3" />
        </Link>
      </div>
      <div className="p-4">{children}</div>
    </div>
  );
}

// ─── Page ────────────────────────────────────────────────────────────────
export default function DashboardPage() {
  const { data: stats, isLoading: statsLoading } = useDashboard();
  const { data: pipeline, isLoading: pipelineLoading } = usePipelineStatus();
  const { data: learningStats } = useLearningStats();
  const { data: audiensiStats } = useAudiensiStats();
  usePageTour("dashboard", DASHBOARD_TOUR_STEPS);

  if (statsLoading || pipelineLoading) {
    return (
      <div className="flex h-64 items-center justify-center">
        <Spinner size="lg" />
      </div>
    );
  }
  if (!stats || !pipeline) return null;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white">
          Dashboard
        </h1>
        <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
          DMS Marketing Outreach Overview
        </p>
      </div>

      {/* Row 1: 4 Stat Cards */}
      <div
        data-tour="dashboard-stats"
        className="grid grid-cols-2 gap-4 lg:grid-cols-4"
      >
        <StatCard
          icon={
            <Building2 className="h-5 w-5 text-indigo-600 dark:text-indigo-400" />
          }
          label="Universities"
          value={stats.total_universities}
          sub={`${formatNumber(stats.universities_with_ig)} with IG`}
          accent
        />
        <StatCard
          icon={
            <Phone className="h-5 w-5 text-indigo-600 dark:text-indigo-400" />
          }
          label="IG Contacts"
          value={stats.total_contacts}
          sub={`${formatNumber(stats.universities_with_phone)} with phones`}
        />
        <StatCard
          icon={
            <MessageSquare className="h-5 w-5 text-indigo-600 dark:text-indigo-400" />
          }
          label="Active Conv."
          value={stats.active_conversations}
          sub={`${formatNumber(stats.total_conversations)} total`}
        />
        <StatCard
          icon={
            <CheckCircle className="h-5 w-5 text-indigo-600 dark:text-indigo-400" />
          }
          label="Got Numbers"
          value={stats.successful_conversations}
          sub={`${((stats.successful_conversations / Math.max(stats.total_contacts, 1)) * 100).toFixed(1)}% of contacts`}
          accent
        />
      </div>

      {/* Row 2: 3 columns */}
      <div className="grid gap-5 lg:grid-cols-3">
        {/* Pipeline */}
        <div data-tour="dashboard-pipeline-card" className="lg:col-span-2">
          <PipelineCard status={pipeline} />
        </div>

        {/* Right column */}
        <div className="space-y-5">
          <div data-tour="dashboard-quota-card">
            <QuotaCard stats={stats} />
          </div>
          <StatusCard stats={stats} />
        </div>
      </div>

      {/* Row 3: Aux cards */}
      <div className="grid gap-5 lg:grid-cols-2">
        <div data-tour="dashboard-audiensi-card">
          <AuxCard
            icon={<Video className="h-4 w-4" />}
            title="Audiensi"
            link="/audiensi"
          >
            <div className="grid grid-cols-3 gap-4">
              <div>
                <p className="text-lg font-bold text-gray-900 dark:text-white">
                  {audiensiStats?.queued ?? 0}
                </p>
                <p className="text-[10px] text-gray-400 dark:text-gray-500">
                  Queued
                </p>
              </div>
              <div>
                <p className="text-lg font-bold text-gray-900 dark:text-white">
                  {audiensiStats?.scheduled ?? 0}
                </p>
                <p className="text-[10px] text-gray-400 dark:text-gray-500">
                  Scheduled
                </p>
              </div>
              <div>
                <p className="text-lg font-bold text-indigo-600 dark:text-indigo-400">
                  {audiensiStats?.completed ?? 0}
                </p>
                <p className="text-[10px] text-gray-400 dark:text-gray-500">
                  Completed
                </p>
              </div>
            </div>
          </AuxCard>
        </div>

        <AuxCard
          icon={<Lightbulb className="h-4 w-4" />}
          title="Learning"
          link="/learning"
        >
          <div className="grid grid-cols-3 gap-4">
            <div>
              <p className="text-lg font-bold text-gray-900 dark:text-white">
                {learningStats?.total_active_lessons ?? 0}
              </p>
              <p className="text-[10px] text-gray-400 dark:text-gray-500">
                Active Lessons
              </p>
            </div>
            <div>
              <p className="text-lg font-bold text-gray-900 dark:text-white">
                {learningStats?.unprocessed_analyses ?? 0}
              </p>
              <p className="text-[10px] text-gray-400 dark:text-gray-500">
                Pending
              </p>
            </div>
          </div>
        </AuxCard>
      </div>
    </div>
  );
}
