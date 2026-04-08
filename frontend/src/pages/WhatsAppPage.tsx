import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  Smartphone,
  Send,
  LogOut,
  RefreshCw,
  FlaskConical,
  Layers,
  Zap,
  Users,
  Wifi,
  WifiOff,
  MessageCircle,
} from "lucide-react";
import {
  useWaStatus,
  useSendTestMessage,
  useWaLogout,
  useWaRestart,
} from "../hooks/useWhatsApp";
import { useStartTestConversation } from "../hooks/useConversations";
import { Button } from "../components/ui/Button";
import { DevicePanel, MyDevicePanel } from "../components/whatsapp/DevicePanel";
import { WaBlastPanel } from "../components/whatsapp/BulkSendPanel";
import { useAuth } from "../context/AuthContext";
import { cn } from "../lib/utils";
import { usePageTour } from "../hooks/usePageTour";
import { WHATSAPP_TOUR_STEPS } from "../tours/whatsapp.tour";

type TabId = "devices" | "quick-test" | "blast";

function TabButton({
  id,
  icon: Icon,
  label,
  badge,
  isActive,
  onClick,
}: {
  id: TabId;
  icon: any;
  label: string;
  badge?: string;
  isActive: boolean;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className={cn(
        "relative flex items-center gap-2 px-5 py-2.5 text-sm font-medium transition-all rounded-t-lg border-b-2",
        isActive
          ? "text-blue-600 dark:text-blue-400 border-blue-600 dark:border-blue-400 bg-white dark:bg-gray-800"
          : "text-gray-500 dark:text-gray-400 border-transparent hover:text-gray-700 dark:hover:text-gray-300 hover:border-gray-300 dark:hover:border-gray-600",
      )}
    >
      <Icon className="w-4 h-4" />
      {label}
      {badge && (
        <span className="ml-1 px-1.5 py-0.5 text-[10px] font-bold rounded-full bg-blue-100 text-blue-600 dark:bg-blue-900/40 dark:text-blue-400">
          {badge}
        </span>
      )}
    </button>
  );
}

export default function WhatsAppPage() {
  const { hasPermission } = useAuth();
  const { data: statusData } = useWaStatus();
  const sendTest = useSendTestMessage();
  const logout = useWaLogout();
  const restart = useWaRestart();
  const startTestConv = useStartTestConversation();
  const navigate = useNavigate();

  const [activeTab, setActiveTab] = useState<TabId>("devices");
  const [testPhone, setTestPhone] = useState("");
  const [testMessage, setTestMessage] = useState("");
  const [testConvPhone, setTestConvPhone] = useState("");
  const [testConvUniName, setTestConvUniName] = useState("");
  const [testConvConflict, setTestConvConflict] = useState<{
    id: number;
    state: string;
  } | null>(null);
  const [showLogoutConfirm, setShowLogoutConfirm] = useState(false);
  const canManageWhatsApp = hasPermission("whatsapp.manage");
  const isAdmin = hasPermission("*");
  usePageTour("whatsapp", WHATSAPP_TOUR_STEPS);

  useEffect(() => {
    if (
      !canManageWhatsApp &&
      activeTab !== "devices" &&
      activeTab !== "blast"
    ) {
      setActiveTab("devices");
    }
  }, [activeTab, canManageWhatsApp]);

  // Get connected devices count from status
  const connectedCount =
    (statusData as any)?.devices?.filter(
      (d: any) => d.connectionState === "connected",
    ).length || 0;
  const totalCount = (statusData as any)?.devices?.length || 0;

  // Queue metrics from status
  const queuePending = (statusData as any)?.queue?.pending || 0;
  const queueSent = (statusData as any)?.queue?.sent || 0;

  const handleSendTest = () => {
    if (!testPhone.trim() || !testMessage.trim()) return;
    sendTest.mutate(
      { to: testPhone.trim(), message: testMessage.trim() },
      {
        onSuccess: () => {
          setTestPhone("");
          setTestMessage("");
        },
      },
    );
  };

  const handleStartTestConv = (force = false) => {
    if (!testConvPhone.trim()) return;
    setTestConvConflict(null);
    startTestConv.mutate(
      {
        phone: testConvPhone.trim(),
        universityName: testConvUniName.trim() || undefined,
        force,
      },
      {
        onSuccess: (data) => {
          setTestConvPhone("");
          setTestConvUniName("");
          setTestConvConflict(null);
          navigate(`/conversations/${data.id}`);
        },
        onError: (error: any) => {
          if (error?.response?.status === 409) {
            const { existing_id, existing_state } = error.response.data;
            setTestConvConflict({ id: existing_id, state: existing_state });
          }
        },
      },
    );
  };

  const handleLogout = () => {
    logout.mutate();
    setShowLogoutConfirm(false);
  };

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
      {/* ── Header ─────────────────────────────────────────── */}
      <div className="mb-6">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="p-2.5 bg-gradient-to-br from-green-500 to-emerald-600 rounded-xl shadow-lg shadow-green-500/20">
              <MessageCircle className="w-6 h-6 text-white" />
            </div>
            <div>
              <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">
                WhatsApp
              </h1>
              <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
                Multi-device connections & messaging
              </p>
            </div>
          </div>

          {/* Status chips */}
          <div data-tour="whatsapp-status" className="flex items-center gap-2">
            <div
              className={cn(
                "flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-semibold",
                connectedCount > 0
                  ? "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400"
                  : "bg-gray-100 text-gray-500 dark:bg-gray-700 dark:text-gray-400",
              )}
            >
              {connectedCount > 0 ? (
                <Wifi className="w-3 h-3" />
              ) : (
                <WifiOff className="w-3 h-3" />
              )}
              {connectedCount}/{totalCount} online
            </div>
            {(queuePending > 0 || queueSent > 0) && (
              <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-semibold bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400">
                <Send className="w-3 h-3" />
                {queuePending > 0
                  ? `${queuePending} queued`
                  : `${queueSent} sent`}
              </div>
            )}
            {canManageWhatsApp && (
              <Button
                variant="ghost"
                size="sm"
                onClick={() => restart.mutate()}
                loading={restart.isPending}
                className="!p-2"
                title="Restart WA service"
              >
                <RefreshCw className="w-4 h-4" />
              </Button>
            )}
          </div>
        </div>
      </div>

      {/* ── Tabs ───────────────────────────────────────────── */}
      <div
        data-tour="whatsapp-tabs"
        className="flex gap-1 border-b border-gray-200 dark:border-gray-700 mb-0"
      >
        <TabButton
          id="devices"
          icon={Layers}
          label="Devices"
          badge={connectedCount > 0 ? String(connectedCount) : undefined}
          isActive={activeTab === "devices"}
          onClick={() => setActiveTab("devices")}
        />
        {canManageWhatsApp && (
          <TabButton
            id="quick-test"
            icon={Zap}
            label="Quick Test"
            isActive={activeTab === "quick-test"}
            onClick={() => setActiveTab("quick-test")}
          />
        )}
        <TabButton
          id="blast"
          icon={Users}
          label="Blast WA"
          isActive={activeTab === "blast"}
          onClick={() => setActiveTab("blast")}
        />
      </div>

      {/* ── Tab Content ────────────────────────────────────── */}
      <div className="bg-white dark:bg-gray-800 rounded-b-xl rounded-tr-xl shadow-sm border border-t-0 border-gray-200 dark:border-gray-700">
        {/* Devices Tab */}
        {activeTab === "devices" && (
          <div className="p-5 space-y-6">
            {/* All users see their own device */}
            <div>
              <h3 className="text-sm font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wider mb-3">
                My WhatsApp
              </h3>
              <MyDevicePanel canManage={canManageWhatsApp} />
            </div>

            {/* Admin only: full device list */}
            {isAdmin && (
              <div>
                <h3 className="text-sm font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wider mb-3">
                  All Devices (Admin View)
                </h3>
                <DevicePanel canManage={true} />
              </div>
            )}
          </div>
        )}

        {/* Quick Test Tab */}
        {activeTab === "quick-test" && canManageWhatsApp && (
          <div className="p-5 space-y-5">
            {connectedCount === 0 && (
              <div className="flex items-center gap-3 p-3 rounded-lg bg-amber-50 dark:bg-amber-900/15 border border-amber-200 dark:border-amber-800">
                <WifiOff className="w-4 h-4 text-amber-500 flex-shrink-0" />
                <p className="text-sm text-amber-700 dark:text-amber-300">
                  Connect at least one device in the <strong>Devices</strong>{" "}
                  tab to send messages.
                </p>
              </div>
            )}

            <div className="grid gap-5 lg:grid-cols-2">
              {/* Send Test Message */}
              <div className="rounded-xl border border-gray-200 dark:border-gray-700 p-5">
                <div className="flex items-center gap-2.5 mb-4">
                  <div className="p-2 bg-blue-100 dark:bg-blue-900/30 rounded-lg">
                    <Send className="w-4 h-4 text-blue-600 dark:text-blue-400" />
                  </div>
                  <div>
                    <h3 className="font-bold text-gray-900 dark:text-gray-100 text-sm">
                      Send Test Message
                    </h3>
                    <p className="text-xs text-gray-500 dark:text-gray-400">
                      Quick direct message test
                    </p>
                  </div>
                </div>

                <div className="space-y-3">
                  <div>
                    <label className="mb-1.5 block text-xs font-semibold text-gray-600 dark:text-gray-400 uppercase tracking-wider">
                      Phone Number
                    </label>
                    <input
                      type="text"
                      value={testPhone}
                      onChange={(e) => setTestPhone(e.target.value)}
                      placeholder="6281234567890"
                      disabled={connectedCount === 0}
                      className="w-full rounded-lg border border-gray-300 dark:border-gray-600 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500 dark:bg-gray-900 dark:text-gray-100 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                    />
                  </div>
                  <div>
                    <label className="mb-1.5 block text-xs font-semibold text-gray-600 dark:text-gray-400 uppercase tracking-wider">
                      Message
                    </label>
                    <textarea
                      value={testMessage}
                      onChange={(e) => setTestMessage(e.target.value)}
                      placeholder="Type your test message..."
                      rows={3}
                      disabled={connectedCount === 0}
                      className="w-full rounded-lg border border-gray-300 dark:border-gray-600 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500 dark:bg-gray-900 dark:text-gray-100 disabled:opacity-50 disabled:cursor-not-allowed transition-colors resize-none"
                    />
                  </div>
                  <Button
                    onClick={handleSendTest}
                    loading={sendTest.isPending}
                    disabled={
                      connectedCount === 0 ||
                      !testPhone.trim() ||
                      !testMessage.trim()
                    }
                    className="w-full"
                    size="sm"
                  >
                    <Send className="w-3.5 h-3.5" />
                    Send Message
                  </Button>
                </div>
              </div>

              {/* Start Test Conversation */}
              <div className="rounded-xl border border-gray-200 dark:border-gray-700 p-5">
                <div className="flex items-center gap-2.5 mb-4">
                  <div className="p-2 bg-purple-100 dark:bg-purple-900/30 rounded-lg">
                    <FlaskConical className="w-4 h-4 text-purple-600 dark:text-purple-400" />
                  </div>
                  <div>
                    <h3 className="font-bold text-gray-900 dark:text-gray-100 text-sm">
                      Test AI Conversation
                    </h3>
                    <p className="text-xs text-gray-500 dark:text-gray-400">
                      Full pipeline test with AI replies
                    </p>
                  </div>
                </div>

                <div className="space-y-3">
                  <div>
                    <label className="mb-1.5 block text-xs font-semibold text-gray-600 dark:text-gray-400 uppercase tracking-wider">
                      Your Phone Number
                    </label>
                    <input
                      type="text"
                      value={testConvPhone}
                      onChange={(e) => setTestConvPhone(e.target.value)}
                      placeholder="6281234567890"
                      disabled={connectedCount === 0}
                      className="w-full rounded-lg border border-gray-300 dark:border-gray-600 px-3 py-2 text-sm focus:border-purple-500 focus:outline-none focus:ring-1 focus:ring-purple-500 dark:bg-gray-900 dark:text-gray-100 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                    />
                  </div>
                  <div>
                    <label className="mb-1.5 block text-xs font-semibold text-gray-600 dark:text-gray-400 uppercase tracking-wider">
                      University Name{" "}
                      <span className="text-gray-400 normal-case">
                        (optional)
                      </span>
                    </label>
                    <input
                      type="text"
                      value={testConvUniName}
                      onChange={(e) => setTestConvUniName(e.target.value)}
                      placeholder="Universitas Test"
                      disabled={connectedCount === 0}
                      className="w-full rounded-lg border border-gray-300 dark:border-gray-600 px-3 py-2 text-sm focus:border-purple-500 focus:outline-none focus:ring-1 focus:ring-purple-500 dark:bg-gray-900 dark:text-gray-100 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                    />
                  </div>
                  <Button
                    onClick={() => handleStartTestConv(false)}
                    loading={startTestConv.isPending}
                    disabled={connectedCount === 0 || !testConvPhone.trim()}
                    variant="secondary"
                    className="w-full"
                    size="sm"
                  >
                    <FlaskConical className="w-3.5 h-3.5" />
                    Start Test Conversation
                  </Button>

                  {testConvConflict && (
                    <div className="rounded-lg border border-yellow-300 bg-yellow-50 dark:bg-yellow-900/15 dark:border-yellow-700 p-3">
                      <p className="text-xs text-yellow-800 dark:text-yellow-200 mb-2 font-medium">
                        Active conversation exists (ID: {testConvConflict.id},
                        state: {testConvConflict.state})
                      </p>
                      <div className="flex gap-2">
                        <Button
                          size="sm"
                          variant="ghost"
                          onClick={() => {
                            setTestConvConflict(null);
                            navigate(`/conversations/${testConvConflict.id}`);
                          }}
                        >
                          View Existing
                        </Button>
                        <Button
                          size="sm"
                          variant="danger"
                          onClick={() => handleStartTestConv(true)}
                          loading={startTestConv.isPending}
                        >
                          Force Restart
                        </Button>
                      </div>
                    </div>
                  )}
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Blast WA Tab */}
        {activeTab === "blast" && (
          <div className="p-5">
            <WaBlastPanel />
          </div>
        )}
      </div>

      {/* ── Footer tip ─────────────────────────────────────── */}
      <p className="mt-4 text-[11px] text-gray-400 dark:text-gray-500 text-center">
        Tip: Use multiple devices to distribute load and avoid rate limiting
      </p>

      {/* Logout Confirmation Modal */}
      {showLogoutConfirm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
          <div className="mx-4 w-full max-w-md rounded-xl bg-white p-6 shadow-2xl dark:bg-gray-800">
            <div className="flex items-center gap-3 mb-4">
              <div className="p-2 bg-red-100 rounded-full dark:bg-red-900/30">
                <LogOut className="w-5 h-5 text-red-600 dark:text-red-400" />
              </div>
              <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100">
                Restart WhatsApp Service?
              </h3>
            </div>
            <p className="text-sm text-gray-500 dark:text-gray-400 mb-6">
              This will restart all device connections. You'll need to scan QR
              codes again to reconnect.
            </p>
            <div className="flex justify-end gap-3">
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setShowLogoutConfirm(false)}
              >
                Cancel
              </Button>
              <Button
                variant="danger"
                size="sm"
                onClick={handleLogout}
                loading={logout.isPending}
              >
                <RefreshCw className="w-4 h-4" />
                Restart All
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
