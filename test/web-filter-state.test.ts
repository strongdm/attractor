import { describe, expect, it } from "vitest";

import {
  applyFilterState,
  hasActiveFilters,
  hasProjectSearchFilter,
  parseProjectFilterState,
  parseRunFilterState
} from "../apps/factory-web/src/client/lib/filter-state";

describe("web filter state helpers", () => {
  it("parses run filters and falls back on invalid values", () => {
    const filters = parseRunFilterState(new URLSearchParams("status=RUNNING&runType=planning&branch=feat"));
    expect(filters).toEqual({ status: "RUNNING", runType: "planning", branch: "feat" });

    const fallback = parseRunFilterState(new URLSearchParams("status=bogus&runType=bogus"));
    expect(fallback.status).toBe("all");
    expect(fallback.runType).toBe("all");
  });

  it("parses project query from query or legacy q param", () => {
    expect(parseProjectFilterState(new URLSearchParams("query=alpha"))).toEqual({ query: "alpha" });
    expect(parseProjectFilterState(new URLSearchParams("q=beta"))).toEqual({ query: "beta" });
  });

  it("applies and clears filter state in URL params", () => {
    const params = new URLSearchParams("status=RUNNING&q=legacy");
    const next = applyFilterState(params, { status: "all", query: "" });

    expect(next.get("status")).toBeNull();
    expect(next.get("query")).toBeNull();
    expect(next.get("q")).toBeNull();
  });

  it("detects active filter sets", () => {
    expect(hasActiveFilters({ status: "all", runType: "all", branch: "" })).toBe(false);
    expect(hasActiveFilters({ status: "RUNNING", runType: "all", branch: "" })).toBe(true);
    expect(hasProjectSearchFilter({ query: "" })).toBe(false);
    expect(hasProjectSearchFilter({ query: "proj" })).toBe(true);
  });
});
