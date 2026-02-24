import { useEffect, useMemo, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { buildApiUrl, cancelRun, getRun, getRunArtifacts } from "../lib/api";
import type { PageState, RunEvent } from "../lib/types";
import { DataStatePanel } from "../components/common/data-state-panel";
import { SectionHeader } from "../components/common/section-header";
import { StatusPill } from "../components/common/status-pill";
import { PageTitle } from "../components/layout/page-title";
import { Badge } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "../components/ui/table";

const TERMINAL_STATUSES = ["SUCCEEDED", "FAILED", "CANCELED", "TIMEOUT"];

function formatDate(value: string | null): string {
  if (!value) {
    return "-";
  }
  return new Date(value).toLocaleString();
}

export function RunDetailPage() {
  const params = useParams<{ runId: string }>();
  const runId = params.runId ?? "";
  const queryClient = useQueryClient();
  const [searchParams, setSearchParams] = useSearchParams();
  const [streamEvents, setStreamEvents] = useState<RunEvent[]>([]);

  const runQuery = useQuery({
    queryKey: ["run", runId],
    queryFn: () => getRun(runId),
    enabled: runId.length > 0,
    refetchInterval: 7000
  });

  const artifactsQuery = useQuery({
    queryKey: ["run-artifacts", runId],
    queryFn: () => getRunArtifacts(runId),
    enabled: runId.length > 0,
    refetchInterval: 7000
  });

  const cancelMutation = useMutation({
    mutationFn: () => cancelRun(runId),
    onSuccess: () => {
      toast.success("Run cancel requested");
      void queryClient.invalidateQueries({ queryKey: ["run", runId] });
    },
    onError: (error) => {
      toast.error(error instanceof Error ? error.message : String(error));
    }
  });

  const tab = searchParams.get("tab") ?? "overview";

  useEffect(() => {
    if (!runId) {
      return;
    }

    const source = new EventSource(buildApiUrl(`/api/runs/${runId}/events`));

    source.onmessage = (event) => {
      try {
        const parsed = JSON.parse(event.data) as RunEvent;
        setStreamEvents((previous) => {
          if (previous.some((item) => item.id === parsed.id)) {
            return previous;
          }
          return [...previous, parsed];
        });
      } catch {
        // ignore malformed/heartbeat events
      }
    };

    source.onerror = () => {
      source.close();
    };

    return () => {
      source.close();
    };
  }, [runId]);

  const mergedEvents = useMemo(() => {
    const byId = new Map<string, RunEvent>();
    for (const item of runQuery.data?.events ?? []) {
      byId.set(item.id, item);
    }
    for (const item of streamEvents) {
      byId.set(item.id, item);
    }
    return [...byId.values()].sort((a, b) => new Date(a.ts).getTime() - new Date(b.ts).getTime());
  }, [runQuery.data?.events, streamEvents]);

  const pageState: PageState = runQuery.isLoading
    ? "loading"
    : runQuery.isError
    ? "error"
    : runQuery.data
    ? "ready"
    : "empty";

  if (pageState !== "ready" || !runQuery.data) {
    return (
      <DataStatePanel
        state={pageState}
        title={runQuery.isError ? "Failed to load run" : pageState === "loading" ? "Loading run" : "Run not found"}
        message={
          runQuery.isError
            ? runQuery.error instanceof Error
              ? runQuery.error.message
              : "Unknown error"
            : pageState === "loading"
            ? "Fetching run status and events..."
            : "The requested run does not exist."
        }
        onRetry={runQuery.isError ? () => void runQuery.refetch() : undefined}
      />
    );
  }

  const run = runQuery.data;
  const artifacts = artifactsQuery.data?.artifacts ?? [];
  const artifactsState: PageState = artifactsQuery.isLoading
    ? "loading"
    : artifactsQuery.isError
    ? "error"
    : artifacts.length > 0
    ? "ready"
    : "empty";

  return (
    <div>
      <PageTitle
        title={`Run ${run.id.slice(0, 12)}`}
        description={`${run.runType} on ${run.targetBranch}`}
        actions={
          <>
            <StatusPill status={run.status} />
            <Button
              variant="outline"
              onClick={() => {
                cancelMutation.mutate();
              }}
              disabled={cancelMutation.isPending || TERMINAL_STATUSES.includes(run.status)}
            >
              Cancel Run
            </Button>
          </>
        }
      />

      <div className="mb-4 flex flex-wrap gap-2">
        {[
          { key: "overview", label: "Overview" },
          { key: "events", label: "Events" },
          { key: "artifacts", label: "Artifacts" }
        ].map((item) => (
          <Button
            key={item.key}
            variant={tab === item.key ? "default" : "outline"}
            onClick={() => {
              const next = new URLSearchParams(searchParams);
              next.set("tab", item.key);
              setSearchParams(next, { replace: true });
            }}
          >
            {item.label}
          </Button>
        ))}
      </div>

      {tab === "overview" ? (
        <div className="grid gap-4 md:grid-cols-2">
          <Card>
            <CardHeader>
              <SectionHeader title="Run Metadata" description="Execution inputs and output references." />
            </CardHeader>
            <CardContent className="space-y-2 text-sm">
              <p>
                <span className="text-muted-foreground">Type:</span> {run.runType}
              </p>
              <p>
                <span className="text-muted-foreground">Source branch:</span> <span className="mono">{run.sourceBranch}</span>
              </p>
              <p>
                <span className="text-muted-foreground">Target branch:</span> <span className="mono">{run.targetBranch}</span>
              </p>
              <p>
                <span className="text-muted-foreground">Spec bundle:</span> {run.specBundleId ?? "-"}
              </p>
              <p>
                <span className="text-muted-foreground">PR URL:</span>{" "}
                {run.prUrl ? (
                  <a href={run.prUrl} target="_blank" rel="noreferrer" className="text-primary underline">
                    Open PR
                  </a>
                ) : (
                  "-"
                )}
              </p>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <SectionHeader title="Timeline" description="Lifecycle and terminal state details." />
            </CardHeader>
            <CardContent className="space-y-2 text-sm">
              <p>
                <span className="text-muted-foreground">Created:</span> {formatDate(run.createdAt)}
              </p>
              <p>
                <span className="text-muted-foreground">Started:</span> {formatDate(run.startedAt)}
              </p>
              <p>
                <span className="text-muted-foreground">Finished:</span> {formatDate(run.finishedAt)}
              </p>
              {run.error ? (
                <p>
                  <span className="text-muted-foreground">Error:</span> {run.error}
                </p>
              ) : null}
            </CardContent>
          </Card>
        </div>
      ) : null}

      {tab === "events" ? (
        <Card>
          <CardHeader>
            <SectionHeader
              title="Live Event Stream"
              description="Server-sent events merged with persisted records for continuity."
              actions={<Badge variant="secondary">{mergedEvents.length} events</Badge>}
            />
          </CardHeader>
          <CardContent>
            <DataStatePanel
              state={mergedEvents.length > 0 ? "ready" : "empty"}
              title="No events yet"
              message="Events appear here as the runner progresses through attractor nodes."
            />

            {mergedEvents.length > 0 ? (
              <div className="max-h-[60vh] overflow-auto rounded-md border border-border bg-background p-3">
                <pre className="text-xs leading-5">
                  {mergedEvents
                    .map((event) => `${event.ts} ${event.type} ${JSON.stringify(event.payload)}`)
                    .join("\n")}
                </pre>
              </div>
            ) : null}
          </CardContent>
        </Card>
      ) : null}

      {tab === "artifacts" ? (
        <Card>
          <CardHeader>
            <SectionHeader
              title="Artifacts"
              description="Open text artifacts in the embedded editor page."
              actions={<Badge variant="secondary">{artifacts.length} files</Badge>}
            />
          </CardHeader>
          <CardContent className="space-y-3">
            <DataStatePanel
              state={artifactsState}
              title={artifactsQuery.isError ? "Failed to load artifacts" : "No artifacts"}
              message={
                artifactsQuery.isError
                  ? artifactsQuery.error instanceof Error
                    ? artifactsQuery.error.message
                    : "Unknown error"
                  : "Artifacts are persisted as the run executes."
              }
              onRetry={artifactsQuery.isError ? () => void artifactsQuery.refetch() : undefined}
            />

            {artifacts.length > 0 ? (
              <>
                <div className="hidden md:block">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Key</TableHead>
                        <TableHead>Path</TableHead>
                        <TableHead>Size</TableHead>
                        <TableHead className="w-[100px]">Open</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {artifacts.map((artifact) => (
                        <TableRow key={artifact.id}>
                          <TableCell>{artifact.key}</TableCell>
                          <TableCell className="mono text-xs">{artifact.path}</TableCell>
                          <TableCell>{artifact.sizeBytes ? `${artifact.sizeBytes.toLocaleString()} B` : "-"}</TableCell>
                          <TableCell>
                            <Button asChild size="sm" variant="outline">
                              <Link to={`/runs/${run.id}/artifacts/${artifact.id}`}>View</Link>
                            </Button>
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>

                <div className="grid gap-2 md:hidden">
                  {artifacts.map((artifact) => (
                    <div key={artifact.id} className="rounded-lg border border-border bg-background p-3">
                      <p className="font-medium">{artifact.key}</p>
                      <p className="mono mt-1 text-xs text-muted-foreground">{artifact.path}</p>
                      <p className="mt-2 text-sm text-muted-foreground">
                        {artifact.sizeBytes ? `${artifact.sizeBytes.toLocaleString()} B` : "Unknown size"}
                      </p>
                      <Button asChild variant="outline" size="sm" className="mt-3 w-full">
                        <Link to={`/runs/${run.id}/artifacts/${artifact.id}`}>View Artifact</Link>
                      </Button>
                    </div>
                  ))}
                </div>
              </>
            ) : null}
          </CardContent>
        </Card>
      ) : null}
    </div>
  );
}
