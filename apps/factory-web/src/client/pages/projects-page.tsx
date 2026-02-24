import { useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { createProject, listProjectsPage } from "../lib/api";
import { applyFilterState, hasProjectSearchFilter, parseProjectFilterState } from "../lib/filter-state";
import type { PageState } from "../lib/types";
import { PageTitle } from "../components/layout/page-title";
import { DataStatePanel } from "../components/common/data-state-panel";
import { SectionHeader } from "../components/common/section-header";
import { Button } from "../components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../components/ui/card";
import { Field } from "../components/ui/field";
import { Input } from "../components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "../components/ui/table";

export function ProjectsPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const filters = parseProjectFilterState(searchParams);

  const queryClient = useQueryClient();
  const [name, setName] = useState("");
  const [namespace, setNamespace] = useState("");

  const projectsQuery = useQuery({
    queryKey: ["projects-page", filters.query],
    queryFn: () => listProjectsPage({ query: filters.query, limit: 100 })
  });

  const createMutation = useMutation({
    mutationFn: createProject,
    onSuccess: (project) => {
      toast.success(`Project ${project.name} created`);
      setName("");
      setNamespace("");
      void queryClient.invalidateQueries({ queryKey: ["projects"] });
      void queryClient.invalidateQueries({ queryKey: ["projects-page"] });
    },
    onError: (error) => {
      toast.error(error instanceof Error ? error.message : String(error));
    }
  });

  const projects = projectsQuery.data?.items ?? [];
  const state: PageState = projectsQuery.isLoading
    ? "loading"
    : projectsQuery.isError
    ? "error"
    : projects.length === 0
    ? "empty"
    : "ready";

  const hasSearch = hasProjectSearchFilter({ query: filters.query });

  const normalizedProjects = useMemo(() => projects, [projects]);

  return (
    <div>
      <PageTitle title="Projects" description="Create and manage project namespaces and repository bindings." />

      <div className="grid gap-4 lg:grid-cols-[2fr,1fr]">
        <Card>
          <CardHeader>
            <SectionHeader title="Project Registry" description="Searchable project list with quick access." />
          </CardHeader>
          <CardContent className="space-y-3">
            <Input
              id="project-search"
              name="projectSearch"
              value={filters.query ?? ""}
              onChange={(event) => {
                const next = applyFilterState(searchParams, { query: event.target.value });
                setSearchParams(next, { replace: true });
              }}
              placeholder="Search by name, namespace, or repo"
              aria-label="Search projects"
            />

            <DataStatePanel
              state={state}
              title={projectsQuery.isError ? "Failed to load projects" : "No projects found"}
              message={
                projectsQuery.isError
                  ? projectsQuery.error instanceof Error
                    ? projectsQuery.error.message
                    : "Unknown error"
                  : hasSearch
                  ? "Try another search term."
                  : "Create your first project to begin."
              }
              onRetry={projectsQuery.isError ? () => void projectsQuery.refetch() : undefined}
            />

            {state === "ready" ? (
              <>
                <div className="hidden md:block">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Name</TableHead>
                        <TableHead>Namespace</TableHead>
                        <TableHead>Repository</TableHead>
                        <TableHead className="w-[120px]">Actions</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {normalizedProjects.map((project) => (
                        <TableRow key={project.id}>
                          <TableCell className="font-medium">{project.name}</TableCell>
                          <TableCell className="mono text-xs">{project.namespace}</TableCell>
                          <TableCell>{project.repoFullName ?? "Not connected"}</TableCell>
                          <TableCell>
                            <Button asChild size="sm" variant="outline">
                              <Link to={`/projects/${project.id}`}>Open</Link>
                            </Button>
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>

                <div className="grid gap-2 md:hidden">
                  {normalizedProjects.map((project) => (
                    <div key={project.id} className="rounded-md border border-border bg-background p-3">
                      <p className="font-medium">{project.name}</p>
                      <p className="mono mt-1 text-xs text-muted-foreground">{project.namespace}</p>
                      <p className="mt-2 text-sm text-muted-foreground">{project.repoFullName ?? "Not connected"}</p>
                      <Button asChild variant="outline" size="sm" className="mt-3 w-full">
                        <Link to={`/projects/${project.id}`}>Open</Link>
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
            <CardTitle>Create Project</CardTitle>
            <CardDescription>
              Namespace defaults to <span className="mono">factory-proj-slug</span> when blank.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <form
              className="space-y-3"
              onSubmit={(event) => {
                event.preventDefault();
                if (name.trim().length < 2) {
                  toast.error("Project name must be at least 2 characters");
                  return;
                }
                createMutation.mutate({
                  name: name.trim(),
                  namespace: namespace.trim().length > 0 ? namespace.trim() : undefined
                });
              }}
            >
              <Field id="project-name" label="Project Name" required>
                <Input
                  id="project-name"
                  name="projectName"
                  value={name}
                  onChange={(event) => setName(event.target.value)}
                  required
                />
              </Field>

              <Field id="project-namespace" label="Namespace" hint="Optional override for deterministic namespace name.">
                <Input
                  id="project-namespace"
                  name="projectNamespace"
                  value={namespace}
                  onChange={(event) => setNamespace(event.target.value)}
                />
              </Field>

              <Button type="submit" disabled={createMutation.isPending} className="w-full">
                {createMutation.isPending ? "Creating..." : "Create Project"}
              </Button>
            </form>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
