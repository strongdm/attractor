import { useState } from "react";
import { useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { createAttractor, listAttractors } from "../lib/api";
import type { PageState, RunType } from "../lib/types";
import { PageTitle } from "../components/layout/page-title";
import { DataStatePanel } from "../components/common/data-state-panel";
import { SectionHeader } from "../components/common/section-header";
import { Badge } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../components/ui/card";
import { Field } from "../components/ui/field";
import { Input } from "../components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "../components/ui/table";
import { Textarea } from "../components/ui/textarea";

export function ProjectAttractorsPage() {
  const params = useParams<{ projectId: string }>();
  const projectId = params.projectId ?? "";
  const queryClient = useQueryClient();

  const [name, setName] = useState("");
  const [repoPath, setRepoPath] = useState("factory/self-bootstrap.dot");
  const [defaultRunType, setDefaultRunType] = useState<RunType>("planning");
  const [description, setDescription] = useState("");

  const attractorsQuery = useQuery({
    queryKey: ["attractors", projectId],
    queryFn: () => listAttractors(projectId),
    enabled: projectId.length > 0
  });

  const createMutation = useMutation({
    mutationFn: () =>
      createAttractor(projectId, {
        name: name.trim(),
        repoPath: repoPath.trim(),
        defaultRunType,
        description: description.trim().length > 0 ? description.trim() : undefined,
        active: true
      }),
    onSuccess: () => {
      toast.success("Attractor saved");
      setName("");
      setDescription("");
      void queryClient.invalidateQueries({ queryKey: ["attractors", projectId] });
    },
    onError: (error) => {
      toast.error(error instanceof Error ? error.message : String(error));
    }
  });

  const attractors = attractorsQuery.data ?? [];
  const state: PageState = attractorsQuery.isLoading
    ? "loading"
    : attractorsQuery.isError
    ? "error"
    : attractors.length === 0
    ? "empty"
    : "ready";

  return (
    <div>
      <PageTitle title="Attractors" description="Register and manage graph definitions for planning and implementation runs." />

      <div className="grid gap-4 lg:grid-cols-[2fr,1fr]">
        <Card>
          <CardHeader>
            <SectionHeader title="Attractor Registry" description="Each attractor points to a repo-relative graph file." />
          </CardHeader>
          <CardContent className="space-y-3">
            <DataStatePanel
              state={state}
              title={attractorsQuery.isError ? "Failed to load attractors" : "No attractors registered"}
              message={
                attractorsQuery.isError
                  ? attractorsQuery.error instanceof Error
                    ? attractorsQuery.error.message
                    : "Unknown error"
                  : "Create an attractor to make this project runnable."
              }
              onRetry={attractorsQuery.isError ? () => void attractorsQuery.refetch() : undefined}
            />

            {state === "ready" ? (
              <>
                <div className="hidden md:block">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Name</TableHead>
                        <TableHead>Path</TableHead>
                        <TableHead>Default Run</TableHead>
                        <TableHead>Status</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {attractors.map((attractor) => (
                        <TableRow key={attractor.id}>
                          <TableCell className="font-medium">{attractor.name}</TableCell>
                          <TableCell className="mono text-xs">{attractor.repoPath}</TableCell>
                          <TableCell>{attractor.defaultRunType}</TableCell>
                          <TableCell>
                            <Badge variant={attractor.active ? "success" : "secondary"}>
                              {attractor.active ? "Active" : "Inactive"}
                            </Badge>
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>

                <div className="grid gap-2 md:hidden">
                  {attractors.map((attractor) => (
                    <div key={attractor.id} className="rounded-lg border border-border bg-background p-3">
                      <div className="flex items-center justify-between gap-2">
                        <p className="font-medium">{attractor.name}</p>
                        <Badge variant={attractor.active ? "success" : "secondary"}>
                          {attractor.active ? "Active" : "Inactive"}
                        </Badge>
                      </div>
                      <p className="mono mt-2 text-xs text-muted-foreground">{attractor.repoPath}</p>
                      <p className="mt-2 text-sm text-muted-foreground">Default: {attractor.defaultRunType}</p>
                    </div>
                  ))}
                </div>
              </>
            ) : null}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Create Attractor</CardTitle>
            <CardDescription>Add another attractor graph for this project.</CardDescription>
          </CardHeader>
          <CardContent>
            <form
              className="space-y-3"
              onSubmit={(event) => {
                event.preventDefault();
                if (!name.trim() || !repoPath.trim()) {
                  toast.error("Name and repository path are required");
                  return;
                }
                createMutation.mutate();
              }}
            >
              <Field id="attractor-name" label="Name" required>
                <Input
                  id="attractor-name"
                  name="attractorName"
                  value={name}
                  onChange={(event) => setName(event.target.value)}
                  required
                />
              </Field>

              <Field id="attractor-repo-path" label="Repo Path" required hint="Example: factory/self-bootstrap.dot">
                <Input
                  id="attractor-repo-path"
                  name="attractorRepoPath"
                  value={repoPath}
                  onChange={(event) => setRepoPath(event.target.value)}
                  required
                />
              </Field>

              <Field id="attractor-default-run-type" label="Default Run Type" required>
                <Select value={defaultRunType} onValueChange={(value: RunType) => setDefaultRunType(value)}>
                  <SelectTrigger id="attractor-default-run-type" aria-label="Default run type" name="defaultRunType">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="planning">planning</SelectItem>
                    <SelectItem value="implementation">implementation</SelectItem>
                  </SelectContent>
                </Select>
              </Field>

              <Field id="attractor-description" label="Description" hint="Optional context for users selecting this attractor.">
                <Textarea
                  id="attractor-description"
                  name="attractorDescription"
                  value={description}
                  onChange={(event) => setDescription(event.target.value)}
                />
              </Field>

              <Button type="submit" disabled={createMutation.isPending} className="w-full">
                {createMutation.isPending ? "Saving..." : "Save Attractor"}
              </Button>
            </form>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
