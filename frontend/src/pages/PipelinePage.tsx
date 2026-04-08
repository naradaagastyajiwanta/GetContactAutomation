import { useState } from "react";
import {
  Download,
  Phone,
  Users,
  User,
  Search,
  GraduationCap,
  Loader2,
  CheckCircle,
  XCircle,
  ChevronDown,
  ChevronUp,
  Clock,
  Timer,
  Play,
  Zap,
  Square,
  RotateCcw,
} from "lucide-react";
import {
  usePipelineStatus,
  usePipelineLogs,
  useTriggerFindHandles,
  useTriggerDiscoverBem,
  useTriggerScrapePosts,
  useTriggerExtractPhones,
  useTriggerFindRectors,
  useTriggerCollectUniversities,
  usePauseBot,
  useResumeBot,
  useProvinces,
} from "../hooks/usePipeline";
import { useControlStatus } from "../hooks/useControl";
import { Spinner } from "../components/ui/Spinner";
import { Select } from "../components/ui/Select";
import { Button } from "../components/ui/Button";
import { useAuth } from "../context/AuthContext";
import { formatNumber } from "../lib/utils";
import type {
  PipelineStatus,
  PipelineLog,
  PipelineAgentType,
  PipelineLogStatus,
} from "../lib/types";
import { usePageTour } from "../hooks/usePageTour";
import { PIPELINE_TOUR_STEPS } from "../tours/pipeline.tour";

// ─── Helpers ─────────────────────────────────────────────────────────────────

const STAGE_KEYS = [
  "pending",
  "ig_found",
  "bem_discovered",
  "ig_scraped",
  "contacted",
  "got_number",
] as const;
const STAGE_LABELS: Record<string, string> = {
  pending: "Pending",
  ig_found: "IG Found",
  bem_discovered: "BEM Found",
  ig_scraped: "IG Scraped",
  contacted: "Contacted",
  got_number: "Got Number",
};

const STAGE_ACCENT: Record<string, boolean> = {
  pending: false,
  ig_found: false,
  bem_discovered: false,
  ig_scraped: false,
  contacted: false,
  got_number: true,
};

const STATUS_COLOR: Record<PipelineLogStatus, string> = {
  running: "text-blue-500",
  completed: "text-emerald-500",
  failed: "text-red-500",
};

const AGENT_COLOR: Record<string, string> = {
  find_handles:
    "bg-blue-50 text-blue-700 dark:bg-blue-950/50 dark:text-blue-300",
  scrape_posts:
    "bg-purple-50 text-purple-700 dark:bg-purple-950/50 dark:text-purple-300",
  extract_phones:
    "bg-green-50 text-green-700 dark:bg-green-950/50 dark:text-green-300",
  collect_universities:
    "bg-amber-50 text-amber-700 dark:bg-amber-950/50 dark:text-amber-300",
  discover_bem:
    "bg-teal-50 text-teal-700 dark:bg-teal-950/50 dark:text-teal-300",
  dms_research:
    "bg-violet-50 text-violet-700 dark:bg-violet-950/50 dark:text-violet-300",
};

const AGENT_LABEL: Record<string, string> = {
  find_handles: "Find IG Handles",
  scrape_posts: "Scrape IG Posts",
  extract_phones: "Extract Phones",
  collect_universities: "Collect Universities",
  discover_bem: "Discover BEM",
  dms_research: "Research Rector",
};

function formatTime(iso: string) {
  try {
    const d = new Date(iso);
    return d.toLocaleString("id-ID", {
      day: "2-digit",
      month: "short",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return iso;
  }
}

function formatDur(s: number | null) {
  if (s == null) return "-";
  return s < 60
    ? `${s.toFixed(0)}s`
    : `${Math.floor(s / 60)}m ${(s % 60).toFixed(0)}s`;
}

// ─── Stage stat pill ──────────────────────────────────────────────────────────
function StageStat({
  stageKey,
  count,
  maxCount,
  accent,
}: {
  stageKey: string;
  count: number;
  maxCount: number;
  accent?: boolean;
}) {
  const pct = maxCount > 0 ? (count / maxCount) * 100 : 0;
  return (
    <div className="flex flex-1 flex-col rounded-xl border border-gray-100 bg-white px-4 py-3 dark:border-gray-700 dark:bg-gray-800">
      <span className="text-[10px] font-semibold uppercase tracking-wide text-gray-400 dark:text-gray-500">
        {STAGE_LABELS[stageKey]}
      </span>
      <span
        className={`mt-1 text-2xl font-bold ${accent ? "text-indigo-600 dark:text-indigo-400" : "text-gray-900 dark:text-white"}`}
      >
        {formatNumber(count)}
      </span>
      <div className="mt-2 h-1 w-full overflow-hidden rounded-full bg-gray-100 dark:bg-gray-700">
        <div
          className={`h-full rounded-full transition-all ${accent ? "bg-indigo-500" : "bg-gray-300 dark:bg-gray-600"}`}
          style={{ width: `${Math.max(pct, count > 0 ? 6 : 0)}%` }}
        />
      </div>
    </div>
  );
}

// ─── Agent trigger card ──────────────────────────────────────────────────────
function AgentCard({
  title,
  description,
  icon,
  onClick,
  loading,
  disabled,
}: {
  title: string;
  description: string;
  icon: React.ReactNode;
  onClick: () => void;
  loading: boolean;
  disabled?: boolean;
}) {
  return (
    <button
      onClick={onClick}
      disabled={loading || disabled}
      className="group flex items-center gap-3 rounded-xl border border-gray-100 bg-white px-4 py-3 text-left transition-all hover:border-indigo-200 hover:shadow-sm disabled:opacity-50 dark:border-gray-700 dark:bg-gray-800 dark:hover:border-indigo-800"
    >
      <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-indigo-50 text-indigo-600 transition-colors group-hover:bg-indigo-100 dark:bg-indigo-950/50 dark:text-indigo-400 dark:group-hover:bg-indigo-900/50">
        {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : icon}
      </div>
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-semibold text-gray-900 dark:text-white">
          {title}
        </p>
        <p className="truncate text-[11px] text-gray-400 dark:text-gray-500">
          {description}
        </p>
      </div>
      <Play className="h-4 w-4 shrink-0 text-indigo-400 opacity-0 transition-opacity group-hover:opacity-100" />
    </button>
  );
}

// ─── PDDIKTI trigger ──────────────────────────────────────────────────────────
function PddiktiCard({
  onTrigger,
  loading,
  disabled,
}: {
  onTrigger: (province: string | undefined) => void;
  loading: boolean;
  disabled?: boolean;
}) {
  const [province, setProvince] = useState("");
  const { data: provinces } = useProvinces();
  const options = [
    { value: "", label: "All Provinces" },
    ...(provinces ?? []).map((p) => ({ value: p, label: p })),
  ];

  return (
    <div className="group flex flex-col gap-2 rounded-xl border border-gray-100 bg-white px-4 py-3 dark:border-gray-700 dark:bg-gray-800">
      <div className="flex items-center gap-3">
        <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-amber-50 text-amber-600 dark:bg-amber-950/50 dark:text-amber-400">
          <GraduationCap className="h-4 w-4" />
        </div>
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-semibold text-gray-900 dark:text-white">
            Collect Universities
          </p>
          <p className="truncate text-[11px] text-gray-400 dark:text-gray-500">
            {province ? `Province: ${province}` : "From PDDIKTI"}
          </p>
        </div>
        <button
          onClick={() => onTrigger(province || undefined)}
          disabled={loading || disabled}
          className="flex shrink-0 items-center gap-1 rounded-lg bg-amber-500 px-3 py-1.5 text-xs font-semibold text-white transition-colors hover:bg-amber-600 disabled:opacity-50"
        >
          {loading ? (
            <Loader2 className="h-3 w-3 animate-spin" />
          ) : (
            <Zap className="h-3 w-3" />
          )}
          Collect
        </button>
      </div>
      <Select
        value={province}
        onChange={(v) => setProvince(v)}
        options={options}
        className="h-7 w-full text-xs"
      />
    </div>
  );
}

// ─── Log row ─────────────────────────────────────────────────────────────────
function LogRow({ log }: { log: PipelineLog }) {
  const [expanded, setExpanded] = useState(false);
  const hasDetails =
    (log.details?.length ?? 0) > 0 ||
    !!log.error ||
    Object.keys(log.summary ?? {}).length > 0;

  return (
    <div className="border-b border-gray-50 last:border-0 dark:border-gray-800">
      <div
        className={`flex cursor-pointer items-center gap-3 px-4 py-2.5 transition-colors hover:bg-gray-50 dark:hover:bg-gray-800/40 ${!hasDetails ? "cursor-default" : ""}`}
        onClick={() => hasDetails && setExpanded((v) => !v)}
      >
        {log.status === "running" ? (
          <Loader2
            className={`h-4 w-4 ${STATUS_COLOR.running} animate-spin shrink-0`}
          />
        ) : log.status === "completed" ? (
          <CheckCircle
            className={`h-4 w-4 ${STATUS_COLOR.completed} shrink-0`}
          />
        ) : (
          <XCircle className={`h-4 w-4 ${STATUS_COLOR.failed} shrink-0`} />
        )}
        <span
          className={`shrink-0 rounded-full px-2 py-0.5 text-[10px] font-semibold ${AGENT_COLOR[log.agent_type] || "bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-300"}`}
        >
          {AGENT_LABEL[log.agent_type] || log.agent_type}
        </span>
        {log.status !== "running" && (
          <span className="text-[11px] text-gray-400 dark:text-gray-500">
            {formatNumber(log.items_processed)} processed
            {log.items_success > 0 && (
              <span className="ml-1.5 text-emerald-500">
                ✓{formatNumber(log.items_success)}
              </span>
            )}
            {log.items_failed > 0 && (
              <span className="ml-1.5 text-red-500">
                ✗{formatNumber(log.items_failed)}
              </span>
            )}
          </span>
        )}
        <div className="flex-1" />
        {log.duration_seconds != null && (
          <span className="flex items-center gap-1 text-[11px] text-gray-400 dark:text-gray-500">
            <Timer className="h-3 w-3" />
            {formatDur(log.duration_seconds)}
          </span>
        )}
        <span className="text-[11px] text-gray-400 dark:text-gray-500">
          {formatTime(log.started_at)}
        </span>
        {hasDetails && (
          <div className="text-gray-400">
            {expanded ? (
              <ChevronUp className="h-4 w-4" />
            ) : (
              <ChevronDown className="h-4 w-4" />
            )}
          </div>
        )}
      </div>

      {expanded && (
        <div className="border-t border-gray-100 bg-gray-50 px-4 py-3 dark:border-gray-800 dark:bg-gray-800/50">
          {Object.keys(log.summary ?? {}).length > 0 && (
            <div className="mb-2 flex flex-wrap gap-1.5">
              {Object.entries(log.summary ?? {}).map(([k, v]) => (
                <span
                  key={k}
                  className="rounded-md bg-white px-2 py-0.5 text-[11px] dark:bg-gray-700"
                >
                  <span className="text-gray-400">
                    {k.replace(/_/g, " ")}:{" "}
                  </span>
                  <span className="font-semibold text-gray-700 dark:text-gray-200">
                    {String(v)}
                  </span>
                </span>
              ))}
            </div>
          )}
          {log.error && (
            <div className="mb-2 rounded-md bg-red-50 p-2 text-[11px] text-red-700 dark:bg-red-950/30 dark:text-red-300">
              <span className="font-semibold">Error: </span>
              {log.error}
            </div>
          )}
          {log.details && log.details.length > 0 && (
            <div className="max-h-40 overflow-auto rounded-md border border-gray-200 dark:border-gray-700">
              <table className="w-full text-left text-[11px]">
                <thead className="bg-gray-100 dark:bg-gray-700">
                  <tr>
                    {Object.keys(log.details[0]).map((k) => (
                      <th
                        key={k}
                        className="px-3 py-1.5 font-medium text-gray-400"
                      >
                        {k.replace(/_/g, " ")}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-50 dark:divide-gray-800">
                  {log.details.map((item, i) => (
                    <tr
                      key={i}
                      className="hover:bg-gray-50 dark:hover:bg-gray-800/50"
                    >
                      {Object.values(item).map((val, j) => (
                        <td
                          key={j}
                          className="px-3 py-1.5 text-gray-600 dark:text-gray-300"
                        >
                          {typeof val === "object"
                            ? JSON.stringify(val)
                            : String(val ?? "-")}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ─── Page ─────────────────────────────────────────────────────────────────────
const AGENT_FILTER_OPTIONS = [
  { value: "", label: "All Agents" },
  { value: "find_handles", label: "Find IG Handles" },
  { value: "scrape_posts", label: "Scrape IG Posts" },
  { value: "extract_phones", label: "Extract Phones" },
  { value: "collect_universities", label: "Collect Universities" },
  { value: "discover_bem", label: "Discover BEM" },
  { value: "dms_research", label: "Research Rector" },
];

export default function PipelinePage() {
  const { hasPermission } = useAuth();
  const { data: status, isLoading: statusLoading } = usePipelineStatus();
  const [logFilter, setLogFilter] = useState("");
  const [logPage, setLogPage] = useState(0);
  const PAGE_SIZE = 20;

  const { data: logData, isLoading: logLoading } = usePipelineLogs({
    agent_type: logFilter || undefined,
    limit: PAGE_SIZE,
    offset: logPage * PAGE_SIZE,
  });

  const findHandles = useTriggerFindHandles();
  const discoverBem = useTriggerDiscoverBem();
  const scrapePosts = useTriggerScrapePosts();
  const extractPhones = useTriggerExtractPhones();
  const findRectors = useTriggerFindRectors();
  const collectUniv = useTriggerCollectUniversities();
  const pauseBot = usePauseBot();
  const resumeBot = useResumeBot();
  const { data: controlStatus } = useControlStatus();

  const isBotPaused = controlStatus?.paused ?? false;
  const canRunPipeline = hasPermission("pipeline.run");
  const canManagePipeline = hasPermission("pipeline.manage");
  usePageTour("pipeline", PIPELINE_TOUR_STEPS);

  if (statusLoading)
    return (
      <div className="flex h-64 items-center justify-center">
        <Spinner size="lg" />
      </div>
    );
  if (!status) return null;

  const logs = logData?.items ?? [];
  const logTotal = logData?.total ?? 0;
  const logPages = Math.ceil(logTotal / PAGE_SIZE);
  const total = STAGE_KEYS.reduce(
    (s, k) => s + ((status[k as keyof PipelineStatus] as number) || 0),
    0,
  );
  const maxCount = Math.max(
    ...STAGE_KEYS.map(
      (k) => (status[k as keyof PipelineStatus] as number) || 0,
    ),
    1,
  );

  return (
    <div className="space-y-6">
      {/* Page header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">
            Pipeline
          </h1>
          <p className="mt-0.5 text-sm text-gray-500 dark:text-gray-400">
            {formatNumber(total)} universities &middot;{" "}
            <span className="text-indigo-600 dark:text-indigo-400">
              {formatNumber(status.got_number || 0)} converted
            </span>
          </p>
        </div>
        <div className="flex items-center gap-2">
          {canManagePipeline && isBotPaused ? (
            <button
              onClick={() => resumeBot.mutate()}
              disabled={resumeBot.isPending}
              className="flex h-8 items-center gap-1.5 rounded-full bg-emerald-50 px-3 text-xs font-medium text-emerald-600 transition-colors hover:bg-emerald-100 disabled:opacity-50 dark:bg-emerald-950/30 dark:text-emerald-400 dark:hover:bg-emerald-900/30"
            >
              {resumeBot.isPending ? (
                <Loader2 className="h-3 w-3 animate-spin" />
              ) : (
                <RotateCcw className="h-3 w-3" />
              )}
              {resumeBot.isPending ? "Resuming..." : "Resume Pipeline"}
            </button>
          ) : canManagePipeline ? (
            <button
              onClick={() => pauseBot.mutate()}
              disabled={pauseBot.isPending}
              className="flex h-8 items-center gap-1.5 rounded-full bg-red-50 px-3 text-xs font-medium text-red-600 transition-colors hover:bg-red-100 disabled:opacity-50 dark:bg-red-950/30 dark:text-red-400 dark:hover:bg-red-900/30"
            >
              {pauseBot.isPending ? (
                <Loader2 className="h-3 w-3 animate-spin" />
              ) : (
                <Square className="h-3 w-3 fill-current" />
              )}
              {pauseBot.isPending ? "Stopping..." : "Stop Pipeline"}
            </button>
          ) : null}
          <div className="flex h-8 items-center gap-1.5 rounded-full bg-emerald-50 px-3 dark:bg-emerald-950/30">
            <div className="h-2 w-2 rounded-full bg-emerald-400 animate-pulse" />
            <span className="text-xs font-medium text-emerald-600 dark:text-emerald-400">
              Live
            </span>
          </div>
        </div>
      </div>

      {/* Stage overview — horizontal pill row */}
      <div
        data-tour="pipeline-stage-stats"
        className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6"
      >
        {STAGE_KEYS.map((k) => (
          <StageStat
            key={k}
            stageKey={k}
            count={(status[k as keyof PipelineStatus] as number) || 0}
            maxCount={maxCount}
            accent={STAGE_ACCENT[k]}
          />
        ))}
        {/* Failed — standalone accent */}
        <div className="flex flex-col rounded-xl border border-red-100 bg-red-50 px-4 py-3 dark:border-red-900/40 dark:bg-red-950/20">
          <span className="text-[10px] font-semibold uppercase tracking-wide text-red-400">
            Failed
          </span>
          <span className="mt-1 text-2xl font-bold text-red-600 dark:text-red-400">
            {formatNumber(status.failed || 0)}
          </span>
        </div>
      </div>

      {/* Trigger agents */}
      <div data-tour="pipeline-agents">
        <div className="mb-3 flex items-center justify-between gap-3">
          <p className="text-xs font-semibold uppercase tracking-wide text-gray-400 dark:text-gray-500">
            Trigger Agents
          </p>
          {!canRunPipeline && (
            <span className="text-xs text-amber-600 dark:text-amber-300">
              Menjalankan agent membutuhkan permission pipeline.run.
            </span>
          )}
        </div>
        <div className="grid gap-3 sm:grid-cols-3 lg:grid-cols-6">
          <PddiktiCard
            onTrigger={(province) =>
              collectUniv.mutate({ province, limit: undefined })
            }
            loading={collectUniv.isPending}
            disabled={!canRunPipeline}
          />
          <AgentCard
            title="Find IG Handles"
            description="Search IG handles"
            icon={<Search className="h-4 w-4" />}
            onClick={() => findHandles.mutate(50)}
            loading={findHandles.isPending}
            disabled={!canRunPipeline}
          />
          <AgentCard
            title="Discover BEM"
            description="Find BEM accounts"
            icon={<Users className="h-4 w-4" />}
            onClick={() => discoverBem.mutate(30)}
            loading={discoverBem.isPending}
            disabled={!canRunPipeline}
          />
          <AgentCard
            title="Scrape IG Posts"
            description="Scrape posts from IG"
            icon={<Download className="h-4 w-4" />}
            onClick={() => scrapePosts.mutate(20)}
            loading={scrapePosts.isPending}
            disabled={!canRunPipeline}
          />
          <AgentCard
            title="Extract Phones"
            description="Extract phones from posts"
            icon={<Phone className="h-4 w-4" />}
            onClick={() => extractPhones.mutate(50)}
            loading={extractPhones.isPending}
            disabled={!canRunPipeline}
          />
          <AgentCard
            title="Find Rectors"
            description="Find rector names"
            icon={<User className="h-4 w-4" />}
            onClick={() => findRectors.mutate(20)}
            loading={findRectors.isPending}
            disabled={!canRunPipeline}
          />
        </div>
      </div>

      {/* Activity log */}
      <div
        data-tour="pipeline-activity-log"
        className="rounded-xl border border-gray-200 bg-white dark:border-gray-700 dark:bg-gray-800"
      >
        {/* Header */}
        <div className="flex items-center justify-between border-b border-gray-100 px-5 py-3 dark:border-gray-700">
          <div className="flex items-center gap-2">
            <Clock className="h-4 w-4 text-gray-400" />
            <span className="text-sm font-semibold text-gray-900 dark:text-white">
              Activity Log
            </span>
            <span className="rounded-full bg-gray-100 px-2 py-0.5 text-[10px] font-medium text-gray-500 dark:bg-gray-700 dark:text-gray-400">
              {formatNumber(logTotal)}
            </span>
          </div>
          <Select
            value={logFilter}
            onChange={(v) => {
              setLogFilter(v);
              setLogPage(0);
            }}
            options={AGENT_FILTER_OPTIONS}
            className="h-7 w-44 text-xs"
          />
        </div>

        {/* Rows */}
        {logLoading ? (
          <div className="flex items-center justify-center py-10">
            <Loader2 className="h-5 w-5 animate-spin text-gray-400" />
          </div>
        ) : logs.length === 0 ? (
          <div className="py-10 text-center text-sm text-gray-400 dark:text-gray-500">
            No pipeline runs yet. Trigger an agent above to get started.
          </div>
        ) : (
          <div className="divide-y divide-gray-50 dark:divide-gray-800">
            {logs.map((log) => (
              <LogRow key={log.id} log={log} />
            ))}
          </div>
        )}

        {/* Pagination */}
        {logPages > 1 && (
          <div className="flex items-center justify-between border-t border-gray-100 px-5 py-2.5 dark:border-gray-700">
            <span className="text-xs text-gray-400 dark:text-gray-500">
              Page {logPage + 1} of {logPages}
            </span>
            <div className="flex gap-2">
              <button
                onClick={() => setLogPage(Math.max(0, logPage - 1))}
                disabled={logPage === 0}
                className="rounded-lg border border-gray-200 bg-white px-3 py-1 text-xs font-medium text-gray-600 hover:bg-gray-50 disabled:opacity-40 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-300"
              >
                Prev
              </button>
              <button
                onClick={() => setLogPage(Math.min(logPages - 1, logPage + 1))}
                disabled={logPage >= logPages - 1}
                className="rounded-lg border border-gray-200 bg-white px-3 py-1 text-xs font-medium text-gray-600 hover:bg-gray-50 disabled:opacity-40 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-300"
              >
                Next
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
