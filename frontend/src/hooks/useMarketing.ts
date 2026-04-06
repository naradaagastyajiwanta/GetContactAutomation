import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  getMarketingGroups,
  getMarketingGroup,
  createMarketingGroup,
  deleteMarketingGroup,
  getMarketingClients,
  addMarketingClient,
  deleteMarketingClient,
  createMarketingContact,
  retryMarketingClientInstagramScrape,
  retryMarketingClientInstagramContactExtraction,
  retryMarketingClientSearch,
  updateMarketingContact,
  bulkApproveGroupContacts,
  importPreview,
  importCommit,
  exportGroupClients,
  startGroupSearch,
  getSearchStatus,
  handoffGroup,
  type ClientType,
} from "../api/marketing";

// ── Query Keys ──────────────────────────────────────────────────────────────

const mkKeys = {
  all: ["marketing"] as const,
  groups: (params: Record<string, unknown>) =>
    ["marketing", "groups", params] as const,
  groupDetail: (id: number) => ["marketing", "group", id] as const,
  groupClients: (id: number, params?: Record<string, unknown>) =>
    ["marketing", "clients", id, params] as const,
  searchStatus: (id: number) => ["marketing", "search", id] as const,
};

// ── Group Hooks ─────────────────────────────────────────────────────────────

export function useMarketingGroups(params?: {
  client_type?: ClientType | "";
  limit?: number;
  offset?: number;
}) {
  return useQuery({
    queryKey: mkKeys.groups(params ?? {}),
    queryFn: () => getMarketingGroups(params),
    retry: 2,
  });
}

export function useMarketingGroupDetail(groupId: number) {
  return useQuery({
    queryKey: mkKeys.groupDetail(groupId),
    queryFn: () => getMarketingGroup(groupId),
    enabled: !!groupId,
    retry: 2,
  });
}

export function useCreateMarketingGroup() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: { name: string; client_type: ClientType }) =>
      createMarketingGroup(payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: mkKeys.all });
    },
    retry: 0,
  });
}

export function useDeleteMarketingGroup() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (groupId: number) => deleteMarketingGroup(groupId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: mkKeys.all });
    },
    retry: 0,
  });
}

export function useUpdateMarketingGroup() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      groupId,
      payload,
    }: {
      groupId: number;
      payload: { name?: string; client_type?: ClientType };
    }) => updateMarketingGroup(groupId, payload),
    onSuccess: (_data, { groupId }) => {
      qc.invalidateQueries({ queryKey: mkKeys.groupDetail(groupId) });
      qc.invalidateQueries({ queryKey: ["marketing", "groups"] });
    },
    retry: 0,
  });
}

// ── Client Hooks ────────────────────────────────────────────────────────────

export function useMarketingClients(
  groupId: number,
  options?: {
    refetchInterval?: number | false;
    limit?: number;
    offset?: number;
    q?: string;
    search_status?: string;
  },
) {
  const { limit, offset, q, search_status, ...rest } = options ?? {};
  return useQuery({
    queryKey: mkKeys.groupClients(groupId, { limit, offset, q, search_status }),
    queryFn: () =>
      getMarketingClients(groupId, { limit, offset, q, search_status }),
    enabled: !!groupId,
    refetchInterval: rest.refetchInterval,
    retry: 2,
  });
}

export function useAddMarketingClient() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ groupId, name }: { groupId: number; name: string }) =>
      addMarketingClient(groupId, { name }),
    onSuccess: (_data, { groupId }) => {
      qc.invalidateQueries({ queryKey: mkKeys.groupClients(groupId) });
      qc.invalidateQueries({ queryKey: mkKeys.groupDetail(groupId) });
    },
    retry: 0,
  });
}

export function useDeleteMarketingClient() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      clientId,
      groupId,
    }: {
      clientId: number;
      groupId: number;
    }) => deleteMarketingClient(clientId),
    onSuccess: (_data, { groupId }) => {
      qc.invalidateQueries({ queryKey: mkKeys.groupClients(groupId) });
      qc.invalidateQueries({ queryKey: mkKeys.groupDetail(groupId) });
      qc.invalidateQueries({ queryKey: ["marketing", "groups"] });
    },
    retry: 0,
  });
}

export function useBulkDeleteMarketingClients() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      groupId,
      clientIds,
    }: {
      groupId: number;
      clientIds: number[];
    }) => bulkDeleteMarketingClients(groupId, clientIds),
    onSuccess: (_data, { groupId }) => {
      qc.invalidateQueries({ queryKey: mkKeys.groupClients(groupId) });
      qc.invalidateQueries({ queryKey: mkKeys.groupDetail(groupId) });
      qc.invalidateQueries({ queryKey: ["marketing", "groups"] });
    },
    retry: 0,
  });
}

export function useCreateMarketingContact() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      clientId,
      payload,
    }: {
      clientId: number;
      payload: {
        contact_type: string;
        value: string;
        source_url?: string;
      };
    }) => createMarketingContact(clientId, payload),
    onSuccess: (_data, { clientId }) => {
      qc.invalidateQueries({
        queryKey: mkKeys.groupClients(undefined, { id: clientId }),
      });
    },
    retry: 0,
  });
}

export function useRetryMarketingClientInstagramScrape() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ clientId }: { clientId: number }) =>
      retryMarketingClientInstagramScrape(clientId),
    onSuccess: (
      _data,
      { clientId: _clientId, groupId }: { clientId: number; groupId: number },
    ) => {
      qc.invalidateQueries({ queryKey: mkKeys.groupClients(groupId) });
      qc.invalidateQueries({ queryKey: mkKeys.groupDetail(groupId) });
    },
    retry: 0,
  });
}

export function useRetryMarketingClientInstagramContactExtraction() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ clientId }: { clientId: number }) =>
      retryMarketingClientInstagramContactExtraction(clientId),
    onSuccess: (_data, { groupId }: { clientId: number; groupId: number }) => {
      qc.invalidateQueries({ queryKey: mkKeys.groupClients(groupId) });
      qc.invalidateQueries({ queryKey: mkKeys.groupDetail(groupId) });
    },
    retry: 0,
  });
}

export function useRetryMarketingClientSearch() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ clientId }: { clientId: number }) =>
      retryMarketingClientSearch(clientId),
    onSuccess: (_data, { groupId }: { clientId: number; groupId: number }) => {
      qc.invalidateQueries({ queryKey: mkKeys.groupClients(groupId) });
      qc.invalidateQueries({ queryKey: mkKeys.groupDetail(groupId) });
      qc.invalidateQueries({ queryKey: mkKeys.searchStatus(groupId) });
      qc.invalidateQueries({ queryKey: mkKeys.all });
    },
    retry: 0,
  });
}

// ── Contact Hooks ──────────────────────────────────────────────────────────

export function useUpdateMarketingContact() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      contactId,
      payload,
    }: {
      contactId: number;
      payload: {
        is_approved?: boolean;
        is_selected?: boolean;
        edited_value?: string;
      };
    }) => updateMarketingContact(contactId, payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: mkKeys.all });
    },
    retry: 0,
  });
}

export function useBulkApproveGroupContacts() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (groupId: number) => bulkApproveGroupContacts(groupId),
    onSuccess: (_data, groupId) => {
      qc.invalidateQueries({ queryKey: mkKeys.groupClients(groupId) });
      qc.invalidateQueries({ queryKey: mkKeys.groupDetail(groupId) });
    },
    retry: 0,
  });
}

// ── Import / Export Hooks ───────────────────────────────────────────────────

export function useImportPreview() {
  return useMutation({
    mutationFn: ({ groupId, file }: { groupId: number; file: File }) =>
      importPreview(groupId, file),
    retry: 0,
  });
}

export function useImportCommit() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ groupId, file }: { groupId: number; file: File }) =>
      importCommit(groupId, file),
    onSuccess: (_data, { groupId }) => {
      qc.invalidateQueries({ queryKey: mkKeys.groupClients(groupId) });
      qc.invalidateQueries({ queryKey: mkKeys.groupDetail(groupId) });
    },
    retry: 0,
  });
}

export function useExportGroupClients() {
  return useMutation({
    mutationFn: (groupId: number) => exportGroupClients(groupId),
    retry: 0,
  });
}

// ── Search Hooks ───────────────────────────────────────────────────────────

export function useStartGroupSearch() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (groupId: number) => startGroupSearch(groupId),
    onSuccess: (_data, groupId) => {
      qc.invalidateQueries({ queryKey: mkKeys.searchStatus(groupId) });
      qc.invalidateQueries({ queryKey: mkKeys.groupDetail(groupId) });
    },
    retry: 0,
  });
}

export function useSearchStatus(groupId: number, enabled = false) {
  return useQuery({
    queryKey: mkKeys.searchStatus(groupId),
    queryFn: () => getSearchStatus(groupId),
    enabled,
    refetchInterval: 3_000,
    retry: 2,
  });
}

export function useHandoffGroup() {
  return useMutation({
    mutationFn: ({
      groupId,
      handoffType,
    }: {
      groupId: number;
      handoffType: "wa_blast" | "email_blast";
    }) => handoffGroup(groupId, handoffType),
    retry: 0,
  });
}
