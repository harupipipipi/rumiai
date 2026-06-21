import { useMemo, useState, type FormEvent } from "react";
import { AlertTriangle, Monitor, X } from "lucide-react";

import { cn } from "../../lib/cn";
import { providerLabel } from "../../features/sandboxes/runtimeStatus";
import type { CreateDesktopRequest, DesktopResolution, DesktopStarter, RuntimeProviderStatus, SandboxTemplate } from "../../features/sandboxes/types";

type DesktopCreateDialogProps = {
  isOpen: boolean;
  templates: SandboxTemplate[];
  providers: RuntimeProviderStatus[];
  selectedProviderId?: string | null;
  loading?: boolean;
  error?: string | null;
  onClose: () => void;
  onCreate: (request: CreateDesktopRequest) => Promise<void> | void;
};

const RESOLUTIONS: DesktopResolution[] = [
  { width: 1280, height: 800 },
  { width: 1440, height: 900 },
  { width: 1920, height: 1080 },
];

function resolutionLabel(resolution: DesktopResolution): string {
  return `${resolution.width} x ${resolution.height}`;
}

function templateLabel(template: SandboxTemplate): string {
  return template.name || template.template_id;
}

export function DesktopCreateDialog({
  isOpen,
  templates,
  providers,
  selectedProviderId,
  loading = false,
  error,
  onClose,
  onCreate,
}: DesktopCreateDialogProps) {
  const firstTemplate = templates[0]?.template_id ?? "";
  const [name, setName] = useState("Ubuntu Desktop");
  const [templateId, setTemplateId] = useState(firstTemplate);
  const [providerId, setProviderId] = useState("auto");
  const [resolution, setResolution] = useState<DesktopResolution>(RESOLUTIONS[0]);
  const [starter, setStarter] = useState<DesktopStarter>("empty");
  const [browserUrl, setBrowserUrl] = useState("");
  const [workspaceId, setWorkspaceId] = useState("");
  const [workspaceAccess, setWorkspaceAccess] = useState("read_write");
  const [assignedAgent, setAssignedAgent] = useState("");

  const effectiveTemplateId = templateId || firstTemplate;
  const selectedTemplate = templates.find((template) => template.template_id === effectiveTemplateId) ?? templates[0] ?? null;
  const selectedProvider = useMemo(() => {
    if (providerId !== "auto") return providers.find((provider) => provider.provider_id === providerId) ?? null;
    return providers.find((provider) => provider.provider_id === selectedProviderId)
      ?? providers.find((provider) => provider.selected)
      ?? null;
  }, [providerId, providers, selectedProviderId]);
  const showLinuxNativeWarning = selectedProvider?.provider_id === "linux_native"
    || selectedProvider?.isolation?.host_process_namespace
    || selectedProvider?.isolation?.host_filesystem_shared
    || selectedProvider?.isolation?.host_network_shared;

  if (!isOpen) return null;

  const handleSubmit = (event: FormEvent) => {
    event.preventDefault();
    if (!effectiveTemplateId) return;
    void onCreate({
      name: name.trim() || "Desktop",
      template_id: effectiveTemplateId,
      provider_id: providerId === "auto" ? null : providerId,
      resolution,
      starter,
      browser_url: starter === "browser_url" ? browserUrl.trim() || undefined : undefined,
      workspace_id: workspaceId.trim() || null,
      workspace_access: workspaceAccess,
      assigned_agent: assignedAgent.trim() || null,
    });
  };

  return (
    <div className="absolute inset-0 rumi-layer-modal flex items-center justify-center bg-black/55 p-4">
      <form onSubmit={handleSubmit} className="flex max-h-[calc(100vh-48px)] w-[min(720px,100%)] flex-col overflow-hidden rounded-lg border border-zinc-800 bg-[#0a0a0c] shadow-2xl">
        <div className="flex items-center justify-between gap-3 border-b border-zinc-800/70 px-4 py-3">
          <div className="flex min-w-0 items-center gap-2">
            <span className="flex h-8 w-8 items-center justify-center rounded-md border border-zinc-700 bg-zinc-900 text-zinc-100">
              <Monitor size={15} />
            </span>
            <div className="min-w-0">
              <p className="truncate text-sm font-semibold text-zinc-100">New Desktop</p>
              <p className="truncate text-xs text-zinc-500">{selectedTemplate?.network_policy?.summary || "Network policy is resolved by the backend template."}</p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="flex h-8 w-8 items-center justify-center rounded-md text-zinc-500 transition-colors hover:bg-zinc-800 hover:text-zinc-100"
            aria-label="Close new desktop dialog"
          >
            <X size={15} />
          </button>
        </div>

        <div className="min-h-0 overflow-y-auto px-4 py-4">
          {templates.length === 0 ? (
            <div className="rounded-lg border border-amber-500/25 bg-amber-500/10 p-3 text-sm text-amber-100">
              Desktop templates are unavailable from the backend.
            </div>
          ) : (
            <div className="grid gap-4 md:grid-cols-2">
              <label className="grid gap-1.5 text-xs text-zinc-400">
                <span>Name</span>
                <input
                  value={name}
                  onChange={(event) => setName(event.target.value)}
                  className="h-9 rounded-md border border-zinc-800 bg-zinc-950 px-2 text-sm text-zinc-100 outline-none focus:border-zinc-600"
                />
              </label>

              <label className="grid gap-1.5 text-xs text-zinc-400">
                <span>Template</span>
                <select
                  value={effectiveTemplateId}
                  onChange={(event) => setTemplateId(event.target.value)}
                  className="h-9 rounded-md border border-zinc-800 bg-zinc-950 px-2 text-sm text-zinc-100 outline-none focus:border-zinc-600"
                >
                  {templates.map((template) => (
                    <option key={template.template_id} value={template.template_id}>
                      {templateLabel(template)}
                    </option>
                  ))}
                </select>
              </label>

              <label className="grid gap-1.5 text-xs text-zinc-400">
                <span>Provider</span>
                <select
                  value={providerId}
                  onChange={(event) => setProviderId(event.target.value)}
                  className="h-9 rounded-md border border-zinc-800 bg-zinc-950 px-2 text-sm text-zinc-100 outline-none focus:border-zinc-600"
                >
                  <option value="auto">Auto</option>
                  {providers.map((provider) => (
                    <option key={provider.provider_id} value={provider.provider_id}>
                      {providerLabel(provider)}
                    </option>
                  ))}
                </select>
              </label>

              <label className="grid gap-1.5 text-xs text-zinc-400">
                <span>Resolution</span>
                <select
                  value={resolutionLabel(resolution)}
                  onChange={(event) => {
                    const next = RESOLUTIONS.find((candidate) => resolutionLabel(candidate) === event.target.value);
                    if (next) setResolution(next);
                  }}
                  className="h-9 rounded-md border border-zinc-800 bg-zinc-950 px-2 text-sm text-zinc-100 outline-none focus:border-zinc-600"
                >
                  {RESOLUTIONS.map((candidate) => (
                    <option key={resolutionLabel(candidate)} value={resolutionLabel(candidate)}>
                      {resolutionLabel(candidate)}
                    </option>
                  ))}
                </select>
              </label>

              <label className="grid gap-1.5 text-xs text-zinc-400">
                <span>Starter</span>
                <select
                  value={starter}
                  onChange={(event) => setStarter(event.target.value as DesktopStarter)}
                  className="h-9 rounded-md border border-zinc-800 bg-zinc-950 px-2 text-sm text-zinc-100 outline-none focus:border-zinc-600"
                >
                  <option value="empty">Empty</option>
                  <option value="browser_url">Browser URL</option>
                  <option value="terminal">Terminal</option>
                </select>
              </label>

              {starter === "browser_url" && (
                <label className="grid gap-1.5 text-xs text-zinc-400">
                  <span>URL</span>
                  <input
                    value={browserUrl}
                    onChange={(event) => setBrowserUrl(event.target.value)}
                    placeholder="https://example.com"
                    className="h-9 rounded-md border border-zinc-800 bg-zinc-950 px-2 text-sm text-zinc-100 outline-none focus:border-zinc-600"
                  />
                </label>
              )}

              <label className="grid gap-1.5 text-xs text-zinc-400">
                <span>Workspace binding</span>
                <input
                  value={workspaceId}
                  onChange={(event) => setWorkspaceId(event.target.value)}
                  className="h-9 rounded-md border border-zinc-800 bg-zinc-950 px-2 text-sm text-zinc-100 outline-none focus:border-zinc-600"
                />
              </label>

              <label className="grid gap-1.5 text-xs text-zinc-400">
                <span>Workspace access</span>
                <select
                  value={workspaceAccess}
                  onChange={(event) => setWorkspaceAccess(event.target.value)}
                  className="h-9 rounded-md border border-zinc-800 bg-zinc-950 px-2 text-sm text-zinc-100 outline-none focus:border-zinc-600"
                >
                  <option value="none">None</option>
                  <option value="read_only">Read only</option>
                  <option value="read_write">Read/write</option>
                </select>
              </label>

              <label className="grid gap-1.5 text-xs text-zinc-400 md:col-span-2">
                <span>Agent assignment</span>
                <input
                  value={assignedAgent}
                  onChange={(event) => setAssignedAgent(event.target.value)}
                  className="h-9 rounded-md border border-zinc-800 bg-zinc-950 px-2 text-sm text-zinc-100 outline-none focus:border-zinc-600"
                />
              </label>
            </div>
          )}

          {showLinuxNativeWarning && (
            <div className="mt-4 flex gap-2 rounded-lg border border-amber-500/25 bg-amber-500/10 p-3 text-xs text-amber-100">
              <AlertTriangle size={15} className="mt-0.5 shrink-0" />
              <p>Linux native desktops can share host process, filesystem, or network namespaces beyond configured sandboxing. The backend isolation facts determine the exact boundary.</p>
            </div>
          )}

          {error && <p className="mt-4 rounded-lg border border-red-500/25 bg-red-500/10 px-3 py-2 text-xs text-red-100">{error}</p>}
        </div>

        <div className="flex items-center justify-end gap-2 border-t border-zinc-800/70 px-4 py-3">
          <button type="button" onClick={onClose} className="h-8 rounded-md border border-zinc-800 px-3 text-xs font-medium text-zinc-300 hover:bg-zinc-900">
            Cancel
          </button>
          <button
            type="submit"
            disabled={loading || templates.length === 0}
            className="h-8 rounded-md bg-zinc-100 px-3 text-xs font-semibold text-zinc-950 hover:bg-white disabled:cursor-not-allowed disabled:opacity-50"
          >
            {loading ? "Creating..." : "Create Desktop"}
          </button>
        </div>
      </form>
    </div>
  );
}
