import { Suspense, lazy } from "react";
import { Link, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { toast } from "sonner";

import { artifactDownloadUrl, getArtifactContent } from "../lib/api";
import { monacoLanguageForArtifact } from "../lib/artifact-language";
import type { PageState } from "../lib/types";
import { DataStatePanel } from "../components/common/data-state-panel";
import { PageTitle } from "../components/layout/page-title";
import { Badge } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../components/ui/card";

const MonacoEditor = lazy(async () => {
  const module = await import("@monaco-editor/react");
  return { default: module.default };
});

export function ArtifactViewerPage() {
  const params = useParams<{ runId: string; artifactId: string }>();
  const runId = params.runId ?? "";
  const artifactId = params.artifactId ?? "";

  const artifactQuery = useQuery({
    queryKey: ["artifact-content", runId, artifactId],
    queryFn: () => getArtifactContent(runId, artifactId),
    enabled: runId.length > 0 && artifactId.length > 0
  });

  const state: PageState = artifactQuery.isLoading
    ? "loading"
    : artifactQuery.isError
    ? "error"
    : artifactQuery.data
    ? "ready"
    : "empty";

  if (state !== "ready" || !artifactQuery.data) {
    return (
      <DataStatePanel
        state={state}
        title={artifactQuery.isError ? "Failed to load artifact" : state === "loading" ? "Loading artifact" : "Artifact not found"}
        message={
          artifactQuery.isError
            ? artifactQuery.error instanceof Error
              ? artifactQuery.error.message
              : "Unknown error"
            : state === "loading"
            ? "Fetching artifact content preview..."
            : "Artifact does not exist for this run."
        }
        onRetry={artifactQuery.isError ? () => void artifactQuery.refetch() : undefined}
      />
    );
  }

  const payload = artifactQuery.data;
  const language = monacoLanguageForArtifact(payload.artifact.key);
  const downloadHref = artifactDownloadUrl(runId, artifactId);
  const isBinary = payload.content === null;

  return (
    <div>
      <PageTitle
        title={payload.artifact.key}
        description={payload.artifact.path}
        actions={
          <>
            <Button asChild variant="outline">
              <Link to={`/runs/${runId}?tab=artifacts`}>Back To Run</Link>
            </Button>
            <Button
              variant="outline"
              onClick={async () => {
                if (!payload.content) {
                  return;
                }
                await navigator.clipboard.writeText(payload.content);
                toast.success("Artifact content copied");
              }}
              disabled={!payload.content}
            >
              Copy
            </Button>
            <Button asChild>
              <a href={downloadHref}>Download</a>
            </Button>
          </>
        }
      />

      <Card className="mb-4">
        <CardHeader>
          <CardTitle>Artifact Metadata</CardTitle>
          <CardDescription>Preview limit and format details for this object.</CardDescription>
        </CardHeader>
        <CardContent className="flex flex-wrap gap-2">
          <Badge variant="secondary">{payload.artifact.contentType ?? "unknown type"}</Badge>
          <Badge variant="secondary">{payload.bytesRead.toLocaleString()} bytes loaded</Badge>
          {payload.artifact.sizeBytes ? (
            <Badge variant="secondary">{payload.artifact.sizeBytes.toLocaleString()} bytes total</Badge>
          ) : null}
          {payload.truncated ? <Badge variant="warning">Preview Truncated</Badge> : null}
          {isBinary ? <Badge variant="warning">Binary Artifact</Badge> : null}
        </CardContent>
      </Card>

      {payload.truncated ? (
        <Card className="mb-4 border-warning/40">
          <CardHeader>
            <CardTitle>Preview limit reached</CardTitle>
            <CardDescription>
              Inline preview is capped for performance. Download the artifact for the full content.
            </CardDescription>
          </CardHeader>
        </Card>
      ) : null}

      {isBinary ? (
        <Card>
          <CardHeader>
            <CardTitle>No inline preview</CardTitle>
            <CardDescription>This artifact is treated as binary and is only available as a download.</CardDescription>
          </CardHeader>
          <CardContent>
            <Button asChild>
              <a href={downloadHref}>Download Artifact</a>
            </Button>
          </CardContent>
        </Card>
      ) : (
        <Card>
          <CardContent className="p-0">
            <Suspense fallback={<div className="p-4 text-sm text-muted-foreground">Loading editor...</div>}>
              <MonacoEditor
                height="68vh"
                value={payload.content ?? ""}
                language={language}
                theme="vs-light"
                options={{
                  readOnly: true,
                  minimap: { enabled: false },
                  lineNumbers: "on",
                  scrollBeyondLastLine: false,
                  fontSize: 13,
                  wordWrap: "on",
                  smoothScrolling: true
                }}
              />
            </Suspense>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
