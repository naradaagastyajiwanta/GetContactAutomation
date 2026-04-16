import { apiClient } from "./client";
import type {
  DeviceQRResponse,
  DeviceStatusResponse,
  WhatsAppDevice,
} from "../types/waDevices";

export interface WaQrResponse {
  qr: string | null;
  dataUrl: string | null;
  connected: boolean;
  phoneNumber: string | null;
}

export interface WaStatusResponse {
  connected?: boolean;
  phoneNumber?: string | null;
  reconnectAttempt?: number;
  maxReconnectAttempts?: number;
  devices?: WhatsAppDevice[];
  antiBan?: Record<string, unknown>;
  queue?: Record<string, unknown>;
  processorActive?: boolean;
  error?: string;
}

export async function getWaQr(): Promise<WaQrResponse> {
  const { data } = await apiClient.get<WaQrResponse>("/wa/qr");
  return data;
}

export async function getWaStatus(): Promise<WaStatusResponse> {
  const { data } = await apiClient.get<WaStatusResponse>("/wa/status");
  return data;
}

export async function sendTestMessage(
  to: string,
  message: string,
  device_id = "device_1",
) {
  const { data } = await apiClient.post("/wa/send-test", {
    to,
    message,
    device_id,
  });
  return data as { success: boolean; messageId?: string; error?: string };
}

export async function waLogout() {
  const { data } = await apiClient.post("/wa/logout");
  return data as { success: boolean; message?: string; error?: string };
}

export async function waRestart() {
  const { data } = await apiClient.post("/wa/restart");
  return data as { success: boolean; message?: string; error?: string };
}

export interface BulkSendPayload {
  phone_numbers: string[];
  message: string;
  device_id: string;
}

export interface BulkSendDocumentPayload {
  phone_numbers: string[];
  file_path: string;
  file_name: string;
  caption?: string;
  device_id: string;
}

export interface BulkSendResponse {
  success: boolean;
  queued: number;
  device_id: string;
  error?: string;
}

export interface BulkSendRotatePayload {
  phone_numbers: string[];
  message: string;
  device_ids: string[];
}

export interface BulkSendDocumentRotatePayload {
  phone_numbers: string[];
  file_path: string;
  file_name: string;
  caption?: string;
  device_ids: string[];
}

export interface PerDeviceResult {
  device_id: string;
  queued: number;
}

export interface BulkSendRotateResponse {
  success: boolean;
  total_queued: number;
  per_device: PerDeviceResult[];
  error?: string;
}

/**
 * Get all WhatsApp devices with their status
 */
export async function getWhatsAppDevices(): Promise<DeviceStatusResponse> {
  const { data } = await apiClient.get<DeviceStatusResponse>("/wa/devices");
  return data;
}

/**
 * Get QR code for a specific device
 */
export async function getDeviceQR(deviceId: string): Promise<DeviceQRResponse> {
  const { data } = await apiClient.get<DeviceQRResponse>(
    `/wa/devices/${deviceId}/qr`,
  );
  return data;
}

/**
 * Connect a specific device
 */
export async function connectDevice(
  deviceId: string,
): Promise<{ success: boolean; message: string }> {
  const { data } = await apiClient.post<{ success: boolean; message: string }>(
    `/wa/devices/${deviceId}/connect`,
  );
  return data;
}

/**
 * Disconnect a specific device
 */
export async function disconnectDevice(
  deviceId: string,
): Promise<{ success: boolean; message: string }> {
  const { data } = await apiClient.post<{ success: boolean; message: string }>(
    `/wa/devices/${deviceId}/disconnect`,
  );
  return data;
}

export async function forceRecoverDevice(
  deviceId: string,
): Promise<{ success: boolean; message: string }> {
  const { data } = await apiClient.post<{ success: boolean; message: string }>(
    `/wa/devices/${deviceId}/recover`,
  );
  return data;
}

/**
 * Get status of a specific device
 */
export async function getDeviceStatus(
  deviceId: string,
): Promise<WhatsAppDevice & { queueStats?: any; antiBan?: any }> {
  const { data } = await apiClient.get<
    WhatsAppDevice & { queueStats?: any; antiBan?: any }
  >(`/wa/devices/${deviceId}/status`);
  return data;
}

/**
 * Bulk send WhatsApp text messages
 */
export async function bulkSendWhatsApp(
  payload: BulkSendPayload,
): Promise<BulkSendResponse> {
  const { data } = await apiClient.post<BulkSendResponse>(
    "/wa/bulk-send",
    payload,
  );
  return data;
}

/**
 * Bulk send WhatsApp document messages
 */
export async function bulkSendDocumentWhatsApp(
  payload: BulkSendDocumentPayload,
): Promise<BulkSendResponse> {
  const { data } = await apiClient.post<BulkSendResponse>(
    "/wa/bulk-send-document",
    payload,
  );
  return data;
}

/**
 * Bulk send text messages distributed round-robin across multiple devices
 */
export async function bulkSendRotateWhatsApp(
  payload: BulkSendRotatePayload,
): Promise<BulkSendRotateResponse> {
  const { data } = await apiClient.post<BulkSendRotateResponse>(
    "/wa/bulk-send-rotate",
    payload,
  );
  return data;
}

/**
 * Bulk send document messages distributed round-robin across multiple devices
 */
export async function bulkSendDocumentRotateWhatsApp(
  payload: BulkSendDocumentRotatePayload,
): Promise<BulkSendRotateResponse> {
  const { data } = await apiClient.post<BulkSendRotateResponse>(
    "/wa/bulk-send-document-rotate",
    payload,
  );
  return data;
}

// ---------------------------------------------------------------------------
// Per-User Device (My Device) API
// ---------------------------------------------------------------------------

export interface AntiBanStatus {
  warmUp: {
    phase: "warming" | "warmed";
    day: number;
    totalDays: number;
    progress: number;
    todaySent: number;
    todayLimit: number;
  };
  health: {
    risk: "low" | "medium" | "high" | "critical";
    paused: boolean;
    score: number;
  };
  timelock: {
    isActive: boolean;
    expiresAt: number | null;
  };
  pausedManually: boolean;
}

export interface MyDeviceEntry {
  device_id: string;
  label: string;
  has_wa_record: boolean;
  device: {
    id: string;
    name: string;
    phoneNumber: string | null;
    connectionState: string;
    isConnecting: boolean;
    metrics: {
      messagesSent: number;
      messagesFailed: number;
      lastMessageAt: number | null;
    };
    lastError: string | null;
    antiBan: AntiBanStatus;
    queueStats: {
      pending: number;
      sending: number;
      sent: number;
      failed: number;
    };
  } | null;
  error: string | null;
}

export interface MyDevicesResponse {
  devices: MyDeviceEntry[];
}

/**
 * Setup the calling user's personal WhatsApp device
 */
export async function setupMyDevice(
  label: string = "",
): Promise<{ success: boolean; device_id: string; already_existed: boolean }> {
  const { data } = await apiClient.post("/wa/me/device", { label });
  return data;
}

/**
 * Get all of the calling user's personal WhatsApp devices
 */
export async function getMyDevices(): Promise<MyDevicesResponse> {
  const { data } = await apiClient.get<MyDevicesResponse>("/wa/me/device");
  return data;
}

/**
 * Delete one of the calling user's personal WhatsApp devices
 */
export async function deleteMyDevice(
  deviceId: string,
): Promise<{ success: boolean; message?: string }> {
  const { data } = await apiClient.delete<{
    success: boolean;
    message?: string;
  }>(`/wa/me/device/${deviceId}`);
  return data;
}

/**
 * Update the label of one of the calling user's personal WhatsApp devices
 */
export async function updateMyDeviceLabel(
  deviceId: string,
  label: string,
): Promise<{ success: boolean }> {
  const { data } = await apiClient.patch<{ success: boolean }>(
    `/wa/me/device/${deviceId}/label`,
    { label },
  );
  return data;
}

// ---------------------------------------------------------------------------
// WA Blast Log
// ---------------------------------------------------------------------------

export interface WaBlastLogEntry {
  id: number;
  blast_id: string;
  phone: string;
  device_id: string;
  mode: "text" | "document";
  preview: string | null;
  triggered_by: string | null;
  created_at: string;
}

export interface WaBlastLogResponse {
  entries: WaBlastLogEntry[];
  total: number;
}

export async function getWaBlastLog(params?: {
  blast_id?: string;
  limit?: number;
  offset?: number;
}): Promise<WaBlastLogResponse> {
  const { data } = await apiClient.get<WaBlastLogResponse>("/wa/blast-log", {
    params,
  });
  return data;
}

/**
 * Pause anti-ban for a specific device
 */
export async function pauseDeviceAntiBan(
  deviceId: string,
): Promise<{ success: boolean; message?: string }> {
  const { data } = await apiClient.post<{ success: boolean; message?: string }>(
    `/wa/devices/${deviceId}/antiban/pause`,
  );
  return data;
}

/**
 * Resume anti-ban for a specific device
 */
export async function resumeDeviceAntiBan(
  deviceId: string,
): Promise<{ success: boolean; message?: string }> {
  const { data } = await apiClient.post<{ success: boolean; message?: string }>(
    `/wa/devices/${deviceId}/antiban/resume`,
  );
  return data;
}
