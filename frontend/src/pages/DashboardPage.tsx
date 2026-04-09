import { Link } from "react-router-dom";
import { useState, useEffect, useRef } from "react";
import {
  Video,
  Building2,
  Phone,
  MessageSquare,
  CheckCircle,
  Lightbulb,
  ArrowRight,
  MapPin,
  Calendar,
} from "lucide-react";
import { useDashboard } from "../hooks/useDashboard";
import { usePipelineStatus } from "../hooks/usePipeline";
import { useLearningStats } from "../hooks/useLearning";
import { useAudiensiStats } from "../hooks/useAudiensi";
import { useDmsSchedules } from "../hooks/useDms";
import { usePageTour } from "../hooks/usePageTour";
import { DASHBOARD_TOUR_STEPS } from "../tours/dashboard.tour";
import { useAuth } from "../context/AuthContext";
import { Spinner } from "../components/ui/Spinner";
import { cn, formatNumber } from "../lib/utils";
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
    <div className="flex items-center gap-3 rounded-xl border border-gray-200 bg-white px-3 py-3 dark:border-gray-700 dark:bg-gray-800 sm:gap-4 sm:px-5 sm:py-4">
      <div
        className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-lg sm:h-11 sm:w-11 sm:rounded-xl ${accent ? "bg-indigo-50 dark:bg-indigo-950/50" : "bg-gray-50 dark:bg-gray-700"}`}
      >
        {icon}
      </div>
      <div className="min-w-0">
        <p className="text-lg font-bold text-gray-900 dark:text-white sm:text-2xl">
          {formatNumber(value)}
        </p>
        <p className="truncate text-xs font-medium text-gray-500 dark:text-gray-400">
          {label}
        </p>
        {sub && (
          <p className="hidden truncate text-[11px] text-gray-400 dark:text-gray-500 sm:block">
            {sub}
          </p>
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
              <div key={stage.key} className="flex items-center gap-2 sm:gap-3">
                <span className="w-16 shrink-0 text-xs font-medium text-gray-500 dark:text-gray-400 sm:w-24">
                  {stage.label}
                </span>
                <div className="h-6 flex-1 overflow-hidden rounded-md bg-gray-100 dark:bg-gray-700 sm:h-7">
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
      <div className="border-b border-gray-100 px-4 py-3 dark:border-gray-700 sm:px-5 sm:py-4">
        <h3 className="text-sm font-semibold text-gray-900 dark:text-white">
          Today's Quota
        </h3>
      </div>
      <div className="flex items-center gap-3 p-4 sm:gap-4 sm:p-5">
        <svg
          viewBox="0 0 72 72"
          className="h-[60px] w-[60px] shrink-0 -rotate-90 sm:h-[72px] sm:w-[72px]"
        >
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

// ─── Audiensi Schedule Card ────────────────────────────────────────────────
function AudiensiScheduleCard({
  queued,
  scheduled,
  completed,
}: {
  queued: number;
  scheduled: number;
  completed: number;
}) {
  const { data } = useDmsSchedules(30, 0);
  const todayStr = new Date().toDateString();

  const upcoming = (data?.schedules ?? [])
    .filter((s) => s.jadwal_audiensi)
    .sort(
      (a, b) =>
        new Date(a.jadwal_audiensi!).getTime() -
        new Date(b.jadwal_audiensi!).getTime(),
    )
    .slice(0, 5);

  return (
    <div className="overflow-hidden rounded-xl border border-gray-200 bg-white dark:border-gray-700 dark:bg-gray-800">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-gray-100 px-4 py-3 dark:border-gray-700">
        <div className="flex items-center gap-2">
          <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-gray-100 text-gray-500 dark:bg-gray-700 dark:text-gray-400">
            <Calendar className="h-4 w-4" />
          </div>
          <span className="text-xs font-semibold text-gray-700 dark:text-gray-200">
            Jadwal Audiensi
          </span>
        </div>
        <Link
          to="/dms"
          className="flex items-center gap-0.5 text-[10px] font-medium text-indigo-600 hover:text-indigo-800 dark:text-indigo-400"
        >
          Lihat Semua <ArrowRight className="h-3 w-3" />
        </Link>
      </div>

      {/* Stat numbers — compact 3-col grid */}
      <div className="grid grid-cols-3 divide-x divide-gray-100 border-b border-gray-100 dark:divide-gray-700 dark:border-gray-700">
        {[
          {
            label: "Antrian",
            value: queued,
            color: "text-amber-600 dark:text-amber-400",
          },
          {
            label: "Dijadwalkan",
            value: scheduled,
            color: "text-indigo-600 dark:text-indigo-400",
          },
          {
            label: "Selesai",
            value: completed,
            color: "text-emerald-600 dark:text-emerald-400",
          },
        ].map((s) => (
          <div key={s.label} className="py-2.5 text-center">
            <p className={`text-base font-bold ${s.color}`}>{s.value}</p>
            <p className="text-[10px] text-gray-400 dark:text-gray-500">
              {s.label}
            </p>
          </div>
        ))}
      </div>

      {/* Schedule list */}
      <div className="p-3">
        {upcoming.length === 0 ? (
          <p className="py-2 text-center text-xs text-gray-400 dark:text-gray-500">
            Tidak ada jadwal 30 hari ke depan
          </p>
        ) : (
          <div className="space-y-0.5">
            {upcoming.map((s) => {
              const date = s.jadwal_audiensi
                ? new Date(s.jadwal_audiensi)
                : null;
              const isToday = date?.toDateString() === todayStr;
              return (
                <Link
                  key={`${s.source}-${s.id}`}
                  to={`/dms/schedules/${s.id}?source=${s.source}`}
                  className="flex items-center gap-2 rounded-lg px-2 py-2 transition-colors hover:bg-gray-50 dark:hover:bg-gray-700/40"
                >
                  {/* Date */}
                  <div
                    className={cn(
                      "w-10 shrink-0 rounded-md py-1 text-center text-[10px] font-bold leading-tight",
                      isToday
                        ? "bg-indigo-100 text-indigo-700 dark:bg-indigo-900/40 dark:text-indigo-300"
                        : "bg-gray-100 text-gray-600 dark:bg-gray-700/60 dark:text-gray-300",
                    )}
                  >
                    {date
                      ? date.toLocaleDateString("id-ID", {
                          day: "2-digit",
                          month: "short",
                        })
                      : "—"}
                  </div>

                  {/* Name + time */}
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-xs font-medium text-gray-800 dark:text-gray-100">
                      {s.nama_universitas ?? "—"}
                    </p>
                    <p className="text-[10px] text-gray-400 dark:text-gray-500">
                      {s.jam_audensi
                        ? `${s.jam_audensi} WIB`
                        : isToday
                          ? "Hari ini"
                          : "\u00A0"}
                    </p>
                  </div>

                  {/* Icon only */}
                  {s.link_zoom ? (
                    <Video className="h-3.5 w-3.5 shrink-0 text-blue-400" />
                  ) : (
                    <MapPin className="h-3.5 w-3.5 shrink-0 text-gray-300 dark:text-gray-600" />
                  )}
                </Link>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}

// ─── Page ────────────────────────────────────────────────────────────────
const MOTIVATIONAL_MESSAGES = [
  (name: string) =>
    `☀️ Selamat datang, ${name}! Hari ini pasti lebih baik dari kemarin.`,
  (name: string) => `💪 Kamu bisa, ${name}! Mulai hari dengan semangat penuh.`,
  (name: string) => `🌟 Hai ${name}, kamu sudah luar biasa sampai sejauh ini!`,
  (name: string) => `🔥 Semangat, ${name}! Kerja kerasmu tidak akan sia-sia.`,
  (name: string) =>
    `✨ ${name}, setiap usaha kecil hari ini akan terasa besok.`,
  (name: string) => `🚀 Ayo ${name}, hari ini giliran kamu bersinar!`,
  (name: string) => `🎯 ${name}, tetap semangat — hasil terbaik menunggumu!`,
  (name: string) =>
    `💡 Ingat, ${name} — perjalanan jauh dimulai dari langkah pertama.`,
  (name: string) =>
    `🏆 ${name}, kamu lebih kuat dari tantangan apapun hari ini.`,
  (name: string) =>
    `🌈 Jangan lupa istirahat juga ya, ${name}. Kamu sudah bekerja keras!`,
  (name: string) =>
    `🎉 Selamat pagi, ${name}! Satu langkah hari ini, satu pencapaian besok.`,
  (name: string) =>
    `⚡ ${name}, energimu hari ini bisa mengubah banyak hal — mulai sekarang!`,
  (name: string) =>
    `🌿 Hai ${name}, tarik napas dalam-dalam. Kamu pasti bisa mengatasi ini.`,
  (name: string) =>
    `🎵 ${name}, ritme kerja yang konsisten lebih kuat dari sprint sesaat.`,
  (name: string) =>
    `🦁 Tunjukkan kepada dunia siapa ${name} hari ini — kamu luar biasa!`,
  (name: string) =>
    `🌙 Mau seberapa sibuk pun hari ini, ${name} pasti bisa melewatinya.`,
  (name: string) =>
    `🎨 Kreativitasmu hari ini bisa jadi terobosan besar, ${name}!`,
  (name: string) =>
    `🤝 ${name}, setiap koneksi yang kamu bangun hari ini adalah investasi masa depan.`,
  (name: string) =>
    `🌊 Ayo ${name}, hadapi setiap tantangan seperti ombak — dengan penuh percaya diri!`,
  (name: string) =>
    `☕ Sebelum mulai, tarik napas dulu ${name}. Hari ini punya banyak potensi.`,
  (name: string) =>
    `🔑 ${name}, kunci kesuksesan hari ini ada di tanganmu sendiri!`,
  (name: string) =>
    `🌺 Hai ${name}, bahkan progress kecil hari ini tetap progress. Terus maju!`,
  (name: string) =>
    `🛡️ ${name}, kamu sudah membuktikan dirimu berkali-kali. Hari ini pun bisa!`,
  (name: string) =>
    `🎖️ Kerja keras ${name} tidak luput dari perhatian — terus jaga konsistensinya!`,
  (name: string) =>
    `🌸 ${name}, jangan lupa apresiasi diri sendiri. Kamu sudah berjuang sejauh ini!`,
];

// ─── Motivational Card ───────────────────────────────────────────────────────
function MotiveCard({ msg, firstName }: { msg: string; firstName: string }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const textRef = useRef<HTMLParagraphElement>(null);
  const [overflow, setOverflow] = useState(0);

  useEffect(() => {
    const el = textRef.current;
    const container = containerRef.current;
    if (el && container && window.innerWidth < 640) {
      setOverflow(Math.max(0, el.scrollWidth - container.clientWidth));
    }
  }, []);

  const parts = msg.split(firstName);
  return (
    <div
      ref={containerRef}
      className="animate-fade-in overflow-hidden rounded-2xl border border-indigo-100 bg-indigo-50/70 px-4 py-2.5 shadow-sm dark:border-indigo-800/40 dark:bg-indigo-950/30 sm:px-5 sm:py-3"
    >
      <p
        ref={textRef}
        className="whitespace-nowrap text-sm text-indigo-600 dark:text-indigo-300 sm:text-base"
        style={
          overflow > 0
            ? ({
                "--marquee-offset": `-${overflow}px`,
                animation: "marqueeScroll 6s ease-in-out infinite",
              } as React.CSSProperties)
            : undefined
        }
      >
        {parts[0]}
        <span className="font-bold text-indigo-900 dark:text-indigo-100">
          {firstName}
        </span>
        {parts[1]}
      </p>
    </div>
  );
}

export default function DashboardPage() {
  const { data: stats, isLoading: statsLoading } = useDashboard();
  const { data: pipeline, isLoading: pipelineLoading } = usePipelineStatus();
  const { data: learningStats } = useLearningStats();
  const { data: audiensiStats } = useAudiensiStats();
  const { user } = useAuth();
  usePageTour("dashboard", DASHBOARD_TOUR_STEPS);

  const firstName = user?.name?.split(" ")[0] ?? "Kamu";
  const [msgIndex] = useState(() =>
    Math.floor(Math.random() * MOTIVATIONAL_MESSAGES.length),
  );

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
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">
            Dashboard
          </h1>
          <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
            DMS Marketing Outreach Overview
          </p>
        </div>
        <MotiveCard
          msg={MOTIVATIONAL_MESSAGES[msgIndex](firstName)}
          firstName={firstName}
        />
      </div>

      {/* Row 1: 4 Stat Cards */}
      <div
        data-tour="dashboard-stats"
        className="grid grid-cols-2 gap-3 sm:grid-cols-4 sm:gap-4"
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

      {/* Row 2: Pipeline + Quota/Overview */}
      <div className="grid gap-5 lg:grid-cols-3">
        {/* Pipeline */}
        <div data-tour="dashboard-pipeline-card" className="lg:col-span-2">
          <PipelineCard status={pipeline} />
        </div>

        {/* Right column — stacked on mobile, side-by-side on tablet, stacked again on desktop */}
        <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-1">
          <div data-tour="dashboard-quota-card">
            <QuotaCard stats={stats} />
          </div>
          <StatusCard stats={stats} />
        </div>
      </div>

      {/* Row 3: Audiensi schedule + Learning */}
      <div className="grid gap-5 md:grid-cols-2 lg:grid-cols-3">
        <div
          data-tour="dashboard-audiensi-card"
          className="md:col-span-1 lg:col-span-2"
        >
          <AudiensiScheduleCard
            queued={audiensiStats?.queued ?? 0}
            scheduled={audiensiStats?.scheduled ?? 0}
            completed={audiensiStats?.completed ?? 0}
          />
        </div>

        <AuxCard
          icon={<Lightbulb className="h-4 w-4" />}
          title="Learning"
          link="/learning"
        >
          <div className="grid grid-cols-2 gap-4">
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
