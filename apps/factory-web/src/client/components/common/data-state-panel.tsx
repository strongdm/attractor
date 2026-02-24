import { AlertCircle, LoaderCircle } from "lucide-react";

import type { PageState } from "../../lib/types";
import { Button } from "../ui/button";

export function DataStatePanel(props: {
  state: PageState;
  title: string;
  message?: string;
  retryLabel?: string;
  onRetry?: () => void;
}) {
  if (props.state === "ready") {
    return null;
  }

  if (props.state === "loading") {
    return (
      <div className="flex items-center gap-2 rounded-md border border-border bg-background px-3 py-3 text-sm text-muted-foreground">
        <LoaderCircle className="h-4 w-4 animate-spin" />
        <span>{props.message ?? "Loading..."}</span>
      </div>
    );
  }

  if (props.state === "error") {
    return (
      <div className="space-y-3 rounded-md border border-destructive/40 bg-destructive/5 px-3 py-3">
        <div className="flex items-start gap-2 text-sm text-destructive">
          <AlertCircle className="mt-0.5 h-4 w-4" />
          <div>
            <p className="font-semibold">{props.title}</p>
            {props.message ? <p className="font-normal">{props.message}</p> : null}
          </div>
        </div>
        {props.onRetry ? (
          <Button variant="outline" size="sm" onClick={props.onRetry}>
            {props.retryLabel ?? "Retry"}
          </Button>
        ) : null}
      </div>
    );
  }

  return (
    <div className="rounded-md border border-border bg-background px-3 py-4 text-sm text-muted-foreground">
      <p className="font-medium text-foreground">{props.title}</p>
      {props.message ? <p className="mt-1">{props.message}</p> : null}
    </div>
  );
}
