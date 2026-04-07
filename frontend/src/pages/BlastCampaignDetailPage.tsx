/**
 * BlastCampaignDetailPage — Edit campaign template, manage recipients, configure
 * sending settings, preview messages, and start/pause/cancel the blast.
 */

import { useState, useRef, useCallback, useMemo, useEffect } from "react";
import { useParams, useNavigate, Link } from "react-router-dom";
import {
  ArrowLeft,
  Megaphone,
  Save,
  Play,
  Pause,
  XCircle,
  Trash2,
  Plus,
  Search,
  Users,
  Eye,
  Settings2,
  MessageSquareText,
  Loader2,
  CheckCircle2,
  AlertCircle,
  Send,
  Clock,
  Phone,
  User,
  GraduationCap,
  X,
  ChevronDown,
  ChevronUp,
  Smartphone,
  Timer,
  Zap,
} from "lucide-react";
import { cn } from "../lib/utils";
import {
  useBlastCampaign,
  useUpdateCampaign,
  useBlastRecipients,
  useAddRecipients,
  useRemoveRecipient,
  useClearRecipients,
  useBlastPreview,
  useBlastContacts,
  useStartCampaign,
  usePauseCampaign,
  useCancelCampaign,
  useDeleteCampaign,
} from "../hooks/useBlast";
import { useMyDevices } from "../hooks/useWhatsApp";
import type {
  BlastContact,
  BlastContactsParams,
  PreviouslyBlastedContact,
} from "../api/blast";
import { checkPreviouslyBlasted } from "../api/blast";
import { useUniversityGroups } from "../hooks/useUniversityGroups";
import { QuickSelectGroups } from "../components/universityGroups/QuickSelectGroups";
import { useAuth } from "../context/AuthContext";

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

const recipientStatusStyle: Record<
  string,
  { color: string; bg: string; icon: React.ElementType }
> = {
  pending: {
    color: "text-gray-500",
    bg: "bg-gray-100 dark:bg-gray-700",
    icon: Clock,
  },
  sent: {
    color: "text-green-600",
    bg: "bg-green-50 dark:bg-green-900/30",
    icon: CheckCircle2,
  },
  failed: {
    color: "text-red-500",
    bg: "bg-red-50 dark:bg-red-900/30",
    icon: AlertCircle,
  },
  skipped: {
    color: "text-amber-500",
    bg: "bg-amber-50 dark:bg-amber-900/30",
    icon: XCircle,
  },
};

function RecipientStatusBadge({ status }: { status: string }) {
  const cfg = recipientStatusStyle[status] || recipientStatusStyle.pending;
  const Icon = cfg.icon;
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[11px] font-medium",
        cfg.bg,
        cfg.color,
      )}
    >
      <Icon className="w-3 h-3" />
      {status}
    </span>
  );
}

function SummaryStat({
  label,
  value,
  hint,
}: {
  label: string;
  value: string;
  hint: string;
}) {
  return (
    <div className="rounded-2xl border border-gray-200 bg-gray-50 px-4 py-3 dark:border-gray-700 dark:bg-gray-900/40">
      <p className="text-[11px] uppercase tracking-[0.18em] text-gray-400 dark:text-gray-500">
        {label}
      </p>
      <p className="mt-1 text-lg font-semibold text-gray-900 dark:text-gray-100">
        {value}
      </p>
      <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">{hint}</p>
    </div>
  );
}

function WorkflowCard({
  step,
  title,
  description,
  ready,
  icon: Icon,
}: {
  step: string;
  title: string;
  description: string;
  ready: boolean;
  icon: React.ElementType;
}) {
  return (
    <div
      className={cn(
        "rounded-2xl border px-4 py-3 transition-colors",
        ready
          ? "border-emerald-200 bg-emerald-50 dark:border-emerald-900/60 dark:bg-emerald-950/20"
          : "border-gray-200 bg-white/90 dark:border-gray-700 dark:bg-gray-900/50",
      )}
    >
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-gray-400 dark:text-gray-500">
            {step}
          </p>
          <p className="mt-1 text-sm font-semibold text-gray-900 dark:text-gray-100">
            {title}
          </p>
        </div>
        <span
          className={cn(
            "inline-flex h-9 w-9 items-center justify-center rounded-xl border",
            ready
              ? "border-emerald-200 bg-emerald-100 text-emerald-600 dark:border-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-300"
              : "border-gray-200 bg-gray-50 text-gray-400 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-500",
          )}
        >
          <Icon className="h-4 w-4" />
        </span>
      </div>
      <p className="mt-2 text-xs leading-5 text-gray-500 dark:text-gray-400">
        {description}
      </p>
      <div className="mt-3">
        <span
          className={cn(
            "inline-flex items-center gap-1 rounded-full px-2 py-1 text-[11px] font-medium",
            ready
              ? "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300"
              : "bg-gray-100 text-gray-500 dark:bg-gray-800 dark:text-gray-400",
          )}
        >
          {ready ? (
            <CheckCircle2 className="h-3.5 w-3.5" />
          ) : (
            <Clock className="h-3.5 w-3.5" />
          )}
          {ready ? "Ready" : "Needs attention"}
        </span>
      </div>
    </div>
  );
}

function SettingHintCard({
  title,
  description,
  value,
}: {
  title: string;
  description: string;
  value: string;
}) {
  return (
    <div className="rounded-2xl border border-gray-200 bg-gray-50 px-4 py-3 dark:border-gray-700 dark:bg-gray-900/40">
      <p className="text-xs font-semibold text-gray-700 dark:text-gray-200">
        {title}
      </p>
      <p className="mt-1 text-[11px] leading-5 text-gray-500 dark:text-gray-400">
        {description}
      </p>
      <p className="mt-2 text-xs font-medium text-indigo-600 dark:text-indigo-300">
        {value}
      </p>
    </div>
  );
}

function formatDelayLabel(ms: number): string {
  if (ms < 1000) return `${ms}ms`;
  const seconds = ms / 1000;
  return Number.isInteger(seconds) ? `${seconds}s` : `${seconds.toFixed(1)}s`;
}

// ---------------------------------------------------------------------------
// Contact Selector Modal
// ---------------------------------------------------------------------------

const PAGE_SIZE = 100;

function ContactSelectorModal({
  campaignId,
  onClose,
}: {
  campaignId: number;
  onClose: () => void;
}) {
  const [searchQuery, setSearchQuery] = useState("");
  const [filters, setFilters] = useState<BlastContactsParams>({
    limit: PAGE_SIZE,
    has_name: true,
  });
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());
  const [selectedGroupIds, setSelectedGroupIds] = useState<Set<number>>(
    new Set(),
  );
  const [page, setPage] = useState(0);
  const [checking, setChecking] = useState(false);
  const [duplicates, setDuplicates] = useState<
    PreviouslyBlastedContact[] | null
  >(null);
  const [excludedIds, setExcludedIds] = useState<Set<number>>(new Set());

  const { data: groupsData } = useUniversityGroups();

  const debouncedSearch = useMemo(() => {
    return searchQuery.trim() || undefined;
  }, [searchQuery]);

  const queryParams = useMemo<BlastContactsParams>(
    () => ({
      ...filters,
      search: debouncedSearch,
      limit: PAGE_SIZE,
      offset: page * PAGE_SIZE,
    }),
    [filters, debouncedSearch, page],
  );

  const { data, isLoading } = useBlastContacts(queryParams, true);
  const addMutation = useAddRecipients();
  const contacts = data?.data || [];
  const totalContacts = data?.total ?? 0;
  const totalPages = Math.max(1, Math.ceil(totalContacts / PAGE_SIZE));

  const toggleContact = (id: number) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const toggleAll = () => {
    const pageIds = contacts.map((c) => c.contact_id);
    const allPageSelected =
      pageIds.length > 0 && pageIds.every((id) => selectedIds.has(id));
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (allPageSelected) {
        pageIds.forEach((id) => next.delete(id));
      } else {
        pageIds.forEach((id) => next.add(id));
      }
      return next;
    });
  };

  const handleAdd = async () => {
    if (selectedIds.size === 0 && selectedGroupIds.size === 0) return;

    if (selectedGroupIds.size > 0 && selectedIds.size === 0) {
      addMutation.mutate(
        { campaignId, group_ids: Array.from(selectedGroupIds) },
        { onSuccess: () => onClose() },
      );
      return;
    }

    setChecking(true);
    try {
      const result = await checkPreviouslyBlasted({
        contact_ids: Array.from(selectedIds),
      });
      if (result.previously_blasted.length > 0) {
        setDuplicates(result.previously_blasted);
        setExcludedIds(new Set());
      } else {
        addMutation.mutate(
          {
            campaignId,
            contact_ids: Array.from(selectedIds),
            group_ids:
              selectedGroupIds.size > 0
                ? Array.from(selectedGroupIds)
                : undefined,
          },
          { onSuccess: () => onClose() },
        );
      }
    } catch {
      addMutation.mutate(
        {
          campaignId,
          contact_ids: Array.from(selectedIds),
          group_ids:
            selectedGroupIds.size > 0
              ? Array.from(selectedGroupIds)
              : undefined,
        },
        { onSuccess: () => onClose() },
      );
    } finally {
      setChecking(false);
    }
  };

  const handleConfirmAdd = () => {
    const finalIds = Array.from(selectedIds).filter(
      (id) => !excludedIds.has(id),
    );
    if (finalIds.length === 0 && selectedGroupIds.size === 0) {
      setDuplicates(null);
      return;
    }

    addMutation.mutate(
      {
        campaignId,
        contact_ids: finalIds.length > 0 ? finalIds : undefined,
        group_ids:
          selectedGroupIds.size > 0 ? Array.from(selectedGroupIds) : undefined,
      },
      {
        onSuccess: () => {
          setDuplicates(null);
          onClose();
        },
      },
    );
  };

  const toggleExclude = (id: number) => {
    setExcludedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm p-4">
      <div className="relative bg-white dark:bg-gray-800 rounded-2xl shadow-2xl w-full max-w-2xl max-h-[85vh] flex flex-col">
        <div className="flex items-center justify-between p-4 border-b border-gray-200 dark:border-gray-700">
          <div className="flex items-center gap-2">
            <Users className="w-5 h-5 text-indigo-500" />
            <h2 className="text-base font-semibold text-gray-900 dark:text-gray-100">
              Select Contacts
            </h2>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700 text-gray-400 transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="p-4 border-b border-gray-100 dark:border-gray-700 space-y-3">
          {groupsData && groupsData.groups.length > 0 && (
            <QuickSelectGroups
              groups={groupsData.groups}
              selectedGroupIds={selectedGroupIds}
              onToggle={(groupId) => {
                setSelectedGroupIds((prev) => {
                  const next = new Set(prev);
                  if (next.has(groupId)) next.delete(groupId);
                  else next.add(groupId);
                  return next;
                });
              }}
            />
          )}

          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => {
                setSearchQuery(e.target.value);
                setPage(0);
              }}
              placeholder="Search university or contact name..."
              className="w-full pl-9 pr-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg text-sm dark:bg-gray-900 dark:text-gray-100 focus:ring-1 focus:ring-indigo-500 focus:border-indigo-500"
            />
          </div>

          <div className="flex flex-wrap gap-2">
            <FilterChip
              label="Has Name"
              active={filters.has_name === true}
              onClick={() => {
                setFilters((f) => ({
                  ...f,
                  has_name: f.has_name ? undefined : true,
                }));
                setPage(0);
              }}
            />
            <FilterChip
              label="Not Contacted"
              active={filters.contacted === false}
              onClick={() => {
                setFilters((f) => ({
                  ...f,
                  contacted: f.contacted === false ? undefined : false,
                }));
                setPage(0);
              }}
            />
            <FilterChip
              label="Contacted"
              active={filters.contacted === true}
              onClick={() => {
                setFilters((f) => ({
                  ...f,
                  contacted: f.contacted ? undefined : true,
                }));
                setPage(0);
              }}
            />
            <FilterChip
              label="Has Conversation"
              active={filters.has_conversation === true}
              onClick={() => {
                setFilters((f) => ({
                  ...f,
                  has_conversation: f.has_conversation ? undefined : true,
                }));
                setPage(0);
              }}
            />
          </div>
        </div>

        <div className="flex-1 overflow-y-auto">
          {isLoading ? (
            <div className="flex items-center justify-center py-12">
              <Loader2 className="w-5 h-5 animate-spin text-gray-400" />
            </div>
          ) : contacts.length === 0 ? (
            <div className="text-center py-12 text-gray-400 text-sm">
              No contacts found
            </div>
          ) : (
            <div>
              <div
                className="sticky top-0 z-10 flex items-center gap-3 px-4 py-2 bg-gray-50 dark:bg-gray-750 border-b border-gray-200 dark:border-gray-700 text-xs font-medium text-gray-500 dark:text-gray-400 cursor-pointer hover:bg-gray-100 dark:hover:bg-gray-700"
                onClick={toggleAll}
              >
                <input
                  type="checkbox"
                  checked={
                    contacts.length > 0 &&
                    contacts.every((contact) =>
                      selectedIds.has(contact.contact_id),
                    )
                  }
                  readOnly
                  className="h-3.5 w-3.5 rounded border-gray-300 text-indigo-600 focus:ring-indigo-500"
                />
                <span>
                  {contacts.length > 0 &&
                  contacts.every((contact) =>
                    selectedIds.has(contact.contact_id),
                  )
                    ? `Deselect page (${contacts.length})`
                    : `Select page (${contacts.length})`}
                  {selectedIds.size > 0 &&
                    ` · ${selectedIds.size} total selected`}
                </span>
              </div>

              {contacts.map((contact) => (
                <div
                  key={contact.contact_id}
                  onClick={() => toggleContact(contact.contact_id)}
                  className={cn(
                    "flex items-center gap-3 px-4 py-2.5 border-b border-gray-100 dark:border-gray-700/50 cursor-pointer transition-colors",
                    selectedIds.has(contact.contact_id)
                      ? "bg-indigo-50 dark:bg-indigo-900/20"
                      : "hover:bg-gray-50 dark:hover:bg-gray-800",
                  )}
                >
                  <input
                    type="checkbox"
                    checked={selectedIds.has(contact.contact_id)}
                    readOnly
                    className="h-3.5 w-3.5 rounded border-gray-300 text-indigo-600 focus:ring-indigo-500"
                  />
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-medium text-gray-900 dark:text-gray-100 truncate">
                        {contact.contact_name || contact.phone_number}
                      </span>
                      {contact.has_person_name ? (
                        <span className="text-[10px] px-1.5 py-0.5 rounded bg-green-100 dark:bg-green-900/30 text-green-600 dark:text-green-400">
                          Named
                        </span>
                      ) : null}
                    </div>
                    <div className="flex items-center gap-3 text-[11px] text-gray-500 dark:text-gray-400 mt-0.5">
                      <span className="flex items-center gap-1">
                        <Phone className="w-3 h-3" />
                        {contact.phone_number}
                      </span>
                      <span className="flex items-center gap-1 truncate">
                        <GraduationCap className="w-3 h-3" />
                        {contact.university_name || "Unknown"}
                      </span>
                      {contact.province && <span>{contact.province}</span>}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {totalContacts > PAGE_SIZE && (
          <div className="flex items-center justify-between px-4 py-2.5 border-t border-gray-100 dark:border-gray-700 bg-white dark:bg-gray-800 text-xs">
            <span className="text-gray-500 dark:text-gray-400">
              Showing {page * PAGE_SIZE + 1}–
              {Math.min((page + 1) * PAGE_SIZE, totalContacts)} of{" "}
              {totalContacts}
            </span>
            <div className="flex items-center gap-1">
              <button
                onClick={() => setPage((current) => Math.max(0, current - 1))}
                disabled={page === 0}
                className="px-2.5 py-1 rounded-md text-xs font-medium border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
              >
                Prev
              </button>
              {(() => {
                const pages: number[] = [];
                const maxVisible = 5;
                let start = Math.max(0, page - Math.floor(maxVisible / 2));
                const end = Math.min(totalPages, start + maxVisible);
                if (end - start < maxVisible)
                  start = Math.max(0, end - maxVisible);
                for (let index = start; index < end; index++) pages.push(index);
                return pages.map((pageIndex) => (
                  <button
                    key={pageIndex}
                    onClick={() => setPage(pageIndex)}
                    className={cn(
                      "w-7 h-7 rounded-md text-xs font-medium transition-colors",
                      pageIndex === page
                        ? "bg-indigo-600 text-white"
                        : "text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-700",
                    )}
                  >
                    {pageIndex + 1}
                  </button>
                ));
              })()}
              <button
                onClick={() =>
                  setPage((current) => Math.min(totalPages - 1, current + 1))
                }
                disabled={page >= totalPages - 1}
                className="px-2.5 py-1 rounded-md text-xs font-medium border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
              >
                Next
              </button>
            </div>
          </div>
        )}

        <div className="flex items-center justify-between p-4 border-t border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800/50">
          <span className="text-sm text-gray-500 dark:text-gray-400">
            {selectedIds.size} selected{data?.total ? ` of ${data.total}` : ""}
          </span>
          <div className="flex gap-2">
            <button
              onClick={onClose}
              className="px-4 py-2 text-sm text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-100 transition-colors"
            >
              Cancel
            </button>
            <button
              onClick={handleAdd}
              disabled={
                (selectedIds.size === 0 && selectedGroupIds.size === 0) ||
                addMutation.isPending ||
                checking
              }
              className="flex items-center gap-1.5 px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white text-sm font-semibold rounded-lg disabled:opacity-50 transition-colors"
            >
              {addMutation.isPending || checking ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                <Plus className="w-4 h-4" />
              )}
              {checking
                ? "Checking..."
                : selectedGroupIds.size > 0 && selectedIds.size === 0
                  ? `Add ${selectedGroupIds.size} Group${selectedGroupIds.size > 1 ? "s" : ""}`
                  : `Add ${selectedIds.size} Contacts${selectedGroupIds.size > 0 ? ` + ${selectedGroupIds.size} Group${selectedGroupIds.size > 1 ? "s" : ""}` : ""}`}
            </button>
          </div>
        </div>

        {duplicates && duplicates.length > 0 && (
          <div className="absolute inset-0 z-10 flex items-center justify-center bg-black/30 backdrop-blur-[2px] rounded-2xl">
            <div className="bg-white dark:bg-gray-800 rounded-xl shadow-2xl w-full max-w-lg mx-4 max-h-[70vh] flex flex-col border border-amber-200 dark:border-amber-700">
              <div className="flex items-center gap-3 p-4 border-b border-amber-100 dark:border-amber-800 bg-amber-50 dark:bg-amber-900/20 rounded-t-xl">
                <div className="p-2 rounded-full bg-amber-100 dark:bg-amber-900/40">
                  <AlertCircle className="w-5 h-5 text-amber-600 dark:text-amber-400" />
                </div>
                <div>
                  <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100">
                    {duplicates.length} contact
                    {duplicates.length > 1 ? "s" : ""} previously blasted
                  </h3>
                  <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
                    These contacts have been sent messages in previous
                    campaigns. Uncheck to exclude them.
                  </p>
                </div>
              </div>

              <div className="flex-1 overflow-y-auto divide-y divide-gray-100 dark:divide-gray-700">
                {duplicates.map((duplicate) => (
                  <label
                    key={duplicate.contact_id}
                    className={cn(
                      "flex items-start gap-3 px-4 py-3 cursor-pointer transition-colors",
                      excludedIds.has(duplicate.contact_id)
                        ? "bg-gray-50 dark:bg-gray-800/50 opacity-60"
                        : "hover:bg-amber-50/50 dark:hover:bg-amber-900/10",
                    )}
                  >
                    <input
                      type="checkbox"
                      checked={!excludedIds.has(duplicate.contact_id)}
                      onChange={() => toggleExclude(duplicate.contact_id)}
                      className="mt-0.5 h-4 w-4 rounded border-gray-300 text-indigo-600 focus:ring-indigo-500"
                    />
                    <div className="flex-1 min-w-0">
                      <div className="text-sm font-medium text-gray-900 dark:text-gray-100 truncate">
                        {duplicate.contact_name || duplicate.phone_number}
                      </div>
                      <div className="flex flex-wrap items-center gap-x-3 gap-y-0.5 mt-0.5 text-[11px] text-gray-500 dark:text-gray-400">
                        <span className="flex items-center gap-1">
                          <Phone className="w-3 h-3" /> {duplicate.phone_number}
                        </span>
                        {duplicate.university_name && (
                          <span className="flex items-center gap-1">
                            <GraduationCap className="w-3 h-3" />{" "}
                            {duplicate.university_name}
                          </span>
                        )}
                      </div>
                      <div className="mt-1 text-[10px] text-amber-600 dark:text-amber-400">
                        Blasted in "{duplicate.campaign_name}"
                        {duplicate.sent_at
                          ? ` on ${new Date(duplicate.sent_at).toLocaleDateString()}`
                          : ""}
                      </div>
                    </div>
                  </label>
                ))}
              </div>

              <div className="flex items-center justify-between p-4 border-t border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800/50 rounded-b-xl">
                <span className="text-xs text-gray-500 dark:text-gray-400">
                  {excludedIds.size > 0 && (
                    <span className="text-amber-600 dark:text-amber-400 font-medium">
                      {excludedIds.size} excluded ·{" "}
                    </span>
                  )}
                  {selectedIds.size - excludedIds.size} will be added
                  {selectedGroupIds.size > 0 &&
                    ` + ${selectedGroupIds.size} group(s)`}
                </span>
                <div className="flex gap-2">
                  <button
                    onClick={() => setDuplicates(null)}
                    className="px-3 py-1.5 text-xs text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-100 transition-colors"
                  >
                    Back
                  </button>
                  <button
                    onClick={handleConfirmAdd}
                    disabled={
                      selectedIds.size - excludedIds.size === 0 ||
                      addMutation.isPending
                    }
                    className="flex items-center gap-1.5 px-3 py-1.5 bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-semibold rounded-lg disabled:opacity-50 transition-colors"
                  >
                    {addMutation.isPending ? (
                      <Loader2 className="w-3.5 h-3.5 animate-spin" />
                    ) : (
                      <CheckCircle2 className="w-3.5 h-3.5" />
                    )}
                    Confirm Add {selectedIds.size - excludedIds.size} Contacts
                  </button>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function FilterChip({
  label,
  active,
  onClick,
}: {
  label: string;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className={cn(
        "px-2.5 py-1 rounded-full text-xs font-medium transition-colors border",
        active
          ? "bg-indigo-100 dark:bg-indigo-900/40 text-indigo-700 dark:text-indigo-300 border-indigo-300 dark:border-indigo-700"
          : "bg-white dark:bg-gray-800 text-gray-500 dark:text-gray-400 border-gray-200 dark:border-gray-700 hover:border-gray-300 dark:hover:border-gray-600",
      )}
    >
      {label}
    </button>
  );
}

// ---------------------------------------------------------------------------
// Template Placeholder Buttons
// ---------------------------------------------------------------------------

const PLACEHOLDERS = [
  { key: "{nama_universitas}", label: "University", icon: GraduationCap },
  { key: "{nama_kontak}", label: "Contact", icon: User },
  { key: "{nomor_telepon}", label: "Phone", icon: Phone },
];

// ---------------------------------------------------------------------------
// Main Page
// ---------------------------------------------------------------------------

export default function BlastCampaignDetailPage() {
  const { hasPermission } = useAuth();
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const campaignId = Number(id);
  const canManageBlast = hasPermission("blast.manage");

  // Campaign data
  const { data: campaign, isLoading: loadingCampaign } = useBlastCampaign(
    campaignId,
    !!id,
  );
  const isDraft = campaign?.status === "draft";
  const isSending = campaign?.status === "sending";
  const isPaused = campaign?.status === "paused";
  const isFinished =
    campaign?.status === "completed" || campaign?.status === "cancelled";
  const canEditCampaign = canManageBlast && (isDraft || isPaused);

  // Recipients
  const [recipientPage, setRecipientPage] = useState(0);
  const RECIPIENTS_PER_PAGE = 50;
  const { data: recipientsData, isLoading: loadingRecipients } =
    useBlastRecipients(
      campaignId,
      {
        limit: RECIPIENTS_PER_PAGE,
        offset: recipientPage * RECIPIENTS_PER_PAGE,
      },
      !!id,
    );
  const recipients = recipientsData?.data || [];
  const totalRecipients = recipientsData?.total || 0;

  // Preview
  const { data: previewData } = useBlastPreview(
    campaignId,
    !!id && !!campaign?.template_message,
  );

  // Devices — only user's own devices
  const { data: myDevicesData } = useMyDevices();
  const myDevices = (myDevicesData?.devices || []).map((e) => ({
    id: e.device_id,
    name: e.label || e.device?.name || e.device_id,
    phoneNumber: e.device?.phoneNumber ?? null,
    connectionState: e.device?.connectionState ?? "disconnected",
  }));
  const connectedDevices = myDevices.filter(
    (d) => d.connectionState === "connected",
  );

  // Mutations
  const updateMutation = useUpdateCampaign();
  const addMutation = useAddRecipients();
  const removeMutation = useRemoveRecipient();
  const clearMutation = useClearRecipients();
  const startMutation = useStartCampaign();
  const pauseMutation = usePauseCampaign();
  const cancelMutation = useCancelCampaign();
  const deleteMutation = useDeleteCampaign();

  // Local form state
  const [templateDraft, setTemplateDraft] = useState<string | null>(null);
  const [deviceDraft, setDeviceDraft] = useState<string | null>(null);
  const [delayDraft, setDelayDraft] = useState<number | null>(null);
  const [humanMinDraft, setHumanMinDraft] = useState<number | null>(null);
  const [humanMaxDraft, setHumanMaxDraft] = useState<number | null>(null);
  const [variationDraft, setVariationDraft] = useState<boolean | null>(null);
  const [scheduleEnabledDraft, setScheduleEnabledDraft] = useState<
    boolean | null
  >(null);
  const [scheduleTimezoneDraft, setScheduleTimezoneDraft] = useState<
    string | null
  >(null);
  const [activeStartDraft, setActiveStartDraft] = useState<number | null>(null);
  const [activeEndDraft, setActiveEndDraft] = useState<number | null>(null);
  const [peakStartDraft, setPeakStartDraft] = useState<number | null>(null);
  const [peakEndDraft, setPeakEndDraft] = useState<number | null>(null);
  const [lunchStartDraft, setLunchStartDraft] = useState<number | null>(null);
  const [lunchEndDraft, setLunchEndDraft] = useState<number | null>(null);
  const [weekendFactorDraft, setWeekendFactorDraft] = useState<number | null>(
    null,
  );
  const [autoResumeDraft, setAutoResumeDraft] = useState<boolean | null>(null);
  const templateRef = useRef<HTMLTextAreaElement>(null);

  // Derived values (draft state overrides server value)
  const currentTemplate = templateDraft ?? campaign?.template_message ?? "";
  const currentDevice = deviceDraft ?? campaign?.device_id ?? "";
  const currentDelay = delayDraft ?? campaign?.delay_between_ms ?? 5000;
  const currentHumanMin = humanMinDraft ?? campaign?.human_delay_min_ms ?? 2000;
  const currentHumanMax = humanMaxDraft ?? campaign?.human_delay_max_ms ?? 8000;
  const currentVariationEnabled =
    variationDraft ?? Boolean(campaign?.content_variation_enabled ?? true);
  const currentScheduleEnabled =
    scheduleEnabledDraft ?? Boolean(campaign?.schedule_enabled ?? true);
  const currentScheduleTimezone =
    scheduleTimezoneDraft ?? campaign?.schedule_timezone ?? "Asia/Jakarta";
  const currentActiveStart =
    activeStartDraft ?? campaign?.active_hours_start ?? 8;
  const currentActiveEnd = activeEndDraft ?? campaign?.active_hours_end ?? 21;
  const currentPeakStart = peakStartDraft ?? campaign?.peak_hours_start ?? 10;
  const currentPeakEnd = peakEndDraft ?? campaign?.peak_hours_end ?? 14;
  const currentLunchStart =
    lunchStartDraft ?? campaign?.lunch_break_start ?? 12;
  const currentLunchEnd = lunchEndDraft ?? campaign?.lunch_break_end ?? 13;
  const currentWeekendFactor =
    weekendFactorDraft ?? campaign?.weekend_factor ?? 0.5;
  const currentAutoResumeEnabled =
    autoResumeDraft ?? Boolean(campaign?.auto_resume_enabled ?? true);
  const campaignSentCount = campaign?.sent_count ?? 0;
  const campaignFailedCount = campaign?.failed_count ?? 0;
  const selectedDeviceDetails = myDevices.find(
    (device) => device.id === currentDevice,
  );
  const selectedDeviceConnected =
    selectedDeviceDetails?.connectionState === "connected";
  const templateReady = currentTemplate.trim().length > 0;
  const recipientReady = totalRecipients > 0;
  const deviceReady = Boolean(selectedDeviceConnected);
  const campaignReady = templateReady && recipientReady && deviceReady;
  const pendingCount = Math.max(
    0,
    totalRecipients - campaignSentCount - campaignFailedCount,
  );
  const namedRecipientCount = recipients.filter((recipient) =>
    Boolean(recipient.contact_name),
  ).length;
  const templateCharacterCount = currentTemplate.trim().length;
  const primaryPreview = previewData?.previews?.[0] ?? null;

  // Auto-select device: if the campaign's stored device_id is not in the user's
  // device list (e.g., old "device_1" default, or device belonging to another user),
  // auto-select the first connected device, then first any device.
  useEffect(() => {
    if (deviceDraft !== null) return; // user already made a choice this session
    if (!myDevicesData || myDevices.length === 0) return;
    const storedId = campaign?.device_id ?? "";
    const inList = myDevices.some((d) => d.id === storedId);
    if (inList) return; // stored device is valid — nothing to do
    const firstConnected = myDevices.find(
      (d) => d.connectionState === "connected",
    );
    const autoId = firstConnected?.id ?? myDevices[0]?.id ?? "";
    if (autoId) setDeviceDraft(autoId);
  }, [myDevicesData, campaign?.device_id, deviceDraft]);

  // Contact selector modal
  const [showContactModal, setShowContactModal] = useState(false);

  // Sections toggle
  const [showSettings, setShowSettings] = useState(true);
  const [showPreview, setShowPreview] = useState(false);

  // Check if there are unsaved changes
  const hasUnsavedChanges =
    (templateDraft !== null && templateDraft !== campaign?.template_message) ||
    (deviceDraft !== null && deviceDraft !== campaign?.device_id) ||
    (delayDraft !== null && delayDraft !== campaign?.delay_between_ms) ||
    (humanMinDraft !== null &&
      humanMinDraft !== campaign?.human_delay_min_ms) ||
    (humanMaxDraft !== null &&
      humanMaxDraft !== campaign?.human_delay_max_ms) ||
    (variationDraft !== null &&
      variationDraft !==
        Boolean(campaign?.content_variation_enabled ?? true)) ||
    (scheduleEnabledDraft !== null &&
      scheduleEnabledDraft !== Boolean(campaign?.schedule_enabled ?? true)) ||
    (scheduleTimezoneDraft !== null &&
      scheduleTimezoneDraft !==
        (campaign?.schedule_timezone ?? "Asia/Jakarta")) ||
    (activeStartDraft !== null &&
      activeStartDraft !== campaign?.active_hours_start) ||
    (activeEndDraft !== null &&
      activeEndDraft !== campaign?.active_hours_end) ||
    (peakStartDraft !== null &&
      peakStartDraft !== campaign?.peak_hours_start) ||
    (peakEndDraft !== null && peakEndDraft !== campaign?.peak_hours_end) ||
    (lunchStartDraft !== null &&
      lunchStartDraft !== campaign?.lunch_break_start) ||
    (lunchEndDraft !== null && lunchEndDraft !== campaign?.lunch_break_end) ||
    (weekendFactorDraft !== null &&
      weekendFactorDraft !== campaign?.weekend_factor) ||
    (autoResumeDraft !== null &&
      autoResumeDraft !== Boolean(campaign?.auto_resume_enabled ?? true));

  const readinessMessage = !templateReady
    ? "Tulis template dulu supaya isi pesan jelas sebelum campaign dijalankan."
    : !recipientReady
      ? "Tambahkan recipient agar campaign punya target kirim."
      : !deviceReady
        ? "Pilih device WhatsApp yang sedang connected sebelum mulai blast."
        : hasUnsavedChanges
          ? "Ada perubahan yang belum disimpan. Simpan draft sebelum mulai kirim."
          : "Campaign sudah siap dijalankan.";

  const buildUpdatePayload = () => {
    const payload: Record<string, unknown> = { id: campaignId };
    if (templateDraft !== null) payload.template_message = templateDraft;
    if (deviceDraft !== null) payload.device_id = deviceDraft;
    if (delayDraft !== null) payload.delay_between_ms = delayDraft;
    if (humanMinDraft !== null) payload.human_delay_min_ms = humanMinDraft;
    if (humanMaxDraft !== null) payload.human_delay_max_ms = humanMaxDraft;
    if (variationDraft !== null)
      payload.content_variation_enabled = variationDraft;
    if (scheduleEnabledDraft !== null)
      payload.schedule_enabled = scheduleEnabledDraft;
    if (scheduleTimezoneDraft !== null)
      payload.schedule_timezone = scheduleTimezoneDraft;
    if (activeStartDraft !== null)
      payload.active_hours_start = activeStartDraft;
    if (activeEndDraft !== null) payload.active_hours_end = activeEndDraft;
    if (peakStartDraft !== null) payload.peak_hours_start = peakStartDraft;
    if (peakEndDraft !== null) payload.peak_hours_end = peakEndDraft;
    if (lunchStartDraft !== null) payload.lunch_break_start = lunchStartDraft;
    if (lunchEndDraft !== null) payload.lunch_break_end = lunchEndDraft;
    if (weekendFactorDraft !== null)
      payload.weekend_factor = weekendFactorDraft;
    if (autoResumeDraft !== null) payload.auto_resume_enabled = autoResumeDraft;
    return payload;
  };

  // Insert placeholder at cursor
  const insertPlaceholder = useCallback(
    (placeholder: string) => {
      const ta = templateRef.current;
      if (!ta) {
        setTemplateDraft(
          (prev) => (prev ?? campaign?.template_message ?? "") + placeholder,
        );
        return;
      }
      const start = ta.selectionStart;
      const end = ta.selectionEnd;
      const text = currentTemplate;
      const newText =
        text.substring(0, start) + placeholder + text.substring(end);
      setTemplateDraft(newText);
      // restore cursor after state update
      requestAnimationFrame(() => {
        ta.selectionStart = ta.selectionEnd = start + placeholder.length;
        ta.focus();
      });
    },
    [currentTemplate, campaign?.template_message],
  );

  // Save handler
  const handleSave = () => {
    if (!canManageBlast) return;
    updateMutation.mutate(buildUpdatePayload() as any, {
      onSuccess: () => {
        setTemplateDraft(null);
        setDeviceDraft(null);
        setDelayDraft(null);
        setHumanMinDraft(null);
        setHumanMaxDraft(null);
        setVariationDraft(null);
        setScheduleEnabledDraft(null);
        setScheduleTimezoneDraft(null);
        setActiveStartDraft(null);
        setActiveEndDraft(null);
        setPeakStartDraft(null);
        setPeakEndDraft(null);
        setLunchStartDraft(null);
        setLunchEndDraft(null);
        setWeekendFactorDraft(null);
        setAutoResumeDraft(null);
      },
    });
  };

  // Delete handler
  const handleDelete = () => {
    if (!canManageBlast) return;
    if (!confirm("Delete this campaign and all its recipients?")) return;
    deleteMutation.mutate(campaignId, {
      onSuccess: () => navigate("/blast"),
    });
  };

  const handleStartOrResume = () => {
    if (!canManageBlast) return;
    if (!campaignReady) return;

    if (hasUnsavedChanges) {
      updateMutation.mutate(buildUpdatePayload() as any, {
        onSuccess: () => startMutation.mutate(campaignId),
      });
      return;
    }

    startMutation.mutate(campaignId);
  };

  // Loading
  if (loadingCampaign) {
    return (
      <div className="flex items-center justify-center py-20">
        <Loader2 className="w-6 h-6 animate-spin text-gray-400" />
      </div>
    );
  }

  if (!campaign) {
    return (
      <div className="flex flex-col items-center justify-center py-20 gap-3">
        <AlertCircle className="w-8 h-8 text-gray-300" />
        <p className="text-gray-500 text-sm">Campaign not found</p>
        <Link to="/blast" className="text-indigo-600 text-sm hover:underline">
          Back to campaigns
        </Link>
      </div>
    );
  }

  const progress =
    campaign.total_recipients > 0
      ? Math.round(
          ((campaign.sent_count + campaign.failed_count) /
            campaign.total_recipients) *
            100,
        )
      : 0;

  return (
    <div className="mx-auto max-w-5xl space-y-5 px-4 py-6 pb-28">
      <section className="overflow-hidden rounded-[28px] border border-gray-200 bg-white shadow-sm dark:border-gray-700 dark:bg-gray-800">
        <div className="p-5 md:p-6">
          <div className="space-y-5">
            <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
              <div className="flex items-start gap-3">
                <Link
                  to="/blast"
                  className="mt-1 rounded-xl border border-gray-200 bg-gray-50 p-2 text-gray-500 transition-colors hover:bg-gray-100 hover:text-gray-700 dark:border-gray-700 dark:bg-gray-900/40 dark:text-gray-400 dark:hover:bg-gray-800 dark:hover:text-gray-200"
                >
                  <ArrowLeft className="h-4 w-4" />
                </Link>
                <div className="rounded-2xl border border-indigo-200 bg-indigo-50 p-3 text-indigo-600 shadow-sm dark:border-indigo-900/50 dark:bg-indigo-900/20 dark:text-indigo-300">
                  <Megaphone className="h-5 w-5" />
                </div>
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <h1 className="text-2xl font-semibold tracking-tight text-gray-900 dark:text-gray-100">
                      {campaign.name}
                    </h1>
                    <CampaignStatusBadge status={campaign.status} />
                  </div>
                  <p className="mt-2 max-w-2xl text-sm leading-6 text-gray-500 dark:text-gray-400">
                    Susun pesan, pilih recipient yang tepat, lalu jalankan blast
                    dengan device dan pengaturan yang aman.
                  </p>
                  <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-gray-500 dark:text-gray-400">
                    <span>
                      Dibuat oleh{" "}
                      {campaign.created_by_name ||
                        campaign.created_by_email ||
                        "Unknown"}
                    </span>
                    {campaign.started_by_name || campaign.started_by_email ? (
                      <span>
                        Terakhir dijalankan oleh{" "}
                        {campaign.started_by_name || campaign.started_by_email}
                      </span>
                    ) : null}
                  </div>
                </div>
              </div>

              {canManageBlast && (isDraft || isFinished) && (
                <button
                  onClick={handleDelete}
                  disabled={deleteMutation.isPending}
                  className="inline-flex items-center gap-2 self-start rounded-xl border border-gray-200 bg-white px-3 py-2 text-sm font-medium text-gray-600 transition-colors hover:border-red-200 hover:bg-red-50 hover:text-red-600 disabled:opacity-50 dark:border-gray-700 dark:bg-gray-900/40 dark:text-gray-300 dark:hover:border-red-900/50 dark:hover:bg-red-950/20 dark:hover:text-red-300"
                >
                  <Trash2 className="h-4 w-4" />
                  Delete
                </button>
              )}
            </div>

            <div className="grid gap-3 md:grid-cols-4">
              <SummaryStat
                label="Recipients"
                value={`${totalRecipients}`}
                hint={
                  recipientReady
                    ? `${pendingCount} pending to process`
                    : "Belum ada target kirim"
                }
              />
              <SummaryStat
                label="Template"
                value={
                  templateReady
                    ? `${templateCharacterCount} chars`
                    : "Belum siap"
                }
                hint={
                  templateReady
                    ? "Pesan utama sudah ditulis"
                    : "Isi pesan belum diisi"
                }
              />
              <SummaryStat
                label="Device"
                value={
                  selectedDeviceConnected
                    ? currentDevice
                    : `${currentDevice} offline`
                }
                hint={
                  selectedDeviceDetails?.phoneNumber ||
                  "Pilih device aktif untuk kirim"
                }
              />
              <SummaryStat
                label="Pacing"
                value={`${formatDelayLabel(currentDelay)} + ${formatDelayLabel(currentHumanMin)}-${formatDelayLabel(currentHumanMax)}`}
                hint={
                  currentScheduleEnabled ? "Scheduler aktif" : "Manual timing"
                }
              />
            </div>

            <div className="grid gap-3 md:grid-cols-4">
              <WorkflowCard
                step="Step 1"
                title="Tulis pesan"
                description="Template yang jelas dan personal jadi fondasi campaign ini."
                ready={templateReady}
                icon={MessageSquareText}
              />
              <WorkflowCard
                step="Step 2"
                title="Pilih recipient"
                description="Tambah kontak bernama agar hasil blast lebih relevan dan mudah dipantau."
                ready={recipientReady}
                icon={Users}
              />
              <WorkflowCard
                step="Step 3"
                title="Atur pengiriman"
                description="Pilih device yang connect dan cek pacing supaya aman dijalankan."
                ready={deviceReady}
                icon={Settings2}
              />
              <WorkflowCard
                step="Step 4"
                title="Review & start"
                description="Setelah semuanya siap, simpan draft dan mulai blast dari action bar bawah."
                ready={campaignReady && !hasUnsavedChanges}
                icon={Play}
              />
            </div>

            <div className="rounded-2xl border border-gray-200 bg-gray-50 px-4 py-3 dark:border-gray-700 dark:bg-gray-900/40">
              <div className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
                <div>
                  <p className="text-xs font-semibold uppercase tracking-[0.18em] text-gray-400 dark:text-gray-500">
                    Campaign readiness
                  </p>
                  <p className="mt-1 text-sm text-gray-700 dark:text-gray-200">
                    {readinessMessage}
                  </p>
                </div>
                <span
                  className={cn(
                    "inline-flex items-center gap-1 self-start rounded-full px-3 py-1 text-xs font-semibold",
                    campaignReady && !hasUnsavedChanges
                      ? "bg-emerald-100 text-emerald-700"
                      : "bg-gray-200 text-gray-600 dark:bg-gray-800 dark:text-gray-300",
                  )}
                >
                  {campaignReady && !hasUnsavedChanges ? (
                    <CheckCircle2 className="h-3.5 w-3.5" />
                  ) : (
                    <AlertCircle className="h-3.5 w-3.5" />
                  )}
                  {campaignReady && !hasUnsavedChanges
                    ? "Ready to launch"
                    : "Setup incomplete"}
                </span>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Progress bar for active campaigns */}
      {(isSending || isPaused) && campaign.total_recipients > 0 && (
        <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-4 shadow-sm">
          <div className="flex items-center justify-between text-sm mb-2">
            <span className="font-medium text-gray-700 dark:text-gray-300">
              {isSending ? (
                <span className="flex items-center gap-1.5">
                  <Loader2 className="w-3.5 h-3.5 animate-spin text-blue-500" />
                  Sending in progress...
                </span>
              ) : (
                "Paused"
              )}
            </span>
            <span className="text-gray-500 dark:text-gray-400 text-xs">
              {campaign.sent_count} sent · {campaign.failed_count} failed ·{" "}
              {campaign.total_recipients -
                campaign.sent_count -
                campaign.failed_count}{" "}
              remaining
            </span>
          </div>
          {isPaused && (campaign.paused_reason || campaign.auto_resume_at) && (
            <div className="mt-2 rounded-lg bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800 px-3 py-2 text-xs text-amber-700 dark:text-amber-300 space-y-1">
              {campaign.paused_reason && (
                <p>Reason: {campaign.paused_reason}</p>
              )}
              {campaign.auto_resume_at && currentAutoResumeEnabled && (
                <p>
                  Auto-resume:{" "}
                  {new Date(campaign.auto_resume_at).toLocaleString()}
                </p>
              )}
            </div>
          )}
          <div className="h-2.5 bg-gray-100 dark:bg-gray-700 rounded-full overflow-hidden flex">
            {campaign.sent_count > 0 && (
              <div
                className="bg-green-500 h-full transition-all duration-500"
                style={{
                  width: `${(campaign.sent_count / campaign.total_recipients) * 100}%`,
                }}
              />
            )}
            {campaign.failed_count > 0 && (
              <div
                className="bg-red-400 h-full transition-all duration-500"
                style={{
                  width: `${(campaign.failed_count / campaign.total_recipients) * 100}%`,
                }}
              />
            )}
          </div>
          <div className="text-right text-xs text-gray-400 mt-1">
            {progress}%
          </div>
        </div>
      )}

      {/* Completed/Cancelled summary */}
      {isFinished && campaign.total_recipients > 0 && (
        <div
          className={cn(
            "flex items-center gap-3 p-4 rounded-xl border shadow-sm",
            campaign.status === "completed"
              ? "bg-green-50 dark:bg-green-900/20 border-green-200 dark:border-green-800"
              : "bg-gray-50 dark:bg-gray-800 border-gray-200 dark:border-gray-700",
          )}
        >
          {campaign.status === "completed" ? (
            <CheckCircle2 className="w-5 h-5 text-green-500" />
          ) : (
            <XCircle className="w-5 h-5 text-gray-400" />
          )}
          <div>
            <p className="text-sm font-medium text-gray-900 dark:text-gray-100">
              {campaign.status === "completed"
                ? "Campaign completed"
                : "Campaign cancelled"}
            </p>
            <p className="text-xs text-gray-500 dark:text-gray-400">
              {campaign.sent_count} sent · {campaign.failed_count} failed ·{" "}
              {campaign.total_recipients -
                campaign.sent_count -
                campaign.failed_count}{" "}
              skipped
            </p>
          </div>
        </div>
      )}

      {/* Failed recipients detail — shown after campaign completes with failures */}
      {isFinished && campaign.failed_count > 0 && (
        <details className="rounded-xl border border-red-200 dark:border-red-800/50 shadow-sm bg-red-50/50 dark:bg-red-900/10 overflow-hidden">
          <summary className="flex items-center gap-2 px-4 py-3 cursor-pointer select-none hover:bg-red-50 dark:hover:bg-red-900/20 transition-colors">
            <AlertCircle className="w-4 h-4 text-red-500 shrink-0" />
            <span className="text-sm font-medium text-red-700 dark:text-red-400">
              {campaign.failed_count} failed deliveries
            </span>
            <span className="text-[11px] text-red-400 dark:text-red-500 ml-auto">
              click to expand
            </span>
          </summary>
          <div className="border-t border-red-200 dark:border-red-800/50 divide-y divide-red-100 dark:divide-red-900/30 max-h-[300px] overflow-y-auto">
            {recipients
              .filter((r) => r.status === "failed")
              .map((r) => (
                <div
                  key={r.id}
                  className="flex items-start gap-3 px-4 py-2.5 text-sm"
                >
                  <div className="min-w-0 flex-1">
                    <p className="font-medium text-gray-900 dark:text-gray-100 truncate">
                      {r.contact_name || r.phone_number}
                    </p>
                    {r.university_name && (
                      <p className="text-[11px] text-gray-500 dark:text-gray-400 truncate">
                        {r.university_name}
                      </p>
                    )}
                  </div>
                  <p className="text-xs text-red-600 dark:text-red-400 max-w-[50%] text-right shrink-0">
                    {r.error_message || "Unknown error"}
                  </p>
                </div>
              ))}
          </div>
        </details>
      )}

      {/* ------------------------------------------------------------------ */}
      {/* Template Editor */}
      {/* ------------------------------------------------------------------ */}
      <section className="overflow-hidden rounded-2xl border border-gray-200 bg-white shadow-sm dark:border-gray-700 dark:bg-gray-800">
        <div className="flex flex-col gap-3 border-b border-gray-100 px-4 py-4 dark:border-gray-700 md:flex-row md:items-start md:justify-between">
          <div className="flex items-start gap-3">
            <div className="rounded-xl bg-indigo-50 p-2 text-indigo-600 dark:bg-indigo-900/30 dark:text-indigo-300">
              <MessageSquareText className="h-4 w-4" />
            </div>
            <div>
              <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-gray-400 dark:text-gray-500">
                Step 1
              </p>
              <h2 className="mt-1 text-sm font-semibold text-gray-900 dark:text-gray-100">
                Message Template
              </h2>
              <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                Tulis pesan inti sejelas mungkin. Personalization akan mengisi
                nama kontak dan universitas secara otomatis.
              </p>
            </div>
          </div>
          <div className="grid grid-cols-2 gap-2 text-xs md:min-w-[240px]">
            <div className="rounded-xl bg-gray-50 px-3 py-2 dark:bg-gray-900/40">
              <p className="text-gray-400 dark:text-gray-500">Characters</p>
              <p className="mt-1 font-semibold text-gray-800 dark:text-gray-100">
                {templateCharacterCount}
              </p>
            </div>
            <div className="rounded-xl bg-gray-50 px-3 py-2 dark:bg-gray-900/40">
              <p className="text-gray-400 dark:text-gray-500">Status</p>
              <p className="mt-1 font-semibold text-gray-800 dark:text-gray-100">
                {templateReady ? "Ready" : "Needs copy"}
              </p>
            </div>
          </div>
        </div>
        <div className="grid gap-5 p-4 lg:grid-cols-[minmax(0,1fr)_320px]">
          <div>
            <div className="mb-3 flex flex-wrap gap-2">
              {PLACEHOLDERS.map((p) => {
                const Icon = p.icon;
                return (
                  <button
                    key={p.key}
                    onClick={() => insertPlaceholder(p.key)}
                    disabled={!canEditCampaign}
                    className="flex items-center gap-1 px-2.5 py-1 text-xs font-medium bg-indigo-50 dark:bg-indigo-900/30 text-indigo-600 dark:text-indigo-400 rounded-lg hover:bg-indigo-100 dark:hover:bg-indigo-900/50 disabled:opacity-40 transition-colors border border-indigo-200 dark:border-indigo-800"
                  >
                    <Icon className="w-3 h-3" />
                    {p.label}
                  </button>
                );
              })}
            </div>
            <textarea
              ref={templateRef}
              value={currentTemplate}
              onChange={(e) => setTemplateDraft(e.target.value)}
              disabled={!canEditCampaign}
              rows={8}
              placeholder="Halo {nama_kontak}, kami dari LSP ingin menghubungi {nama_universitas}..."
              className="w-full rounded-2xl border border-gray-300 px-4 py-3 text-sm leading-6 dark:border-gray-600 dark:bg-gray-900 dark:text-gray-100 focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 disabled:cursor-not-allowed disabled:opacity-60 resize-none"
            />
            <div className="mt-2 flex flex-col gap-2 text-[11px] text-gray-400 dark:text-gray-500 md:flex-row md:items-center md:justify-between">
              <p>
                Gunakan placeholder di atas untuk personalisasi otomatis tiap
                recipient.
              </p>
              {hasUnsavedChanges && (
                <p className="font-medium text-amber-500">
                  Ada perubahan draft yang belum disimpan.
                </p>
              )}
            </div>
          </div>

          <div className="space-y-3">
            <div className="rounded-2xl border border-gray-200 bg-gray-50 p-4 dark:border-gray-700 dark:bg-gray-900/40">
              <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-gray-400 dark:text-gray-500">
                Inline preview
              </p>
              {!templateReady ? (
                <p className="mt-3 text-sm leading-6 text-gray-500 dark:text-gray-400">
                  Tulis template dulu. Setelah recipient ada dan draft disimpan,
                  preview personal akan muncul di sini.
                </p>
              ) : (
                <div className="mt-3 space-y-3">
                  <div>
                    <p className="text-[11px] text-gray-400 dark:text-gray-500">
                      {primaryPreview?.contact_name ||
                        recipients[0]?.contact_name ||
                        "Sample recipient"}
                      {primaryPreview?.phone_number
                        ? ` • ${primaryPreview.phone_number}`
                        : ""}
                    </p>
                    <div className="mt-2 max-w-full rounded-2xl rounded-tl-sm bg-green-100 px-3 py-2 text-sm leading-6 text-gray-800 dark:bg-green-900/30 dark:text-gray-100 whitespace-pre-wrap">
                      {primaryPreview?.rendered_message || currentTemplate}
                    </div>
                  </div>
                  {!primaryPreview && recipientReady && (
                    <p className="text-[11px] text-amber-500">
                      Simpan draft untuk melihat preview yang sudah
                      dipersonalisasi.
                    </p>
                  )}
                </div>
              )}
            </div>

            <div className="rounded-2xl border border-gray-200 bg-gray-50 p-4 dark:border-gray-700 dark:bg-gray-900/40">
              <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-gray-400 dark:text-gray-500">
                Copy guidance
              </p>
              <ul className="mt-3 space-y-2 text-sm leading-6 text-gray-500 dark:text-gray-400">
                <li>
                  Mulai dari konteks dan tujuan, jangan langsung minta data.
                </li>
                <li>
                  Jaga agar 1 pesan tetap ringkas supaya nyaman dibaca di
                  WhatsApp.
                </li>
                <li>
                  Pakai nama kontak bila tersedia agar pembuka terasa lebih
                  natural.
                </li>
              </ul>
            </div>
          </div>
        </div>
      </section>

      {/* ------------------------------------------------------------------ */}
      {/* Recipients */}
      {/* ------------------------------------------------------------------ */}
      <section className="overflow-hidden rounded-2xl border border-gray-200 bg-white shadow-sm dark:border-gray-700 dark:bg-gray-800">
        <div className="flex flex-col gap-3 border-b border-gray-100 px-4 py-4 dark:border-gray-700 md:flex-row md:items-start md:justify-between">
          <div className="flex items-start gap-3">
            <div className="rounded-xl bg-indigo-50 p-2 text-indigo-600 dark:bg-indigo-900/30 dark:text-indigo-300">
              <Users className="h-4 w-4" />
            </div>
            <div>
              <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-gray-400 dark:text-gray-500">
                Step 2
              </p>
              <h2 className="mt-1 text-sm font-semibold text-gray-900 dark:text-gray-100">
                Recipients
                {totalRecipients > 0 && (
                  <span className="ml-1.5 text-xs font-normal text-gray-400">
                    ({totalRecipients})
                  </span>
                )}
              </h2>
              <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                Pilih recipient yang akan menerima campaign. Kontak bernama akan
                lebih mudah dianalisis hasilnya.
              </p>
            </div>
          </div>
          {canEditCampaign && (
            <div className="flex items-center gap-2">
              {totalRecipients > 0 && (
                <button
                  onClick={() => {
                    if (confirm("Remove all pending recipients?"))
                      clearMutation.mutate(campaignId);
                  }}
                  disabled={clearMutation.isPending}
                  className="px-2.5 py-1 text-xs text-red-500 hover:bg-red-50 dark:hover:bg-red-900/30 rounded-lg transition-colors"
                >
                  Clear All
                </button>
              )}
              <button
                onClick={() => setShowContactModal(true)}
                className="flex items-center gap-1 px-3 py-1.5 bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-medium rounded-lg transition-colors"
              >
                <Plus className="w-3.5 h-3.5" />
                Add Contacts
              </button>
            </div>
          )}
        </div>

        <div className="grid gap-3 border-b border-gray-100 bg-gray-50/70 px-4 py-3 dark:border-gray-700 dark:bg-gray-900/20 md:grid-cols-3">
          <div className="rounded-xl bg-white px-3 py-3 dark:bg-gray-800/80">
            <p className="text-[11px] uppercase tracking-[0.14em] text-gray-400 dark:text-gray-500">
              Pending
            </p>
            <p className="mt-1 text-base font-semibold text-gray-900 dark:text-gray-100">
              {pendingCount}
            </p>
            <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
              Target yang belum diproses worker
            </p>
          </div>
          <div className="rounded-xl bg-white px-3 py-3 dark:bg-gray-800/80">
            <p className="text-[11px] uppercase tracking-[0.14em] text-gray-400 dark:text-gray-500">
              Named Contacts
            </p>
            <p className="mt-1 text-base font-semibold text-gray-900 dark:text-gray-100">
              {namedRecipientCount}
            </p>
            <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
              Recipient dengan nama yang bisa dipersonalisasi
            </p>
          </div>
          <div className="rounded-xl bg-white px-3 py-3 dark:bg-gray-800/80">
            <p className="text-[11px] uppercase tracking-[0.14em] text-gray-400 dark:text-gray-500">
              Results
            </p>
            <p className="mt-1 text-base font-semibold text-gray-900 dark:text-gray-100">
              {campaign.sent_count} sent · {campaign.failed_count} failed
            </p>
            <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
              Ringkasan hasil campaign sampai saat ini
            </p>
          </div>
        </div>

        {loadingRecipients ? (
          <div className="flex items-center justify-center py-10">
            <Loader2 className="w-5 h-5 animate-spin text-gray-400" />
          </div>
        ) : recipients.length === 0 ? (
          <div className="px-4 py-8">
            <div className="rounded-2xl border border-dashed border-gray-300 bg-gray-50/80 px-6 py-10 text-center dark:border-gray-700 dark:bg-gray-900/30">
              <Users className="w-8 h-8 mx-auto text-gray-300 dark:text-gray-600 mb-2" />
              <p className="text-sm font-medium text-gray-500 dark:text-gray-400">
                Belum ada recipient di campaign ini
              </p>
              <p className="mt-1 text-xs text-gray-400 dark:text-gray-500">
                Pilih kontak dari database atau quick-select by group untuk
                mulai membangun target list.
              </p>
              {canEditCampaign && (
                <button
                  onClick={() => setShowContactModal(true)}
                  className="mt-4 inline-flex items-center gap-2 rounded-xl bg-indigo-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-indigo-700"
                >
                  <Plus className="h-4 w-4" />
                  Pilih recipient
                </button>
              )}
            </div>
          </div>
        ) : (
          <div>
            {/* Table header */}
            <div className="grid grid-cols-[1fr_1fr_1fr_80px_40px] gap-2 px-4 py-2 bg-gray-50 dark:bg-gray-750 text-[11px] font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider border-b border-gray-200 dark:border-gray-700">
              <span>Contact</span>
              <span>University</span>
              <span>Phone</span>
              <span>Status</span>
              <span></span>
            </div>
            {/* Rows */}
            {recipients.map((r) => (
              <div
                key={r.id}
                className="grid grid-cols-[1fr_1fr_1fr_80px_40px] gap-2 items-center px-4 py-2 border-b border-gray-100 dark:border-gray-700/50 hover:bg-gray-50 dark:hover:bg-gray-800 text-sm"
              >
                <span className="truncate text-gray-900 dark:text-gray-100">
                  {r.contact_name || "-"}
                </span>
                <span className="truncate text-gray-500 dark:text-gray-400 text-xs">
                  {r.university_name || "-"}
                </span>
                <span className="text-gray-600 dark:text-gray-400 text-xs font-mono">
                  {r.phone_number}
                </span>
                <RecipientStatusBadge status={r.status} />
                <div>
                  {canEditCampaign && r.status === "pending" && (
                    <button
                      onClick={() =>
                        removeMutation.mutate({ campaignId, recipientId: r.id })
                      }
                      className="p-1 rounded text-gray-300 hover:text-red-500 transition-colors"
                      title="Remove"
                    >
                      <X className="w-3.5 h-3.5" />
                    </button>
                  )}
                  {r.status === "failed" && r.error_message && (
                    <span title={r.error_message}>
                      <AlertCircle className="w-3.5 h-3.5 text-red-400 cursor-help" />
                    </span>
                  )}
                </div>
              </div>
            ))}

            {/* Pagination */}
            {totalRecipients > RECIPIENTS_PER_PAGE && (
              <div className="flex items-center justify-between px-4 py-2.5 bg-gray-50 dark:bg-gray-800/50">
                <span className="text-xs text-gray-400">
                  Page {recipientPage + 1} of{" "}
                  {Math.ceil(totalRecipients / RECIPIENTS_PER_PAGE)}
                </span>
                <div className="flex gap-1">
                  <button
                    onClick={() => setRecipientPage((p) => Math.max(0, p - 1))}
                    disabled={recipientPage === 0}
                    className="px-2.5 py-1 text-xs rounded border border-gray-200 dark:border-gray-700 text-gray-600 dark:text-gray-400 disabled:opacity-40 hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors"
                  >
                    Prev
                  </button>
                  <button
                    onClick={() => setRecipientPage((p) => p + 1)}
                    disabled={
                      (recipientPage + 1) * RECIPIENTS_PER_PAGE >=
                      totalRecipients
                    }
                    className="px-2.5 py-1 text-xs rounded border border-gray-200 dark:border-gray-700 text-gray-600 dark:text-gray-400 disabled:opacity-40 hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors"
                  >
                    Next
                  </button>
                </div>
              </div>
            )}
          </div>
        )}
      </section>

      {/* ------------------------------------------------------------------ */}
      {/* Settings (collapsible) */}
      {/* ------------------------------------------------------------------ */}
      <section className="overflow-hidden rounded-2xl border border-gray-200 bg-white shadow-sm dark:border-gray-700 dark:bg-gray-800">
        <button
          onClick={() => setShowSettings(!showSettings)}
          className="flex items-center justify-between w-full px-4 py-3 text-left hover:bg-gray-50 dark:hover:bg-gray-800/50 transition-colors"
        >
          <div className="flex items-center gap-2">
            <Settings2 className="w-4 h-4 text-indigo-500" />
            <div>
              <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-gray-400 dark:text-gray-500">
                Step 3
              </p>
              <h2 className="text-sm font-semibold text-gray-800 dark:text-gray-200">
                Sending Settings
              </h2>
            </div>
          </div>
          <div className="hidden items-center gap-2 md:flex">
            <span
              className={cn(
                "rounded-full px-2 py-1 text-[11px] font-medium",
                selectedDeviceConnected
                  ? "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300"
                  : "bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300",
              )}
            >
              {selectedDeviceConnected
                ? `${currentDevice} connected`
                : `${currentDevice} offline`}
            </span>
            <span className="rounded-full bg-gray-100 px-2 py-1 text-[11px] font-medium text-gray-500 dark:bg-gray-800 dark:text-gray-400">
              {currentScheduleEnabled ? "Scheduler on" : "Scheduler off"}
            </span>
          </div>
          {showSettings ? (
            <ChevronUp className="w-4 h-4 text-gray-400" />
          ) : (
            <ChevronDown className="w-4 h-4 text-gray-400" />
          )}
        </button>
        {showSettings && (
          <div className="space-y-4 border-t border-gray-100 px-4 pb-4 pt-3 dark:border-gray-700">
            <div className="rounded-2xl border border-gray-200 bg-gray-50/80 p-4 dark:border-gray-700 dark:bg-gray-900/30">
              <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
                <div>
                  <p className="text-sm font-semibold text-gray-900 dark:text-gray-100">
                    Pengaturan ini menentukan cara campaign dikirim
                  </p>
                  <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                    Pilih device, atur delay, lalu aktifkan scheduler bila
                    perlu.
                  </p>
                </div>
                {hasUnsavedChanges && canEditCampaign && (
                  <span className="inline-flex items-center gap-1 self-start rounded-full bg-amber-100 px-2.5 py-1 text-[11px] font-medium text-amber-700 dark:bg-amber-900/30 dark:text-amber-300">
                    <AlertCircle className="h-3.5 w-3.5" />
                    Draft settings belum disimpan
                  </span>
                )}
              </div>
            </div>

            <div className="grid gap-3 md:grid-cols-3">
              <SettingHintCard
                title="Device aktif"
                description="Pengirim"
                value={
                  selectedDeviceConnected
                    ? `${currentDevice}${selectedDeviceDetails?.phoneNumber ? ` · ${selectedDeviceDetails.phoneNumber}` : ""}`
                    : `${currentDevice} belum connected`
                }
              />
              <SettingHintCard
                title="Ritme kirim"
                description="Base + random delay"
                value={`${formatDelayLabel(currentDelay)} + ${formatDelayLabel(currentHumanMin)}-${formatDelayLabel(currentHumanMax)}`}
              />
              <SettingHintCard
                title="Scheduler"
                description="Jam operasional"
                value={
                  currentScheduleEnabled
                    ? `${currentActiveStart}:00-${currentActiveEnd}:00 ${currentScheduleTimezone}`
                    : "Nonaktif, kirim mengikuti run campaign"
                }
              />
            </div>

            <div className="grid gap-4 xl:grid-cols-[1.2fr_0.8fr]">
              <div className="rounded-2xl border border-gray-200 p-4 dark:border-gray-700">
                <div className="flex items-start gap-3">
                  <div className="rounded-xl bg-indigo-50 p-2 text-indigo-600 dark:bg-indigo-900/30 dark:text-indigo-300">
                    <Smartphone className="h-4 w-4" />
                  </div>
                  <div>
                    <p className="text-sm font-semibold text-gray-900 dark:text-gray-100">
                      Device & ritme kirim
                    </p>
                  </div>
                </div>

                <div className="mt-4 space-y-4">
                  <div>
                    <label className="mb-1.5 flex items-center gap-1.5 text-xs font-medium text-gray-700 dark:text-gray-300">
                      <Smartphone className="h-3.5 w-3.5" />
                      WhatsApp Device
                    </label>
                    <select
                      value={currentDevice}
                      onChange={(e) => setDeviceDraft(e.target.value)}
                      disabled={!canEditCampaign}
                      className="w-full rounded-xl border border-gray-300 px-3 py-2 text-sm dark:border-gray-600 dark:bg-gray-900 dark:text-gray-100 focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 disabled:opacity-60"
                    >
                      {myDevices.length === 0 && (
                        <option value="" disabled>
                          Belum ada device — setup di halaman WhatsApp
                        </option>
                      )}
                      {myDevices.map((dev) => {
                        const isConnected = dev.connectionState === "connected";
                        return (
                          <option key={dev.id} value={dev.id}>
                            {dev.name}
                            {dev.phoneNumber
                              ? ` (${dev.phoneNumber})`
                              : ""}{" "}
                            {isConnected ? "✓ Connected" : "✗ Offline"}
                          </option>
                        );
                      })}
                    </select>
                    {connectedDevices.length === 0 ? (
                      <p className="mt-2 text-[11px] text-amber-500">
                        Belum ada device yang connected. Hubungkan device dulu
                        dari halaman WhatsApp.
                      </p>
                    ) : (
                      <p className="mt-2 text-[11px] text-gray-500 dark:text-gray-400">
                        Device terpilih:{" "}
                        {selectedDeviceDetails?.phoneNumber ||
                          "nomor belum tersedia"}
                        .
                      </p>
                    )}
                  </div>

                  <div>
                    <label className="mb-1.5 flex items-center gap-1.5 text-xs font-medium text-gray-700 dark:text-gray-300">
                      <Timer className="h-3.5 w-3.5" />
                      Base Delay Between Messages
                    </label>
                    <input
                      type="number"
                      value={currentDelay}
                      onChange={(e) =>
                        setDelayDraft(Math.max(1000, Number(e.target.value)))
                      }
                      disabled={!canEditCampaign}
                      min={1000}
                      step={1000}
                      className="w-full rounded-xl border border-gray-300 px-3 py-2 text-sm dark:border-gray-600 dark:bg-gray-900 dark:text-gray-100 focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 disabled:opacity-60"
                    />
                  </div>

                  <div className="grid gap-3 md:grid-cols-2">
                    <div>
                      <label className="mb-1.5 flex items-center gap-1.5 text-xs font-medium text-gray-700 dark:text-gray-300">
                        <Zap className="h-3.5 w-3.5" />
                        Human Delay Min
                      </label>
                      <input
                        type="number"
                        value={currentHumanMin}
                        onChange={(e) =>
                          setHumanMinDraft(
                            Math.max(500, Number(e.target.value)),
                          )
                        }
                        disabled={!canEditCampaign}
                        min={500}
                        step={500}
                        className="w-full rounded-xl border border-gray-300 px-3 py-2 text-sm dark:border-gray-600 dark:bg-gray-900 dark:text-gray-100 focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 disabled:opacity-60"
                      />
                    </div>
                    <div>
                      <label className="mb-1.5 flex items-center gap-1.5 text-xs font-medium text-gray-700 dark:text-gray-300">
                        <Zap className="h-3.5 w-3.5" />
                        Human Delay Max
                      </label>
                      <input
                        type="number"
                        value={currentHumanMax}
                        onChange={(e) =>
                          setHumanMaxDraft(
                            Math.max(
                              currentHumanMin + 500,
                              Number(e.target.value),
                            ),
                          )
                        }
                        disabled={!canEditCampaign}
                        min={1000}
                        step={500}
                        className="w-full rounded-xl border border-gray-300 px-3 py-2 text-sm dark:border-gray-600 dark:bg-gray-900 dark:text-gray-100 focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 disabled:opacity-60"
                      />
                    </div>
                  </div>

                  <div className="rounded-2xl border border-gray-200 bg-gray-50 px-3 py-3 dark:border-gray-700 dark:bg-gray-900/30">
                    <p className="text-xs font-medium text-gray-700 dark:text-gray-300">
                      Estimasi delay aktual per pesan
                    </p>
                    <p className="mt-1 text-sm font-semibold text-gray-900 dark:text-gray-100">
                      {formatDelayLabel(currentDelay)} + random{" "}
                      {formatDelayLabel(currentHumanMin)} sampai{" "}
                      {formatDelayLabel(currentHumanMax)}
                    </p>
                  </div>
                </div>
              </div>

              <div className="rounded-2xl border border-gray-200 p-4 dark:border-gray-700">
                <div className="flex items-start gap-3">
                  <div className="rounded-xl bg-indigo-50 p-2 text-indigo-600 dark:bg-indigo-900/30 dark:text-indigo-300">
                    <Settings2 className="h-4 w-4" />
                  </div>
                  <div>
                    <p className="text-sm font-semibold text-gray-900 dark:text-gray-100">
                      Proteksi & automasi
                    </p>
                  </div>
                </div>

                <div className="mt-4 space-y-3">
                  <label className="flex items-start gap-3 rounded-2xl border border-gray-200 px-3 py-3 dark:border-gray-700">
                    <input
                      type="checkbox"
                      checked={currentVariationEnabled}
                      onChange={(e) => setVariationDraft(e.target.checked)}
                      disabled={!canEditCampaign}
                      className="mt-0.5 h-4 w-4 rounded border-gray-300 text-indigo-600 focus:ring-indigo-500"
                    />
                    <span>
                      <span className="block text-sm font-medium text-gray-700 dark:text-gray-300">
                        Content variation
                      </span>
                      <span className="mt-1 block text-[11px] text-gray-500 dark:text-gray-400">
                        Pesan tidak identik untuk setiap recipient.
                      </span>
                    </span>
                  </label>

                  <label className="flex items-start gap-3 rounded-2xl border border-gray-200 px-3 py-3 dark:border-gray-700">
                    <input
                      type="checkbox"
                      checked={currentAutoResumeEnabled}
                      onChange={(e) => setAutoResumeDraft(e.target.checked)}
                      disabled={!canEditCampaign}
                      className="mt-0.5 h-4 w-4 rounded border-gray-300 text-indigo-600 focus:ring-indigo-500"
                    />
                    <span>
                      <span className="block text-sm font-medium text-gray-700 dark:text-gray-300">
                        Auto-resume after anti-ban cooldown
                      </span>
                      <span className="mt-1 block text-[11px] text-gray-500 dark:text-gray-400">
                        Lanjut otomatis setelah cooldown selesai.
                      </span>
                    </span>
                  </label>
                </div>
              </div>
            </div>

            <div className="rounded-2xl border border-gray-200 p-4 dark:border-gray-700">
              <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
                <div className="flex items-start gap-3">
                  <div className="rounded-xl bg-indigo-50 p-2 text-indigo-600 dark:bg-indigo-900/30 dark:text-indigo-300">
                    <Clock className="h-4 w-4" />
                  </div>
                  <div>
                    <p className="text-sm font-semibold text-gray-900 dark:text-gray-100">
                      Safe-hours scheduler
                    </p>
                    <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                      Batasi jam kirim bila campaign tidak boleh jalan sepanjang
                      hari.
                    </p>
                  </div>
                </div>
                <label className="flex items-start gap-2 rounded-xl border border-gray-200 px-3 py-2 dark:border-gray-700">
                  <input
                    type="checkbox"
                    checked={currentScheduleEnabled}
                    onChange={(e) => setScheduleEnabledDraft(e.target.checked)}
                    disabled={!canEditCampaign}
                    className="mt-0.5 h-4 w-4 rounded border-gray-300 text-indigo-600 focus:ring-indigo-500"
                  />
                  <span>
                    <span className="block text-sm font-medium text-gray-700 dark:text-gray-300">
                      Aktifkan scheduler
                    </span>
                    <span className="mt-1 block text-[11px] text-gray-500 dark:text-gray-400">
                      Gunakan jam operasional di bawah.
                    </span>
                  </span>
                </label>
              </div>

              {currentScheduleEnabled ? (
                <div className="mt-4 space-y-4 rounded-2xl border border-gray-200 bg-gray-50/60 p-4 dark:border-gray-700 dark:bg-gray-900/20">
                  <div className="grid gap-3 md:grid-cols-3">
                    <SettingHintCard
                      title="Jam aktif"
                      description="Active hours"
                      value={`${currentActiveStart}:00-${currentActiveEnd}:00`}
                    />
                    <SettingHintCard
                      title="Peak window"
                      description="Faster window"
                      value={`${currentPeakStart}:00-${currentPeakEnd}:00`}
                    />
                    <SettingHintCard
                      title="Lunch slowdown"
                      description="Lunch + weekend"
                      value={`${currentLunchStart}:00-${currentLunchEnd}:00 · weekend x${currentWeekendFactor}`}
                    />
                  </div>

                  <div className="grid gap-3 md:grid-cols-[1.2fr_1fr_1fr]">
                    <div>
                      <label className="mb-1.5 block text-xs font-medium text-gray-700 dark:text-gray-300">
                        Timezone
                      </label>
                      <input
                        type="text"
                        value={currentScheduleTimezone}
                        onChange={(e) =>
                          setScheduleTimezoneDraft(e.target.value)
                        }
                        disabled={!canEditCampaign}
                        placeholder="Asia/Jakarta"
                        className="w-full rounded-xl border border-gray-300 px-3 py-2 text-sm dark:border-gray-600 dark:bg-gray-900 dark:text-gray-100 focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 disabled:opacity-60"
                      />
                    </div>
                    <div>
                      <label className="mb-1.5 block text-xs font-medium text-gray-700 dark:text-gray-300">
                        Active Start
                      </label>
                      <input
                        type="number"
                        value={currentActiveStart}
                        onChange={(e) =>
                          setActiveStartDraft(
                            Math.max(0, Math.min(23, Number(e.target.value))),
                          )
                        }
                        disabled={!canEditCampaign}
                        min={0}
                        max={23}
                        className="w-full rounded-xl border border-gray-300 px-3 py-2 text-sm dark:border-gray-600 dark:bg-gray-900 dark:text-gray-100 focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 disabled:opacity-60"
                      />
                    </div>
                    <div>
                      <label className="mb-1.5 block text-xs font-medium text-gray-700 dark:text-gray-300">
                        Active End
                      </label>
                      <input
                        type="number"
                        value={currentActiveEnd}
                        onChange={(e) =>
                          setActiveEndDraft(
                            Math.max(
                              currentActiveStart + 1,
                              Math.min(24, Number(e.target.value)),
                            ),
                          )
                        }
                        disabled={!canEditCampaign}
                        min={1}
                        max={24}
                        className="w-full rounded-xl border border-gray-300 px-3 py-2 text-sm dark:border-gray-600 dark:bg-gray-900 dark:text-gray-100 focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 disabled:opacity-60"
                      />
                    </div>
                  </div>

                  <div className="grid gap-3 md:grid-cols-5">
                    <div>
                      <label className="mb-1.5 block text-xs font-medium text-gray-700 dark:text-gray-300">
                        Peak Start
                      </label>
                      <input
                        type="number"
                        value={currentPeakStart}
                        onChange={(e) =>
                          setPeakStartDraft(
                            Math.max(0, Math.min(23, Number(e.target.value))),
                          )
                        }
                        disabled={!canEditCampaign}
                        min={0}
                        max={23}
                        className="w-full rounded-xl border border-gray-300 px-3 py-2 text-sm dark:border-gray-600 dark:bg-gray-900 dark:text-gray-100 focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 disabled:opacity-60"
                      />
                    </div>
                    <div>
                      <label className="mb-1.5 block text-xs font-medium text-gray-700 dark:text-gray-300">
                        Peak End
                      </label>
                      <input
                        type="number"
                        value={currentPeakEnd}
                        onChange={(e) =>
                          setPeakEndDraft(
                            Math.max(
                              currentPeakStart,
                              Math.min(24, Number(e.target.value)),
                            ),
                          )
                        }
                        disabled={!canEditCampaign}
                        min={0}
                        max={24}
                        className="w-full rounded-xl border border-gray-300 px-3 py-2 text-sm dark:border-gray-600 dark:bg-gray-900 dark:text-gray-100 focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 disabled:opacity-60"
                      />
                    </div>
                    <div>
                      <label className="mb-1.5 block text-xs font-medium text-gray-700 dark:text-gray-300">
                        Lunch Start
                      </label>
                      <input
                        type="number"
                        value={currentLunchStart}
                        onChange={(e) =>
                          setLunchStartDraft(
                            Math.max(0, Math.min(23, Number(e.target.value))),
                          )
                        }
                        disabled={!canEditCampaign}
                        min={0}
                        max={23}
                        className="w-full rounded-xl border border-gray-300 px-3 py-2 text-sm dark:border-gray-600 dark:bg-gray-900 dark:text-gray-100 focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 disabled:opacity-60"
                      />
                    </div>
                    <div>
                      <label className="mb-1.5 block text-xs font-medium text-gray-700 dark:text-gray-300">
                        Lunch End
                      </label>
                      <input
                        type="number"
                        value={currentLunchEnd}
                        onChange={(e) =>
                          setLunchEndDraft(
                            Math.max(
                              currentLunchStart,
                              Math.min(24, Number(e.target.value)),
                            ),
                          )
                        }
                        disabled={!canEditCampaign}
                        min={0}
                        max={24}
                        className="w-full rounded-xl border border-gray-300 px-3 py-2 text-sm dark:border-gray-600 dark:bg-gray-900 dark:text-gray-100 focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 disabled:opacity-60"
                      />
                    </div>
                    <div>
                      <label className="mb-1.5 block text-xs font-medium text-gray-700 dark:text-gray-300">
                        Weekend Factor
                      </label>
                      <input
                        type="number"
                        value={currentWeekendFactor}
                        onChange={(e) =>
                          setWeekendFactorDraft(
                            Math.max(0, Number(e.target.value)),
                          )
                        }
                        disabled={!canEditCampaign}
                        min={0}
                        max={2}
                        step={0.1}
                        className="w-full rounded-xl border border-gray-300 px-3 py-2 text-sm dark:border-gray-600 dark:bg-gray-900 dark:text-gray-100 focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 disabled:opacity-60"
                      />
                    </div>
                  </div>

                  <p className="text-[11px] text-gray-500 dark:text-gray-400">
                    Weekend factor: 0 berhenti, 1 normal, di bawah 1 lebih
                    lambat.
                  </p>
                </div>
              ) : (
                <div className="mt-4 rounded-2xl border border-dashed border-gray-200 px-4 py-4 dark:border-gray-700">
                  <p className="text-sm font-medium text-gray-700 dark:text-gray-300">
                    Scheduler sedang nonaktif
                  </p>
                  <p className="mt-1 text-[11px] text-gray-500 dark:text-gray-400">
                    Campaign mengikuti delay biasa tanpa batas jam.
                  </p>
                </div>
              )}
            </div>
          </div>
        )}
      </section>

      {/* ------------------------------------------------------------------ */}
      {/* Message Preview */}
      {/* ------------------------------------------------------------------ */}
      <section className="overflow-hidden rounded-2xl border border-gray-200 bg-white shadow-sm dark:border-gray-700 dark:bg-gray-800">
        <button
          onClick={() => setShowPreview(!showPreview)}
          className="flex items-center justify-between w-full px-4 py-3 text-left hover:bg-gray-50 dark:hover:bg-gray-800/50 transition-colors"
        >
          <div className="flex items-center gap-2">
            <Eye className="w-4 h-4 text-indigo-500" />
            <div>
              <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-gray-400 dark:text-gray-500">
                Step 4
              </p>
              <h2 className="text-sm font-semibold text-gray-800 dark:text-gray-200">
                Review Messages
              </h2>
            </div>
          </div>
          {showPreview ? (
            <ChevronUp className="w-4 h-4 text-gray-400" />
          ) : (
            <ChevronDown className="w-4 h-4 text-gray-400" />
          )}
        </button>
        {showPreview && (
          <div className="px-4 pb-4 pt-1 border-t border-gray-100 dark:border-gray-700">
            {!previewData?.previews?.length ? (
              <p className="text-sm text-gray-400 py-4 text-center">
                {!currentTemplate.trim()
                  ? "Write a template first to see previews"
                  : totalRecipients === 0
                    ? "Add recipients first"
                    : "Save changes to generate preview"}
              </p>
            ) : (
              <div className="space-y-3 mt-2">
                {previewData.previews.map((p, i) => (
                  <div key={i} className="flex gap-3">
                    {/* Chat bubble */}
                    <div className="flex-1">
                      <div className="flex items-center gap-2 mb-1">
                        <span className="text-[11px] font-medium text-gray-500 dark:text-gray-400">
                          → {p.phone_number}
                        </span>
                        {p.contact_name && (
                          <span className="text-[11px] text-gray-400">
                            ({p.contact_name})
                          </span>
                        )}
                      </div>
                      <div className="bg-green-100 dark:bg-green-900/30 text-gray-800 dark:text-gray-200 text-sm px-3 py-2 rounded-lg rounded-tl-sm max-w-md whitespace-pre-wrap">
                        {p.rendered_message}
                      </div>
                    </div>
                  </div>
                ))}
                <p className="text-[11px] text-gray-400 text-center mt-2">
                  Showing up to 5 sample messages
                </p>
              </div>
            )}
          </div>
        )}
      </section>

      {/* Contact Selector Modal */}
      {showContactModal && (
        <ContactSelectorModal
          campaignId={campaignId}
          onClose={() => setShowContactModal(false)}
        />
      )}

      <div className="sticky bottom-4 z-20">
        <div className="rounded-2xl border border-gray-200 bg-white/95 px-4 py-3 shadow-xl shadow-gray-900/5 backdrop-blur dark:border-gray-700 dark:bg-gray-900/95">
          <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
            <div>
              <p className="text-sm font-semibold text-gray-900 dark:text-gray-100">
                {campaignReady
                  ? "Campaign siap dijalankan"
                  : "Lengkapi setup campaign"}
              </p>
              <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                {readinessMessage}
              </p>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              {canEditCampaign && (
                <button
                  onClick={() => setShowContactModal(true)}
                  className="inline-flex items-center gap-1.5 rounded-xl border border-gray-200 px-3 py-2 text-sm font-medium text-gray-600 transition-colors hover:bg-gray-50 dark:border-gray-700 dark:text-gray-300 dark:hover:bg-gray-800"
                >
                  <Plus className="h-4 w-4" />
                  Recipient
                </button>
              )}

              {hasUnsavedChanges && canEditCampaign && (
                <button
                  onClick={handleSave}
                  disabled={updateMutation.isPending}
                  className="inline-flex items-center gap-1.5 rounded-xl bg-indigo-600 px-3 py-2 text-sm font-medium text-white transition-colors hover:bg-indigo-700 disabled:opacity-50"
                >
                  {updateMutation.isPending ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <Save className="h-4 w-4" />
                  )}
                  Simpan Draft
                </button>
              )}

              {canManageBlast && (isDraft || isPaused) && (
                <button
                  onClick={handleStartOrResume}
                  disabled={
                    !campaignReady ||
                    startMutation.isPending ||
                    updateMutation.isPending
                  }
                  className="inline-flex items-center gap-1.5 rounded-xl bg-emerald-600 px-4 py-2 text-sm font-semibold text-white transition-colors hover:bg-emerald-700 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {startMutation.isPending ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <Play className="h-4 w-4" />
                  )}
                  {isPaused ? "Resume Blast" : "Mulai Blast"}
                </button>
              )}

              {canManageBlast && isSending && (
                <button
                  onClick={() => pauseMutation.mutate(campaignId)}
                  disabled={pauseMutation.isPending}
                  className="inline-flex items-center gap-1.5 rounded-xl bg-amber-500 px-4 py-2 text-sm font-semibold text-white transition-colors hover:bg-amber-600 disabled:opacity-50"
                >
                  {pauseMutation.isPending ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <Pause className="h-4 w-4" />
                  )}
                  Pause
                </button>
              )}

              {canManageBlast && (isSending || isPaused) && (
                <button
                  onClick={() => cancelMutation.mutate(campaignId)}
                  disabled={cancelMutation.isPending}
                  className="inline-flex items-center gap-1.5 rounded-xl bg-red-500 px-4 py-2 text-sm font-semibold text-white transition-colors hover:bg-red-600 disabled:opacity-50"
                >
                  <XCircle className="h-4 w-4" />
                  Cancel
                </button>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Status badge (reused from list page)
// ---------------------------------------------------------------------------

const campaignStatusConfig: Record<
  string,
  { label: string; color: string; bg: string; icon: React.ElementType }
> = {
  draft: {
    label: "Draft",
    color: "text-gray-600 dark:text-gray-400",
    bg: "bg-gray-100 dark:bg-gray-800",
    icon: Clock,
  },
  sending: {
    label: "Sending",
    color: "text-blue-600 dark:text-blue-400",
    bg: "bg-blue-50 dark:bg-blue-900/30",
    icon: Send,
  },
  paused: {
    label: "Paused",
    color: "text-amber-600 dark:text-amber-400",
    bg: "bg-amber-50 dark:bg-amber-900/30",
    icon: Pause,
  },
  completed: {
    label: "Completed",
    color: "text-green-600 dark:text-green-400",
    bg: "bg-green-50 dark:bg-green-900/30",
    icon: CheckCircle2,
  },
  cancelled: {
    label: "Cancelled",
    color: "text-red-600 dark:text-red-400",
    bg: "bg-red-50 dark:bg-red-900/30",
    icon: XCircle,
  },
};

function CampaignStatusBadge({ status }: { status: string }) {
  const cfg = campaignStatusConfig[status] || campaignStatusConfig.draft;
  const Icon = cfg.icon;
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-semibold",
        cfg.bg,
        cfg.color,
      )}
    >
      <Icon className="w-3 h-3" />
      {cfg.label}
    </span>
  );
}
