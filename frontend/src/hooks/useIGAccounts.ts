import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { showIGPopup } from "../lib/igPopup";
import {
  getIGAccounts,
  createIGAccount,
  updateIGAccount,
  deleteIGAccount,
  testIGAccountLogin,
} from "../api/igAccounts";
import { queryKeys } from "../lib/queryKeys";

export function useIGAccounts() {
  return useQuery({
    queryKey: queryKeys.igAccounts,
    queryFn: getIGAccounts,
    refetchInterval: 30_000,
  });
}

export function useCreateIGAccount() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: createIGAccount,
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.igAccounts });
      showIGPopup({
        id: "ig-account-created",
        type: "success",
        title: `Akun @${data.account.username} berhasil ditambahkan`,
        message:
          'Akun sudah terdaftar. Selanjutnya import cookies agar akun bisa digunakan untuk scraping — klik tombol "Import Cookies" di kartu akun.',
        duration: 8_000,
      });
    },
    onError: (error: any) => {
      const detail: string =
        error?.response?.data?.detail || "Terjadi kesalahan tidak terduga";
      const msg = detail.toLowerCase().includes("unique")
        ? "Username ini sudah terdaftar. Gunakan username yang berbeda."
        : detail;
      showIGPopup({
        id: "ig-account-create-fail",
        type: "error",
        title: "Gagal menambahkan akun",
        message: msg,
        duration: 8_000,
      });
    },
  });
}

export function useUpdateIGAccount() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      id,
      ...payload
    }: { id: number } & Parameters<typeof updateIGAccount>[1]) =>
      updateIGAccount(id, payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.igAccounts });
      showIGPopup({
        id: "ig-account-updated",
        type: "success",
        title: "Perubahan disimpan",
        message: "Data akun Instagram berhasil diperbarui.",
        duration: 5_000,
      });
    },
    onError: (error: any) => {
      const msg =
        error?.response?.data?.detail || "Terjadi kesalahan tidak terduga";
      showIGPopup({
        id: "ig-account-update-fail",
        type: "error",
        title: "Gagal memperbarui akun",
        message: msg,
        duration: 8_000,
      });
    },
  });
}

export function useDeleteIGAccount() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: deleteIGAccount,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.igAccounts });
      showIGPopup({
        id: "ig-account-deleted",
        type: "success",
        title: "Akun berhasil dihapus",
        message:
          "Akun sudah dihapus dari sistem. Data sesi di server masih tersimpan tapi tidak akan digunakan lagi.",
        duration: 5_000,
      });
    },
    onError: (error: any) => {
      const msg =
        error?.response?.data?.detail || "Terjadi kesalahan tidak terduga";
      showIGPopup({
        id: "ig-account-delete-fail",
        type: "error",
        title: "Gagal menghapus akun",
        message: msg,
        duration: 8_000,
      });
    },
  });
}

export function useTestIGAccountLogin() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: testIGAccountLogin,
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.igAccounts });
      if (data.result.success) {
        showIGPopup({
          id: "ig-login-test-ok",
          type: "success",
          title: "Akun berhasil diverifikasi",
          message: data.result.message || "Sesi aktif dan siap digunakan.",
          duration: 6_000,
        });
      } else {
        showIGPopup({
          id: "ig-login-test-fail",
          type: "error",
          title: "Verifikasi akun gagal",
          message:
            data.result.message ||
            "Sesi tidak valid. Coba import ulang cookies dari browser kamu.",
          ctaLabel: "Import Cookies di Pengaturan",
          ctaHref: "/settings?tab=instagram",
          duration: 0,
        });
      }
    },
    onError: (error: any) => {
      const msg =
        error?.response?.data?.detail || "Terjadi kesalahan tidak terduga";
      showIGPopup({
        id: "ig-login-test-error",
        type: "error",
        title: "Gagal menguji koneksi akun",
        message: msg,
        duration: 8_000,
      });
    },
  });
}
