import { useEffect, useMemo, useState } from "react";
import { useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import {
  listGlobalSecrets,
  listProjectSecrets,
  listProviderSchemas,
  upsertGlobalSecret,
  upsertProjectSecret
} from "../lib/api";
import type { PageState, ProviderSchema } from "../lib/types";
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

function firstLogicalKey(schema: ProviderSchema | undefined): string {
  if (!schema) {
    return "";
  }
  if ((schema.requiredAll?.length ?? 0) > 0) {
    return schema.requiredAll?.[0] ?? "";
  }
  if ((schema.requiredAny?.length ?? 0) > 0) {
    return schema.requiredAny?.[0] ?? "";
  }
  return Object.keys(schema.envByLogicalKey ?? {})[0] ?? "";
}

function defaultSecretKey(schema: ProviderSchema | undefined, logicalKey: string): string {
  if (!schema || !logicalKey) {
    return "";
  }
  const envName = schema.envByLogicalKey[logicalKey] ?? logicalKey;
  return envName.toLowerCase();
}

export function ProjectSecretsPage() {
  const params = useParams<{ projectId: string }>();
  const projectId = params.projectId ?? "";
  const queryClient = useQueryClient();

  const schemasQuery = useQuery({ queryKey: ["provider-schemas"], queryFn: listProviderSchemas });
  const projectSecretsQuery = useQuery({
    queryKey: ["project-secrets", projectId],
    queryFn: () => listProjectSecrets(projectId),
    enabled: projectId.length > 0
  });
  const globalSecretsQuery = useQuery({ queryKey: ["global-secrets"], queryFn: listGlobalSecrets });

  const [projectProvider, setProjectProvider] = useState("openai");
  const [projectName, setProjectName] = useState("llm-openai");
  const [projectLogicalKey, setProjectLogicalKey] = useState("apiKey");
  const [projectSecretKey, setProjectSecretKey] = useState("openai_api_key");
  const [projectSecretValue, setProjectSecretValue] = useState("");

  const [globalProvider, setGlobalProvider] = useState("openai");
  const [globalName, setGlobalName] = useState("global-openai");
  const [globalLogicalKey, setGlobalLogicalKey] = useState("apiKey");
  const [globalSecretKey, setGlobalSecretKey] = useState("openai_api_key");
  const [globalSecretValue, setGlobalSecretValue] = useState("");

  const schemaByProvider = useMemo(() => {
    return Object.fromEntries((schemasQuery.data ?? []).map((schema) => [schema.provider, schema]));
  }, [schemasQuery.data]);

  const currentProjectSchema = schemaByProvider[projectProvider];
  const currentGlobalSchema = schemaByProvider[globalProvider];

  useEffect(() => {
    const firstSchema = schemasQuery.data?.[0];
    if (!firstSchema) {
      return;
    }

    if (!schemaByProvider[projectProvider]) {
      const logicalKey = firstLogicalKey(firstSchema);
      setProjectProvider(firstSchema.provider);
      setProjectName(`llm-${firstSchema.provider}`);
      setProjectLogicalKey(logicalKey);
      setProjectSecretKey(defaultSecretKey(firstSchema, logicalKey));
    }

    if (!schemaByProvider[globalProvider]) {
      const logicalKey = firstLogicalKey(firstSchema);
      setGlobalProvider(firstSchema.provider);
      setGlobalName(`global-${firstSchema.provider}`);
      setGlobalLogicalKey(logicalKey);
      setGlobalSecretKey(defaultSecretKey(firstSchema, logicalKey));
    }
  }, [globalProvider, projectProvider, schemaByProvider, schemasQuery.data]);

  const projectMutation = useMutation({
    mutationFn: () =>
      upsertProjectSecret(projectId, {
        name: projectName.trim(),
        provider: projectProvider,
        keyMappings: { [projectLogicalKey]: projectSecretKey.trim() },
        values: { [projectSecretKey.trim()]: projectSecretValue }
      }),
    onSuccess: () => {
      toast.success("Project secret saved");
      setProjectSecretValue("");
      void queryClient.invalidateQueries({ queryKey: ["project-secrets", projectId] });
    },
    onError: (error) => {
      toast.error(error instanceof Error ? error.message : String(error));
    }
  });

  const globalMutation = useMutation({
    mutationFn: () =>
      upsertGlobalSecret({
        name: globalName.trim(),
        provider: globalProvider,
        keyMappings: { [globalLogicalKey]: globalSecretKey.trim() },
        values: { [globalSecretKey.trim()]: globalSecretValue }
      }),
    onSuccess: () => {
      toast.success("Global secret saved");
      setGlobalSecretValue("");
      void queryClient.invalidateQueries({ queryKey: ["global-secrets"] });
      void queryClient.invalidateQueries({ queryKey: ["project-secrets", projectId] });
    },
    onError: (error) => {
      toast.error(error instanceof Error ? error.message : String(error));
    }
  });

  const state: PageState = schemasQuery.isLoading
    ? "loading"
    : schemasQuery.isError
    ? "error"
    : "ready";
  const projectSecretsState: PageState = projectSecretsQuery.isLoading
    ? "loading"
    : projectSecretsQuery.isError
    ? "error"
    : (projectSecretsQuery.data?.length ?? 0) > 0
    ? "ready"
    : "empty";
  const globalSecretsState: PageState = globalSecretsQuery.isLoading
    ? "loading"
    : globalSecretsQuery.isError
    ? "error"
    : (globalSecretsQuery.data?.length ?? 0) > 0
    ? "ready"
    : "empty";

  return (
    <div>
      <PageTitle
        title="Secrets"
        description="Manage project and global credentials. Project-level secrets override global values for the same provider."
      />

      <div className="mb-4 flex items-center gap-2 rounded-md border border-warning/40 bg-warning/10 px-3 py-2">
        <Badge variant="warning">Override Rule</Badge>
        <p className="text-sm text-warning-foreground">
          If both global and project secret exist for one provider, run pods use the project-scoped secret.
        </p>
      </div>

      <DataStatePanel
        state={state}
        title={schemasQuery.isError ? "Failed to load provider mappings" : "Loading provider mappings"}
        message={
          schemasQuery.isError
            ? schemasQuery.error instanceof Error
              ? schemasQuery.error.message
              : "Unknown error"
            : "Preparing provider key mapping forms..."
        }
        onRetry={schemasQuery.isError ? () => void schemasQuery.refetch() : undefined}
      />

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <SectionHeader
              title="Project Secret"
              description="Stored in project namespace and used first for provider authentication."
            />
          </CardHeader>
          <CardContent>
            <form
              className="space-y-3"
              onSubmit={(event) => {
                event.preventDefault();
                if (!projectSecretValue.trim()) {
                  toast.error("Project secret value is required");
                  return;
                }
                if (!projectName.trim() || !projectLogicalKey.trim() || !projectSecretKey.trim()) {
                  toast.error("Project secret name, logical key, and secret key are required");
                  return;
                }
                projectMutation.mutate();
              }}
            >
              <Field id="project-secret-name" label="Secret Name" required>
                <Input
                  id="project-secret-name"
                  name="projectSecretName"
                  value={projectName}
                  onChange={(event) => setProjectName(event.target.value)}
                  required
                />
              </Field>

              <Field id="project-secret-provider" label="Provider" required>
                <Select
                  value={projectProvider}
                  onValueChange={(provider) => {
                    const schema = schemaByProvider[provider];
                    const logicalKey = firstLogicalKey(schema);
                    setProjectProvider(provider);
                    setProjectName(`llm-${provider}`);
                    setProjectLogicalKey(logicalKey);
                    setProjectSecretKey(defaultSecretKey(schema, logicalKey));
                  }}
                >
                  <SelectTrigger id="project-secret-provider" aria-label="Project secret provider" name="projectSecretProvider">
                    <SelectValue placeholder="Select provider" />
                  </SelectTrigger>
                  <SelectContent>
                    {(schemasQuery.data ?? []).map((schema) => (
                      <SelectItem key={schema.provider} value={schema.provider}>
                        {schema.provider}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </Field>

              <div className="grid gap-3 md:grid-cols-2">
                <Field id="project-logical-key" label="Logical Key" required>
                  <Select
                    value={projectLogicalKey}
                    onValueChange={(logicalKey) => {
                      setProjectLogicalKey(logicalKey);
                      setProjectSecretKey(defaultSecretKey(currentProjectSchema, logicalKey));
                    }}
                  >
                    <SelectTrigger id="project-logical-key" aria-label="Project logical key" name="projectLogicalKey">
                      <SelectValue placeholder="Select key" />
                    </SelectTrigger>
                    <SelectContent>
                      {Object.keys(currentProjectSchema?.envByLogicalKey ?? {}).map((key) => (
                        <SelectItem key={key} value={key}>
                          {key}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </Field>

                <Field id="project-secret-key" label="Secret Key" required>
                  <Input
                    id="project-secret-key"
                    name="projectSecretKey"
                    value={projectSecretKey}
                    onChange={(event) => setProjectSecretKey(event.target.value)}
                    required
                  />
                </Field>
              </div>

              <Field id="project-secret-value" label="Secret Value" required>
                <Input
                  id="project-secret-value"
                  name="projectSecretValue"
                  type="password"
                  value={projectSecretValue}
                  onChange={(event) => setProjectSecretValue(event.target.value)}
                  autoComplete="off"
                  required
                />
              </Field>

              <Button type="submit" disabled={projectMutation.isPending} className="w-full">
                {projectMutation.isPending ? "Saving..." : "Save Project Secret"}
              </Button>
            </form>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <SectionHeader
              title="Global Secret"
              description="Shared defaults across all projects. Use project secret to override per project."
            />
          </CardHeader>
          <CardContent>
            <form
              className="space-y-3"
              onSubmit={(event) => {
                event.preventDefault();
                if (!globalSecretValue.trim()) {
                  toast.error("Global secret value is required");
                  return;
                }
                if (!globalName.trim() || !globalLogicalKey.trim() || !globalSecretKey.trim()) {
                  toast.error("Global secret name, logical key, and secret key are required");
                  return;
                }
                globalMutation.mutate();
              }}
            >
              <Field id="global-secret-name" label="Secret Name" required>
                <Input
                  id="global-secret-name"
                  name="globalSecretName"
                  value={globalName}
                  onChange={(event) => setGlobalName(event.target.value)}
                  required
                />
              </Field>

              <Field id="global-secret-provider" label="Provider" required>
                <Select
                  value={globalProvider}
                  onValueChange={(provider) => {
                    const schema = schemaByProvider[provider];
                    const logicalKey = firstLogicalKey(schema);
                    setGlobalProvider(provider);
                    setGlobalName(`global-${provider}`);
                    setGlobalLogicalKey(logicalKey);
                    setGlobalSecretKey(defaultSecretKey(schema, logicalKey));
                  }}
                >
                  <SelectTrigger id="global-secret-provider" aria-label="Global secret provider" name="globalSecretProvider">
                    <SelectValue placeholder="Select provider" />
                  </SelectTrigger>
                  <SelectContent>
                    {(schemasQuery.data ?? []).map((schema) => (
                      <SelectItem key={schema.provider} value={schema.provider}>
                        {schema.provider}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </Field>

              <div className="grid gap-3 md:grid-cols-2">
                <Field id="global-logical-key" label="Logical Key" required>
                  <Select
                    value={globalLogicalKey}
                    onValueChange={(logicalKey) => {
                      setGlobalLogicalKey(logicalKey);
                      setGlobalSecretKey(defaultSecretKey(currentGlobalSchema, logicalKey));
                    }}
                  >
                    <SelectTrigger id="global-logical-key" aria-label="Global logical key" name="globalLogicalKey">
                      <SelectValue placeholder="Select key" />
                    </SelectTrigger>
                    <SelectContent>
                      {Object.keys(currentGlobalSchema?.envByLogicalKey ?? {}).map((key) => (
                        <SelectItem key={key} value={key}>
                          {key}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </Field>

                <Field id="global-secret-key" label="Secret Key" required>
                  <Input
                    id="global-secret-key"
                    name="globalSecretKey"
                    value={globalSecretKey}
                    onChange={(event) => setGlobalSecretKey(event.target.value)}
                    required
                  />
                </Field>
              </div>

              <Field id="global-secret-value" label="Secret Value" required>
                <Input
                  id="global-secret-value"
                  name="globalSecretValue"
                  type="password"
                  value={globalSecretValue}
                  onChange={(event) => setGlobalSecretValue(event.target.value)}
                  autoComplete="off"
                  required
                />
              </Field>

              <Button type="submit" disabled={globalMutation.isPending} className="w-full">
                {globalMutation.isPending ? "Saving..." : "Save Global Secret"}
              </Button>
            </form>
          </CardContent>
        </Card>
      </div>

      <div className="mt-6 grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Project Secrets</CardTitle>
          </CardHeader>
          <CardContent>
            <DataStatePanel
              state={projectSecretsState}
              title={
                projectSecretsQuery.isError ? "Failed to load project secrets" : "No project secrets"
              }
              message={
                projectSecretsQuery.isError
                  ? projectSecretsQuery.error instanceof Error
                    ? projectSecretsQuery.error.message
                    : "Unknown error"
                  : "Add a project secret to override global credentials."
              }
              onRetry={projectSecretsQuery.isError ? () => void projectSecretsQuery.refetch() : undefined}
            />
            {(projectSecretsQuery.data?.length ?? 0) > 0 ? (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Name</TableHead>
                    <TableHead>Provider</TableHead>
                    <TableHead>K8s Secret</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {(projectSecretsQuery.data ?? []).map((secret) => (
                    <TableRow key={secret.id}>
                      <TableCell>{secret.name}</TableCell>
                      <TableCell>{secret.provider}</TableCell>
                      <TableCell className="mono text-xs">{secret.k8sSecretName}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            ) : null}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Global Secrets</CardTitle>
          </CardHeader>
          <CardContent>
            <DataStatePanel
              state={globalSecretsState}
              title={globalSecretsQuery.isError ? "Failed to load global secrets" : "No global secrets"}
              message={
                globalSecretsQuery.isError
                  ? globalSecretsQuery.error instanceof Error
                    ? globalSecretsQuery.error.message
                    : "Unknown error"
                  : "Create a global secret to share provider credentials across projects."
              }
              onRetry={globalSecretsQuery.isError ? () => void globalSecretsQuery.refetch() : undefined}
            />
            {(globalSecretsQuery.data?.length ?? 0) > 0 ? (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Name</TableHead>
                    <TableHead>Provider</TableHead>
                    <TableHead>K8s Secret</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {(globalSecretsQuery.data ?? []).map((secret) => (
                    <TableRow key={secret.id}>
                      <TableCell>{secret.name}</TableCell>
                      <TableCell>{secret.provider}</TableCell>
                      <TableCell className="mono text-xs">{secret.k8sSecretName}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            ) : null}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
