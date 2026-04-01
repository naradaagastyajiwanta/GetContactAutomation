/**
 * WhatsApp Device Types
 *
 * Types for multi-device WhatsApp service management.
 */

export interface DeviceMetrics {
  messagesSent: number;
  messagesFailed: number;
  lastMessageAt: number | null;
}

export interface DeviceAuthRecoveryStatus {
  authResetCount: number;
  authCloseAfterCredsCount: number;
  lastCredsUpdateAt: number | null;
  lastIssue: string | null;
  lastIssueAt: number | null;
  lastRecoveryAt: number | null;
  lastRecoveryReason: string | null;
  recoveryRecommended: boolean;
}

export type DeviceConnectionState =
  | 'disconnected'
  | 'connecting'
  | 'connected'
  | 'error';

export interface WhatsAppDevice {
  id: string;
  name: string;
  phoneNumber: string | null;
  connectionState: DeviceConnectionState;
  isConnecting: boolean;
  metrics: DeviceMetrics;
  lastError: string | null;
  authRecovery: DeviceAuthRecoveryStatus;
}

export interface DeviceStatusResponse {
  devices: WhatsAppDevice[];
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

export interface DeviceQRResponse {
  deviceId: string;
  name: string;
  qr: string | null;
  connected: boolean;
  phoneNumber: string | null;
  isConnecting: boolean;
}
