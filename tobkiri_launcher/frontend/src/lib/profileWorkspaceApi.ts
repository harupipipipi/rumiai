import { load } from 'js-yaml';
import { apiFetch, fetchStartupProfiles } from './api';
import type {
  ApiProfileWorkspaceDetail,
  ApiStartupProfile,
  StartupProfilesResponseData,
} from './apiTypes';

export interface FlowPreviewDiagnostic {
  code: string;
  message: string;
  severity: 'info' | 'warning' | 'error';
}

export interface FlowCompilePreview {
  ok: boolean;
  stepCount: number;
  diagnostics: FlowPreviewDiagnostic[];
}

export async function fetchProfileWorkspace(profileId: string): Promise<ApiProfileWorkspaceDetail> {
  return apiFetch<ApiProfileWorkspaceDetail>(
    `/api/panel/startup/profiles/${encodeURIComponent(profileId)}/workspace`,
  );
}

export async function fetchActiveProfileWorkspace(): Promise<{
  startupProfiles: StartupProfilesResponseData;
  activeProfile: ApiStartupProfile | null;
  workspace: ApiProfileWorkspaceDetail | null;
}> {
  const startupProfiles = await fetchStartupProfiles();
  const activeProfile =
    startupProfiles.profiles.find((profile) => profile.profile_id === startupProfiles.active_profile_id) ??
    startupProfiles.profiles[0] ??
    null;
  const workspace = activeProfile ? await fetchProfileWorkspace(activeProfile.profile_id) : null;
  return { startupProfiles, activeProfile, workspace };
}

export function compileFlowPreview(yamlContent: string): FlowCompilePreview {
  const diagnostics: FlowPreviewDiagnostic[] = [];
  let parsed: unknown;
  try {
    parsed = load(yamlContent);
  } catch (error) {
    return {
      ok: false,
      stepCount: 0,
      diagnostics: [
        {
          code: 'yaml.parse',
          message: error instanceof Error ? error.message : 'YAML parse failed',
          severity: 'error',
        },
      ],
    };
  }

  const document = parsed && typeof parsed === 'object' ? parsed as Record<string, unknown> : {};
  const steps = Array.isArray(document.steps) ? document.steps : [];
  if (!document.flow_id) {
    diagnostics.push({ code: 'flow.flow_id', message: 'flow_id is missing.', severity: 'error' });
  }
  if (!steps.length) {
    diagnostics.push({ code: 'flow.steps', message: 'No flow steps found.', severity: 'error' });
  }
  const stepIds = new Set<string>();
  steps.forEach((step, index) => {
    const item = step && typeof step === 'object' ? step as Record<string, unknown> : {};
    const id = String(item.id ?? '');
    if (!id) {
      diagnostics.push({ code: 'step.id', message: `Step ${index + 1} is missing an id.`, severity: 'error' });
      return;
    }
    if (stepIds.has(id)) {
      diagnostics.push({ code: 'step.duplicate', message: `Step ${id} is duplicated.`, severity: 'error' });
    }
    stepIds.add(id);
    if (!item.type || !item.function) {
      diagnostics.push({ code: 'step.contract', message: `Step ${id} is missing type or function.`, severity: 'warning' });
    }
  });
  return {
    ok: diagnostics.every((diagnostic) => diagnostic.severity !== 'error'),
    stepCount: steps.length,
    diagnostics,
  };
}
