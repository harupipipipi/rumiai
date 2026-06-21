import { AlertTriangle, Bot, Cpu, Monitor, Network, Shield, UserCheck } from "lucide-react";

import { cn } from "../../lib/cn";
import type { DesktopInstance, RuntimeIsolationFacts } from "../../features/sandboxes/types";

type DesktopInspectorProps = {
  desktop: DesktopInstance | null;
  hasLease: boolean;
  leaseError?: string | null;
  actionError?: string | null;
};

function factRow(label: string, value: string, tone: "default" | "warning" = "default") {
  return (
    <div className="flex items-start justify-between gap-3 border-b border-zinc-900 py-2 last:border-b-0">
      <span className="text-zinc-500">{label}</span>
      <span className={cn("max-w-[180px] text-right text-zinc-200", tone === "warning" && "text-amber-200")}>{value}</span>
    </div>
  );
}

function isolationRows(isolation: RuntimeIsolationFacts | null | undefined, providerId?: string | null) {
  if (!isolation) {
    return [factRow("Facts", "Unavailable from backend", "warning")];
  }
  const rows = [
    factRow("Mode", isolation.summary || isolation.mode || "Backend-defined"),
  ];
  if (providerId === "linux_native" || isolation.mode === "linux_native") {
    rows.push(factRow("VM isolation", "No VM claimed", "warning"));
  } else {
    rows.push(factRow("VM isolation", isolation.vm ? "Yes" : "No"));
  }
  rows.push(factRow("Container", isolation.container ? "Yes" : "No"));
  rows.push(factRow("Host process namespace", isolation.host_process_namespace ? "Shared" : "Isolated", isolation.host_process_namespace ? "warning" : "default"));
  rows.push(factRow("Host filesystem", isolation.host_filesystem_shared ? "Shared" : "Backend-limited", isolation.host_filesystem_shared ? "warning" : "default"));
  rows.push(factRow("Host network", isolation.host_network_shared ? "Shared" : "Backend-limited", isolation.host_network_shared ? "warning" : "default"));
  return rows;
}

export function DesktopInspector({ desktop, hasLease, leaseError, actionError }: DesktopInspectorProps) {
  if (!desktop) {
    return (
      <aside className="rounded-lg border border-zinc-800/70 bg-[#0a0a0c] p-4">
        <Monitor size={22} className="text-zinc-600" />
        <p className="mt-3 text-sm font-semibold text-zinc-200">No desktop selected</p>
        <p className="mt-1 text-xs text-zinc-500">Desktop status and isolation facts appear after the backend returns a seat.</p>
      </aside>
    );
  }

  return (
    <aside className="grid gap-3 rounded-lg border border-zinc-800/70 bg-[#0a0a0c] p-4 text-xs">
      <div className="min-w-0">
        <p className="truncate text-sm font-semibold text-zinc-100">{desktop.name}</p>
        <p className="mt-1 truncate font-mono text-[11px] text-zinc-500">{desktop.seat_id}</p>
      </div>

      <section>
        <div className="mb-2 flex items-center gap-1.5 text-zinc-300">
          <Cpu size={13} />
          <span className="font-semibold">Status/provider</span>
        </div>
        <div className="rounded-md border border-zinc-800 bg-zinc-950/60 px-3">
          {factRow("Status", desktop.status)}
          {factRow("Provider", desktop.provider_label || desktop.provider_id || "Pending")}
          {factRow("Template", desktop.template_id || "Unknown")}
          {factRow("Resolution", desktop.resolution ? `${desktop.resolution.width} x ${desktop.resolution.height}` : "Unknown")}
        </div>
      </section>

      <section>
        <div className="mb-2 flex items-center gap-1.5 text-zinc-300">
          <Shield size={13} />
          <span className="font-semibold">Isolation</span>
        </div>
        <div className="rounded-md border border-zinc-800 bg-zinc-950/60 px-3">
          {isolationRows(desktop.isolation, desktop.provider_id).map((row, index) => (
            <div key={index}>{row}</div>
          ))}
        </div>
      </section>

      <section>
        <div className="mb-2 flex items-center gap-1.5 text-zinc-300">
          <Network size={13} />
          <span className="font-semibold">Workspace/network</span>
        </div>
        <div className="rounded-md border border-zinc-800 bg-zinc-950/60 px-3">
          {factRow("Workspace", desktop.workspace?.label || desktop.workspace?.workspace_id || "None")}
          {factRow("Access", desktop.workspace?.access || "Backend policy")}
          {factRow("Network", desktop.network_policy?.summary || desktop.network_policy?.default || "Backend policy")}
        </div>
      </section>

      <section>
        <div className="mb-2 flex items-center gap-1.5 text-zinc-300">
          {hasLease ? <UserCheck size={13} /> : <Bot size={13} />}
          <span className="font-semibold">Agent/control</span>
        </div>
        <div className="rounded-md border border-zinc-800 bg-zinc-950/60 px-3">
          {factRow("Assigned agent", desktop.assigned_agent || "Unassigned")}
          {factRow("Control", hasLease ? "Human takeover" : desktop.control?.holder === "ai" ? "AI" : "Available")}
          {desktop.control?.message && factRow("Control note", desktop.control.message)}
        </div>
      </section>

      {(desktop.last_error || leaseError || actionError) && (
        <section className="rounded-lg border border-red-500/25 bg-red-500/10 p-3 text-red-100">
          <div className="flex items-center gap-1.5 font-semibold">
            <AlertTriangle size={13} />
            <span>Latest issue</span>
          </div>
          <p className="mt-1">
            {actionError
              || leaseError
              || (typeof desktop.last_error === "string" ? desktop.last_error : desktop.last_error?.message)
              || "Unknown desktop error."}
          </p>
        </section>
      )}
    </aside>
  );
}
