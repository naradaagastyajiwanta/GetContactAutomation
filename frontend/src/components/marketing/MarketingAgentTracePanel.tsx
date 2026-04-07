import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  ChevronDown,
  ChevronUp,
  Globe,
  Instagram,
  Database,
  Sparkles,
  Bot,
  CheckCircle2,
  XCircle,
  Clock,
} from "lucide-react";
import { getClientOrchestrationRuns } from "../../api/marketing";
import { Spinner } from "../ui/Spinner";

// Map agent names to icons and colors
const AGENT_CONFIG: Record<
  string,
  { label: string; icon: React.ElementType; color: string }
> = {
  spawn_web_search_agent: {
    label: "Web Search",
    icon: Globe,
    color: "text-blue-500",
  },
  spawn_instagram_agent: {
    label: "Instagram",
    icon: Instagram,
    color: "text-pink-500",
  },
  spawn_registry_agent: {
    label: "Registry",
    icon: Database,
    color: "text-purple-500",
  },
  spawn_gemini_agent: {
    label: "Gemini AI",
    icon: Sparkles,
    color: "text-yellow-500",
  },
};

function formatDuration(seconds: number | null): string {
  if (!seconds) return "";
  if (seconds < 60) return `${Math.round(seconds)}s`;
  return `${Math.floor(seconds / 60)}m ${Math.round(seconds % 60)}s`;
}

interface AgentTracePanelProps {
  clientId: number;
}

export function MarketingAgentTracePanel({ clientId }: AgentTracePanelProps) {
  const [isOpen, setIsOpen] = useState(false);

  const { data: runs, isLoading } = useQuery({
    queryKey: ["marketingRuns", clientId],
    queryFn: () => getClientOrchestrationRuns(clientId),
    enabled: isOpen, // lazy load — only fetch when opened
    staleTime: 30_000,
  });

  const latestRun = runs?.[0];
  const subAgentCalls =
    latestRun?.summary?.sub_agent_calls ??
    latestRun?.plan?.sub_agent_calls ??
    [];
  const isAgentMode = latestRun?.summary?.agent_mode ?? false;
  const totalContacts = latestRun?.summary?.contacts_found ?? 0;
  const totalTokens = latestRun?.summary?.total_tokens ?? 0;
  const duration = latestRun?.duration_seconds;
  const agentSummary =
    latestRun?.summary?.summary ?? latestRun?.error_message ?? "";

  if (!isOpen) {
    return (
      <button
        onClick={() => setIsOpen(true)}
        className="flex items-center gap-1.5 text-xs text-indigo-600 dark:text-indigo-400 hover:text-indigo-800 dark:hover:text-indigo-200 transition-colors"
      >
        <Bot className="h-3.5 w-3.5" />
        <span>Lihat AI Agent Trace</span>
        <ChevronDown className="h-3 w-3" />
      </button>
    );
  }

  return (
    <div className="mt-2 rounded-lg border border-indigo-200 dark:border-indigo-800 bg-indigo-50 dark:bg-indigo-950/30 p-3">
      {/* Header */}
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <Bot className="h-4 w-4 text-indigo-600 dark:text-indigo-400" />
          <span className="text-sm font-medium text-indigo-700 dark:text-indigo-300">
            AI Agent Trace
          </span>
          {isAgentMode && (
            <span className="text-xs bg-indigo-100 dark:bg-indigo-900 text-indigo-600 dark:text-indigo-400 px-2 py-0.5 rounded-full">
              GPT-5 Orchestrated
            </span>
          )}
          {duration && (
            <span className="text-xs text-gray-500 flex items-center gap-1">
              <Clock className="h-3 w-3" /> {formatDuration(duration)}
            </span>
          )}
        </div>
        <button
          onClick={() => setIsOpen(false)}
          className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-200"
        >
          <ChevronUp className="h-4 w-4" />
        </button>
      </div>

      {/* Loading */}
      {isLoading && (
        <div className="flex items-center gap-2 py-2">
          <Spinner className="h-4 w-4" />
          <span className="text-xs text-gray-500">Memuat trace...</span>
        </div>
      )}

      {/* No runs */}
      {!isLoading && !latestRun && (
        <p className="text-xs text-gray-500 dark:text-gray-400">
          Belum ada run.
        </p>
      )}

      {/* Sub-agent timeline */}
      {!isLoading && subAgentCalls.length > 0 && (
        <div className="space-y-1.5 mb-2">
          {subAgentCalls.map((call, idx) => {
            const config = AGENT_CONFIG[call.agent] ?? {
              label: call.agent,
              icon: Bot,
              color: "text-gray-500",
            };
            const Icon = config.icon;
            return (
              <div key={idx} className="flex items-start gap-2 text-xs">
                <Icon
                  className={`h-3.5 w-3.5 mt-0.5 flex-shrink-0 ${config.color}`}
                />
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-1.5 flex-wrap">
                    <span className="font-medium text-gray-700 dark:text-gray-300">
                      {config.label}
                    </span>
                    {call.contacts_found > 0 ? (
                      <span className="flex items-center gap-0.5 text-green-600 dark:text-green-400">
                        <CheckCircle2 className="h-3 w-3" />
                        {call.contacts_found} kontak
                      </span>
                    ) : (
                      <span className="flex items-center gap-0.5 text-gray-400">
                        <XCircle className="h-3 w-3" />0 kontak
                      </span>
                    )}
                    {call.ig_handle && (
                      <span className="text-pink-500">@{call.ig_handle}</span>
                    )}
                    {call.duration_seconds > 0 && (
                      <span className="text-gray-400">
                        {formatDuration(call.duration_seconds)}
                      </span>
                    )}
                  </div>
                  <p className="text-gray-500 dark:text-gray-400 truncate">
                    {call.summary}
                  </p>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Summary */}
      {agentSummary && (
        <div className="border-t border-indigo-200 dark:border-indigo-700 pt-2 mt-1">
          <p className="text-xs text-gray-600 dark:text-gray-300">
            {agentSummary}
          </p>
        </div>
      )}

      {/* Footer stats */}
      {(totalContacts > 0 || totalTokens > 0) && (
        <div className="flex gap-3 mt-2 text-xs text-gray-400 dark:text-gray-500">
          {totalContacts > 0 && <span>{totalContacts} kontak tersimpan</span>}
          {totalTokens > 0 && (
            <span>{(totalTokens / 1000).toFixed(1)}K tokens</span>
          )}
        </div>
      )}
    </div>
  );
}
