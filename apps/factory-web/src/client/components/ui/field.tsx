import type { ReactNode } from "react";

import { cn } from "../../lib/utils";
import { Label } from "./label";

export function Field(props: {
  id: string;
  label: string;
  required?: boolean;
  hint?: string;
  error?: string;
  children: ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("space-y-1.5", props.className)}>
      <Label htmlFor={props.id}>
        {props.label}
        {props.required ? <span aria-hidden="true" className="ml-1 text-destructive">*</span> : null}
      </Label>
      {props.children}
      {props.error ? <FieldError>{props.error}</FieldError> : null}
      {props.hint && !props.error ? <FieldHint>{props.hint}</FieldHint> : null}
    </div>
  );
}

export function FieldHint({ children }: { children: ReactNode }) {
  return <p className="text-xs text-muted-foreground">{children}</p>;
}

export function FieldError({ children }: { children: ReactNode }) {
  return <p className="text-xs text-destructive">{children}</p>;
}
