import { useState } from "react";
import { Link } from "react-router-dom";
import {
  Users,
  Plus,
  Trash2,
  Clock,
  Search,
  CheckCircle2,
  AlertCircle,
  Loader2,
  ChevronRight,
} from "lucide-react";
import { cn } from "../lib/utils";
import { Pagination } from "../components/ui/Pagination";
import {
  useMarketingGroups,
  useDeleteMarketingGroup,
} from "../hooks/useMarketing";
import { Card } from "../components/ui/Card";
import { Button } from "../components/ui/Button";
import { Spinner } from "../components/ui/Spinner";
import { Select } from "../components/ui/Select";
import { EmptyState } from "../components/ui/EmptyState";
import { MarketingGenerateGroupModal } from "../components/marketing/MarketingGenerateGroupModal";
import { useAuth } from "../context/AuthContext";
import { formatDate } from "../lib/utils";
import {
  type MarketingGroup,
  type ClientType,
  CLIENT_TYPE_LABELS,
} from "../api/marketing";

// Options use snake_case values (matching API); import label map for display
const CLIENT_TYPE_OPTIONS: { value: ClientType | ""; label: string }[] = [
  { value: "", label: "Semua Tipe" },
  { value: "lembaga_negara", label: "Lembaga Negara Non Kementerian" },
  { value: "kementerian", label: "Kementerian" },
  { value: "bumn", label: "BUMN" },
  { value: "swasta_besar", label: "Perusahaan Swasta Besar" },
  { value: "asosiasi", label: "Asosiasi" },
  { value: "lpk", label: "Lembaga Pelatihan Kerja (LPK)" },
  { value: "lkp", label: "Lembaga Karier (LKP)" },
  { value: "lsp_p1", label: "LSP P1" },
  { value: "lsp_p2", label: "LSP P2" },
  { value: "lsp_p3", label: "LSP P3" },
  { value: "dinas", label: "Dinas" },
];

const statusConfig: Record<
  string,
  { label: string; color: string; bg: string; icon: React.ElementType }
> = {
  draft: {
    label: "Draft",
    color: "text-gray-600 dark:text-gray-400",
    bg: "bg-gray-100 dark:bg-gray-800",
    icon: Clock,
  },
  searching: {
    label: "Searching",
    color: "text-blue-600 dark:text-blue-400",
    bg: "bg-blue-50 dark:bg-blue-900/30",
    icon: Loader2,
  },
  done: {
    label: "Done",
    color: "text-green-600 dark:text-green-400",
    bg: "bg-green-50 dark:bg-green-900/30",
    icon: CheckCircle2,
  },
};

function GroupStatusBadge({ status }: { status: string }) {
  const cfg = statusConfig[status] || statusConfig.draft;
  const Icon = cfg.icon;
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-semibold",
        cfg.bg,
        cfg.color,
      )}
    >
      <Icon
        className={cn("h-3 w-3", status === "searching" && "animate-spin")}
      />
      {cfg.label}
    </span>
  );
}

function GroupRow({
  group,
  canManage,
  onDelete,
}: {
  group: MarketingGroup;
  canManage: boolean;
  onDelete: (id: number) => void;
}) {
  return (
    <tr className="hover:bg-gray-50 dark:hover:bg-gray-800/50 transition-colors">
      <td className="px-4 py-3">
        <Link
          to={`/marketing/groups/${group.id}`}
          className="font-medium text-gray-900 dark:text-gray-100 hover:text-indigo-600 dark:hover:text-indigo-400"
        >
          {group.name}
        </Link>
      </td>
      <td className="px-4 py-3 text-sm text-gray-600 dark:text-gray-400">
        {CLIENT_TYPE_LABELS[group.client_type] ?? group.client_type}
      </td>
      <td className="px-4 py-3 text-center text-sm text-gray-600 dark:text-gray-400">
        {group.total_clients}
      </td>
      <td className="px-4 py-3 text-center text-sm text-green-600 dark:text-green-400">
        {group.found_count}
      </td>
      <td className="px-4 py-3 text-center text-sm text-gray-600 dark:text-gray-400">
        {group.not_found_count}
      </td>
      <td className="px-4 py-3">
        <GroupStatusBadge status={group.status} />
      </td>
      <td className="px-4 py-3 text-sm text-gray-400 dark:text-gray-500">
        {formatDate(group.created_at)}
      </td>
      <td className="px-4 py-3">
        <div className="flex items-center gap-3">
          <Link
            to={`/marketing/groups/${group.id}`}
            className="text-indigo-600 hover:text-indigo-800 dark:text-indigo-400 dark:hover:text-indigo-300"
          >
            <ChevronRight className="h-4 w-4" />
          </Link>
          {canManage && (
            <button
              onClick={() => onDelete(group.id)}
              className="text-gray-400 hover:text-red-500 transition-colors"
              title="Hapus group"
            >
              <Trash2 className="h-4 w-4" />
            </button>
          )}
        </div>
      </td>
    </tr>
  );
}

export default function MarketingGetContactPage() {
  const { hasPermission } = useAuth();
  const [clientTypeFilter, setClientTypeFilter] = useState<ClientType | "">("");
  const [createModalOpen, setCreateModalOpen] = useState(false);
  const [page, setPage] = useState(1);
  const pageSize = 50;
  const canManage = hasPermission("marketing.manage");

  const { data, isLoading } = useMarketingGroups({
    ...(clientTypeFilter ? { client_type: clientTypeFilter } : {}),
    limit: pageSize,
    offset: (page - 1) * pageSize,
  });
  const deleteMutation = useDeleteMarketingGroup();

  const groups = data?.groups ?? [];
  const total = data?.total ?? 0;
  const totalPages = Math.ceil(total / pageSize);

  function handleDelete(groupId: number) {
    if (!window.confirm("Hapus group ini beserta seluruh client di dalamnya?"))
      return;
    deleteMutation.mutate(groupId);
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br from-indigo-500 to-purple-600 text-white shadow">
            <Users className="h-5 w-5" />
          </div>
          <div>
            <h1 className="text-xl font-bold text-gray-900 dark:text-gray-100">
              Marketing Get Contact
            </h1>
            <p className="text-xs text-gray-500 dark:text-gray-400">
              Kelola group client dan outbound outreach automation
            </p>
          </div>
        </div>
        {canManage && (
          <Button onClick={() => setCreateModalOpen(true)}>
            <Plus className="h-4 w-4" />
            Buat Group
          </Button>
        )}
      </div>

      {/* Filter */}
      <div className="flex items-center gap-3">
        <div className="flex items-center gap-2 text-sm text-gray-600 dark:text-gray-400">
          <Search className="h-4 w-4" />
          <span>Filter:</span>
        </div>
        <Select
          value={clientTypeFilter}
          onChange={(v) => {
            setClientTypeFilter(v as ClientType | "");
            setPage(1);
          }}
          options={CLIENT_TYPE_OPTIONS}
          className="w-56"
        />
      </div>

      {/* Table */}
      {isLoading ? (
        <div className="flex h-48 items-center justify-center">
          <Spinner size="lg" />
        </div>
      ) : groups.length === 0 ? (
        <EmptyState
          icon={Users}
          title="Belum ada group"
          description="Buat group pertama untuk mulai mengelola client"
          action={
            canManage ? (
              <Button onClick={() => setCreateModalOpen(true)}>
                <Plus className="h-4 w-4" />
                Buat Group
              </Button>
            ) : undefined
          }
        />
      ) : (
        <Card padding={false} className="overflow-hidden">
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
              <thead className="bg-gray-50 dark:bg-gray-800/50">
                <tr>
                  <th className="px-4 py-2.5 text-left text-xs font-medium uppercase tracking-wider text-gray-500 dark:text-gray-400">
                    Nama Group
                  </th>
                  <th className="px-4 py-2.5 text-left text-xs font-medium uppercase tracking-wider text-gray-500 dark:text-gray-400">
                    Tipe Client
                  </th>
                  <th className="px-4 py-2.5 text-center text-xs font-medium uppercase tracking-wider text-gray-500 dark:text-gray-400">
                    Total
                  </th>
                  <th className="px-4 py-2.5 text-center text-xs font-medium uppercase tracking-wider text-gray-500 dark:text-gray-400">
                    Ditemukan
                  </th>
                  <th className="px-4 py-2.5 text-center text-xs font-medium uppercase tracking-wider text-gray-500 dark:text-gray-400">
                    Tidak Ditemukan
                  </th>
                  <th className="px-4 py-2.5 text-left text-xs font-medium uppercase tracking-wider text-gray-500 dark:text-gray-400">
                    Status
                  </th>
                  <th className="px-4 py-2.5 text-left text-xs font-medium uppercase tracking-wider text-gray-500 dark:text-gray-400">
                    Tanggal
                  </th>
                  <th className="px-4 py-2.5 text-left text-xs font-medium uppercase tracking-wider text-gray-500 dark:text-gray-400">
                    Aksi
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-200 dark:divide-gray-700 bg-white dark:bg-gray-900">
                {groups.map((g) => (
                  <GroupRow
                    key={g.id}
                    group={g}
                    canManage={canManage}
                    onDelete={handleDelete}
                  />
                ))}
              </tbody>
            </table>
          </div>
          {/* Pagination */}
          {groups.length > 0 && (
            <div className="flex items-center justify-between px-4 py-3 border-t border-gray-100 dark:border-gray-700">
              <p className="text-sm text-gray-500 dark:text-gray-400">
                Menampilkan {(page - 1) * pageSize + 1}–
                {Math.min(page * pageSize, total)} dari {total} group
              </p>
              <Pagination
                currentPage={page}
                totalPages={totalPages}
                onPageChange={(p) => setPage(p)}
              />
            </div>
          )}
        </Card>
      )}

      {createModalOpen && (
        <MarketingGenerateGroupModal
          onClose={() => setCreateModalOpen(false)}
        />
      )}
    </div>
  );
}
