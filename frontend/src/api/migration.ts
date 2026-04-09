import { apiClient } from "./client";

export interface MigrationJobState {
  job_status: "idle" | "running" | "done" | "error";
  dry_run: boolean;
  create_missing: boolean;
  started_at: string | null;
  finished_at: string | null;
  matched: number;
  unmatched: number;
  unmatched_names: string[];
  created: number;
  contacts_synced: number;
  contacts_skipped: number;
  contacts_errors: number;
}

export interface MigrationStatus {
  dms_host: string;
  dms_database: string;
  dms_status: string;
  total_universities: number;
  matched_universities: number;
  unmatched_universities: number;
  total_ig_contacts: number;
  total_kontak_auto_from_ai: number;
  last_job: MigrationJobState;
}

export interface MigrationRunResult {
  status: string;
  dry_run: boolean;
  target_db: string;
  target_host: string;
}

export async function getMigrationStatus(): Promise<MigrationStatus> {
  const { data } = await apiClient.get<MigrationStatus>(
    "/migration/dms/status",
  );
  return data;
}

export async function runMigration(
  dryRun: boolean = false,
  createMissing: boolean = false,
): Promise<MigrationRunResult> {
  const { data } = await apiClient.post<MigrationRunResult>(
    "/migration/dms/run",
    null,
    {
      params: { dry_run: dryRun, create_missing: createMissing },
    },
  );
  return data;
}
