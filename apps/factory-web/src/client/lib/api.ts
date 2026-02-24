import type {
  Artifact,
  ArtifactContentResponse,
  AttractorDef,
  CursorPage,
  FilterState,
  GlobalSecret,
  Project,
  ProjectSecret,
  ProviderSchema,
  Run,
  RunModelConfig,
  SpecBundle
} from "./types";

const DEFAULT_API_BASE = "/api";

export function getApiBase(): string {
  const configBase = window.__FACTORY_APP_CONFIG__?.apiBaseUrl;
  const envBase = (import.meta as ImportMeta & { env?: Record<string, string | undefined> }).env
    ?.VITE_API_BASE_URL;
  return (configBase ?? envBase ?? DEFAULT_API_BASE).replace(/\/+$/, "");
}

export function buildApiUrl(path: string): string {
  const base = getApiBase();
  const normalizedPath = path.startsWith("/") ? path : `/${path}`;
  if (base.endsWith("/api") && normalizedPath.startsWith("/api/")) {
    return `${base}${normalizedPath.slice(4)}`;
  }
  return `${base}${normalizedPath}`;
}

async function apiRequest<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(buildApiUrl(path), {
    headers: {
      "content-type": "application/json",
      ...(init?.headers ?? {})
    },
    ...init
  });

  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    const errorMessage =
      typeof payload?.error === "string" ? payload.error : `${response.status} ${response.statusText}`;
    throw new Error(errorMessage);
  }
  return payload as T;
}

function withQuery(path: string, params: Record<string, string | number | undefined>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === "") {
      continue;
    }
    search.set(key, String(value));
  }
  const suffix = search.toString();
  return suffix ? `${path}?${suffix}` : path;
}

export function artifactDownloadUrl(runId: string, artifactId: string): string {
  return buildApiUrl(`/api/runs/${runId}/artifacts/${artifactId}/download`);
}

export async function listProjects(filters?: Pick<FilterState, "query" | "limit" | "cursor">): Promise<Project[]> {
  const payload = await apiRequest<{ projects: Project[]; nextCursor?: string | null }>(
    withQuery("/api/projects", {
      query: filters?.query,
      limit: filters?.limit,
      cursor: filters?.cursor
    })
  );
  return payload.projects;
}

export async function listProjectsPage(
  filters?: Pick<FilterState, "query" | "limit" | "cursor">
): Promise<CursorPage<Project>> {
  const payload = await apiRequest<{ projects: Project[]; nextCursor?: string | null }>(
    withQuery("/api/projects", {
      query: filters?.query,
      limit: filters?.limit,
      cursor: filters?.cursor
    })
  );
  return {
    items: payload.projects,
    nextCursor: payload.nextCursor ?? null
  };
}

export async function connectProjectRepo(
  projectId: string,
  input: { installationId: string; repoFullName: string; defaultBranch: string }
): Promise<Project> {
  return apiRequest<Project>(`/api/projects/${projectId}/repo/connect/github`, {
    method: "POST",
    body: JSON.stringify(input)
  });
}

export async function createProject(input: { name: string; namespace?: string }): Promise<Project> {
  return apiRequest<Project>("/api/projects", {
    method: "POST",
    body: JSON.stringify(input)
  });
}

export async function bootstrapSelf(input: {
  repoFullName: string;
  defaultBranch: string;
  attractorPath: string;
}): Promise<{ project: Project; attractor: AttractorDef }> {
  return apiRequest<{ project: Project; attractor: AttractorDef }>("/api/bootstrap/self", {
    method: "POST",
    body: JSON.stringify(input)
  });
}

export async function listProviders(): Promise<string[]> {
  const payload = await apiRequest<{ providers: string[] }>("/api/models/providers");
  return payload.providers;
}

export async function listModels(provider: string): Promise<Array<{ id: string; name: string; provider: string; api: string }>> {
  const payload = await apiRequest<{
    provider: string;
    models: Array<{ id: string; name: string; provider: string; api: string }>;
  }>(`/api/models?provider=${encodeURIComponent(provider)}`);
  return payload.models;
}

export async function listProviderSchemas(): Promise<ProviderSchema[]> {
  const payload = await apiRequest<{ providers: ProviderSchema[] }>("/api/secrets/providers");
  return payload.providers;
}

export async function listGlobalSecrets(): Promise<GlobalSecret[]> {
  const payload = await apiRequest<{ secrets: GlobalSecret[] }>("/api/secrets/global");
  return payload.secrets;
}

export async function upsertGlobalSecret(input: {
  name: string;
  provider: string;
  keyMappings: Record<string, string>;
  values: Record<string, string>;
}): Promise<GlobalSecret> {
  return apiRequest<GlobalSecret>("/api/secrets/global", {
    method: "POST",
    body: JSON.stringify(input)
  });
}

export async function listProjectSecrets(projectId: string): Promise<ProjectSecret[]> {
  const payload = await apiRequest<{ secrets: ProjectSecret[] }>(`/api/projects/${projectId}/secrets`);
  return payload.secrets;
}

export async function upsertProjectSecret(
  projectId: string,
  input: {
    name: string;
    provider: string;
    keyMappings: Record<string, string>;
    values: Record<string, string>;
  }
): Promise<ProjectSecret> {
  return apiRequest<ProjectSecret>(`/api/projects/${projectId}/secrets`, {
    method: "POST",
    body: JSON.stringify(input)
  });
}

export async function listAttractors(projectId: string): Promise<AttractorDef[]> {
  const payload = await apiRequest<{ attractors: AttractorDef[] }>(`/api/projects/${projectId}/attractors`);
  return payload.attractors;
}

export async function createAttractor(
  projectId: string,
  input: {
    name: string;
    repoPath: string;
    defaultRunType: "planning" | "implementation";
    description?: string;
    active?: boolean;
  }
): Promise<AttractorDef> {
  return apiRequest<AttractorDef>(`/api/projects/${projectId}/attractors`, {
    method: "POST",
    body: JSON.stringify(input)
  });
}

export async function listProjectRuns(
  projectId: string,
  filters?: Pick<FilterState, "status" | "runType" | "branch" | "limit" | "cursor">
): Promise<Run[]> {
  const payload = await apiRequest<{ runs: Run[]; nextCursor?: string | null }>(
    withQuery(`/api/projects/${projectId}/runs`, {
      status: filters?.status,
      runType: filters?.runType,
      branch: filters?.branch,
      limit: filters?.limit,
      cursor: filters?.cursor
    })
  );
  return payload.runs;
}

export async function listProjectRunsPage(
  projectId: string,
  filters?: Pick<FilterState, "status" | "runType" | "branch" | "limit" | "cursor">
): Promise<CursorPage<Run>> {
  const payload = await apiRequest<{ runs: Run[]; nextCursor?: string | null }>(
    withQuery(`/api/projects/${projectId}/runs`, {
      status: filters?.status,
      runType: filters?.runType,
      branch: filters?.branch,
      limit: filters?.limit,
      cursor: filters?.cursor
    })
  );
  return {
    items: payload.runs,
    nextCursor: payload.nextCursor ?? null
  };
}

export async function createRun(input: {
  projectId: string;
  attractorDefId: string;
  runType: "planning" | "implementation";
  sourceBranch: string;
  targetBranch: string;
  specBundleId?: string;
  modelConfig: RunModelConfig;
}): Promise<{ runId: string; status: string }> {
  return apiRequest<{ runId: string; status: string }>("/api/runs", {
    method: "POST",
    body: JSON.stringify(input)
  });
}

export async function getRun(runId: string): Promise<Run> {
  return apiRequest<Run>(`/api/runs/${runId}`);
}

export async function cancelRun(runId: string): Promise<{ runId: string; status: string }> {
  return apiRequest<{ runId: string; status: string }>(`/api/runs/${runId}/cancel`, {
    method: "POST"
  });
}

export async function getRunArtifacts(runId: string): Promise<{ artifacts: Artifact[]; specBundle: SpecBundle | null }> {
  return apiRequest<{ artifacts: Artifact[]; specBundle: SpecBundle | null }>(`/api/runs/${runId}/artifacts`);
}

export async function getArtifactContent(runId: string, artifactId: string): Promise<ArtifactContentResponse> {
  return apiRequest<ArtifactContentResponse>(`/api/runs/${runId}/artifacts/${artifactId}/content`);
}
