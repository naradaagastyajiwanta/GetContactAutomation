import { useState } from "react";
import { useParams, useNavigate, Link } from "react-router-dom";
import {
  ArrowLeft,
  CheckCircle2,
  AlertTriangle,
  Loader2,
  X,
  RotateCcw,
  Trash2,
  Instagram,
  Pencil,
} from "lucide-react";
import { cn } from "../lib/utils";
import { Card } from "../components/ui/Card";
import { Button } from "../components/ui/Button";
import { Spinner } from "../components/ui/Spinner";
import {
  useMarketingClientDetail,
  useUpdateMarketingContact,
  useDeleteMarketingClient,
  useRetryMarketingClientInstagramScrape,
  useRetryMarketingClientInstagramContactExtraction,
  useRetryMarketingClientSearch,
  useOverrideClientIgHandle,
} from "../hooks/useMarketing";
import {
  MarketingContactsPanel,
  MarketingInstagramPostsPanel,
  MarketingInstagramAccountsPanel,
  InstagramDiscoveryPanel,
} from "../components/marketing/MarketingClientResultsTable";
import { useAuth } from "../context/AuthContext";
import toast from "react-hot-toast";

type Tab = "contacts" | "posts" | "instagram";

export default function MarketingClientPage() {
  const { id } = useParams<{ id: string }>();
  const clientId = Number(id);
  const navigate = useNavigate();
  const { hasPermission } = useAuth();
  const canManage = hasPermission("marketing.manage");

  const [activeTab, setActiveTab] = useState<Tab>("contacts");
  const [igOverrideMode, setIgOverrideMode] = useState(false);
  const [igOverrideInput, setIgOverrideInput] = useState("");

  const { data: client, isLoading, error } = useMarketingClientDetail(clientId);
  const updateContact = useUpdateMarketingContact();
  const deleteClient = useDeleteMarketingClient();
  const retryInstagramScrape = useRetryMarketingClientInstagramScrape();
  const retryInstagramContactExtraction =
    useRetryMarketingClientInstagramContactExtraction();
  const retryClientSearch = useRetryMarketingClientSearch();
  const overrideIg = useOverrideClientIgHandle();

  function handleApprove(contactId: number, approved: boolean) {
    updateContact.mutate({ contactId, payload: { is_approved: approved } });
  }

  function handleEdit(contactId: number, value: string) {
    updateContact.mutate({ contactId, payload: { edited_value: value } });
  }

  function handleDelete() {
    if (!client) return;
    if (!window.confirm("Hapus client ini?")) return;
    deleteClient.mutate(
      { clientId: client.id, groupId: client.group_id },
      {
        onSuccess: () => {
          navigate(`/marketing/groups/${client.group_id}`);
        },
      },
    );
  }

  async function handleRetryInstagramScrape() {
    if (!client) return;
    try {
      const result = await retryInstagramScrape.mutateAsync({
        clientId: client.id,
        groupId: client.group_id,
      });
      if (result.posts > 0 && result.contacts_added === 0) {
        toast.success(
          `${result.message}. Post tersimpan, tapi kontak belum terdeteksi.`,
        );
      } else {
        toast.success(result.message);
      }
    } catch (err) {
      toast.error(
        err instanceof Error ? err.message : "Gagal retry IG post scrape",
      );
    }
  }

  async function handleRetryInstagramContactExtraction() {
    if (!client) return;
    try {
      const result = await retryInstagramContactExtraction.mutateAsync({
        clientId: client.id,
        groupId: client.group_id,
      });
      toast.success(result.message);
      setActiveTab("contacts");
    } catch (err) {
      toast.error(
        err instanceof Error
          ? err.message
          : "Gagal extract contact dari post Instagram",
      );
    }
  }

  async function handleRetrySearch() {
    if (!client) return;
    try {
      const result = await retryClientSearch.mutateAsync({
        clientId: client.id,
        groupId: client.group_id,
      });
      toast.success(result.message);
      setActiveTab("contacts");
    } catch (err) {
      toast.error(
        err instanceof Error ? err.message : "Gagal retry search client",
      );
    }
  }

  if (isLoading) {
    return (
      <div className="flex h-64 items-center justify-center">
        <Spinner size="lg" />
      </div>
    );
  }

  if (error || !client) {
    return (
      <div className="p-6">
        <p className="text-sm text-red-600 dark:text-red-400">
          Client tidak ditemukan atau gagal dimuat.
        </p>
        <Button
          variant="outline"
          size="sm"
          className="mt-4"
          onClick={() => navigate(-1)}
        >
          <ArrowLeft className="h-4 w-4" /> Kembali
        </Button>
      </div>
    );
  }

  const tabs: Array<{ key: Tab; label: string; count: number }> = [
    { key: "contacts", label: "Contacts", count: client.contacts?.length ?? 0 },
    { key: "posts", label: "Posts", count: client.ig_posts?.length ?? 0 },
    {
      key: "instagram",
      label: "IG Accounts",
      count: Math.max(
        client.ig_candidates?.length ?? 0,
        client.ig_handle ? 1 : 0,
      ),
    },
  ];

  return (
    <div className="mx-auto max-w-5xl space-y-5 p-4 sm:p-6">
      {/* Breadcrumb */}
      <Link
        to={`/marketing/groups/${client.group_id}`}
        className="inline-flex items-center gap-1.5 text-sm text-gray-500 transition-colors hover:text-gray-900 dark:text-gray-400 dark:hover:text-white"
      >
        <ArrowLeft className="h-4 w-4" />
        Kembali ke Group
      </Link>

      {/* Header card */}
      <Card className="space-y-3">
        <div className="flex items-start justify-between gap-4">
          <div className="min-w-0 space-y-1.5">
            <div className="flex flex-wrap items-center gap-2">
              <h1 className="text-lg font-semibold text-gray-900 dark:text-white">
                {client.name}
              </h1>
              {/* Status badge */}
              {client.search_status === "found" && (
                <span className="inline-flex items-center gap-1 rounded-full bg-green-50 px-2.5 py-1 text-xs font-semibold text-green-700 dark:bg-green-900/30 dark:text-green-400">
                  <CheckCircle2 className="h-3.5 w-3.5" /> Ditemukan
                </span>
              )}
              {client.search_status === "partial" && (
                <span className="inline-flex items-center gap-1 rounded-full bg-yellow-50 px-2.5 py-1 text-xs font-semibold text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-300">
                  Partial
                </span>
              )}
              {client.search_status === "not_found" && (
                <span className="inline-flex items-center gap-1 rounded-full bg-red-50 px-2.5 py-1 text-xs font-semibold text-red-600 dark:bg-red-900/30 dark:text-red-400">
                  <X className="h-3.5 w-3.5" /> Tidak Ditemukan
                </span>
              )}
              {client.search_status === "error" && (
                <span className="inline-flex items-center gap-1 rounded-full bg-red-50 px-2.5 py-1 text-xs font-semibold text-red-600 dark:bg-red-900/30 dark:text-red-400">
                  <AlertTriangle className="h-3.5 w-3.5" /> Error
                </span>
              )}
              {client.search_status === "searching" && (
                <span className="inline-flex items-center gap-1 rounded-full bg-blue-50 px-2.5 py-1 text-xs font-semibold text-blue-600 dark:bg-blue-900/30 dark:text-blue-400">
                  <Loader2 className="h-3.5 w-3.5 animate-spin" /> Searching...
                </span>
              )}
              {client.search_status === "pending" && (
                <span className="inline-flex items-center rounded-full bg-gray-100 px-2.5 py-1 text-xs font-semibold text-gray-500 dark:bg-gray-800 dark:text-gray-400">
                  Pending
                </span>
              )}
            </div>

            {/* IG handle display + override */}
            {igOverrideMode ? (
              <div className="flex items-center gap-1.5">
                <Instagram className="h-3.5 w-3.5 text-gray-400" />
                <span className="text-xs text-gray-400">@</span>
                <input
                  autoFocus
                  value={igOverrideInput}
                  onChange={(e) =>
                    setIgOverrideInput(e.target.value.replace("@", ""))
                  }
                  onKeyDown={(e) => {
                    if (e.key === "Escape") {
                      setIgOverrideMode(false);
                      setIgOverrideInput("");
                    }
                  }}
                  placeholder="handle_instagram"
                  className="rounded border border-indigo-400 bg-white px-2 py-0.5 text-sm focus:outline-none focus:ring-1 focus:ring-indigo-500 dark:border-indigo-600 dark:bg-gray-800 dark:text-gray-100"
                />
                <Button
                  size="sm"
                  loading={overrideIg.isPending}
                  disabled={!igOverrideInput.trim()}
                  onClick={() => {
                    overrideIg.mutate(
                      { clientId: client.id, igHandle: igOverrideInput.trim() },
                      {
                        onSuccess: () => {
                          toast.success("IG handle berhasil diperbarui");
                          setIgOverrideMode(false);
                          setIgOverrideInput("");
                        },
                        onError: () => toast.error("Gagal mengubah IG handle"),
                      },
                    );
                  }}
                >
                  Simpan
                </Button>
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => {
                    setIgOverrideMode(false);
                    setIgOverrideInput("");
                  }}
                >
                  Batal
                </Button>
              </div>
            ) : (
              <div className="flex items-center gap-1.5">
                {client.ig_handle ? (
                  <div className="flex items-center gap-1 text-sm text-gray-500 dark:text-gray-400">
                    <Instagram className="h-3.5 w-3.5" />
                    <span>@{client.ig_handle}</span>
                  </div>
                ) : (
                  <span className="text-xs text-gray-400 dark:text-gray-500">
                    Belum ada IG handle
                  </span>
                )}
                {canManage && (
                  <button
                    type="button"
                    onClick={() => {
                      setIgOverrideInput(client.ig_handle ?? "");
                      setIgOverrideMode(true);
                    }}
                    className="rounded p-0.5 text-gray-400 transition-colors hover:text-indigo-600 dark:hover:text-indigo-400"
                    title="Override IG handle secara manual"
                  >
                    <Pencil className="h-3.5 w-3.5" />
                  </button>
                )}
              </div>
            )}

            <p className="text-sm text-gray-500 dark:text-gray-400">
              {(client.contacts ?? []).length} kontak ·{" "}
              {(client.contacts ?? []).filter((c) => c.is_approved).length}{" "}
              approved
            </p>
          </div>

          {/* Action buttons */}
          <div className="flex shrink-0 items-center gap-2">
            {canManage &&
              (client.search_status === "not_found" ||
                client.search_status === "error") && (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={handleRetrySearch}
                  loading={retryClientSearch.isPending}
                >
                  <RotateCcw className="h-4 w-4" />
                  Retry Search
                </Button>
              )}
            {canManage && (
              <Button
                variant="outline"
                size="sm"
                onClick={handleDelete}
                loading={deleteClient.isPending}
                className="text-red-600 hover:border-red-300 hover:bg-red-50 dark:text-red-400 dark:hover:bg-red-950/30"
              >
                <Trash2 className="h-4 w-4" />
                Hapus
              </Button>
            )}
          </div>
        </div>

        {client.error_message && (
          <div className="rounded-lg border border-red-200 bg-red-50/60 px-3 py-2 text-xs text-red-700 dark:border-red-900/60 dark:bg-red-950/20 dark:text-red-300">
            {client.error_message}
          </div>
        )}
      </Card>

      {/* Instagram discovery summary */}
      <Card padding={false} className="overflow-hidden">
        <InstagramDiscoveryPanel client={client} />
      </Card>

      {/* Tabs */}
      <Card padding={false} className="overflow-hidden">
        <div className="border-b border-gray-200 px-4 dark:border-gray-700">
          <nav className="flex gap-4 overflow-x-auto">
            {tabs.map((tab) => (
              <button
                key={tab.key}
                type="button"
                onClick={() => setActiveTab(tab.key)}
                className={cn(
                  "whitespace-nowrap border-b-2 px-1 py-3 text-sm font-medium transition-colors",
                  activeTab === tab.key
                    ? "border-indigo-500 text-indigo-600 dark:text-indigo-400"
                    : "border-transparent text-gray-500 hover:border-gray-300 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-300",
                )}
              >
                {tab.label}
                <span className="ml-2 rounded-full bg-gray-100 px-2 py-0.5 text-xs text-gray-600 dark:bg-gray-800 dark:text-gray-300">
                  {tab.count}
                </span>
              </button>
            ))}
          </nav>
        </div>

        {activeTab === "contacts" && (
          <MarketingContactsPanel
            client={client}
            groupId={client.group_id}
            canManage={canManage}
            onApprove={handleApprove}
            onEdit={handleEdit}
            onRetryExtractContacts={handleRetryInstagramContactExtraction}
            retryingExtractContacts={retryInstagramContactExtraction.isPending}
            onRetrySearch={handleRetrySearch}
            retryingSearch={retryClientSearch.isPending}
          />
        )}
        {activeTab === "posts" && (
          <MarketingInstagramPostsPanel
            client={client}
            canManage={canManage}
            onRetry={handleRetryInstagramScrape}
            retrying={retryInstagramScrape.isPending}
          />
        )}
        {activeTab === "instagram" && (
          <MarketingInstagramAccountsPanel client={client} />
        )}
      </Card>
    </div>
  );
}
