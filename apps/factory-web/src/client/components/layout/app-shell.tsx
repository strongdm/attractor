import { useMemo, useState } from "react";
import { Link, NavLink, Outlet, useLocation, useNavigate, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Menu, X } from "lucide-react";

import { getRun, listProjects } from "../../lib/api";
import { pathForProjectSelection } from "../../lib/project-routing";
import { cn } from "../../lib/utils";
import { Button } from "../ui/button";
import { ProjectContextSwitcher } from "./project-context-switcher";

const primaryNav = [
  { to: "/", label: "Dashboard" },
  { to: "/projects", label: "Projects" }
];

function toTitleCase(value: string): string {
  return value
    .split("-")
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function trimLabel(input: string): string {
  if (input.length <= 28) {
    return input;
  }
  return `${input.slice(0, 25)}...`;
}

export function AppShell() {
  const location = useLocation();
  const navigate = useNavigate();
  const params = useParams<{ projectId?: string; runId?: string }>();
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const projectIdFromPath = params.projectId;
  const runIdFromPath = params.runId;

  const projectsQuery = useQuery({
    queryKey: ["projects"],
    queryFn: () => listProjects({ limit: 200 })
  });

  const runContextQuery = useQuery({
    queryKey: ["run-context", runIdFromPath],
    queryFn: () => getRun(runIdFromPath ?? ""),
    enabled: Boolean(runIdFromPath)
  });

  const breadcrumbs = useMemo(() => {
    const parts = location.pathname.split("/").filter(Boolean);
    const items: Array<{ href: string; label: string }> = [{ href: "/", label: "Dashboard" }];

    if (parts.length === 0) {
      return items;
    }

    let cursor = "";
    for (let index = 0; index < parts.length; index += 1) {
      const part = parts[index] ?? "";
      cursor += `/${part}`;

      if (part === "projects" && index + 1 < parts.length) {
        const projectId = parts[index + 1] ?? "";
        const project = projectsQuery.data?.find((candidate) => candidate.id === projectId);
        items.push({ href: "/projects", label: "Projects" });
        items.push({ href: `/projects/${projectId}`, label: trimLabel(project?.name ?? "Project") });
        index += 1;
        cursor += `/${projectId}`;
        continue;
      }

      if (part === "runs" && index + 1 < parts.length) {
        const runId = parts[index + 1] ?? "";
        const runProjectId = runContextQuery.data?.projectId;
        const runProject = runProjectId
          ? projectsQuery.data?.find((candidate) => candidate.id === runProjectId)
          : undefined;
        if (runProjectId) {
          items.push({ href: "/projects", label: "Projects" });
          items.push({ href: `/projects/${runProjectId}`, label: trimLabel(runProject?.name ?? "Project") });
          items.push({ href: `/projects/${runProjectId}/runs`, label: "Runs" });
        } else {
          items.push({ href: "/projects", label: "Runs" });
        }
        items.push({ href: `/runs/${runId}`, label: runId.slice(0, 8) });
        index += 1;
        cursor += `/${runId}`;
        continue;
      }

      items.push({ href: cursor, label: toTitleCase(part) });
    }

    return items;
  }, [location.pathname, projectsQuery.data, runContextQuery.data?.projectId]);

  const selectedProjectId = useMemo(() => {
    if (projectIdFromPath) {
      return projectIdFromPath;
    }

    if (runContextQuery.data?.projectId) {
      return runContextQuery.data.projectId;
    }

    if (runIdFromPath && runContextQuery.isLoading) {
      return undefined;
    }

    return projectsQuery.data?.[0]?.id;
  }, [
    projectIdFromPath,
    projectsQuery.data,
    runContextQuery.data?.projectId,
    runContextQuery.isLoading,
    runIdFromPath
  ]);

  return (
    <div className="flex min-h-screen flex-col md:flex-row">
      <div className="flex items-center justify-between border-b border-border/80 bg-card/90 px-4 py-3 backdrop-blur md:hidden">
        <div>
          <p className="text-xs uppercase tracking-[0.22em] text-muted-foreground">Attractor</p>
          <p className="text-lg font-semibold leading-tight">Factory</p>
        </div>
        <Button
          type="button"
          variant="outline"
          size="sm"
          aria-label={mobileNavOpen ? "Close navigation" : "Open navigation"}
          onClick={() => setMobileNavOpen((open) => !open)}
        >
          {mobileNavOpen ? <X className="h-4 w-4" /> : <Menu className="h-4 w-4" />}
        </Button>
      </div>

      <aside
        className={cn(
          "border-b border-border/80 bg-card/90 p-4 backdrop-blur md:min-h-screen md:w-72 md:border-b-0 md:border-r",
          mobileNavOpen ? "block" : "hidden md:block"
        )}
      >
        <div className="mb-6 hidden md:block">
          <p className="text-xs uppercase tracking-[0.22em] text-muted-foreground">Attractor</p>
          <h1 className="text-xl font-semibold">Factory</h1>
        </div>

        <nav className="space-y-1">
          {primaryNav.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              onClick={() => setMobileNavOpen(false)}
              className={({ isActive }) =>
                cn(
                  "block rounded-md px-3 py-2.5 text-sm font-medium transition-colors",
                  isActive
                    ? "bg-primary text-primary-foreground"
                    : "text-muted-foreground hover:bg-muted hover:text-foreground"
                )
              }
              end={item.to === "/"}
            >
              {item.label}
            </NavLink>
          ))}

          {selectedProjectId ? (
            <div className="mt-4 space-y-1 border-t border-border pt-4">
              {[
                { to: `/projects/${selectedProjectId}`, label: "Overview" },
                { to: `/projects/${selectedProjectId}/secrets`, label: "Secrets" },
                { to: `/projects/${selectedProjectId}/attractors`, label: "Attractors" },
                { to: `/projects/${selectedProjectId}/runs`, label: "Runs" }
              ].map((item) => (
                <NavLink
                  key={item.to}
                  to={item.to}
                  onClick={() => setMobileNavOpen(false)}
                  className={({ isActive }) =>
                    cn(
                      "block rounded-md px-3 py-2 text-sm transition-colors",
                      isActive
                        ? "bg-secondary text-secondary-foreground"
                        : "text-muted-foreground hover:bg-muted hover:text-foreground"
                    )
                  }
                >
                  {item.label}
                </NavLink>
              ))}
            </div>
          ) : null}
        </nav>
      </aside>

      <div className="flex-1">
        <header className="border-b border-border/80 bg-card/80 px-4 py-3 backdrop-blur md:px-6 md:py-4">
          <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
            <nav aria-label="Breadcrumb" className="flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
              {breadcrumbs.map((crumb, index) => {
                const isLast = index === breadcrumbs.length - 1;
                return (
                  <div key={`${crumb.href}-${index}`} className="flex items-center gap-2">
                    {index > 0 ? <span aria-hidden="true">/</span> : null}
                    {isLast ? (
                      <span className="font-medium text-foreground">{crumb.label}</span>
                    ) : (
                      <Link to={crumb.href} className="hover:text-foreground">
                        {crumb.label}
                      </Link>
                    )}
                  </div>
                );
              })}
            </nav>

            <ProjectContextSwitcher
              projects={projectsQuery.data ?? []}
              value={selectedProjectId}
              disabled={projectsQuery.isLoading || (projectsQuery.data?.length ?? 0) === 0}
              onValueChange={(value) => {
                navigate(pathForProjectSelection(location.pathname, value));
              }}
            />
          </div>
        </header>

        <main className="p-4 md:p-6 lg:p-7">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
