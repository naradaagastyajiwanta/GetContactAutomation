import { useState, useEffect, useMemo } from "react";
import { useSearchParams } from "react-router-dom";
import {
  Upload,
  Building2,
  Megaphone,
  Plus,
  Download,
  ClipboardList,
  ListChecks,
  RefreshCw,
  X,
} from "lucide-react";
import { formatDistanceToNow } from "date-fns";
import { useUniversities } from "../hooks/useUniversities";
import { exportUniversitiesExcel } from "../api/universities";
import { Button } from "../components/ui/Button";
import { Card } from "../components/ui/Card";
import { Spinner } from "../components/ui/Spinner";
import { Pagination } from "../components/ui/Pagination";
import { EmptyState } from "../components/ui/EmptyState";
import { UniversityFilters } from "../components/universities/UniversityFilters";
import { UniversityTable } from "../components/universities/UniversityTable";
import { RunningAgentsBanner } from "../components/universities/RunningAgentsBanner";
import { ImportModal } from "../components/universities/ImportModal";
import { AddUniversityModal } from "../components/universities/AddUniversityModal";
import { BulkSelectModal } from "../components/universities/BulkSelectModal";
import { BulkUpdateContactsModal } from "../components/universities/BulkUpdateContactsModal";
import { AddToBlastModal } from "../components/blast/AddToBlastModal";
import { ITEMS_PER_PAGE } from "../lib/constants";
import { useAuth } from "../context/AuthContext";
import { usePageTour } from "../hooks/usePageTour";
import { UNIVERSITIES_TOUR_STEPS } from "../tours/universities.tour";

export default function UniversitiesPage() {
  const { hasPermission } = useAuth();
  const [searchParams, setSearchParams] = useSearchParams();

  // Initialize state from URL params
  const initialSearch = searchParams.get("search") || "";
  const initialStatus = searchParams.get("status") || "";
  const initialProvince = searchParams.get("province") || "";
  const initialHasIg = searchParams.get("has_ig") || "";
  const initialEnabled = searchParams.get("enabled") || "";
  const initialSort = searchParams.get("sort") || "";
  const initialGroupId = searchParams.get("group_id") || "";
  const initialPage = Math.max(1, parseInt(searchParams.get("page") || "1"));

  const [search, setSearch] = useState(initialSearch);
  const [status, setStatus] = useState(initialStatus);
  const [province, setProvince] = useState(initialProvince);
  const [hasIg, setHasIg] = useState(initialHasIg);
  const [enabledFilter, setEnabledFilter] = useState(initialEnabled);
  const [sort, setSort] = useState(initialSort);
  const [groupId, setGroupId] = useState(initialGroupId);
  const [page, setPage] = useState(initialPage);
  const [importOpen, setImportOpen] = useState(false);
  const [addOpen, setAddOpen] = useState(false);
  const [bulkSelectOpen, setBulkSelectOpen] = useState(false);
  const [bulkContactsOpen, setBulkContactsOpen] = useState(false);
  const [blastOpen, setBlastOpen] = useState(false);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [lastUpdated, setLastUpdated] = useState<Date>(new Date());
  const [isAutoRefreshing, setIsAutoRefreshing] = useState(true);
  const canManageUniversities = hasPermission("universities.manage");
  const canRunPipeline = hasPermission("pipeline.run");
  const canManageBlast = hasPermission("blast.manage");
  const canSelectUniversities =
    canManageUniversities || canRunPipeline || canManageBlast;
  usePageTour("universities", UNIVERSITIES_TOUR_STEPS);

  // Helper to update URL params
  const updateUrlParams = (updates: Record<string, string | null | number>) => {
    const newParams = new URLSearchParams(searchParams);

    Object.entries(updates).forEach(([key, value]) => {
      if (value === null || value === "") {
        newParams.delete(key);
      } else if (key === "page" && value === 1) {
        newParams.delete("page");
      } else {
        newParams.set(key, String(value));
      }
    });

    setSearchParams(newParams);
  };

  // Check if any filters are active
  const hasActiveFilters = useMemo(() => {
    return !!(
      search ||
      status ||
      province ||
      hasIg ||
      enabledFilter ||
      sort ||
      groupId
    );
  }, [search, status, province, hasIg, enabledFilter, sort, groupId]);

  // Clear all filters
  const clearFilters = () => {
    setSearch("");
    setStatus("");
    setProvince("");
    setHasIg("");
    setEnabledFilter("");
    setSort("");
    setGroupId("");
    setPage(1);
    setSelected(new Set());

    // Clear all URL params
    setSearchParams({});
  };

  const params = {
    search: search || undefined,
    status: status || undefined,
    province: province || undefined,
    has_ig: hasIg === "yes" ? true : hasIg === "no" ? false : undefined,
    enabled:
      enabledFilter === "yes"
        ? true
        : enabledFilter === "no"
          ? false
          : undefined,
    limit: ITEMS_PER_PAGE,
    offset: (page - 1) * ITEMS_PER_PAGE,
    sort_by: sort ? sort.replace(/_desc$|_asc$/, "") : undefined,
    order: sort?.endsWith("_desc")
      ? "desc"
      : sort?.endsWith("_asc")
        ? "asc"
        : undefined,
    group_id: groupId ? parseInt(groupId) : undefined,
  };

  const {
    data: result,
    isLoading,
    isFetching,
    refetch,
  } = useUniversities(params, isAutoRefreshing);

  // Track last update time
  useEffect(() => {
    if (isFetching && !isLoading) {
      setLastUpdated(new Date());
    }
  }, [isFetching, isLoading]);

  useEffect(() => {
    if (!canSelectUniversities && selected.size > 0) {
      setSelected(new Set());
    }
  }, [canSelectUniversities, selected]);

  const universities = result?.data ?? [];
  const total = result?.total ?? 0;
  const totalPages = Math.max(1, Math.ceil(total / ITEMS_PER_PAGE));

  const handleSearchChange = (value: string) => {
    setSearch(value);
    setPage(1);
    updateUrlParams({ search: value || null, page: 1 });
  };

  const handleStatusChange = (value: string) => {
    setStatus(value);
    setPage(1);
    updateUrlParams({ status: value || null, page: 1 });
  };

  const handleProvinceChange = (value: string) => {
    setProvince(value);
    setPage(1);
    updateUrlParams({ province: value || null, page: 1 });
  };

  const handleHasIgChange = (value: string) => {
    setHasIg(value);
    setPage(1);
    updateUrlParams({ has_ig: value || null, page: 1 });
  };

  const handleEnabledChange = (value: string) => {
    setEnabledFilter(value);
    setPage(1);
    updateUrlParams({ enabled: value || null, page: 1 });
  };

  const handleSortChange = (value: string) => {
    setSort(value);
    setPage(1);
    updateUrlParams({ sort: value || null, page: 1 });
  };

  const handleGroupChange = (value: string) => {
    setGroupId(value);
    setPage(1);
    updateUrlParams({ group_id: value || null, page: 1 });
  };

  const handlePageChange = (newPage: number) => {
    setPage(newPage);
    updateUrlParams({ page: newPage });
  };

  const handleExport = () => {
    if (selected.size > 0) {
      exportUniversitiesExcel({ ids: Array.from(selected) });
    } else {
      exportUniversitiesExcel({
        search: search || undefined,
        status: status || undefined,
        province: province || undefined,
        has_ig: hasIg === "yes" ? true : hasIg === "no" ? false : undefined,
        enabled:
          enabledFilter === "yes"
            ? true
            : enabledFilter === "no"
              ? false
              : undefined,
      });
    }
  };

  const from = total === 0 ? 0 : (page - 1) * ITEMS_PER_PAGE + 1;
  const to = Math.min(page * ITEMS_PER_PAGE, total);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">
          Universities
        </h1>
        <div
          data-tour="universities-actions"
          className="flex items-center gap-2"
        >
          {canManageUniversities && (
            <Button onClick={() => setAddOpen(true)}>
              <Plus className="h-4 w-4" />
              Add University
            </Button>
          )}
          {canSelectUniversities && (
            <Button variant="secondary" onClick={() => setBulkSelectOpen(true)}>
              <ClipboardList className="h-4 w-4" />
              Bulk Select
            </Button>
          )}
          {canManageUniversities && (
            <Button
              variant="secondary"
              onClick={() => setBulkContactsOpen(true)}
            >
              <ListChecks className="h-4 w-4" />
              Bulk Update Status
            </Button>
          )}
          {canManageBlast && selected.size > 0 && (
            <Button variant="secondary" onClick={() => setBlastOpen(true)}>
              <Megaphone className="h-4 w-4" />
              Add to Blast ({selected.size})
            </Button>
          )}
          <Button variant="secondary" onClick={handleExport}>
            <Download className="h-4 w-4" />
            {selected.size > 0
              ? `Export Contacts (${selected.size})`
              : "Export All Contacts"}
          </Button>
          {canManageUniversities && (
            <Button variant="secondary" onClick={() => setImportOpen(true)}>
              <Upload className="h-4 w-4" />
              Import CSV/Excel
            </Button>
          )}
        </div>
      </div>

      <div data-tour="universities-filters">
        <UniversityFilters
          search={search}
          onSearchChange={handleSearchChange}
          status={status}
          onStatusChange={handleStatusChange}
          province={province}
          onProvinceChange={handleProvinceChange}
          hasIg={hasIg}
          onHasIgChange={handleHasIgChange}
          enabled={enabledFilter}
          onEnabledChange={handleEnabledChange}
          sort={sort}
          onSortChange={handleSortChange}
          groupId={groupId}
          onGroupChange={handleGroupChange}
        />
      </div>

      {/* Active filters bar */}
      {hasActiveFilters && (
        <div className="flex items-center justify-between rounded-lg bg-indigo-50 px-4 py-2 dark:bg-indigo-950/30">
          <div className="flex flex-wrap items-center gap-2 text-sm">
            <span className="font-medium text-indigo-700 dark:text-indigo-300">
              Active filters:
            </span>
            {search && (
              <span className="flex items-center gap-1 rounded-full bg-white px-2 py-0.5 text-xs text-gray-700 dark:bg-gray-700 dark:text-gray-200">
                Search: "{search}"
                <button
                  onClick={() => handleSearchChange("")}
                  className="ml-1 rounded-full p-0.5 hover:bg-gray-200 dark:hover:bg-gray-600"
                >
                  <X className="h-3 w-3" />
                </button>
              </span>
            )}
            {status && (
              <span className="flex items-center gap-1 rounded-full bg-white px-2 py-0.5 text-xs text-gray-700 dark:bg-gray-700 dark:text-gray-200">
                Status: {status}
                <button
                  onClick={() => handleStatusChange("")}
                  className="ml-1 rounded-full p-0.5 hover:bg-gray-200 dark:hover:bg-gray-600"
                >
                  <X className="h-3 w-3" />
                </button>
              </span>
            )}
            {province && (
              <span className="flex items-center gap-1 rounded-full bg-white px-2 py-0.5 text-xs text-gray-700 dark:bg-gray-700 dark:text-gray-200">
                Province: {province}
                <button
                  onClick={() => handleProvinceChange("")}
                  className="ml-1 rounded-full p-0.5 hover:bg-gray-200 dark:hover:bg-gray-600"
                >
                  <X className="h-3 w-3" />
                </button>
              </span>
            )}
            {hasIg && (
              <span className="flex items-center gap-1 rounded-full bg-white px-2 py-0.5 text-xs text-gray-700 dark:bg-gray-700 dark:text-gray-200">
                IG: {hasIg === "yes" ? "Has IG" : "No IG"}
                <button
                  onClick={() => handleHasIgChange("")}
                  className="ml-1 rounded-full p-0.5 hover:bg-gray-200 dark:hover:bg-gray-600"
                >
                  <X className="h-3 w-3" />
                </button>
              </span>
            )}
            {groupId && (
              <span className="flex items-center gap-1 rounded-full bg-white px-2 py-0.5 text-xs text-gray-700 dark:bg-gray-700 dark:text-gray-200">
                Group: ID {groupId}
                <button
                  onClick={() => handleGroupChange("")}
                  className="ml-1 rounded-full p-0.5 hover:bg-gray-200 dark:hover:bg-gray-600"
                >
                  <X className="h-3 w-3" />
                </button>
              </span>
            )}
            {enabledFilter && (
              <span className="flex items-center gap-1 rounded-full bg-white px-2 py-0.5 text-xs text-gray-700 dark:bg-gray-700 dark:text-gray-200">
                Enabled: {enabledFilter === "yes" ? "Yes" : "No"}
                <button
                  onClick={() => handleEnabledChange("")}
                  className="ml-1 rounded-full p-0.5 hover:bg-gray-200 dark:hover:bg-gray-600"
                >
                  <X className="h-3 w-3" />
                </button>
              </span>
            )}
          </div>
          <button
            onClick={clearFilters}
            className="rounded px-3 py-1 text-xs font-medium text-indigo-700 hover:bg-indigo-100 dark:text-indigo-300 dark:hover:bg-indigo-900/50"
          >
            Clear All
          </button>
        </div>
      )}

      {/* Running agents indicator */}
      <RunningAgentsBanner />

      {/* Summary bar with auto-refresh indicator */}
      <div className="flex items-center justify-between text-sm text-gray-500 dark:text-gray-400">
        <span>
          {total > 0
            ? `Showing ${from.toLocaleString()}–${to.toLocaleString()} of ${total.toLocaleString()} universities`
            : "No universities found"}
        </span>
        <div className="flex items-center gap-3">
          {/* Auto-refresh indicator */}
          <div className="flex items-center gap-1.5">
            <button
              onClick={() => refetch()}
              className="rounded p-1 text-gray-500 hover:bg-gray-100 dark:text-gray-400 dark:hover:bg-gray-700 transition-colors"
              title="Manually refresh"
            >
              <RefreshCw className="h-3.5 w-3.5" />
            </button>
            <button
              onClick={() => setIsAutoRefreshing(!isAutoRefreshing)}
              className={`flex items-center gap-1 rounded px-2 py-0.5 text-xs transition-colors ${
                isAutoRefreshing
                  ? "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300"
                  : "bg-gray-100 text-gray-600 hover:bg-gray-200 dark:bg-gray-700 dark:text-gray-300 dark:hover:bg-gray-600"
              }`}
              title={
                isAutoRefreshing ? "Auto-refresh on (30s)" : "Auto-refresh off"
              }
            >
              <span
                className={`w-1.5 h-1.5 rounded-full ${
                  isAutoRefreshing ? "bg-emerald-500" : "bg-gray-400"
                }`}
              ></span>
              <span>{isAutoRefreshing ? "Auto" : "Off"}</span>
            </button>
            {isFetching && !isLoading ? (
              <span className="flex items-center gap-1 text-xs text-gray-500">
                <Spinner size="sm" /> Updating…
              </span>
            ) : (
              <span className="text-xs text-gray-400">
                Updated {formatDistanceToNow(lastUpdated)}
              </span>
            )}
          </div>
        </div>
      </div>

      {isLoading ? (
        <div className="flex h-64 items-center justify-center">
          <Spinner size="lg" />
        </div>
      ) : universities.length === 0 ? (
        <Card>
          <EmptyState
            icon={Building2}
            title="No universities found"
            description="Try adjusting your filters or import universities from a CSV file."
            action={
              canManageUniversities ? (
                <Button onClick={() => setImportOpen(true)} size="sm">
                  <Upload className="h-4 w-4" />
                  Import CSV
                </Button>
              ) : undefined
            }
          />
        </Card>
      ) : (
        <>
          <Card padding={false}>
            <UniversityTable
              universities={universities}
              selected={selected}
              onSelectedChange={setSelected}
              canManageUniversities={canManageUniversities}
              canRunPipeline={canRunPipeline}
              canSelectUniversities={canSelectUniversities}
            />
          </Card>
          <div className="flex justify-center">
            <Pagination
              currentPage={page}
              totalPages={totalPages}
              onPageChange={handlePageChange}
            />
          </div>
        </>
      )}

      {canManageUniversities && (
        <ImportModal isOpen={importOpen} onClose={() => setImportOpen(false)} />
      )}
      {canManageUniversities && (
        <AddUniversityModal
          isOpen={addOpen}
          onClose={() => setAddOpen(false)}
        />
      )}
      {canSelectUniversities && (
        <BulkSelectModal
          isOpen={bulkSelectOpen}
          onClose={() => setBulkSelectOpen(false)}
          currentSelected={selected}
          onSelect={setSelected}
        />
      )}
      {canManageUniversities && (
        <BulkUpdateContactsModal
          isOpen={bulkContactsOpen}
          onClose={() => setBulkContactsOpen(false)}
          onUpdated={() => {}}
        />
      )}
      {canManageBlast && (
        <AddToBlastModal
          isOpen={blastOpen}
          onClose={() => setBlastOpen(false)}
          universityIds={Array.from(selected)}
          label={`Contacts from ${selected.size} selected universities`}
        />
      )}
    </div>
  );
}
