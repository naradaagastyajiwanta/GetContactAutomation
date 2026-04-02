import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  getMarketingGroups,
  getMarketingGroup,
  createMarketingGroup,
  deleteMarketingGroup,
  getMarketingClients,
  addMarketingClient,
  deleteMarketingClient,
  updateMarketingContact,
  bulkApproveGroupContacts,
  importPreview,
  importCommit,
  exportGroupClients,
  startGroupSearch,
  getSearchStatus,
  handoffGroup,
  type ClientType,
} from '../api/marketing'

// ── Query Keys ──────────────────────────────────────────────────────────────

const mkKeys = {
  all: ['marketing'] as const,
  groups: (params: Record<string, unknown>) => ['marketing', 'groups', params] as const,
  groupDetail: (id: number) => ['marketing', 'group', id] as const,
  groupClients: (id: number) => ['marketing', 'clients', id] as const,
  searchStatus: (id: number) => ['marketing', 'search', id] as const,
}

// ── Group Hooks ─────────────────────────────────────────────────────────────

export function useMarketingGroups(params?: { client_type?: ClientType | '' }) {
  return useQuery({
    queryKey: mkKeys.groups(params ?? {}),
    queryFn: () => getMarketingGroups(params),
  })
}

export function useMarketingGroupDetail(groupId: number) {
  return useQuery({
    queryKey: mkKeys.groupDetail(groupId),
    queryFn: () => getMarketingGroup(groupId),
    enabled: !!groupId,
  })
}

export function useCreateMarketingGroup() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (payload: { name: string; client_type: ClientType }) =>
      createMarketingGroup(payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: mkKeys.all })
    },
  })
}

export function useDeleteMarketingGroup() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (groupId: number) => deleteMarketingGroup(groupId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: mkKeys.all })
    },
  })
}

// ── Client Hooks ────────────────────────────────────────────────────────────

export function useMarketingClients(
  groupId: number,
  options?: { refetchInterval?: number | false }
) {
  return useQuery({
    queryKey: mkKeys.groupClients(groupId),
    queryFn: () => getMarketingClients(groupId),
    enabled: !!groupId,
    refetchInterval: options?.refetchInterval,
  })
}

export function useAddMarketingClient() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ groupId, name }: { groupId: number; name: string }) =>
      addMarketingClient(groupId, { name }),
    onSuccess: (_data, { groupId }) => {
      qc.invalidateQueries({ queryKey: mkKeys.groupClients(groupId) })
      qc.invalidateQueries({ queryKey: mkKeys.groupDetail(groupId) })
    },
  })
}

export function useDeleteMarketingClient() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ clientId, groupId }: { clientId: number; groupId: number }) =>
      deleteMarketingClient(clientId),
    onSuccess: (_data, { groupId }) => {
      qc.invalidateQueries({ queryKey: mkKeys.groupClients(groupId) })
      qc.invalidateQueries({ queryKey: mkKeys.groupDetail(groupId) })
      qc.invalidateQueries({ queryKey: ['marketing', 'groups'] })
    },
  })
}

// ── Contact Hooks ──────────────────────────────────────────────────────────

export function useUpdateMarketingContact() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({
      contactId,
      payload,
    }: {
      contactId: number
      payload: { is_approved?: boolean; is_selected?: boolean; edited_value?: string }
    }) => updateMarketingContact(contactId, payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: mkKeys.all })
    },
  })
}

export function useBulkApproveGroupContacts() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (groupId: number) => bulkApproveGroupContacts(groupId),
    onSuccess: (_data, groupId) => {
      qc.invalidateQueries({ queryKey: mkKeys.groupClients(groupId) })
      qc.invalidateQueries({ queryKey: mkKeys.groupDetail(groupId) })
    },
  })
}

// ── Import / Export Hooks ───────────────────────────────────────────────────

export function useImportPreview() {
  return useMutation({
    mutationFn: ({ groupId, file }: { groupId: number; file: File }) =>
      importPreview(groupId, file),
  })
}

export function useImportCommit() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ groupId, file }: { groupId: number; file: File }) =>
      importCommit(groupId, file),
    onSuccess: (_data, { groupId }) => {
      qc.invalidateQueries({ queryKey: mkKeys.groupClients(groupId) })
      qc.invalidateQueries({ queryKey: mkKeys.groupDetail(groupId) })
    },
  })
}

export function useExportGroupClients() {
  return useMutation({
    mutationFn: (groupId: number) => exportGroupClients(groupId),
  })
}

// ── Search Hooks ───────────────────────────────────────────────────────────

export function useStartGroupSearch() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (groupId: number) => startGroupSearch(groupId),
    onSuccess: (_data, groupId) => {
      qc.invalidateQueries({ queryKey: mkKeys.searchStatus(groupId) })
      qc.invalidateQueries({ queryKey: mkKeys.groupDetail(groupId) })
    },
  })
}

export function useSearchStatus(groupId: number, enabled = false) {
  return useQuery({
    queryKey: mkKeys.searchStatus(groupId),
    queryFn: () => getSearchStatus(groupId),
    enabled,
    refetchInterval: 3_000,
  })
}

// ── Handoff Hook ────────────────────────────────────────────────────────────

export function useHandoffGroup() {
  return useMutation({
    mutationFn: ({
      groupId,
      handoffType,
    }: {
      groupId: number
      handoffType: 'wa_blast' | 'email_blast'
    }) => handoffGroup(groupId, handoffType),
  })
}
