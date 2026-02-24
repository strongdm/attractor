import type { ReactNode } from "react";

import { cn } from "../../lib/utils";

export function SectionHeader(props: {
  title: string;
  description?: string;
  actions?: ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("flex flex-col gap-3 md:flex-row md:items-start md:justify-between", props.className)}>
      <div>
        <h3 className="text-lg font-semibold tracking-tight">{props.title}</h3>
        {props.description ? <p className="mt-1 text-sm text-muted-foreground">{props.description}</p> : null}
      </div>
      {props.actions ? <div className="flex flex-wrap items-center gap-2">{props.actions}</div> : null}
    </div>
  );
}
