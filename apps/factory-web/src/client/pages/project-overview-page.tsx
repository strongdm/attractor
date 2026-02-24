import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import {
  connectProjectRepo,
  listAttractors,
  listProjectRuns,
  listProjects,
  listProjectSecrets
} from "../lib/api";
import type { PageState } from "../lib/types";
import { PageTitle } from "../components/layout/page-title";
import { DataStatePanel } from "../components/common/data-state-panel";
import { SectionHeader } from "../components/common/section-header";
import { Button } from "../components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../components/ui/card";
import { Field } from "../components/ui/field";
import { Input } from "../components/ui/input";

export function ProjectOverviewPage() {
  const params = useParams<{ projectId: string }>();
  const projectId = params.projectId ?? "";
  const queryClient = useQueryClient();

  const [installationId, setInstallationId] = useState("");
  const [repoFullName, setRepoFullName] = useState("");
  const [defaultBranch, setDefaultBranch] = useState("main");

  const projectsQuery = useQuery({ queryKey: ["projects"], queryFn: () => listProjects({ limit: 200 }) });
  const runsQuery = useQuery({
    queryKey: ["project-runs", projectId],
    queryFn: () => listProjectRuns(projectId, { limit: 5 }),
    enabled: projectId.length > 0
  });
  const attractorsQuery = useQuery({
    queryKey: ["attractors", projectId],
    queryFn: () => listAttractors(projectId),
    enabled: projectId.length > 0
  });
  const secretsQuery = useQuery({
    queryKey: ["project-secrets", projectId],
    queryFn: () => listProjectSecrets(projectId),
    enabled: projectId.length > 0
  });

  const project = useMemo(
    () => projectsQuery.data?.find((candidate) => candidate.id === projectId),
    [projectsQuery.data, projectId]
  );

  useEffect(() => {
    if (!project) {
      return;
    }
    setInstallationId(project.githubInstallationId ?? "");
    setRepoFullName(project.repoFullName ?? "");
    setDefaultBranch(project.defaultBranch ?? "main");
  }, [project]);

  const connectMutation = useMutation({
    mutationFn: (input: { installationId: string; repoFullName: string; defaultBranch: string }) =>
      connectProjectRepo(projectId, input),
    onSuccess: () => {
      toast.success("Repository connection saved");
      void queryClient.invalidateQueries({ queryKey: ["projects"] });
    },
    onError: (error) => {
      toast.error(error instanceof Error ? error.message : String(error));
    }
  });

  const state: PageState = projectsQuery.isLoading
    ? "loading"
    : projectsQuery.isError
    ? "error"
    : project
    ? "ready"
    : "empty";

  if (state !== "ready" || !project) {
    return (
      <DataStatePanel
        state={state}
        title={state === "loading" ? "Loading project" : state === "error" ? "Failed to load project" : "Project not found"}
        message={
          state === "loading"
            ? "Fetching project context..."
            : state === "error"
            ? projectsQuery.error instanceof Error
              ? projectsQuery.error.message
              : "Unknown error"
            : "Select another project from the project switcher."
        }
        onRetry={state === "error" ? () => void projectsQuery.refetch() : undefined}
      />
    );
  }

  return (
    <div>
      <PageTitle
        title={project.name}
        description={`Namespace: ${project.namespace}`}
        actions={
          <Button asChild variant="outline">
            <Link to={`/projects/${project.id}/runs`}>Start Run</Link>
          </Button>
        }
      />

      <div className="grid gap-4 md:grid-cols-3">
        <Card>
          <CardHeader>
            <CardDescription>Recent Runs</CardDescription>
            <CardTitle>{runsQuery.data?.length ?? 0}</CardTitle>
          </CardHeader>
        </Card>
        <Card>
          <CardHeader>
            <CardDescription>Registered Attractors</CardDescription>
            <CardTitle>{attractorsQuery.data?.length ?? 0}</CardTitle>
          </CardHeader>
        </Card>
        <Card>
          <CardHeader>
            <CardDescription>Project Secrets</CardDescription>
            <CardTitle>{secretsQuery.data?.length ?? 0}</CardTitle>
          </CardHeader>
        </Card>
      </div>

      <div className="mt-6 grid gap-4 lg:grid-cols-[2fr,1fr]">
        <Card>
          <CardHeader>
            <SectionHeader
              title="Repository Connection"
              description="GitHub App installation and repository metadata used for branch and PR operations."
            />
          </CardHeader>
          <CardContent>
            <form
              className="grid gap-3 md:grid-cols-2"
              onSubmit={(event) => {
                event.preventDefault();
                if (!installationId.trim() || !repoFullName.trim() || !defaultBranch.trim()) {
                  toast.error("Installation ID, repository, and default branch are required");
                  return;
                }
                connectMutation.mutate({
                  installationId: installationId.trim(),
                  repoFullName: repoFullName.trim(),
                  defaultBranch: defaultBranch.trim()
                });
              }}
            >
              <Field id="installation-id" label="Installation ID" required>
                <Input
                  id="installation-id"
                  name="installationId"
                  value={installationId}
                  onChange={(event) => setInstallationId(event.target.value)}
                  placeholder="123456"
                  required
                />
              </Field>

              <Field id="repo-full-name" label="Repository" required>
                <Input
                  id="repo-full-name"
                  name="repoFullName"
                  value={repoFullName}
                  onChange={(event) => setRepoFullName(event.target.value)}
                  placeholder="owner/repo"
                  required
                />
              </Field>

              <Field id="default-branch" label="Default Branch" required>
                <Input
                  id="default-branch"
                  name="defaultBranch"
                  value={defaultBranch}
                  onChange={(event) => setDefaultBranch(event.target.value)}
                  placeholder="main"
                  required
                />
              </Field>

              <div className="flex items-end">
                <Button type="submit" disabled={connectMutation.isPending} className="w-full md:w-auto">
                  {connectMutation.isPending ? "Saving..." : "Save Connection"}
                </Button>
              </div>
            </form>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Project Context</CardTitle>
            <CardDescription>Current metadata snapshot.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-2 text-sm">
            <p>
              <span className="text-muted-foreground">ID:</span> <span className="mono text-xs">{project.id}</span>
            </p>
            <p>
              <span className="text-muted-foreground">Repo:</span> {project.repoFullName ?? "Not connected"}
            </p>
            <p>
              <span className="text-muted-foreground">Default branch:</span> {project.defaultBranch ?? "-"}
            </p>
            <p>
              <span className="text-muted-foreground">GitHub installation:</span> {project.githubInstallationId ?? "-"}
            </p>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
