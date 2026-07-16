import {
  Component,
  createElement,
  type ComponentType,
  type ErrorInfo,
  type ReactElement,
  type ReactNode,
} from "react";

export const FRONTEND_COMPONENT_API_VERSION = "rumi.frontend.component.v1";
export const UNSUPPORTED_COMPONENT_ID = "rumi.ui.unsupported";

export type JsonSchema = {
  type?: "object" | "array" | "string" | "number" | "integer" | "boolean" | "null";
  properties?: Record<string, JsonSchema>;
  required?: string[];
  additionalProperties?: boolean;
  items?: JsonSchema;
  enum?: unknown[];
  minLength?: number;
  maxLength?: number;
  minimum?: number;
  maximum?: number;
  maxItems?: number;
};

export type FrontendComponentDiagnostic = {
  severity: "warning" | "error";
  code: string;
  message: string;
  componentId: string;
  apiVersion?: string;
  sourcePackId?: string;
  templateSourcePackId?: string;
  templateId?: string;
  slot?: string;
  path?: string;
  trust?: string;
  templateTrust?: string;
};

export type FrontendComponentRenderProps = {
  props: Record<string, unknown>;
  data: Record<string, unknown>;
  actions: Record<string, FrontendComponentActionBinding>;
  context: {
    componentId: string;
    slot: string;
    sourcePackId: string;
    templateId?: string;
    trust: string;
  };
};

export type FrontendComponentActionBinding = {
  actionId: string;
  payload?: Record<string, unknown>;
};

export type FrontendComponentDefinition = {
  componentId: string;
  apiVersion: string;
  supportedSlots: string[];
  propsSchema?: JsonSchema;
  dataContract?: JsonSchema;
  actionContract?: JsonSchema;
  allowedDataSourceIds?: string[];
  allowedActionIds?: string[];
  requiredPermissions?: string[];
  fallbackComponentId?: string;
  render: ComponentType<FrontendComponentRenderProps>;
};

export type RegisteredFrontendComponent = FrontendComponentDefinition & {
  sourceKind: "builtin" | "approved_pack";
  sourcePackId: string;
  trust: "builtin" | "local";
};

export type ApprovedPackRegistration = {
  sourcePackId: string;
  approved: boolean;
  bundleVerified: boolean;
  declaredSlots: string[];
  grantedPermissions: string[];
};

export type FrontendComponentRequest = {
  componentId: string;
  apiVersion?: string;
  slot: string;
  props?: Record<string, unknown>;
  data?: Record<string, unknown>;
  actions?: Record<string, FrontendComponentActionBinding>;
  dataSourceIds?: string[];
  fallbackComponentId?: string;
  templateId?: string;
  templateSourcePackId?: string;
  templateTrust?: string;
};

export type FrontendComponentResolution = {
  ok: boolean;
  entry: RegisteredFrontendComponent;
  requestedComponentId: string;
  props: Record<string, unknown>;
  data: Record<string, unknown>;
  actions: Record<string, FrontendComponentActionBinding>;
  diagnostics: FrontendComponentDiagnostic[];
};

export type FrontendComponentRegistry = {
  registerBuiltin: (definition: FrontendComponentDefinition) => FrontendComponentDiagnostic[];
  registerApprovedPack: (
    definition: FrontendComponentDefinition,
    approval: ApprovedPackRegistration,
  ) => FrontendComponentDiagnostic[];
  unregisterSourcePack: (sourcePackId: string) => number;
  resolve: (request: FrontendComponentRequest) => FrontendComponentResolution;
  get: (componentId: string) => RegisteredFrontendComponent | null;
  entries: () => RegisteredFrontendComponent[];
};

const COMPONENT_ID_PATTERN = /^[a-z0-9][a-z0-9._-]{2,127}$/;

export function createFrontendComponentRegistry(
  builtins: FrontendComponentDefinition[] = [],
): FrontendComponentRegistry {
  const entries = new Map<string, RegisteredFrontendComponent>();

  const register = (
    definition: FrontendComponentDefinition,
    source: Pick<RegisteredFrontendComponent, "sourceKind" | "sourcePackId" | "trust">,
    approval?: ApprovedPackRegistration,
  ): FrontendComponentDiagnostic[] => {
    const diagnostics = validateDefinition(definition, source, approval);
    const existing = entries.get(definition.componentId);
    if (existing) {
      diagnostics.push(
        diagnostic(
          "frontend.component.registration_collision",
          `Component ID is already registered by ${existing.sourcePackId}`,
          definition.componentId,
          { ...source, apiVersion: definition.apiVersion },
        ),
      );
    }
    if (diagnostics.some((item) => item.severity === "error")) return diagnostics;
    entries.set(definition.componentId, { ...definition, ...source });
    return diagnostics;
  };

  const registry: FrontendComponentRegistry = {
    registerBuiltin(definition) {
      return register(definition, {
        sourceKind: "builtin",
        sourcePackId: "defaultspack",
        trust: "builtin",
      });
    },
    registerApprovedPack(definition, approval) {
      return register(
        definition,
        {
          sourceKind: "approved_pack",
          sourcePackId: approval.sourcePackId,
          trust: "local",
        },
        approval,
      );
    },
    unregisterSourcePack(sourcePackId) {
      let removed = 0;
      for (const [componentId, entry] of entries) {
        if (entry.sourceKind !== "approved_pack" || entry.sourcePackId !== sourcePackId) continue;
        entries.delete(componentId);
        removed += 1;
      }
      return removed;
    },
    resolve(request) {
      const requested = entries.get(request.componentId);
      if (!requested) {
        return fallbackResolution(entries, request, [
          diagnostic(
            "frontend.component.unknown_id",
            "Component ID is not registered",
            request.componentId,
            {
              sourcePackId: "unknown",
              trust: request.templateTrust ?? "local",
              apiVersion: request.apiVersion,
            },
            request,
          ),
        ]);
      }

      const diagnostics = validateRequest(requested, request);
      if (diagnostics.length > 0) return fallbackResolution(entries, request, diagnostics, requested);
      return {
        ok: true,
        entry: requested,
        requestedComponentId: request.componentId,
        props: { ...(request.props ?? {}) },
        data: { ...(request.data ?? {}) },
        actions: { ...(request.actions ?? {}) },
        diagnostics: [],
      };
    },
    get(componentId) {
      return entries.get(componentId) ?? null;
    },
    entries() {
      return [...entries.values()];
    },
  };

  for (const definition of builtins) registry.registerBuiltin(definition);
  return registry;
}

function validateDefinition(
  definition: FrontendComponentDefinition,
  source: Pick<RegisteredFrontendComponent, "sourceKind" | "sourcePackId" | "trust">,
  approval?: ApprovedPackRegistration,
): FrontendComponentDiagnostic[] {
  const result: FrontendComponentDiagnostic[] = [];
  const diagnosticSource = { ...source, apiVersion: definition.apiVersion };
  if (!COMPONENT_ID_PATTERN.test(definition.componentId) || definition.componentId.includes("..")) {
    result.push(
      diagnostic(
        "frontend.component.invalid_id",
        "Component ID must be an opaque dotted identifier, never a path or module specifier",
        definition.componentId,
        diagnosticSource,
      ),
    );
  }
  if (definition.apiVersion !== FRONTEND_COMPONENT_API_VERSION) {
    result.push(
      diagnostic(
        "frontend.component.unsupported_api_version",
        `Unsupported component API version: ${definition.apiVersion}`,
        definition.componentId,
        diagnosticSource,
      ),
    );
  }
  if (definition.supportedSlots.length === 0 || definition.supportedSlots.some((slot) => !slot.trim())) {
    result.push(
      diagnostic(
        "frontend.component.invalid_slots",
        "At least one non-empty supported slot is required",
        definition.componentId,
        diagnosticSource,
      ),
    );
  }
  if (definition.fallbackComponentId === definition.componentId) {
    result.push(
      diagnostic(
        "frontend.component.self_fallback",
        "A component cannot use itself as its failure fallback",
        definition.componentId,
        diagnosticSource,
      ),
    );
  }
  if (source.sourceKind === "approved_pack") {
    if (!approval?.approved || !approval.bundleVerified) {
      result.push(
        diagnostic(
          "frontend.component.pack_bundle_not_approved",
          "Pack component registration requires an approved and verified frontend bundle",
          definition.componentId,
          diagnosticSource,
        ),
      );
    }
    const undeclaredSlots = definition.supportedSlots.filter(
      (slot) => !approval?.declaredSlots.includes(slot),
    );
    if (undeclaredSlots.length > 0) {
      result.push(
        diagnostic(
          "frontend.component.undeclared_slot",
          `Pack component requested undeclared slots: ${undeclaredSlots.join(", ")}`,
          definition.componentId,
          diagnosticSource,
        ),
      );
    }
    const missingPermissions = (definition.requiredPermissions ?? []).filter(
      (permission) => !approval?.grantedPermissions.includes(permission),
    );
    if (missingPermissions.length > 0) {
      result.push(
        diagnostic(
          "frontend.component.permission_not_granted",
          `Pack component is missing permissions: ${missingPermissions.join(", ")}`,
          definition.componentId,
          diagnosticSource,
        ),
      );
    }
  }
  return result;
}

function validateRequest(
  entry: RegisteredFrontendComponent,
  request: FrontendComponentRequest,
): FrontendComponentDiagnostic[] {
  const diagnostics: FrontendComponentDiagnostic[] = [];
  if ((request.apiVersion ?? FRONTEND_COMPONENT_API_VERSION) !== entry.apiVersion) {
    diagnostics.push(
      diagnostic(
        "frontend.component.api_version_mismatch",
        `Requested ${request.apiVersion}; registered ${entry.apiVersion}`,
        entry.componentId,
        entry,
        request,
      ),
    );
  }
  if (!entry.supportedSlots.includes(request.slot)) {
    diagnostics.push(
      diagnostic(
        "frontend.component.incompatible_slot",
        `Component does not support slot: ${request.slot}`,
        entry.componentId,
        entry,
        request,
      ),
    );
  }
  diagnostics.push(
    ...schemaDiagnostics(entry.propsSchema, request.props ?? {}, "props", entry, request),
    ...schemaDiagnostics(entry.dataContract, request.data ?? {}, "data", entry, request),
    ...schemaDiagnostics(entry.actionContract, request.actions ?? {}, "actions", entry, request),
  );
  const unexpectedSources = (request.dataSourceIds ?? []).filter(
    (sourceId) => !(entry.allowedDataSourceIds ?? []).includes(sourceId),
  );
  if (unexpectedSources.length > 0) {
    diagnostics.push(
      diagnostic(
        "frontend.component.data_source_not_registered",
        `Unregistered data sources: ${unexpectedSources.join(", ")}`,
        entry.componentId,
        entry,
        request,
      ),
    );
  }
  const unexpectedActions = Object.values(request.actions ?? {})
    .map((binding) => binding.actionId)
    .filter((actionId) => !(entry.allowedActionIds ?? []).includes(actionId));
  if (unexpectedActions.length > 0) {
    diagnostics.push(
      diagnostic(
        "frontend.component.action_not_registered",
        `Unregistered actions: ${unexpectedActions.join(", ")}`,
        entry.componentId,
        entry,
        request,
      ),
    );
  }
  return diagnostics;
}

function schemaDiagnostics(
  schema: JsonSchema | undefined,
  value: unknown,
  path: string,
  entry: RegisteredFrontendComponent,
  request: FrontendComponentRequest,
): FrontendComponentDiagnostic[] {
  if (!schema) return [];
  return validateJsonSchema(schema, value, path).map((message) =>
    diagnostic(
      `frontend.component.invalid_${path}`,
      message,
      entry.componentId,
      entry,
      request,
      path,
    ),
  );
}

function validateJsonSchema(schema: JsonSchema, value: unknown, path: string): string[] {
  const errors: string[] = [];
  if (schema.enum && !schema.enum.some((candidate) => Object.is(candidate, value))) {
    errors.push(`${path} is not an allowed value`);
    return errors;
  }
  if (schema.type && !matchesType(schema.type, value)) {
    errors.push(`${path} must be ${schema.type}`);
    return errors;
  }
  if (schema.type === "object" && isRecord(value)) {
    for (const required of schema.required ?? []) {
      if (!(required in value)) errors.push(`${path}.${required} is required`);
    }
    for (const [key, child] of Object.entries(value)) {
      const propertySchema = schema.properties?.[key];
      if (!propertySchema) {
        if (schema.additionalProperties === false) errors.push(`${path}.${key} is not allowed`);
        continue;
      }
      errors.push(...validateJsonSchema(propertySchema, child, `${path}.${key}`));
    }
  }
  if (schema.type === "array" && Array.isArray(value)) {
    if (schema.maxItems !== undefined && value.length > schema.maxItems) {
      errors.push(`${path} exceeds maxItems ${schema.maxItems}`);
    }
    if (schema.items) {
      value.forEach((item, index) => {
        errors.push(...validateJsonSchema(schema.items!, item, `${path}[${index}]`));
      });
    }
  }
  if (schema.type === "string" && typeof value === "string") {
    if (schema.minLength !== undefined && value.length < schema.minLength) {
      errors.push(`${path} is shorter than ${schema.minLength}`);
    }
    if (schema.maxLength !== undefined && value.length > schema.maxLength) {
      errors.push(`${path} is longer than ${schema.maxLength}`);
    }
  }
  if ((schema.type === "number" || schema.type === "integer") && typeof value === "number") {
    if (schema.minimum !== undefined && value < schema.minimum) {
      errors.push(`${path} is less than ${schema.minimum}`);
    }
    if (schema.maximum !== undefined && value > schema.maximum) {
      errors.push(`${path} is greater than ${schema.maximum}`);
    }
  }
  return errors;
}

function matchesType(type: NonNullable<JsonSchema["type"]>, value: unknown): boolean {
  if (type === "null") return value === null;
  if (type === "array") return Array.isArray(value);
  if (type === "object") return isRecord(value);
  if (type === "integer") return typeof value === "number" && Number.isInteger(value);
  return typeof value === type;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function fallbackResolution(
  entries: Map<string, RegisteredFrontendComponent>,
  request: FrontendComponentRequest,
  diagnostics: FrontendComponentDiagnostic[],
  requested?: RegisteredFrontendComponent,
): FrontendComponentResolution {
  const fallbackId =
    request.fallbackComponentId ?? requested?.fallbackComponentId ?? UNSUPPORTED_COMPONENT_ID;
  const fallback =
    (fallbackId !== request.componentId ? entries.get(fallbackId) : undefined) ??
    entries.get(UNSUPPORTED_COMPONENT_ID) ??
    internalFallbackEntry();
  return {
    ok: false,
    entry: fallback,
    requestedComponentId: request.componentId,
    props: {
      title: "Unsupported component",
      message: diagnostics.map((item) => item.message).join("; "),
      requestedComponentId: request.componentId,
    },
    data: {},
    actions: {},
    diagnostics,
  };
}

function InternalFallback({ props }: FrontendComponentRenderProps) {
  return (
    <div role="alert" data-frontend-component={UNSUPPORTED_COMPONENT_ID}>
      <strong>{String(props.title ?? "Unsupported component")}</strong>
      <p>{String(props.message ?? "")}</p>
    </div>
  );
}

function internalFallbackEntry(): RegisteredFrontendComponent {
  return {
    componentId: UNSUPPORTED_COMPONENT_ID,
    apiVersion: FRONTEND_COMPONENT_API_VERSION,
    supportedSlots: ["*"],
    propsSchema: { type: "object" },
    render: InternalFallback,
    sourceKind: "builtin",
    sourcePackId: "defaultspack",
    trust: "builtin",
  };
}

function diagnostic(
  code: string,
  message: string,
  componentId: string,
  source: { sourcePackId?: string; trust?: string; apiVersion?: string },
  request?: Pick<
    FrontendComponentRequest,
    "templateId" | "templateSourcePackId" | "templateTrust" | "slot"
  >,
  path?: string,
): FrontendComponentDiagnostic {
  return {
    severity: "error",
    code,
    message,
    componentId,
    apiVersion: source.apiVersion,
    sourcePackId: source.sourcePackId,
    trust: source.trust,
    templateId: request?.templateId,
    templateSourcePackId: request?.templateSourcePackId,
    templateTrust: request?.templateTrust,
    slot: request?.slot,
    path,
  };
}

type BoundaryProps = {
  children: ReactNode;
  fallback: ReactElement;
  onError?: (error: Error, info: ErrorInfo) => void;
};

type BoundaryState = { failed: boolean };

export class FrontendComponentErrorBoundary extends Component<BoundaryProps, BoundaryState> {
  state: BoundaryState = { failed: false };

  static getDerivedStateFromError(): BoundaryState {
    return { failed: true };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    this.props.onError?.(error, info);
  }

  render(): ReactNode {
    return this.state.failed ? this.props.fallback : this.props.children;
  }
}

export function FrontendComponentHost({
  registry,
  request,
  onDiagnostic,
}: {
  registry: FrontendComponentRegistry;
  request: FrontendComponentRequest;
  onDiagnostic?: (diagnostic: FrontendComponentDiagnostic) => void;
}): ReactElement {
  const resolution = registry.resolve(request);
  resolution.diagnostics.forEach((item) => onDiagnostic?.(item));
  const context = {
    componentId: resolution.entry.componentId,
    slot: request.slot,
    sourcePackId: resolution.entry.sourcePackId,
    templateId: request.templateId,
    trust: resolution.entry.trust,
  };
  const rendered = createElement(resolution.entry.render, {
    props: resolution.props,
    data: resolution.data,
    actions: resolution.actions,
    context,
  });
  const fallback = registry.resolve({
    componentId: UNSUPPORTED_COMPONENT_ID,
    slot: request.slot,
    props: {
      title: "Component failed",
      message: `The ${request.componentId} extension failed safely.`,
      requestedComponentId: request.componentId,
    },
  });
  return (
    <FrontendComponentErrorBoundary
      fallback={createElement(fallback.entry.render, {
        props: fallback.props,
        data: {},
        actions: {},
        context: { ...context, componentId: fallback.entry.componentId },
      })}
      onError={(error) =>
        onDiagnostic?.({
          severity: "error",
          code: "frontend.component.render_failed",
          message: error.message || "Component render failed",
          componentId: request.componentId,
          apiVersion: resolution.entry.apiVersion,
          sourcePackId: resolution.entry.sourcePackId,
          templateId: request.templateId,
          templateSourcePackId: request.templateSourcePackId,
          templateTrust: request.templateTrust,
          slot: request.slot,
          trust: resolution.entry.trust,
        })
      }
    >
      {rendered}
    </FrontendComponentErrorBoundary>
  );
}
