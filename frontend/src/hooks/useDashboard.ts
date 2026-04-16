import { useQuery } from "@tanstack/react-query";
import { getDashboardStats } from "../api/dashboard";
import { queryKeys } from "../lib/queryKeys";

export function useDashboard() {
  return useQuery({
    queryKey: queryKeys.dashboard,
    queryFn: getDashboardStats,
    refetchInterval: 30_000,
  });
}
