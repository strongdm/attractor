import { useMemo, useState } from "react";
import { Check, ChevronsUpDown } from "lucide-react";

import type { Project } from "../../lib/types";
import { cn } from "../../lib/utils";
import { Button } from "../ui/button";
import { Command, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList } from "../ui/command";
import { Popover, PopoverContent, PopoverTrigger } from "../ui/popover";

export function ProjectContextSwitcher(props: {
  projects: Project[];
  value?: string;
  onValueChange: (projectId: string) => void;
  disabled?: boolean;
}) {
  const [open, setOpen] = useState(false);

  const current = useMemo(
    () => props.projects.find((project) => project.id === props.value),
    [props.projects, props.value]
  );
  const sortedProjects = useMemo(
    () => [...props.projects].sort((left, right) => left.name.localeCompare(right.name)),
    [props.projects]
  );

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button
          variant="outline"
          role="combobox"
          aria-expanded={open}
          aria-label="Select project context"
          className="w-full justify-between md:w-80"
          disabled={props.disabled}
        >
          <span className="truncate text-left">{current?.name ?? "Select project"}</span>
          <ChevronsUpDown className="ml-2 h-4 w-4 shrink-0 opacity-60" />
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-[min(90vw,24rem)] p-0" align="end">
        <Command>
          <CommandInput placeholder="Search project by name or namespace" />
          <CommandList>
            <CommandEmpty>No projects found.</CommandEmpty>
            <CommandGroup>
              {sortedProjects.map((project) => (
                <CommandItem
                  key={project.id}
                  value={`${project.name} ${project.namespace} ${project.id}`}
                  data-current={props.value === project.id ? "true" : "false"}
                  className={cn(
                    "gap-3",
                    props.value === project.id && "bg-secondary/70 text-foreground ring-1 ring-border"
                  )}
                  onSelect={() => {
                    props.onValueChange(project.id);
                    setOpen(false);
                  }}
                >
                  <div className="min-w-0 flex-1">
                    <div className="truncate text-sm font-medium leading-tight">{project.name}</div>
                    <div className="truncate text-xs text-muted-foreground">{project.namespace}</div>
                  </div>
                  <Check className={cn("h-4 w-4", props.value === project.id ? "opacity-100" : "opacity-0")} />
                </CommandItem>
              ))}
            </CommandGroup>
          </CommandList>
        </Command>
      </PopoverContent>
    </Popover>
  );
}
