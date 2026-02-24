import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";

import { listProjects, listProviders, listProjectRuns } from "../lib/api";
import type { PageState } from "../lib/types";
import { PageTitle } from "../components/layout/page-title";
import { DataStatePanel } from "../components/common/data-state-panel";
import { SectionHeader } from "../components/common/section-header";
import { StatusPill } from "../components/common/status-pill";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../components/ui/card";
import { Button } from "../components/ui/button";

export function DashboardPage() {
  const projectsQuery = useQuery({ queryKey: ["projects"], queryFn: () => listProjects({ limit: 50 }) });
  const providersQuery = useQuery({ queryKey: ["providers"], queryFn: listProviders });
  const latestProjectId = projectsQuery.data?.[0]?.id;
  const recentRunsQuery = useQuery({
    queryKey: ["project-runs", latestProjectId],
    queryFn: () => listProjectRuns(latestProjectId ?? "", { limit: 8 }),
    enabled: Boolean(latestProjectId)
  });

  const state: PageState =
    projectsQuery.isLoading || providersQuery.isLoading
      ? "loading"
      : projectsQuery.isError || providersQuery.isError
      ? "error"
      : "ready";

  return (
    <div>
      <PageTitle
        title="Dashboard"
        description="System summary and quick paths into project operations."
        actions={
          <Button asChild>
            <Link to="/projects">Create Project</Link>
          </Button>
        }
      />

      <DataStatePanel
        state={state}
        title={
          state === "loading"
            ? "Loading dashboard"
            : state === "error"
            ? "Failed to load dashboard"
            : "Ready"
        }
        message={
          state === "loading"
            ? "Fetching project and model catalog data..."
            : state === "error"
            ? projectsQuery.error instanceof Error
              ? projectsQuery.error.message
              : providersQuery.error instanceof Error
              ? providersQuery.error.message
              : "Unknown error"
            : undefined
        }
      />

      <div className="grid gap-4 md:grid-cols-3">
        <Card>
          <CardHeader>
            <CardDescription>Projects</CardDescription>
            <CardTitle>{projectsQuery.data?.length ?? 0}</CardTitle>
          </CardHeader>
        </Card>
        <Card>
          <CardHeader>
            <CardDescription>Providers Available</CardDescription>
            <CardTitle>{providersQuery.data?.length ?? 0}</CardTitle>
          </CardHeader>
        </Card>
        <Card>
          <CardHeader>
            <CardDescription>Recent Runs (Latest Project)</CardDescription>
            <CardTitle>{recentRunsQuery.data?.length ?? 0}</CardTitle>
          </CardHeader>
        </Card>
      </div>

      <div className="mt-6 grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <SectionHeader
              title="Recent Runs"
              description="Latest executions from the currently selected default project context."
            />
          </CardHeader>
          <CardContent className="space-y-2">
            {(recentRunsQuery.data ?? []).map((run) => (
              <Link
                key={run.id}
                to={`/runs/${run.id}`}
                className="flex items-center justify-between rounded-md border border-border bg-background px-3 py-3 text-sm transition-colors hover:bg-muted"
              >
                <div className="min-w-0">
                  <p className="mono truncate text-xs">{run.id}</p>
                  <p className="text-xs text-muted-foreground">{run.runType}</p>
                </div>
                <StatusPill status={run.status} />
              </Link>
            ))}
            {(recentRunsQuery.data?.length ?? 0) === 0 ? (
              <DataStatePanel
                state="empty"
                title="No recent runs"
                message="Launch a planning or implementation run from the Runs page."
              />
            ) : null}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <SectionHeader title="Quick Actions" description="Jump into primary workflows." />
          </CardHeader>
          <CardContent className="grid gap-2">
            <Button asChild variant="outline">
              <Link to="/projects">Manage Projects</Link>
            </Button>
            <Button asChild variant="outline">
              <Link to={latestProjectId ? `/projects/${latestProjectId}/secrets` : "/projects"}>Manage Secrets</Link>
            </Button>
            <Button asChild variant="outline">
              <Link to={latestProjectId ? `/projects/${latestProjectId}/attractors` : "/projects"}>Manage Attractors</Link>
            </Button>
            <Button asChild variant="outline">
              <Link to={latestProjectId ? `/projects/${latestProjectId}/runs` : "/projects"}>Launch Runs</Link>
            </Button>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
