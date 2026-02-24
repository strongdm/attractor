import type { FilterState, RunStatus, RunType } from "./types";

const RUN_STATUSES: Array<RunStatus | "all"> = [
  "all",
  "QUEUED",
  "RUNNING",
  "SUCCEEDED",
  "FAILED",
  "CANCELED",
  "TIMEOUT"
];
const RUN_TYPES: Array<RunType | "all"> = ["all", "planning", "implementation"];

export function parseRunFilterState(params: URLSearchParams): FilterState {
  const status = params.get("status") ?? "all";
  const runType = params.get("runType") ?? "all";
  const branch = params.get("branch") ?? "";

  return {
    status: RUN_STATUSES.includes(status as RunStatus | "all")
      ? (status as RunStatus | "all")
      : "all",
    runType: RUN_TYPES.includes(runType as RunType | "all")
      ? (runType as RunType | "all")
      : "all",
    branch
  };
}

export function parseProjectFilterState(params: URLSearchParams): FilterState {
  const query = params.get("query") ?? params.get("q") ?? "";
  return { query };
}

export function applyFilterState(params: URLSearchParams, patch: Partial<FilterState>): URLSearchParams {
  const next = new URLSearchParams(params);

  const entries = Object.entries(patch) as Array<[keyof FilterState, FilterState[keyof FilterState]]>;
  for (const [key, value] of entries) {
    const serialized = value === undefined ? "" : String(value);
    if (serialized.trim().length === 0 || serialized === "all") {
      next.delete(key);
      if (key === "query") {
        next.delete("q");
      }
    } else {
      next.set(key, serialized);
      if (key === "query") {
        next.delete("q");
      }
    }
  }

  return next;
}

export function hasActiveFilters(filters: Pick<FilterState, "status" | "runType" | "branch">): boolean {
  return (
    (filters.status ?? "all") !== "all" ||
    (filters.runType ?? "all") !== "all" ||
    (filters.branch ?? "").trim().length > 0
  );
}

export function hasProjectSearchFilter(filters: Pick<FilterState, "query">): boolean {
  return (filters.query ?? "").trim().length > 0;
}
