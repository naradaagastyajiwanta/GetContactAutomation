import { apiClient } from "./client";

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

export interface MyDeviceStatusResponse {
  has_device: boolean;
  device_id: string | null;
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
  error?: string;
}

export interface WaQrResponse {
  qr: string | null;
  dataUrl: string | null;
  connected: boolean;
  phoneNumber: string | null;
}

export interface WaStatusResponse {
  connected: boolean;
  phoneNumber: string | null;
  reconnectAttempt: number;
  maxReconnectAttempts: number;
}

export async function getWaQr(): Promise<WaQrResponse> {
  const { data } = await apiClient.get<WaQrResponse>("/wa/qr");
  return data;
}

export async function getWaStatus(): Promise<WaStatusResponse> {
  const { data } = await apiClient.get<WaStatusResponse>("/wa/status");
  return data;
}

export async function sendTestMessage(to: string, message: string) {
  const { data } = await apiClient.post("/wa/send-test", { to, message });
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

// ---------------------------------------------------------------------------
// Multi-Device Support
// ---------------------------------------------------------------------------

export interface DeviceMetrics {
  messagesSent: number;
  messagesFailed: number;
  lastMessageAt: number | null;
}

export type DeviceConnectionState =
  | "disconnected"
  | "connecting"
  | "connected"
  | "error";

export interface WhatsAppDevice {
  id: string;
  name: string;
  phoneNumber: string | null;
  connectionState: DeviceConnectionState;
  isConnecting: boolean;
  metrics: DeviceMetrics;
  lastError: string | null;
}

export interface DeviceStatusResponse {
  devices: WhatsAppDevice[];
}

export interface DeviceQRResponse {
  deviceId: string;
  name: string;
  qr: string | null;
  connected: boolean;
  phoneNumber: string | null;
  isConnecting: boolean;
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

/**
 * Get status of a specific device
 */
export async function getDeviceStatus(
  deviceId: string,
): Promise<WhatsAppDevice & { queueStats?: any }> {
  const { data } = await apiClient.get<WhatsAppDevice & { queueStats?: any }>(
    `/wa/devices/${deviceId}/status`,
  );
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

// ---------------------------------------------------------------------------
// Per-User Device (My Device)
// ---------------------------------------------------------------------------

/**
 * Create the current user's personal device slot (idempotent)
 */
export async function setupMyDevice(): Promise<{
  success: boolean;
  device_id: string;
  already_existed: boolean;
}> {
  const { data } = await apiClient.post<{
    success: boolean;
    device_id: string;
    already_existed: boolean;
  }>("/wa/me/device");
  return data;
}

/**
 * Get the current user's personal device status
 */
export async function getMyDevice(): Promise<MyDeviceStatusResponse> {
  const { data } = await apiClient.get<MyDeviceStatusResponse>("/wa/me/device");
  return data;
}

/**
 * Disconnect and delete the current user's personal device
 */
export async function deleteMyDevice(): Promise<{
  success: boolean;
  device_id?: string;
}> {
  const { data } = await apiClient.delete<{
    success: boolean;
    device_id?: string;
  }>("/wa/me/device");
  return data;
}

/**
 * Pause anti-ban system for a device
 */
export async function pauseDeviceAntiBan(
  deviceId: string,
): Promise<{ success: boolean; antiBan: AntiBanStatus }> {
  const { data } = await apiClient.post<{
    success: boolean;
    antiBan: AntiBanStatus;
  }>(`/wa/devices/${deviceId}/antiban/pause`);
  return data;
}

/**
 * Resume anti-ban system for a device
 */
export async function resumeDeviceAntiBan(
  deviceId: string,
): Promise<{ success: boolean; antiBan: AntiBanStatus }> {
  const { data } = await apiClient.post<{
    success: boolean;
    antiBan: AntiBanStatus;
  }>(`/wa/devices/${deviceId}/antiban/resume`);
  return data;
}
