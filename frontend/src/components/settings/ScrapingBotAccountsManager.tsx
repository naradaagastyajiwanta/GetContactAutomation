import { useState, useMemo } from "react";
import {
  Plus,
  Trash2,
  Eye,
  EyeOff,
  CheckCircle2,
  Clock,
  AlertCircle,
  Loader2,
  Bot,
  ExternalLink,
} from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { Card, CardHeader, CardTitle } from "../ui/Card";
import { Button } from "../ui/Button";
import { cn } from "../../lib/utils";
import { useUpdateInstagramConfig } from "../../hooks/useConfig";
import { useHealth } from "../../hooks/useHealth";
import { apiClient } from "../../api/client";
import toast from "react-hot-toast";

type SBAccount = { username: string; api_key: string };

type SBPoolAccount = {
  username: string;
  available: boolean;
  quota_exceeded_until: string | null;
  requests_served: number;
  failures: number;
};

// ── helpers ──────────────────────────────────────────────────────────────────

function maskKey(key: string): string {
  if (key.length <= 6) return "••••••";
  return "••••••••" + key.slice(-6);
}

function StatusBadge({ account }: { account?: SBPoolAccount }) {
  if (!account) {
    return (
      <span className="inline-flex items-center gap-1 rounded-full bg-gray-100 px-2 py-0.5 text-xs text-gray-500 dark:bg-gray-700 dark:text-gray-400">
        <AlertCircle size={11} /> Unknown
      </span>
    );
  }
  if (account.available) {
    return (
      <span className="inline-flex items-center gap-1 rounded-full bg-green-100 px-2 py-0.5 text-xs font-medium text-green-700 dark:bg-green-900/30 dark:text-green-400">
        <CheckCircle2 size={11} /> Ready
      </span>
    );
  }
  const until = account.quota_exceeded_until
    ? new Date(account.quota_exceeded_until).toLocaleTimeString("id-ID", {
        hour: "2-digit",
        minute: "2-digit",
      })
    : "?";
  return (
    <span className="inline-flex items-center gap-1 rounded-full bg-amber-100 px-2 py-0.5 text-xs font-medium text-amber-700 dark:bg-amber-900/30 dark:text-amber-400">
      <Clock size={11} /> Cooldown s/d {until}
    </span>
  );
}

// ── Add account form ──────────────────────────────────────────────────────────

function AddAccountForm({
  onAdd,
  onCancel,
}: {
  onAdd: (acc: SBAccount) => void;
  onCancel: () => void;
}) {
  const [username, setUsername] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [showKey, setShowKey] = useState(false);

  const canSubmit = username.trim() && apiKey.trim();

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!canSubmit) return;
    onAdd({ username: username.trim(), api_key: apiKey.trim() });
  };

  return (
    <form
      onSubmit={handleSubmit}
      className="rounded-lg border border-blue-200 bg-blue-50/60 p-4 dark:border-blue-700/40 dark:bg-blue-900/10"
    >
      <p className="mb-3 text-sm font-medium text-gray-700 dark:text-gray-200">
        Tambah akun ScrapingBot
      </p>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <div>
          <label className="mb-1 block text-xs font-medium text-gray-500 dark:text-gray-400">
            Username
          </label>
          <input
            type="text"
            placeholder="e.g. john_doe"
            value={username}
            autoFocus
            onChange={(e) => setUsername(e.target.value)}
            className="w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 placeholder-gray-400 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500 dark:border-gray-600 dark:bg-gray-800 dark:text-gray-100 dark:placeholder-gray-500"
          />
        </div>
        <div>
          <label className="mb-1 block text-xs font-medium text-gray-500 dark:text-gray-400">
            API Key
          </label>
          <div className="relative">
            <input
              type={showKey ? "text" : "password"}
              placeholder="API key dari dashboard"
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              onKeyDown={(e) =>
                e.key === "Enter" && canSubmit && handleSubmit(e as any)
              }
              className="w-full rounded-md border border-gray-300 bg-white py-2 pl-3 pr-9 text-sm text-gray-900 placeholder-gray-400 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500 dark:border-gray-600 dark:bg-gray-800 dark:text-gray-100 dark:placeholder-gray-500"
            />
            <button
              type="button"
              onClick={() => setShowKey((v) => !v)}
              className="absolute right-2.5 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300"
            >
              {showKey ? <EyeOff size={14} /> : <Eye size={14} />}
            </button>
          </div>
        </div>
      </div>
      <div className="mt-3 flex gap-2">
        <Button type="submit" size="sm" disabled={!canSubmit}>
          Tambah
        </Button>
        <Button type="button" variant="outline" size="sm" onClick={onCancel}>
          Batal
        </Button>
      </div>
    </form>
  );
}

// ── Main component ────────────────────────────────────────────────────────────

export function ScrapingBotAccountsManager() {
  const { data: sbConfigData } = useQuery({
    queryKey: ["config", "SCRAPINGBOT_ACCOUNTS"],
    queryFn: () =>
      apiClient
        .get<{ key: string; value: string }>("/config/SCRAPINGBOT_ACCOUNTS")
        .then((r) => r.data),
  });
  const { data: health } = useHealth();
  const updateConfig = useUpdateInstagramConfig();

  const [showAddForm, setShowAddForm] = useState(false);
  const [deleteIdx, setDeleteIdx] = useState<number | null>(null);

  // Parse accounts from config
  const accounts = useMemo<SBAccount[]>(() => {
    const raw = sbConfigData?.value;
    if (!raw || raw === "") return [];
    try {
      const parsed = JSON.parse(raw);
      return Array.isArray(parsed) ? parsed : [];
    } catch {
      return [];
    }
  }, [sbConfigData]);

  // Pool runtime status from health endpoint
  const poolAccounts: SBPoolAccount[] = useMemo(() => {
    return (health as any)?.api_keys?.scrapingbot?.accounts ?? [];
  }, [health]);

  const availableCount = useMemo(
    () => poolAccounts.filter((a) => a.available).length,
    [poolAccounts],
  );

  const save = (updated: SBAccount[]) => {
    const value = updated.length > 0 ? JSON.stringify(updated) : "";
    updateConfig.mutate(
      { SCRAPINGBOT_ACCOUNTS: value },
      {
        onSuccess: () => {
          setShowAddForm(false);
          setDeleteIdx(null);
        },
      },
    );
  };

  const handleAdd = (acc: SBAccount) => {
    if (accounts.some((a) => a.username === acc.username)) {
      toast.error(`Username "${acc.username}" sudah ada`);
      return;
    }
    save([...accounts, acc]);
  };

  const handleDelete = (idx: number) => {
    save(accounts.filter((_, i) => i !== idx));
  };

  const isSaving = updateConfig.isPending;

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Bot className="h-5 w-5 text-blue-500" />
            <div>
              <CardTitle>ScrapingBot Accounts</CardTitle>
              <p className="text-xs text-gray-500 dark:text-gray-400">
                Multi-akun free tier rotation — akun bergantian otomatis, quota
                habis di-skip 24 jam
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            {accounts.length > 0 && (
              <span className="rounded-full bg-gray-100 px-2.5 py-0.5 text-xs font-medium text-gray-600 dark:bg-gray-700 dark:text-gray-300">
                {poolAccounts.length > 0
                  ? `${availableCount}/${accounts.length} ready`
                  : `${accounts.length} akun`}
              </span>
            )}
            <a
              href="https://www.scraping-bot.io/dashboard/"
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center gap-1 text-xs text-gray-400 hover:text-blue-500"
              title="Buka ScrapingBot Dashboard"
            >
              <ExternalLink size={13} />
            </a>
            <Button
              size="sm"
              onClick={() => setShowAddForm((v) => !v)}
              disabled={isSaving}
            >
              <Plus size={14} className="mr-1" />
              Tambah Akun
            </Button>
          </div>
        </div>
      </CardHeader>

      <div className="px-4 pb-4 space-y-3">
        {/* Add form */}
        {showAddForm && (
          <AddAccountForm
            onAdd={handleAdd}
            onCancel={() => setShowAddForm(false)}
          />
        )}

        {/* Empty state */}
        {accounts.length === 0 && !showAddForm && (
          <div className="rounded-lg border border-dashed border-gray-300 py-8 text-center dark:border-gray-600">
            <Bot className="mx-auto mb-2 h-8 w-8 text-gray-300 dark:text-gray-600" />
            <p className="text-sm text-gray-500 dark:text-gray-400">
              Belum ada akun ScrapingBot
            </p>
            <p className="mt-1 text-xs text-gray-400 dark:text-gray-500">
              Daftar gratis di{" "}
              <a
                href="https://www.scraping-bot.io"
                target="_blank"
                rel="noopener noreferrer"
                className="text-blue-500 hover:underline"
              >
                scraping-bot.io
              </a>
              , lalu tambah akun di sini
            </p>
          </div>
        )}

        {/* Account table */}
        {accounts.length > 0 && (
          <div className="overflow-hidden rounded-lg border border-gray-200 dark:border-gray-700">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-200 bg-gray-50 dark:border-gray-700 dark:bg-gray-800/50">
                  <th className="px-4 py-2.5 text-left text-xs font-medium text-gray-500 dark:text-gray-400">
                    #
                  </th>
                  <th className="px-4 py-2.5 text-left text-xs font-medium text-gray-500 dark:text-gray-400">
                    Username
                  </th>
                  <th className="px-4 py-2.5 text-left text-xs font-medium text-gray-500 dark:text-gray-400">
                    API Key
                  </th>
                  <th className="px-4 py-2.5 text-left text-xs font-medium text-gray-500 dark:text-gray-400">
                    Status
                  </th>
                  <th className="px-4 py-2.5 text-right text-xs font-medium text-gray-500 dark:text-gray-400">
                    Requests
                  </th>
                  <th className="px-4 py-2.5" />
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100 dark:divide-gray-700">
                {accounts.map((acc, idx) => {
                  const poolAcc = poolAccounts.find(
                    (p) => p.username === acc.username,
                  );
                  const isDeleting = deleteIdx === idx;

                  return (
                    <tr
                      key={idx}
                      className={cn(
                        "transition-colors",
                        isDeleting
                          ? "bg-red-50 dark:bg-red-900/10"
                          : "hover:bg-gray-50 dark:hover:bg-gray-800/30",
                      )}
                    >
                      <td className="px-4 py-3 text-xs text-gray-400">
                        {idx + 1}
                      </td>
                      <td className="px-4 py-3 font-mono text-sm font-medium text-gray-800 dark:text-gray-200">
                        {acc.username}
                      </td>
                      <td className="px-4 py-3 font-mono text-xs text-gray-400">
                        {maskKey(acc.api_key)}
                      </td>
                      <td className="px-4 py-3">
                        <StatusBadge account={poolAcc} />
                      </td>
                      <td className="px-4 py-3 text-right text-xs text-gray-400">
                        {poolAcc ? poolAcc.requests_served : "—"}
                      </td>
                      <td className="px-4 py-3 text-right">
                        {isDeleting ? (
                          <div className="flex items-center justify-end gap-2">
                            <span className="text-xs text-red-600 dark:text-red-400">
                              Hapus?
                            </span>
                            <button
                              onClick={() => handleDelete(idx)}
                              disabled={isSaving}
                              className="rounded px-2 py-0.5 text-xs font-medium text-white bg-red-500 hover:bg-red-600 disabled:opacity-50"
                            >
                              {isSaving ? (
                                <Loader2 size={12} className="animate-spin" />
                              ) : (
                                "Ya"
                              )}
                            </button>
                            <button
                              onClick={() => setDeleteIdx(null)}
                              className="rounded px-2 py-0.5 text-xs text-gray-500 hover:bg-gray-100 dark:hover:bg-gray-700"
                            >
                              Batal
                            </button>
                          </div>
                        ) : (
                          <button
                            onClick={() => setDeleteIdx(idx)}
                            className="rounded p-1.5 text-gray-400 hover:bg-red-50 hover:text-red-500 dark:hover:bg-red-900/20"
                            title="Hapus akun"
                          >
                            <Trash2 size={14} />
                          </button>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}

        {/* Info box */}
        {accounts.length > 0 && (
          <div className="flex items-start gap-2 rounded-md bg-blue-50 px-3 py-2 text-xs text-blue-700 dark:bg-blue-900/20 dark:text-blue-300">
            <AlertCircle size={13} className="mt-0.5 shrink-0" />
            <span>
              Akun dirotasi otomatis (round-robin). Jika satu akun kena quota
              (402), sistem skip 24 jam lalu coba akun berikutnya.
            </span>
          </div>
        )}
      </div>
    </Card>
  );
}
