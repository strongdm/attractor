import { useMemo, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import {
  createRun,
  listAttractors,
  listModels,
  listProjectRunsPage,
  listProviders
} from "../lib/api";
import { applyFilterState, hasActiveFilters, parseRunFilterState } from "../lib/filter-state";
import type { PageState, RunType } from "../lib/types";
import { DataStatePanel } from "../components/common/data-state-panel";
import { FilterBar } from "../components/common/filter-bar";
import { SectionHeader } from "../components/common/section-header";
import { StatusPill } from "../components/common/status-pill";
import { PageTitle } from "../components/layout/page-title";
import { Button } from "../components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../components/ui/card";
import { Field } from "../components/ui/field";
import { Input } from "../components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "../components/ui/table";

const RUN_STATUSES = ["all", "QUEUED", "RUNNING", "SUCCEEDED", "FAILED", "CANCELED", "TIMEOUT"] as const;
const RUN_TYPES = ["all", "planning", "implementation"] as const;
const REASONING_LEVELS = ["minimal", "low", "medium", "high", "xhigh"] as const;

export function ProjectRunsPage() {
  const params = useParams<{ projectId: string }>();
  const projectId = params.projectId ?? "";
  const queryClient = useQueryClient();
  const [searchParams, setSearchParams] = useSearchParams();
  const filters = parseRunFilterState(searchParams);

  const [runType, setRunType] = useState<RunType>("planning");
  const [attractorDefId, setAttractorDefId] = useState("");
  const [provider, setProvider] = useState("openai");
  const [modelId, setModelId] = useState("");
  const [reasoningLevel, setReasoningLevel] = useState("high");
  const [sourceBranch, setSourceBranch] = useState("main");
  const [targetBranch, setTargetBranch] = useState("attractor/new-run");
  const [specBundleId, setSpecBundleId] = useState("");
  const [temperature, setTemperature] = useState("0.2");
  const [maxTokens, setMaxTokens] = useState("");

  const runsQuery = useQuery({
    queryKey: ["project-runs-page", projectId, filters.status, filters.runType, filters.branch],
    queryFn: () =>
      listProjectRunsPage(projectId, {
        status: filters.status,
        runType: filters.runType,
        branch: filters.branch,
        limit: 100
      }),
    enabled: projectId.length > 0
  });
  const attractorsQuery = useQuery({
    queryKey: ["attractors", projectId],
    queryFn: () => listAttractors(projectId),
    enabled: projectId.length > 0
  });
  const providersQuery = useQuery({ queryKey: ["providers"], queryFn: listProviders });
  const modelsQuery = useQuery({
    queryKey: ["models", provider],
    queryFn: () => listModels(provider),
    enabled: provider.length > 0
  });

  const runs = runsQuery.data?.items ?? [];
  const hasFilters = hasActiveFilters({
    status: filters.status,
    runType: filters.runType,
    branch: filters.branch
  });
  const runsState: PageState = runsQuery.isLoading
    ? "loading"
    : runsQuery.isError
    ? "error"
    : runs.length === 0
    ? "empty"
    : "ready";

  const selectedAttractor = useMemo(
    () => (attractorDefId ? (attractorsQuery.data ?? []).find((item) => item.id === attractorDefId) : undefined),
    [attractorDefId, attractorsQuery.data]
  );

  const createRunMutation = useMutation({
    mutationFn: () => {
      if (!attractorDefId) {
        throw new Error("Attractor definition is required");
      }
      if (!modelId) {
        throw new Error("Model ID is required");
      }
      if (sourceBranch.trim().length === 0 || targetBranch.trim().length === 0) {
        throw new Error("Source and target branches are required");
      }

      const parsedTemperature = Number.parseFloat(temperature);
      if (Number.isNaN(parsedTemperature)) {
        throw new Error("Temperature must be a valid number");
      }

      if (runType === "implementation" && specBundleId.trim().length === 0) {
        throw new Error("Implementation runs require a spec bundle ID");
      }

      const parsedMaxTokens = maxTokens.trim().length > 0 ? Number.parseInt(maxTokens, 10) : undefined;
      if (parsedMaxTokens !== undefined && Number.isNaN(parsedMaxTokens)) {
        throw new Error("Max tokens must be a valid integer");
      }

      return createRun({
        projectId,
        attractorDefId,
        runType,
        sourceBranch: sourceBranch.trim(),
        targetBranch: targetBranch.trim(),
        ...(runType === "implementation" ? { specBundleId: specBundleId.trim() } : {}),
        modelConfig: {
          provider,
          modelId,
          reasoningLevel: reasoningLevel as "minimal" | "low" | "medium" | "high" | "xhigh",
          temperature: parsedTemperature,
          ...(parsedMaxTokens !== undefined ? { maxTokens: parsedMaxTokens } : {})
        }
      });
    },
    onSuccess: (payload) => {
      toast.success(`Run queued: ${payload.runId}`);
      void queryClient.invalidateQueries({ queryKey: ["project-runs-page", projectId] });
      void queryClient.invalidateQueries({ queryKey: ["project-runs", projectId] });
    },
    onError: (error) => {
      toast.error(error instanceof Error ? error.message : String(error));
    }
  });

  return (
    <div>
      <PageTitle title="Runs" description="Launch branch-isolated planning and implementation runs." />

      <div className="grid gap-4 lg:grid-cols-[2fr,1fr]">
        <Card>
          <CardHeader>
            <SectionHeader
              title="Run History"
              description="Filter by status, run type, and branch. Filters are URL-synced for deep links."
            />
          </CardHeader>
          <CardContent className="space-y-3">
            <FilterBar
              hasActiveFilters={hasFilters}
              onReset={() => {
                setSearchParams(new URLSearchParams(), { replace: true });
              }}
            >
              <Select
                value={filters.status ?? "all"}
                onValueChange={(value) => {
                  setSearchParams(applyFilterState(searchParams, { status: value as (typeof RUN_STATUSES)[number] }), {
                    replace: true
                  });
                }}
              >
                <SelectTrigger aria-label="Filter by run status">
                  <SelectValue placeholder="Status" />
                </SelectTrigger>
                <SelectContent>
                  {RUN_STATUSES.map((status) => (
                    <SelectItem key={status} value={status}>
                      {status}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>

              <Select
                value={filters.runType ?? "all"}
                onValueChange={(value) => {
                  setSearchParams(applyFilterState(searchParams, { runType: value as (typeof RUN_TYPES)[number] }), {
                    replace: true
                  });
                }}
              >
                <SelectTrigger aria-label="Filter by run type">
                  <SelectValue placeholder="Run type" />
                </SelectTrigger>
                <SelectContent>
                  {RUN_TYPES.map((item) => (
                    <SelectItem key={item} value={item}>
                      {item}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>

              <Input
                id="runs-branch-filter"
                name="runsBranchFilter"
                value={filters.branch ?? ""}
                onChange={(event) => {
                  setSearchParams(applyFilterState(searchParams, { branch: event.target.value }), { replace: true });
                }}
                placeholder="Filter source or target branch"
                aria-label="Filter by branch"
              />
            </FilterBar>

            <DataStatePanel
              state={runsState}
              title={runsQuery.isError ? "Failed to load runs" : "No runs found"}
              message={
                runsQuery.isError
                  ? runsQuery.error instanceof Error
                    ? runsQuery.error.message
                    : "Unknown error"
                  : hasFilters
                  ? "No runs match the selected filters."
                  : "Start a planning run to create your first spec bundle."
              }
              onRetry={runsQuery.isError ? () => void runsQuery.refetch() : undefined}
            />

            {runsState === "ready" ? (
              <>
                <div className="hidden md:block">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Run</TableHead>
                        <TableHead>Type</TableHead>
                        <TableHead>Status</TableHead>
                        <TableHead>Source</TableHead>
                        <TableHead>Target</TableHead>
                        <TableHead className="w-[110px]">Action</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {runs.map((run) => (
                        <TableRow key={run.id}>
                          <TableCell className="mono text-xs">{run.id.slice(0, 12)}</TableCell>
                          <TableCell>{run.runType}</TableCell>
                          <TableCell>
                            <StatusPill status={run.status} />
                          </TableCell>
                          <TableCell className="mono text-xs">{run.sourceBranch}</TableCell>
                          <TableCell className="mono text-xs">{run.targetBranch}</TableCell>
                          <TableCell>
                            <Button asChild variant="outline" size="sm">
                              <Link to={`/runs/${run.id}`}>Open</Link>
                            </Button>
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>

                <div className="grid gap-2 md:hidden">
                  {runs.map((run) => (
                    <div key={run.id} className="rounded-lg border border-border bg-background p-3">
                      <div className="flex items-start justify-between gap-2">
                        <p className="mono text-xs">{run.id}</p>
                        <StatusPill status={run.status} />
                      </div>
                      <p className="mt-2 text-sm">{run.runType}</p>
                      <p className="mono mt-1 text-xs text-muted-foreground">
                        {run.sourceBranch} → {run.targetBranch}
                      </p>
                      <Button asChild variant="outline" size="sm" className="mt-3 w-full">
                        <Link to={`/runs/${run.id}`}>Open Run</Link>
                      </Button>
                    </div>
                  ))}
                </div>
              </>
            ) : null}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Launch Run</CardTitle>
            <CardDescription>One run creates one Kubernetes Job and one runner pod.</CardDescription>
          </CardHeader>
          <CardContent>
            <form
              className="space-y-3"
              onSubmit={(event) => {
                event.preventDefault();
                createRunMutation.mutate();
              }}
            >
              <Field id="run-attractor" label="Attractor" required>
                <Select value={attractorDefId.length > 0 ? attractorDefId : undefined} onValueChange={setAttractorDefId}>
                  <SelectTrigger id="run-attractor" aria-label="Select attractor" name="attractorDefId">
                    <SelectValue placeholder="Select attractor" />
                  </SelectTrigger>
                  <SelectContent>
                    {(attractorsQuery.data ?? []).map((attractor) => (
                      <SelectItem key={attractor.id} value={attractor.id}>
                        {attractor.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </Field>

              <Field id="run-type" label="Run Type" required>
                <Select
                  value={runType}
                  onValueChange={(value: RunType) => {
                    setRunType(value);
                    if (value === "planning") {
                      setSpecBundleId("");
                    }
                  }}
                >
                  <SelectTrigger id="run-type" aria-label="Run type" name="runType">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="planning">planning</SelectItem>
                    <SelectItem value="implementation">implementation</SelectItem>
                  </SelectContent>
                </Select>
              </Field>

              <div className="grid gap-3 md:grid-cols-2">
                <Field id="run-provider" label="Provider" required>
                  <Select
                    value={provider}
                    onValueChange={(value) => {
                      setProvider(value);
                      setModelId("");
                    }}
                  >
                    <SelectTrigger id="run-provider" aria-label="Provider" name="provider">
                      <SelectValue placeholder="Select provider" />
                    </SelectTrigger>
                    <SelectContent>
                      {(providersQuery.data ?? []).map((item) => (
                        <SelectItem key={item} value={item}>
                          {item}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </Field>

                <Field id="run-model" label="Model" required>
                  <Select value={modelId.length > 0 ? modelId : undefined} onValueChange={setModelId}>
                    <SelectTrigger id="run-model" aria-label="Model" name="modelId">
                      <SelectValue placeholder="Select model" />
                    </SelectTrigger>
                    <SelectContent>
                      {(modelsQuery.data ?? []).map((model) => (
                        <SelectItem key={model.id} value={model.id}>
                          {model.id}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </Field>
              </div>

              <Field id="run-reasoning-level" label="Reasoning Level">
                <Select value={reasoningLevel} onValueChange={setReasoningLevel}>
                  <SelectTrigger id="run-reasoning-level" aria-label="Reasoning level" name="reasoningLevel">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {REASONING_LEVELS.map((item) => (
                      <SelectItem key={item} value={item}>
                        {item}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </Field>

              <div className="grid gap-3 md:grid-cols-2">
                <Field id="run-source-branch" label="Source Branch" required>
                  <Input
                    id="run-source-branch"
                    name="sourceBranch"
                    value={sourceBranch}
                    onChange={(event) => setSourceBranch(event.target.value)}
                    required
                  />
                </Field>

                <Field id="run-target-branch" label="Target Branch" required>
                  <Input
                    id="run-target-branch"
                    name="targetBranch"
                    value={targetBranch}
                    onChange={(event) => setTargetBranch(event.target.value)}
                    required
                  />
                </Field>
              </div>

              {runType === "implementation" ? (
                <Field
                  id="run-spec-bundle"
                  label="Spec Bundle ID"
                  required
                  hint="Use a planning run output bundle ID."
                >
                  <Input
                    id="run-spec-bundle"
                    name="specBundleId"
                    value={specBundleId}
                    onChange={(event) => setSpecBundleId(event.target.value)}
                    required
                  />
                </Field>
              ) : null}

              <div className="grid gap-3 md:grid-cols-2">
                <Field id="run-temperature" label="Temperature">
                  <Input
                    id="run-temperature"
                    name="temperature"
                    value={temperature}
                    onChange={(event) => setTemperature(event.target.value)}
                  />
                </Field>

                <Field id="run-max-tokens" label="Max Tokens" hint="Optional">
                  <Input
                    id="run-max-tokens"
                    name="maxTokens"
                    value={maxTokens}
                    onChange={(event) => setMaxTokens(event.target.value)}
                  />
                </Field>
              </div>

              {selectedAttractor ? (
                <p className="text-xs text-muted-foreground">
                  Selected attractor path: <span className="mono">{selectedAttractor.repoPath}</span>
                </p>
              ) : null}

              <Button type="submit" disabled={createRunMutation.isPending} className="w-full">
                {createRunMutation.isPending ? "Queueing..." : "Queue Run"}
              </Button>
            </form>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
