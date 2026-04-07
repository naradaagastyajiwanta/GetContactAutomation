import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import toast from "react-hot-toast";
import {
  getWaQr,
  getWaStatus,
  sendTestMessage,
  waLogout,
  waRestart,
  getWhatsAppDevices,
  getDeviceQR,
  connectDevice,
  disconnectDevice,
  forceRecoverDevice,
  bulkSendWhatsApp,
  bulkSendDocumentWhatsApp,
  setupMyDevice,
  getMyDevices,
  deleteMyDevice,
  updateMyDeviceLabel,
  pauseDeviceAntiBan,
  resumeDeviceAntiBan,
} from "../api/whatsapp";
import { queryKeys } from "../lib/queryKeys";

export function useWaQr() {
  return useQuery({
    queryKey: queryKeys.whatsapp.qr,
    queryFn: getWaQr,
    refetchInterval: 3_000,
  });
}

export function useWaStatus() {
  return useQuery({
    queryKey: queryKeys.whatsapp.status,
    queryFn: getWaStatus,
    refetchInterval: 10_000,
  });
}

export function useSendTestMessage() {
  return useMutation({
    mutationFn: ({ to, message }: { to: string; message: string }) =>
      sendTestMessage(to, message),
    onSuccess: (data) => {
      if (data.success) {
        toast.success("Test message sent!");
      } else {
        toast.error(data.error || "Failed to send message");
      }
    },
    onError: () => {
      toast.error("Failed to send test message");
    },
  });
}

export function useWaLogout() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: waLogout,
    onSuccess: () => {
      toast.success("Logged out from WhatsApp");
      queryClient.invalidateQueries({ queryKey: queryKeys.whatsapp.all });
      queryClient.invalidateQueries({ queryKey: queryKeys.health });
    },
    onError: () => {
      toast.error("Failed to logout");
    },
  });
}

export function useWaRestart() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: waRestart,
    onSuccess: () => {
      toast.success("Restarting WhatsApp connection...");
      queryClient.invalidateQueries({ queryKey: queryKeys.whatsapp.all });
      queryClient.invalidateQueries({ queryKey: queryKeys.health });
    },
    onError: () => {
      toast.error("Failed to restart connection");
    },
  });
}

// ---------------------------------------------------------------------------
// Multi-Device Support Hooks
// ---------------------------------------------------------------------------

export function useWhatsAppDevices() {
  return useQuery({
    queryKey: queryKeys.whatsapp.devices,
    queryFn: getWhatsAppDevices,
    refetchInterval: 5_000,
  });
}

export function useDeviceQR(deviceId: string) {
  return useQuery({
    queryKey: queryKeys.whatsapp.deviceQr(deviceId),
    queryFn: () => getDeviceQR(deviceId),
    refetchInterval: 3_000,
    enabled: !!deviceId,
  });
}

export function useConnectDevice() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (deviceId: string) => connectDevice(deviceId),
    onSuccess: (_, deviceId) => {
      toast.success(`Connecting device ${deviceId}...`);
      queryClient.invalidateQueries({ queryKey: queryKeys.whatsapp.devices });
      queryClient.invalidateQueries({
        queryKey: queryKeys.whatsapp.device(deviceId),
      });
    },
    onError: (error, deviceId) => {
      toast.error(`Failed to connect device ${deviceId}`);
      console.error(error);
    },
  });
}

export function useDisconnectDevice() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (deviceId: string) => disconnectDevice(deviceId),
    onSuccess: (_, deviceId) => {
      toast.success(`Device ${deviceId} disconnected`);
      queryClient.invalidateQueries({ queryKey: queryKeys.whatsapp.devices });
      queryClient.invalidateQueries({
        queryKey: queryKeys.whatsapp.device(deviceId),
      });
    },
    onError: (error, deviceId) => {
      toast.error(`Failed to disconnect device ${deviceId}`);
      console.error(error);
    },
  });
}

export function useForceRecoverDevice() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (deviceId: string) => forceRecoverDevice(deviceId),
    onSuccess: (_, deviceId) => {
      toast.success(`Force recovery started for ${deviceId}`);
      queryClient.invalidateQueries({ queryKey: queryKeys.whatsapp.all });
      queryClient.invalidateQueries({
        queryKey: queryKeys.whatsapp.device(deviceId),
      });
      queryClient.invalidateQueries({
        queryKey: queryKeys.whatsapp.deviceQr(deviceId),
      });
    },
    onError: (error, deviceId) => {
      toast.error(`Failed to start force recovery for ${deviceId}`);
      console.error(error);
    },
  });
}

export function useBulkSendWhatsApp() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: bulkSendWhatsApp,
    onSuccess: (data) => {
      if (data.success) {
        toast.success(`${data.queued} messages queued via ${data.device_id}`);
        queryClient.invalidateQueries({ queryKey: queryKeys.whatsapp.devices });
      } else {
        toast.error(data.error || "Failed to bulk send");
      }
    },
    onError: (error) => {
      toast.error("Failed to bulk send messages");
      console.error(error);
    },
  });
}

export function useBulkSendDocumentWhatsApp() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: bulkSendDocumentWhatsApp,
    onSuccess: (data) => {
      if (data.success) {
        toast.success(`${data.queued} documents queued via ${data.device_id}`);
        queryClient.invalidateQueries({ queryKey: queryKeys.whatsapp.devices });
      } else {
        toast.error(data.error || "Failed to bulk send documents");
      }
    },
    onError: (error) => {
      toast.error("Failed to bulk send documents");
      console.error(error);
    },
  });
}

// ---------------------------------------------------------------------------
// Per-User Device (My Device) Hooks
// ---------------------------------------------------------------------------

export function useMyDevices() {
  return useQuery({
    queryKey: queryKeys.whatsapp.myDevices,
    queryFn: getMyDevices,
    refetchInterval: 5_000,
  });
}

export function useSetupMyDevice() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (label: string = "") => setupMyDevice(label),
    onSuccess: () => {
      toast.success("WhatsApp device created. Scan the QR to connect.");
      queryClient.invalidateQueries({ queryKey: queryKeys.whatsapp.myDevices });
      queryClient.invalidateQueries({ queryKey: queryKeys.whatsapp.devices });
    },
    onError: () => {
      toast.error("Failed to setup WhatsApp device");
    },
  });
}

export function useDeleteMyDevice() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (deviceId: string) => deleteMyDevice(deviceId),
    onSuccess: () => {
      toast.success("WhatsApp device removed");
      queryClient.invalidateQueries({ queryKey: queryKeys.whatsapp.myDevices });
      queryClient.invalidateQueries({ queryKey: queryKeys.whatsapp.devices });
    },
    onError: () => {
      toast.error("Failed to delete WhatsApp device");
    },
  });
}

export function useUpdateMyDeviceLabel() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ deviceId, label }: { deviceId: string; label: string }) =>
      updateMyDeviceLabel(deviceId, label),
    onSuccess: () => {
      toast.success("Device label updated");
      queryClient.invalidateQueries({ queryKey: queryKeys.whatsapp.myDevices });
    },
    onError: () => {
      toast.error("Failed to update device label");
    },
  });
}

export function usePauseAntiBan() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (deviceId: string) => pauseDeviceAntiBan(deviceId),
    onSuccess: () => {
      toast.success("Anti-ban paused");
      queryClient.invalidateQueries({ queryKey: queryKeys.whatsapp.myDevices });
    },
    onError: () => {
      toast.error("Failed to pause anti-ban");
    },
  });
}

export function useResumeAntiBan() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (deviceId: string) => resumeDeviceAntiBan(deviceId),
    onSuccess: () => {
      toast.success("Anti-ban resumed");
      queryClient.invalidateQueries({ queryKey: queryKeys.whatsapp.myDevices });
    },
    onError: () => {
      toast.error("Failed to resume anti-ban");
    },
  });
}
