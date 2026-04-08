import { useState, useRef, useEffect } from "react";
import { useQueryClient } from "@tanstack/react-query";
import {
  Plus,
  Trash2,
  Eye,
  EyeOff,
  ToggleLeft,
  ToggleRight,
  Timer,
  Instagram,
  RefreshCw,
  ShieldCheck,
  ShieldX,
  ShieldQuestion,
  ShieldAlert,
  Loader2,
  AlertCircle,
  X,
  CheckCircle2,
  Download,
  Upload,
  Cookie,
  MoreVertical,
  Pencil,
  HelpCircle,
} from "lucide-react";
import { Card, CardHeader, CardTitle } from "../ui/Card";
import { Button } from "../ui/Button";
import { Badge } from "../ui/Badge";
import { Modal } from "../ui/Modal";
import { Spinner } from "../ui/Spinner";
import { cn } from "../../lib/utils";
import {
  useIGAccounts,
  useCreateIGAccount,
  useUpdateIGAccount,
  useDeleteIGAccount,
} from "../../hooks/useIGAccounts";
import type { IGAccount, IGAccountPoolStatus } from "../../api/igAccounts";
import { exportIGSession, importIGSession } from "../../api/igAccounts";
import { IGCookieImportModal } from "./IGCookieImportModal";
import { IGSetupGuideModal } from "./IGSetupGuideModal";
import { queryKeys } from "../../lib/queryKeys";

// ---------------------------------------------------------------------------
// Add / Edit form modal
// ---------------------------------------------------------------------------

function AccountFormModal({
  isOpen,
  onClose,
  onCreated,
  initial,
}: {
  isOpen: boolean;
  onClose: () => void;
  onCreated?: (accountId: number) => void;
  initial?: IGAccount;
}) {
  const [username, setUsername] = useState(initial?.username ?? "");
  const [password, setPassword] = useState("");
  const [notes, setNotes] = useState(initial?.notes ?? "");
  const [showPw, setShowPw] = useState(false);

  const createMut = useCreateIGAccount();
  const updateMut = useUpdateIGAccount();
  const isLoading = createMut.isPending || updateMut.isPending;

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (initial) {
      const payload: Record<string, unknown> = { id: initial.id };
      if (username && username !== initial.username)
        payload.username = username;
      if (password) payload.password = password;
      if (notes !== initial.notes) payload.notes = notes;
      updateMut.mutate(payload as any, { onSuccess: () => onClose() });
    } else {
      createMut.mutate(
        { username: username.trim(), password, notes },
        {
          onSuccess: (data) => {
            onClose();
            if (onCreated && data.account?.id) {
              onCreated(data.account.id);
            }
          },
        },
      );
    }
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title={initial ? "Edit IG Account" : "Add IG Account"}
      size="sm"
    >
      <form onSubmit={handleSubmit} className="space-y-4">
        <div>
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
            Username
          </label>
          <div className="flex items-center">
            <span className="inline-flex items-center rounded-l-md border border-r-0 border-gray-300 bg-gray-50 px-3 text-sm text-gray-500 dark:border-gray-600 dark:bg-gray-700 dark:text-gray-400">
              @
            </span>
            <input
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value.replace(/^@/, ""))}
              placeholder="instagram_username"
              required={!initial}
              className="block w-full rounded-r-md border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 focus:border-indigo-500 focus:ring-indigo-500 dark:border-gray-600 dark:bg-gray-700 dark:text-gray-100"
            />
          </div>
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
            Password{" "}
            {initial && (
              <span className="text-gray-400">
                (leave blank to keep current)
              </span>
            )}
          </label>
          <div className="relative">
            <input
              type={showPw ? "text" : "password"}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder={initial ? "••••••••" : "Enter password"}
              required={!initial}
              className="block w-full rounded-md border border-gray-300 bg-white px-3 py-2 pr-10 text-sm text-gray-900 focus:border-indigo-500 focus:ring-indigo-500 dark:border-gray-600 dark:bg-gray-700 dark:text-gray-100"
            />
            <button
              type="button"
              onClick={() => setShowPw(!showPw)}
              className="absolute inset-y-0 right-0 flex items-center pr-3 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300"
            >
              {showPw ? (
                <EyeOff className="h-4 w-4" />
              ) : (
                <Eye className="h-4 w-4" />
              )}
            </button>
          </div>
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
            Notes <span className="text-gray-400">(optional)</span>
          </label>
          <input
            type="text"
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            placeholder="e.g. alt account, main account..."
            className="block w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 focus:border-indigo-500 focus:ring-indigo-500 dark:border-gray-600 dark:bg-gray-700 dark:text-gray-100"
          />
        </div>

        <div className="flex justify-end gap-2 pt-2">
          <Button type="button" variant="secondary" size="sm" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" size="sm" loading={isLoading}>
            {initial ? "Save Changes" : "Add Account"}
          </Button>
        </div>
      </form>
    </Modal>
  );
}

// ---------------------------------------------------------------------------
// Dropdown menu for secondary actions
// ---------------------------------------------------------------------------

function ActionDropdown({
  children,
  trigger,
}: {
  children: React.ReactNode;
  trigger: React.ReactNode;
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node))
        setOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open]);

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="rounded-lg p-1.5 text-gray-400 hover:bg-gray-100 hover:text-gray-600 dark:hover:bg-gray-700 dark:hover:text-gray-300"
      >
        {trigger}
      </button>
      {open && (
        <div
          className="absolute right-0 top-full z-30 mt-1 w-48 rounded-lg border border-gray-200 bg-white py-1 shadow-lg dark:border-gray-700 dark:bg-gray-800"
          onClick={() => setOpen(false)}
        >
          {children}
        </div>
      )}
    </div>
  );
}

function DropdownItem({
  icon,
  label,
  onClick,
  disabled,
  danger,
}: {
  icon: React.ReactNode;
  label: string;
  onClick: () => void;
  disabled?: boolean;
  danger?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className={cn(
        "flex w-full items-center gap-2.5 px-3 py-2 text-left text-sm transition-colors disabled:opacity-40 disabled:cursor-not-allowed",
        danger
          ? "text-red-600 hover:bg-red-50 dark:text-red-400 dark:hover:bg-red-900/20"
          : "text-gray-700 hover:bg-gray-50 dark:text-gray-300 dark:hover:bg-gray-700/50",
      )}
    >
      {icon}
      {label}
    </button>
  );
}

// ---------------------------------------------------------------------------
// Status badge for pool runtime state
// ---------------------------------------------------------------------------

function PoolStatusBadge({ poolInfo }: { poolInfo?: IGAccountPoolStatus }) {
  if (!poolInfo) {
    return (
      <Badge variant="bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-400">
        Not in pool
      </Badge>
    );
  }
  if (!poolInfo.login_ok) {
    return (
      <Badge variant="bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-400">
        Login Failed
      </Badge>
    );
  }
  if (poolInfo.cooldown_remaining_s > 0) {
    const mins = Math.ceil(poolInfo.cooldown_remaining_s / 60);
    return (
      <Badge variant="bg-yellow-100 text-yellow-700 dark:bg-yellow-900/40 dark:text-yellow-400">
        <Timer className="mr-1 h-3 w-3 inline" />
        Cooldown {mins}m
      </Badge>
    );
  }
  return (
    <Badge variant="bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-400">
      Healthy
    </Badge>
  );
}

// ---------------------------------------------------------------------------
// Login verification status icon + text
// ---------------------------------------------------------------------------

function LoginStatusIndicator({
  acct,
  isTesting,
}: {
  acct: IGAccount;
  isTesting: boolean;
}) {
  if (isTesting) {
    return (
      <div className="flex items-center gap-1.5 text-blue-600 dark:text-blue-400">
        <Loader2 className="h-4 w-4 animate-spin" />
        <span className="text-xs font-medium">Testing...</span>
      </div>
    );
  }

  const status = acct.login_status || "untested";
  const lastTest = acct.last_login_test
    ? new Date(acct.last_login_test).toLocaleString("id-ID", {
        dateStyle: "short",
        timeStyle: "short",
      })
    : null;

  const configs: Record<
    string,
    { icon: React.ReactNode; label: string; color: string }
  > = {
    success: {
      icon: <ShieldCheck className="h-4 w-4" />,
      label: "Verified",
      color: "text-green-600 dark:text-green-400",
    },
    failed: {
      icon: <ShieldX className="h-4 w-4" />,
      label: "Failed",
      color: "text-red-600 dark:text-red-400",
    },
    challenge: {
      icon: <ShieldQuestion className="h-4 w-4" />,
      label: "Needs Verify",
      color: "text-yellow-600 dark:text-yellow-400",
    },
    banned: {
      icon: <ShieldAlert className="h-4 w-4" />,
      label: "Banned",
      color: "text-red-600 dark:text-red-400",
    },
    rate_limited: {
      icon: <Timer className="h-4 w-4" />,
      label: "Rate Limited",
      color: "text-yellow-600 dark:text-yellow-400",
    },
    auth_limited: {
      icon: <ShieldQuestion className="h-4 w-4" />,
      label: "Auth Limited",
      color: "text-amber-600 dark:text-amber-400",
    },
    untested: {
      icon: <ShieldQuestion className="h-4 w-4" />,
      label: "Untested",
      color: "text-gray-400 dark:text-gray-500",
    },
  };

  const cfg = configs[status] ?? configs.untested;

  return (
    <div>
      <div className={cn("flex items-center gap-1.5", cfg.color)}>
        {cfg.icon}
        <span className="text-xs font-medium">{cfg.label}</span>
      </div>
      {lastTest && (
        <span className="text-[10px] text-gray-400 ml-5.5">{lastTest}</span>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Account Card
// ---------------------------------------------------------------------------

function AccountCard({
  acct,
  pool,
  isTesting,
  isSyncing,
  onTestLogin,
  onToggleEnabled,
  onEdit,
  onDelete,
  onExportSession,
  onImportSession,
  onCookieImport,
  testingDisabled,
}: {
  acct: IGAccount;
  pool?: IGAccountPoolStatus;
  isTesting: boolean;
  isSyncing: boolean;
  onTestLogin: () => void;
  onToggleEnabled: () => void;
  onEdit: () => void;
  onDelete: () => void;
  onExportSession: () => void;
  onImportSession: () => void;
  onCookieImport: () => void;
  testingDisabled: boolean;
}) {
  const borderColor = !acct.enabled
    ? "border-gray-200 dark:border-gray-700"
    : acct.login_status === "success"
      ? "border-green-200 dark:border-green-800"
      : acct.login_status === "auth_limited" ||
          acct.login_status === "rate_limited"
        ? "border-amber-200 dark:border-amber-800"
        : acct.login_status === "failed" || acct.login_status === "banned"
          ? "border-red-200 dark:border-red-800"
          : "border-gray-200 dark:border-gray-700";

  return (
    <div
      className={cn(
        "relative rounded-xl border bg-white p-4 transition-shadow hover:shadow-md dark:bg-gray-800",
        borderColor,
        !acct.enabled && "opacity-60",
      )}
    >
      {/* Top row: avatar + username + dropdown */}
      <div className="flex items-start justify-between">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-full bg-gradient-to-br from-purple-400 via-pink-400 to-orange-400">
            <span className="text-sm font-bold text-white">
              {acct.username.charAt(0).toUpperCase()}
            </span>
          </div>
          <div>
            <p className="text-sm font-semibold text-gray-900 dark:text-gray-100">
              @{acct.username}
            </p>
            {acct.notes && (
              <p className="text-xs text-gray-400 dark:text-gray-500 max-w-[180px] truncate">
                {acct.notes}
              </p>
            )}
          </div>
        </div>
        <ActionDropdown trigger={<MoreVertical className="h-4 w-4" />}>
          <DropdownItem
            icon={<Pencil className="h-4 w-4" />}
            label="Edit Account"
            onClick={onEdit}
          />
          <DropdownItem
            icon={
              acct.enabled ? (
                <ToggleLeft className="h-4 w-4" />
              ) : (
                <ToggleRight className="h-4 w-4" />
              )
            }
            label={acct.enabled ? "Disable" : "Enable"}
            onClick={onToggleEnabled}
          />
          <div className="my-1 border-t border-gray-100 dark:border-gray-700" />
          <DropdownItem
            icon={<Download className="h-4 w-4" />}
            label="Export Session"
            onClick={onExportSession}
            disabled={isSyncing}
          />
          <DropdownItem
            icon={<Upload className="h-4 w-4" />}
            label="Import Session"
            onClick={onImportSession}
            disabled={isSyncing}
          />
          <DropdownItem
            icon={<Cookie className="h-4 w-4" />}
            label="Import Cookies"
            onClick={onCookieImport}
          />
          <div className="my-1 border-t border-gray-100 dark:border-gray-700" />
          <DropdownItem
            icon={<Trash2 className="h-4 w-4" />}
            label="Delete"
            onClick={onDelete}
            danger
          />
        </ActionDropdown>
      </div>

      {/* Status badges row */}
      <div className="mt-3 flex flex-wrap items-center gap-2">
        {acct.enabled ? (
          <Badge variant="bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-400">
            Enabled
          </Badge>
        ) : (
          <Badge variant="bg-gray-100 text-gray-500 dark:bg-gray-700 dark:text-gray-400">
            Disabled
          </Badge>
        )}
        <PoolStatusBadge poolInfo={pool} />
        {pool && pool.profiles_today > 0 && (
          <span className="text-[11px] text-gray-400">
            {pool.profiles_today} scraped today
          </span>
        )}
      </div>

      {/* Login status + Test button */}
      <div className="mt-3 flex items-center justify-between rounded-lg bg-gray-50 px-3 py-2 dark:bg-gray-700/30">
        <LoginStatusIndicator acct={acct} isTesting={isTesting} />
        <button
          onClick={onTestLogin}
          disabled={testingDisabled}
          className={cn(
            "inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-medium transition-colors",
            "bg-indigo-100 text-indigo-700 hover:bg-indigo-200 dark:bg-indigo-900/40 dark:text-indigo-400 dark:hover:bg-indigo-900/60",
            "disabled:opacity-40 disabled:cursor-not-allowed",
          )}
        >
          {isTesting ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
          ) : (
            <Cookie className="h-3.5 w-3.5" />
          )}
          {isTesting ? "Opening..." : "Import Cookies"}
        </button>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export function IGAccountsManager() {
  const { data, isLoading, refetch } = useIGAccounts();
  const queryClient = useQueryClient();
  const deleteMut = useDeleteIGAccount();
  const updateMut = useUpdateIGAccount();

  const [showAddModal, setShowAddModal] = useState(false);
  const [showGuide, setShowGuide] = useState(false);
  const [editAccount, setEditAccount] = useState<IGAccount | null>(null);
  const [confirmDeleteId, setConfirmDeleteId] = useState<number | null>(null);
  const [lastTestResult, setLastTestResult] = useState<{
    accountId: number;
    success: boolean;
    message: string;
  } | null>(null);
  const [syncingAccountId, setSyncingAccountId] = useState<number | null>(null);
  const importFileRef = useRef<HTMLInputElement>(null);
  const [importTargetAccount, setImportTargetAccount] = useState<{
    id: number;
    username: string;
  } | null>(null);
  const [cookieImportAccount, setCookieImportAccount] = useState<{
    id: number;
    username: string;
  } | null>(null);

  const accounts = data?.accounts ?? [];
  const poolStatus = data?.pool_status ?? [];

  const poolMap = new Map<string, IGAccountPoolStatus>();
  for (const ps of poolStatus) {
    poolMap.set(ps.username, ps);
  }

  const handleToggleEnabled = (acct: IGAccount) => {
    updateMut.mutate({ id: acct.id, enabled: !acct.enabled });
  };

  const handleTestLogin = (acct: IGAccount) => {
    setLastTestResult(null);
    setCookieImportAccount({ id: acct.id, username: acct.username });
  };

  const handleAccountCreated = (accountId: number) => {
    const acct = accounts.find((a) => a.id === accountId);
    if (acct) {
      setCookieImportAccount({ id: acct.id, username: acct.username });
    } else {
      refetch().then((res) => {
        const freshAcct = res.data?.accounts?.find(
          (a: IGAccount) => a.id === accountId,
        );
        if (freshAcct) {
          setCookieImportAccount({
            id: freshAcct.id,
            username: freshAcct.username,
          });
        }
      });
    }
  };

  const handleDelete = (id: number) => {
    deleteMut.mutate(id, { onSuccess: () => setConfirmDeleteId(null) });
  };

  const handleExportSession = async (acct: IGAccount) => {
    setSyncingAccountId(acct.id);
    try {
      await exportIGSession(acct.id, acct.username);
      setLastTestResult({
        accountId: acct.id,
        success: true,
        message: `Session exported for @${acct.username}`,
      });
    } catch (e: any) {
      const msg = e?.response?.data?.detail || e?.message || "Export failed";
      setLastTestResult({ accountId: acct.id, success: false, message: msg });
    } finally {
      setSyncingAccountId(null);
    }
  };

  const handleImportSession = (acct: IGAccount) => {
    setImportTargetAccount({ id: acct.id, username: acct.username });
    importFileRef.current?.click();
  };

  const handleImportFileSelected = async (
    e: React.ChangeEvent<HTMLInputElement>,
  ) => {
    const file = e.target.files?.[0];
    if (!file || !importTargetAccount) return;
    e.target.value = "";

    setSyncingAccountId(importTargetAccount.id);
    try {
      const result = await importIGSession(importTargetAccount.id, file);
      const verified = result.verify?.status === "connected";
      setLastTestResult({
        accountId: importTargetAccount.id,
        success: verified,
        message: verified
          ? `Session imported & verified for @${importTargetAccount.username}!`
          : result.verify?.status === "auth_limited"
            ? `Session imported for @${importTargetAccount.username}, but it only has public-profile access. Following list is still unavailable.`
            : `Session imported but verification ${result.verify?.status}: ${result.verify?.reason || "unknown"}`,
      });
      await queryClient.invalidateQueries({
        queryKey: queryKeys.igAccountsHealth,
      });
      refetch();
    } catch (e: any) {
      const msg = e?.response?.data?.detail || e?.message || "Import failed";
      setLastTestResult({
        accountId: importTargetAccount.id,
        success: false,
        message: msg,
      });
    } finally {
      setSyncingAccountId(null);
      setImportTargetAccount(null);
    }
  };

  const healthyCount = poolStatus.filter((p) => p.healthy).length;
  const activePoolCount = poolStatus.length;

  return (
    <>
      {/* Hidden file input for session import */}
      <input
        ref={importFileRef}
        type="file"
        accept=".tar.gz,.tgz"
        className="hidden"
        onChange={handleImportFileSelected}
      />

      <Card padding={false}>
        <CardHeader className="flex flex-row items-center justify-between px-5 pt-5">
          <div className="flex items-center gap-2">
            <Instagram className="h-5 w-5 text-pink-500" />
            <CardTitle>Instagram Accounts</CardTitle>
            {activePoolCount > 0 && (
              <Badge variant="bg-indigo-100 text-indigo-700 dark:bg-indigo-900/40 dark:text-indigo-400">
                {healthyCount}/{activePoolCount} active
              </Badge>
            )}
          </div>
          <div className="flex gap-2">
            <button
              onClick={() => setShowGuide(true)}
              title="Cara setup Instagram"
              className="rounded-lg p-1.5 text-gray-400 hover:bg-gray-100 hover:text-gray-600 dark:hover:bg-gray-700 dark:hover:text-gray-300"
            >
              <HelpCircle className="h-4 w-4" />
            </button>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => refetch()}
              title="Refresh"
            >
              <RefreshCw className="h-4 w-4" />
            </Button>
            <Button size="sm" onClick={() => setShowAddModal(true)}>
              <Plus className="h-4 w-4" />
              Add Account
            </Button>
          </div>
        </CardHeader>

        {lastTestResult && (
          <div
            className={cn(
              "mx-5 mb-2 rounded-lg border px-3 py-2 text-xs",
              lastTestResult.success
                ? "border-green-200 bg-green-50 text-green-800 dark:border-green-800 dark:bg-green-900/20 dark:text-green-400"
                : "border-red-200 bg-red-50 text-red-800 dark:border-red-800 dark:bg-red-900/20 dark:text-red-400",
            )}
          >
            <div className="flex items-start justify-between">
              <div className="flex items-start gap-2">
                {lastTestResult.success ? (
                  <CheckCircle2 className="mt-0.5 h-3.5 w-3.5 flex-shrink-0" />
                ) : (
                  <AlertCircle className="mt-0.5 h-3.5 w-3.5 flex-shrink-0" />
                )}
                <p className="font-medium">{lastTestResult.message}</p>
              </div>
              <button
                onClick={() => setLastTestResult(null)}
                className="ml-2 flex-shrink-0 rounded p-0.5 hover:bg-black/10 dark:hover:bg-white/10"
              >
                <X className="h-3.5 w-3.5" />
              </button>
            </div>
          </div>
        )}

        <div className="p-5 pt-2">
          {isLoading ? (
            <div className="flex justify-center py-8">
              <Spinner />
            </div>
          ) : accounts.length === 0 ? (
            <div className="rounded-xl border-2 border-dashed border-gray-200 p-8 text-center dark:border-gray-700">
              <Instagram className="mx-auto h-10 w-10 text-gray-300 dark:text-gray-600" />
              <p className="mt-2 text-sm font-medium text-gray-600 dark:text-gray-400">
                No Instagram accounts configured
              </p>
              <p className="mt-1 text-xs text-gray-400 dark:text-gray-500">
                Add accounts to enable multi-account rotation for IG scraping.
                Multiple accounts help avoid rate limits.
              </p>
              <Button
                size="sm"
                className="mt-4"
                onClick={() => setShowAddModal(true)}
              >
                <Plus className="h-4 w-4" />
                Add First Account
              </Button>
            </div>
          ) : (
            <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
              {accounts.map((acct) => (
                <AccountCard
                  key={acct.id}
                  acct={acct}
                  pool={poolMap.get(acct.username)}
                  isTesting={false}
                  isSyncing={syncingAccountId === acct.id}
                  testingDisabled={false}
                  onTestLogin={() => handleTestLogin(acct)}
                  onToggleEnabled={() => handleToggleEnabled(acct)}
                  onEdit={() => setEditAccount(acct)}
                  onDelete={() => setConfirmDeleteId(acct.id)}
                  onExportSession={() => handleExportSession(acct)}
                  onImportSession={() => handleImportSession(acct)}
                  onCookieImport={() =>
                    setCookieImportAccount({
                      id: acct.id,
                      username: acct.username,
                    })
                  }
                />
              ))}
            </div>
          )}
        </div>
      </Card>

      {/* Add modal */}
      {showAddModal && (
        <AccountFormModal
          isOpen={showAddModal}
          onClose={() => setShowAddModal(false)}
          onCreated={handleAccountCreated}
        />
      )}

      {/* Edit modal */}
      {editAccount && (
        <AccountFormModal
          isOpen={!!editAccount}
          onClose={() => setEditAccount(null)}
          initial={editAccount}
        />
      )}

      {/* Delete confirmation */}
      {confirmDeleteId !== null && (
        <Modal
          isOpen
          onClose={() => setConfirmDeleteId(null)}
          title="Delete Account"
          size="sm"
        >
          <p className="text-sm text-gray-600 dark:text-gray-400">
            Are you sure you want to remove this account? The browser profile
            data will remain on disk.
          </p>
          <div className="mt-4 flex justify-end gap-2">
            <Button
              variant="secondary"
              size="sm"
              onClick={() => setConfirmDeleteId(null)}
            >
              Cancel
            </Button>
            <Button
              variant="danger"
              size="sm"
              loading={deleteMut.isPending}
              onClick={() => handleDelete(confirmDeleteId)}
            >
              Delete
            </Button>
          </div>
        </Modal>
      )}

      {/* Cookie Import modal */}
      {cookieImportAccount && (
        <IGCookieImportModal
          accountId={cookieImportAccount.id}
          username={cookieImportAccount.username}
          isOpen={true}
          onClose={() => {
            setCookieImportAccount(null);
            refetch();
          }}
        />
      )}

      <IGSetupGuideModal
        isOpen={showGuide}
        onClose={() => setShowGuide(false)}
        initialTab="accounts"
        onOpenCookieImport={() => {
          if (accounts.length > 0) {
            setCookieImportAccount({
              id: accounts[0].id,
              username: accounts[0].username,
            });
          } else {
            setShowAddModal(true);
          }
        }}
      />
    </>
  );
}
