import { Badge } from "../ui/badge";

export function StatusPill(props: { status: string }) {
  const normalized = props.status.toUpperCase();

  const variant: "success" | "warning" | "destructive" | "secondary" =
    normalized === "SUCCEEDED"
      ? "success"
      : normalized === "RUNNING"
      ? "warning"
      : normalized === "FAILED"
      ? "destructive"
      : "secondary";

  return <Badge variant={variant}>{normalized}</Badge>;
}
