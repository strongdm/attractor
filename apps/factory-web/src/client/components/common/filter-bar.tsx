import type { ReactNode } from "react";

import { cn } from "../../lib/utils";
import { Button } from "../ui/button";

export function FilterBar(props: {
  children: ReactNode;
  onReset?: () => void;
  hasActiveFilters?: boolean;
  className?: string;
}) {
  return (
    <div className={cn("rounded-lg border border-border bg-background p-3", props.className)}>
      <div className="flex flex-col gap-2 md:flex-row md:items-end">
        <div className="grid flex-1 gap-2 md:grid-cols-3">{props.children}</div>
        {props.onReset ? (
          <Button
            variant="ghost"
            size="sm"
            onClick={props.onReset}
            disabled={!props.hasActiveFilters}
            className="self-start md:self-auto"
          >
            Clear Filters
          </Button>
        ) : null}
      </div>
    </div>
  );
}
