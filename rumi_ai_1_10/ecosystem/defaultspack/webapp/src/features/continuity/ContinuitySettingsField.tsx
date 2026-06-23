import { useEffect, useMemo, useState } from "react";
import { CheckCircle2, Copy, KeyRound, Link2, Loader2, Play, RefreshCw, Route, Server, ShieldAlert, ShieldCheck } from "lucide-react";

import { cn } from "../../lib/cn";
import type { SettingsFieldRendererProps } from "../../renderers/settings/fieldRendererRegistry";
import {
  continuityApi,
  type ContinuityHandoffOperation,
  type ContinuityHandoffPlan,
  type ContinuityNode,
  type ContinuityPairingStartResponse,
  type ContinuityPreflightResult,
  type ContinuityProviderRoute,
} from "./api";

type ContinuityFieldConfig = {
  sandbox_id: string;
  destination_node_id: string;
  route_id: string;
  mode: string;
  last_operation_id?: string;
};

type ContinuityInitialData = {
  local_node?: ContinuityNode | null;
  nodes: ContinuityNode[];
  routes: ContinuityProviderRoute[];
  operations: ContinuityHandoffOperation[];
  plan?: ContinuityHandoffPlan | null;
};

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {};
}

function stringValue(value: unknown, fallback = ""): string {
  const text = String(value ?? "").trim();
  return text || fallback;
}

function configFromValue(value: unknown): ContinuityFieldConfig {
  const raw = asRecord(value);
  return {
    sandbox_id: stringValue(raw.sandbox_id ?? raw.seat_id, "logical-sandbox"),
    destination_node_id: stringValue(raw.destination_node_id ?? raw.node_id),
    route_id: stringValue(raw.route_id),
    mode: stringValue(raw.mode, "move"),
    last_operation_id: stringValue(raw.last_operation_id) || undefined,
  };
}

function listFromRecord<T>(value: unknown): T[] {
  return Array.isArray(value) ? value.filter((item): item is T => Boolean(item && typeof item === "object")) : [];
}

function initialDataFromDefault(value: unknown): ContinuityInitialData {
  const raw = asRecord(value);
  return {
    local_node: (raw.local_node && typeof raw.local_node === "object" ? raw.local_node as ContinuityNode : null),
    nodes: listFromRecord<ContinuityNode>(raw.nodes),
    routes: listFromRecord<ContinuityProviderRoute>(raw.routes),
    operations: listFromRecord<ContinuityHandoffOperation>(raw.operations),
    plan: raw.plan && typeof raw.plan === "object" ? raw.plan as ContinuityHandoffPlan : null,
  };
}

function routeLabel(route: ContinuityProviderRoute | undefined): string {
  if (!route) return "No provider route";
  return route.qualified_route || [route.provider_id, route.api_id, route.model_id].filter(Boolean).join("/");
}

function nodeLabel(node: ContinuityNode | undefined): string {
  if (!node) return "No destination";
  return node.display_name || node.node_id;
}

function statusTone(ok: boolean | undefined): string {
  if (ok === true) return "border-emerald-500/30 bg-emerald-500/10 text-emerald-200";
  if (ok === false) return "border-amber-500/30 bg-amber-500/10 text-amber-200";
  return "border-zinc-800 bg-zinc-950 text-zinc-400";
}

function formatError(error: unknown): string {
  return error instanceof Error ? error.message : "Continuity request failed.";
}

function latestOperation(operations: ContinuityHandoffOperation[]): ContinuityHandoffOperation | null {
  return operations[0] ?? null;
}

function copyText(text: string, onCopied: (label: string) => void) {
  if (!navigator.clipboard?.writeText) return;
  void navigator.clipboard.writeText(text).then(() => onCopied("copied")).catch(() => undefined);
}

export function ContinuitySettingsField({
  sectionId,
  field,
  value,
  onChange,
}: SettingsFieldRendererProps) {
  const initial = useMemo(() => initialDataFromDefault(field.default), [field.default]);
  const config = useMemo(() => configFromValue(value ?? field.default), [field.default, value]);
  const [localNode, setLocalNode] = useState<ContinuityNode | null>(initial.local_node ?? null);
  const [nodes, setNodes] = useState<ContinuityNode[]>(initial.nodes);
  const [routes, setRoutes] = useState<ContinuityProviderRoute[]>(initial.routes);
  const [operations, setOperations] = useState<ContinuityHandoffOperation[]>(initial.operations);
  const [selectedNodeId, setSelectedNodeId] = useState(config.destination_node_id);
  const [selectedRouteId, setSelectedRouteId] = useState(config.route_id);
  const [sandboxId, setSandboxId] = useState(config.sandbox_id);
  const [mode, setMode] = useState(config.mode);
  const [pairing, setPairing] = useState<ContinuityPairingStartResponse | null>(null);
  const [probe, setProbe] = useState<ContinuityPreflightResult | null>(null);
  const [plan, setPlan] = useState<ContinuityHandoffPlan | null>(initial.plan ?? null);
  const [loading, setLoading] = useState(false);
  const [action, setAction] = useState<"idle" | "pairing" | "probe" | "plan" | "handoff">("idle");
  const [error, setError] = useState("");
  const [copyState, setCopyState] = useState("");

  const destinationNodes = nodes.filter((node) => node.destination_kind !== "source");
  const selectedNode = destinationNodes.find((node) => node.node_id === selectedNodeId) ?? destinationNodes[0];
  const portableRoutes = routes.filter((route) => route.portable);
  const selectedRoute = routes.find((route) => route.route_id === selectedRouteId) ?? portableRoutes[0] ?? routes[0];
  const operation = latestOperation(operations);
  const canRun = Boolean(selectedNode?.node_id && selectedRoute?.route_id && selectedRoute.portable);

  const persistConfig = (patch: Partial<ContinuityFieldConfig>) => {
    const next = {
      ...config,
      sandbox_id: sandboxId,
      destination_node_id: selectedNode?.node_id || selectedNodeId,
      route_id: selectedRoute?.route_id || selectedRouteId,
      mode,
      ...patch,
    };
    onChange(sectionId, field.id, next);
  };

  const refresh = async () => {
    setLoading(true);
    setError("");
    try {
      const [nodeResult, routeResult, operationResult] = await Promise.all([
        continuityApi.listNodes(),
        continuityApi.listProviderRoutes(),
        continuityApi.listHandoffs(),
      ]);
      setLocalNode(nodeResult.local_node ?? null);
      setNodes(nodeResult.nodes ?? []);
      setRoutes(routeResult.routes ?? []);
      setOperations(operationResult.operations ?? []);
      const nextDestination = (nodeResult.nodes ?? []).find((node) => node.destination_kind !== "source");
      const nextRoute = (routeResult.routes ?? []).find((route) => route.portable) ?? (routeResult.routes ?? [])[0];
      if (!selectedNodeId && nextDestination?.node_id) setSelectedNodeId(nextDestination.node_id);
      if (!selectedRouteId && nextRoute?.route_id) setSelectedRouteId(nextRoute.route_id);
    } catch (refreshError) {
      setError(formatError(refreshError));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void refresh();
    // The first load should happen once; field.default already seeds SSR and tests.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handoffPayload = () => ({
    sandbox_id: sandboxId.trim() || "logical-sandbox",
    destination_node_id: selectedNode?.node_id || selectedNodeId,
    route_id: selectedRoute?.route_id || selectedRouteId,
    mode,
    credential_ttl_seconds: 3600,
  });

  const handleProbe = async () => {
    if (!selectedRoute?.route_id) return;
    setAction("probe");
    setError("");
    try {
      const result = await continuityApi.probeProviderRoute(selectedRoute.route_id, selectedNode?.node_id || selectedNodeId);
      setProbe(result);
    } catch (probeError) {
      setError(formatError(probeError));
    } finally {
      setAction("idle");
    }
  };

  const handlePlan = async () => {
    if (!canRun) return;
    setAction("plan");
    setError("");
    try {
      const result = await continuityApi.planHandoff(handoffPayload());
      setPlan(result.plan);
      persistConfig({});
    } catch (planError) {
      setError(formatError(planError));
    } finally {
      setAction("idle");
    }
  };

  const handleHandoff = async () => {
    if (!canRun) return;
    setAction("handoff");
    setError("");
    try {
      const result = await continuityApi.startHandoff(handoffPayload());
      setOperations((current) => [result.operation, ...current.filter((item) => item.operation_id !== result.operation.operation_id)]);
      persistConfig({ last_operation_id: result.operation.operation_id });
    } catch (handoffError) {
      setError(formatError(handoffError));
    } finally {
      setAction("idle");
    }
  };

  const handlePairingCode = async () => {
    setAction("pairing");
    setError("");
    try {
      const result = await continuityApi.startPairing("Rumi destination");
      setPairing(result);
    } catch (pairingError) {
      setError(formatError(pairingError));
    } finally {
      setAction("idle");
    }
  };

  const handoffPrompt = [
    "Use this continuity destination for the next handoff.",
    `sandbox_id: ${sandboxId.trim() || "logical-sandbox"}`,
    `destination_node_id: ${selectedNode?.node_id || selectedNodeId || "unselected"}`,
    `provider_route: ${routeLabel(selectedRoute)}`,
  ].join("\n");

  return (
    <div className="space-y-4" data-settings-renderer="continuity" data-continuity-settings>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="min-w-0">
          <div className="flex items-center gap-2 text-sm font-medium text-zinc-200">
            <Server size={15} />
            <span>{field.label || "Continuity Handoff"}</span>
          </div>
          <p className="mt-1 text-xs text-zinc-500">
            {localNode?.display_name || "This device"} · {destinationNodes.length} destinations · {routes.length} provider routes
          </p>
        </div>
        <button
          type="button"
          onClick={() => void refresh()}
          className="inline-flex h-8 items-center gap-1.5 rounded-md border border-zinc-800 bg-zinc-950 px-2.5 text-xs text-zinc-300 hover:border-zinc-700"
        >
          {loading ? <Loader2 size={13} className="animate-spin" /> : <RefreshCw size={13} />}
          Refresh
        </button>
      </div>

      {error && (
        <div className="rounded-md border border-rose-500/30 bg-rose-500/10 px-3 py-2 text-xs text-rose-100">
          {error}
        </div>
      )}

      <div className="grid gap-3 lg:grid-cols-3">
        <label className="space-y-1.5">
          <span className="text-[11px] uppercase tracking-[0.18em] text-zinc-600">Sandbox</span>
          <input
            value={sandboxId}
            onChange={(event) => {
              setSandboxId(event.target.value);
              persistConfig({ sandbox_id: event.target.value });
            }}
            className="h-9 w-full rounded-md border border-zinc-800 bg-zinc-950 px-3 font-mono text-xs text-zinc-200 outline-none focus:border-zinc-600"
            placeholder="logical-sandbox"
          />
        </label>
        <label className="space-y-1.5">
          <span className="text-[11px] uppercase tracking-[0.18em] text-zinc-600">Destination</span>
          <select
            value={selectedNode?.node_id ?? selectedNodeId}
            onChange={(event) => {
              setSelectedNodeId(event.target.value);
              persistConfig({ destination_node_id: event.target.value });
            }}
            className="h-9 w-full rounded-md border border-zinc-800 bg-zinc-950 px-3 text-xs text-zinc-200 outline-none focus:border-zinc-600"
          >
            {destinationNodes.length === 0 && <option value="">No paired destination</option>}
            {destinationNodes.map((node) => (
              <option key={node.node_id} value={node.node_id}>
                {nodeLabel(node)}
              </option>
            ))}
          </select>
        </label>
        <label className="space-y-1.5">
          <span className="text-[11px] uppercase tracking-[0.18em] text-zinc-600">Mode</span>
          <select
            value={mode}
            onChange={(event) => {
              setMode(event.target.value);
              persistConfig({ mode: event.target.value });
            }}
            className="h-9 w-full rounded-md border border-zinc-800 bg-zinc-950 px-3 text-xs text-zinc-200 outline-none focus:border-zinc-600"
          >
            <option value="move">Move primary</option>
            <option value="checkpoint">Checkpoint only</option>
            <option value="shadow">Shadow resume</option>
          </select>
        </label>
      </div>

      <div className="grid gap-3 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        <div className="space-y-2 rounded-md border border-zinc-800 bg-zinc-950/60 p-3">
          <div className="flex items-center justify-between gap-2">
            <span className="inline-flex items-center gap-1.5 text-xs font-medium text-zinc-300">
              <Route size={14} />
              Provider route
            </span>
            <span className={cn("rounded-full border px-2 py-0.5 text-[10px]", statusTone(selectedRoute?.portable))}>
              {selectedRoute?.portable ? "portable" : selectedRoute?.blocked_reason || "not ready"}
            </span>
          </div>
          <select
            value={selectedRoute?.route_id ?? selectedRouteId}
            onChange={(event) => {
              setSelectedRouteId(event.target.value);
              persistConfig({ route_id: event.target.value });
            }}
            className="h-9 w-full rounded-md border border-zinc-800 bg-zinc-950 px-3 text-xs text-zinc-200 outline-none focus:border-zinc-600"
          >
            {routes.length === 0 && <option value="">No configured API route</option>}
            {routes.map((route) => (
              <option key={route.route_id} value={route.route_id}>
                {routeLabel(route)}
              </option>
            ))}
          </select>
          <p className="min-h-5 truncate font-mono text-[11px] text-zinc-500">
            {selectedRoute?.endpoint_class || "endpoint unknown"} · {selectedRoute?.credential_ref || "credential ref missing"}
          </p>
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              disabled={!selectedRoute?.route_id || action !== "idle"}
              onClick={() => void handleProbe()}
              className="inline-flex h-8 items-center gap-1.5 rounded-md border border-zinc-800 bg-zinc-950 px-2.5 text-xs text-zinc-300 hover:border-zinc-700 disabled:cursor-not-allowed disabled:opacity-45"
            >
              {action === "probe" ? <Loader2 size={13} className="animate-spin" /> : <ShieldCheck size={13} />}
              Probe
            </button>
            <button
              type="button"
              onClick={() => copyText(handoffPrompt, setCopyState)}
              className="inline-flex h-8 items-center gap-1.5 rounded-md border border-zinc-800 bg-zinc-950 px-2.5 text-xs text-zinc-300 hover:border-zinc-700"
              title="Copy handoff instruction"
            >
              <Copy size={13} />
              {copyState ? "Copied" : "Copy"}
            </button>
          </div>
        </div>

        <div className="space-y-2 rounded-md border border-zinc-800 bg-zinc-950/60 p-3">
          <div className="flex items-center justify-between gap-2">
            <span className="inline-flex items-center gap-1.5 text-xs font-medium text-zinc-300">
              <KeyRound size={14} />
              Pairing
            </span>
            <span className="rounded-full border border-zinc-800 bg-zinc-950 px-2 py-0.5 text-[10px] text-zinc-500">
              X25519 envelope
            </span>
          </div>
          {pairing ? (
            <div className="space-y-2">
              <div className="flex items-center justify-between gap-3 rounded-md border border-zinc-800 bg-zinc-950 px-3 py-2">
                <span className="font-mono text-sm text-zinc-100">{pairing.code}</span>
                <button
                  type="button"
                  onClick={() => copyText(pairing.code, setCopyState)}
                  className="rounded p-1.5 text-zinc-400 hover:bg-zinc-800 hover:text-zinc-100"
                  title="Copy pairing code"
                >
                  <Copy size={13} />
                </button>
              </div>
              <p className="text-[11px] text-zinc-500">
                Enter this code on the destination device, then refresh.
              </p>
            </div>
          ) : (
            <button
              type="button"
              disabled={action !== "idle"}
              onClick={() => void handlePairingCode()}
              className="inline-flex h-8 items-center gap-1.5 rounded-md border border-zinc-800 bg-zinc-950 px-2.5 text-xs text-zinc-300 hover:border-zinc-700 disabled:cursor-not-allowed disabled:opacity-45"
            >
              {action === "pairing" ? <Loader2 size={13} className="animate-spin" /> : <Link2 size={13} />}
              New pairing code
            </button>
          )}
          <p className="text-[11px] text-zinc-500">
            {selectedNode ? `${nodeLabel(selectedNode)} · ${selectedNode.platform || "platform unknown"} · ${selectedNode.online ? "online" : "offline"}` : "Add a paired destination before handoff."}
          </p>
        </div>
      </div>

      <div className="grid gap-3 lg:grid-cols-[minmax(0,1fr)_220px]">
        <div className="rounded-md border border-zinc-800 bg-zinc-950/60 p-3">
          <div className="flex items-center justify-between gap-2">
            <span className="inline-flex items-center gap-1.5 text-xs font-medium text-zinc-300">
              {probe?.ok || plan?.status === "ready" ? <CheckCircle2 size={14} /> : <ShieldAlert size={14} />}
              Preflight
            </span>
            <span className={cn("rounded-full border px-2 py-0.5 text-[10px]", statusTone(probe?.ok ?? (plan ? plan.status === "ready" : undefined)))}>
              {probe ? (probe.ok ? "pass" : "blocked") : plan ? plan.status : "not run"}
            </span>
          </div>
          <div className="mt-3 grid gap-2 sm:grid-cols-2">
            {(probe?.checks ?? []).slice(0, 3).map((check, index) => (
              <div key={`${String(check.code ?? "check")}-${index}`} className="rounded border border-zinc-800 bg-zinc-950 px-2.5 py-2 text-[11px] text-zinc-400">
                <span className="font-mono text-zinc-200">{String(check.code ?? "CHECK")}</span>
              </div>
            ))}
            {(probe?.errors ?? []).slice(0, 3).map((item, index) => (
              <div key={`${String(item.code ?? "error")}-${index}`} className="rounded border border-amber-500/30 bg-amber-500/10 px-2.5 py-2 text-[11px] text-amber-100">
                <span className="font-mono">{String(item.code ?? "ERROR")}</span>
              </div>
            ))}
            {!probe && !plan && (
              <div className="rounded border border-zinc-800 bg-zinc-950 px-2.5 py-2 text-[11px] text-zinc-500">
                Destination, route, credential envelope, and primary lease will be checked before cutover.
              </div>
            )}
          </div>
        </div>

        <div className="space-y-2">
          <button
            type="button"
            disabled={!canRun || action !== "idle"}
            onClick={() => void handlePlan()}
            className="inline-flex h-9 w-full items-center justify-center gap-1.5 rounded-md border border-zinc-800 bg-zinc-950 px-3 text-xs text-zinc-200 hover:border-zinc-700 disabled:cursor-not-allowed disabled:opacity-45"
          >
            {action === "plan" ? <Loader2 size={13} className="animate-spin" /> : <ShieldCheck size={13} />}
            Plan
          </button>
          <button
            type="button"
            disabled={!canRun || action !== "idle"}
            onClick={() => void handleHandoff()}
            className="inline-flex h-9 w-full items-center justify-center gap-1.5 rounded-md border border-emerald-500/40 bg-emerald-500/10 px-3 text-xs font-medium text-emerald-100 hover:border-emerald-400/70 disabled:cursor-not-allowed disabled:opacity-45"
          >
            {action === "handoff" ? <Loader2 size={13} className="animate-spin" /> : <Play size={13} />}
            Start handoff
          </button>
        </div>
      </div>

      {operation && (
        <div className="flex flex-wrap items-center justify-between gap-2 rounded-md border border-zinc-800 bg-zinc-950/60 px-3 py-2 text-xs">
          <span className="min-w-0 truncate text-zinc-400">
            Last operation <span className="font-mono text-zinc-200">{operation.operation_id}</span>
          </span>
          <span className={cn(
            "rounded-full border px-2 py-0.5",
            operation.status === "COMPLETED"
              ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-200"
              : "border-zinc-800 bg-zinc-950 text-zinc-400",
          )}>
            {operation.status}
          </span>
        </div>
      )}
    </div>
  );
}
