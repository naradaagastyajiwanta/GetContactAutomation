/**
 * BulkSendPanel Component — Redesigned
 *
 * Clean form for bulk sending WhatsApp messages with device selection.
 */

import { useState } from "react";
import { Send, FileText, Upload, RefreshCw, Loader2, Hash } from "lucide-react";
import {
  useMyDevices,
  useBulkSendWhatsApp,
  useBulkSendDocumentWhatsApp,
} from "../../hooks/useWhatsApp";
import { cn } from "../../lib/utils";

export function BulkSendPanel() {
  const { data: myDevicesData } = useMyDevices();
  const bulkSendMutation = useBulkSendWhatsApp();
  const bulkSendDocMutation = useBulkSendDocumentWhatsApp();

  const [mode, setMode] = useState<"text" | "document">("text");
  const [selectedDeviceId, setSelectedDeviceId] = useState<string>("");
  const [phoneNumbers, setPhoneNumbers] = useState<string>("");
  const [message, setMessage] = useState<string>("");
  const [filePath, setFilePath] = useState<string>("");
  const [fileName, setFileName] = useState<string>("");
  const [caption, setCaption] = useState<string>("");

  // Only show user's own connected devices
  const connectedDevices = (myDevicesData?.devices || [])
    .filter((e) => e.device?.connectionState === "connected")
    .map((e) => ({
      id: e.device_id,
      name: e.label || e.device?.name || e.device_id,
      phoneNumber: e.device?.phoneNumber ?? null,
    }));
  const recipientCount = phoneNumbers
    .split("\n")
    .filter((n) => n.trim().length > 0).length;

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();

    if (!selectedDeviceId) return alert("Please select a device");

    const numbers = phoneNumbers
      .split("\n")
      .map((n) => n.trim())
      .filter((n) => n.length > 0);

    if (numbers.length === 0)
      return alert("Please enter at least one phone number");

    if (mode === "text") {
      if (!message.trim()) return alert("Please enter a message");
      bulkSendMutation.mutate({
        phone_numbers: numbers,
        message: message.trim(),
        device_id: selectedDeviceId,
      });
      setPhoneNumbers("");
      setMessage("");
    } else {
      if (!filePath.trim()) return alert("Please enter a file path");
      if (!fileName.trim()) return alert("Please enter a file name");
      bulkSendDocMutation.mutate({
        phone_numbers: numbers,
        file_path: filePath.trim(),
        file_name: fileName.trim(),
        caption: caption.trim() || undefined,
        device_id: selectedDeviceId,
      });
      setPhoneNumbers("");
      setFilePath("");
      setFileName("");
      setCaption("");
    }
  };

  const isSending = bulkSendMutation.isPending || bulkSendDocMutation.isPending;

  return (
    <div>
      {/* Mode Toggle */}
      <div className="inline-flex rounded-lg bg-gray-100 dark:bg-gray-900 p-0.5 mb-5">
        <button
          type="button"
          onClick={() => setMode("text")}
          className={cn(
            "flex items-center gap-1.5 px-4 py-1.5 rounded-md text-xs font-semibold transition-all",
            mode === "text"
              ? "bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 shadow-sm"
              : "text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300",
          )}
        >
          <Send className="w-3.5 h-3.5" />
          Text Message
        </button>
        <button
          type="button"
          onClick={() => setMode("document")}
          className={cn(
            "flex items-center gap-1.5 px-4 py-1.5 rounded-md text-xs font-semibold transition-all",
            mode === "document"
              ? "bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 shadow-sm"
              : "text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300",
          )}
        >
          <FileText className="w-3.5 h-3.5" />
          Document
        </button>
      </div>

      <form onSubmit={handleSubmit} className="space-y-4">
        {/* Device Selection */}
        <div>
          <label className="block text-xs font-semibold text-gray-600 dark:text-gray-400 uppercase tracking-wider mb-1.5">
            Device <span className="text-red-400">*</span>
          </label>
          <select
            value={selectedDeviceId}
            onChange={(e) => setSelectedDeviceId(e.target.value)}
            required
            className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg text-sm focus:ring-1 focus:ring-blue-500 focus:border-blue-500 dark:bg-gray-900 dark:text-gray-100 transition-colors"
          >
            <option value="">Select a connected device...</option>
            {connectedDevices.map((device) => (
              <option key={device.id} value={device.id}>
                {device.name}{" "}
                {device.phoneNumber ? `(${device.phoneNumber})` : ""}
              </option>
            ))}
          </select>
          {connectedDevices.length === 0 && (
            <p className="mt-1.5 text-xs text-amber-600 dark:text-amber-400">
              No connected devices. Connect one in the Devices tab first.
            </p>
          )}
        </div>

        {/* Phone Numbers */}
        <div>
          <label className="flex items-center justify-between mb-1.5">
            <span className="text-xs font-semibold text-gray-600 dark:text-gray-400 uppercase tracking-wider">
              Phone Numbers <span className="text-red-400">*</span>
            </span>
            {recipientCount > 0 && (
              <span className="flex items-center gap-1 text-xs font-medium text-blue-600 dark:text-blue-400">
                <Hash className="w-3 h-3" />
                {recipientCount} recipient{recipientCount !== 1 ? "s" : ""}
              </span>
            )}
          </label>
          <textarea
            value={phoneNumbers}
            onChange={(e) => setPhoneNumbers(e.target.value)}
            required
            rows={4}
            placeholder={"62812345678\n62898765432\n..."}
            className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg text-sm font-mono focus:ring-1 focus:ring-blue-500 focus:border-blue-500 dark:bg-gray-900 dark:text-gray-100 transition-colors resize-none"
          />
          <p className="mt-1 text-[11px] text-gray-400 dark:text-gray-500">
            One number per line. International format (628xxx for Indonesia).
          </p>
        </div>

        {/* Message (text mode) */}
        {mode === "text" && (
          <div>
            <label className="block text-xs font-semibold text-gray-600 dark:text-gray-400 uppercase tracking-wider mb-1.5">
              Message <span className="text-red-400">*</span>
            </label>
            <textarea
              value={message}
              onChange={(e) => setMessage(e.target.value)}
              required
              rows={4}
              placeholder="Enter your message here..."
              className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg text-sm focus:ring-1 focus:ring-blue-500 focus:border-blue-500 dark:bg-gray-900 dark:text-gray-100 transition-colors resize-none"
            />
          </div>
        )}

        {/* Document fields */}
        {mode === "document" && (
          <div className="space-y-4">
            <div>
              <label className="block text-xs font-semibold text-gray-600 dark:text-gray-400 uppercase tracking-wider mb-1.5">
                File Path <span className="text-red-400">*</span>
              </label>
              <input
                type="text"
                value={filePath}
                onChange={(e) => setFilePath(e.target.value)}
                required
                placeholder="/path/to/document.pdf"
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg font-mono text-sm focus:ring-1 focus:ring-blue-500 focus:border-blue-500 dark:bg-gray-900 dark:text-gray-100 transition-colors"
              />
            </div>
            <div>
              <label className="block text-xs font-semibold text-gray-600 dark:text-gray-400 uppercase tracking-wider mb-1.5">
                File Name <span className="text-red-400">*</span>
              </label>
              <input
                type="text"
                value={fileName}
                onChange={(e) => setFileName(e.target.value)}
                required
                placeholder="document.pdf"
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg text-sm focus:ring-1 focus:ring-blue-500 focus:border-blue-500 dark:bg-gray-900 dark:text-gray-100 transition-colors"
              />
            </div>
            <div>
              <label className="block text-xs font-semibold text-gray-600 dark:text-gray-400 uppercase tracking-wider mb-1.5">
                Caption{" "}
                <span className="text-gray-400 normal-case font-normal">
                  (optional)
                </span>
              </label>
              <textarea
                value={caption}
                onChange={(e) => setCaption(e.target.value)}
                rows={2}
                placeholder="Optional caption..."
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg text-sm focus:ring-1 focus:ring-blue-500 focus:border-blue-500 dark:bg-gray-900 dark:text-gray-100 transition-colors resize-none"
              />
            </div>
          </div>
        )}

        {/* Submit */}
        <div className="flex items-center justify-end pt-4 border-t border-gray-100 dark:border-gray-700">
          <button
            type="submit"
            disabled={
              isSending || !selectedDeviceId || connectedDevices.length === 0
            }
            className="flex items-center gap-2 px-5 py-2 bg-blue-600 hover:bg-blue-700 text-white text-sm font-semibold rounded-lg shadow-sm transition-all disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {isSending ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin" />
                Queuing...
              </>
            ) : (
              <>
                <Send className="w-4 h-4" />
                Queue{" "}
                {recipientCount > 0
                  ? `${recipientCount} Message${recipientCount !== 1 ? "s" : ""}`
                  : "Send"}
              </>
            )}
          </button>
        </div>
      </form>

      {/* Note */}
      <div className="mt-5 flex items-start gap-2 p-3 bg-gray-50 dark:bg-gray-900/50 rounded-lg border border-gray-100 dark:border-gray-700">
        <span className="text-gray-400 dark:text-gray-500 text-xs mt-px">
          i
        </span>
        <p className="text-xs text-gray-500 dark:text-gray-400 leading-relaxed">
          Messages are queued and sent with human-like delays to avoid rate
          limiting. Check device metrics for progress.
        </p>
      </div>
    </div>
  );
}
