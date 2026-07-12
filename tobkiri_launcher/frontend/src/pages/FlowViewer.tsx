import { useMemo, useState } from 'react';
import { load } from 'js-yaml';
import { AlertTriangle, CheckCircle2, GitBranch, ShieldAlert } from 'lucide-react';
import { Badge } from '@/src/components/ui/Badge';
import { Button } from '@/src/components/ui/Button';
import { compileFlowPreview } from '@/src/lib/profileWorkspaceApi';

interface FlowViewerProps {
  yamlContent: string;
  sourcePath?: string | null;
}

interface FlowStep {
  id: string;
  type?: string;
  function?: string;
  when?: string;
}

function parseSteps(yamlContent: string): FlowStep[] {
  try {
    const document = load(yamlContent);
    const rawSteps = document && typeof document === 'object'
      ? (document as { steps?: unknown }).steps
      : [];
    if (!Array.isArray(rawSteps)) return [];
    return rawSteps.map((step, index) => {
      const item = step && typeof step === 'object' ? step as Record<string, unknown> : {};
      return {
        id: String(item.id ?? `step-${index + 1}`),
        type: typeof item.type === 'string' ? item.type : undefined,
        function: typeof item.function === 'string' ? item.function : undefined,
        when: typeof item.when === 'string' ? item.when : undefined,
      };
    });
  } catch {
    return [];
  }
}

function riskTone(step: FlowStep): 'secondary' | 'warning' | 'destructive' | 'success' {
  const text = `${step.id} ${step.function ?? ''}`.toLowerCase();
  if (text.includes('permissions')) return 'success';
  if (text.includes('approval') || text.includes('tool') || text.includes('complete')) return 'warning';
  if (text.includes('delete') || text.includes('write')) return 'destructive';
  return 'secondary';
}

export function FlowViewer({ yamlContent, sourcePath }: FlowViewerProps) {
  const [draft, setDraft] = useState(yamlContent);
  const [preview, setPreview] = useState(() => compileFlowPreview(yamlContent));
  const steps = useMemo(() => parseSteps(draft), [draft]);

  return (
    <div className="grid min-h-0 grid-cols-1 gap-4 xl:grid-cols-[minmax(0,1fr)_360px]">
      <section className="min-h-[520px] border border-border bg-bg-main">
        <div className="flex items-center justify-between border-b border-border px-4 py-3">
          <div className="min-w-0">
            <h2 className="text-sm font-semibold text-text-main">Flow YAML</h2>
            <p className="truncate text-xs text-text-muted">{sourcePath || 'No profile flow selected'}</p>
          </div>
          <div className="flex items-center gap-2">
            <Button variant="secondary" size="sm" onClick={() => setPreview(compileFlowPreview(draft))}>
              Validate
            </Button>
            <Button variant="outline" size="sm" disabled title="Saving flow YAML requires an approval path">
              Save disabled
            </Button>
          </div>
        </div>
        <textarea
          className="h-[460px] w-full resize-none bg-bg-main p-4 font-mono text-xs leading-5 text-text-main outline-none"
          value={draft}
          spellCheck={false}
          onChange={(event) => setDraft(event.target.value)}
        />
      </section>

      <aside className="space-y-4">
        <section className="border border-border bg-bg-main p-4">
          <div className="flex items-center gap-2">
            {preview.ok ? (
              <CheckCircle2 className="h-4 w-4 text-emerald-600" />
            ) : (
              <AlertTriangle className="h-4 w-4 text-amber-600" />
            )}
            <h2 className="text-sm font-semibold text-text-main">Compile Preview</h2>
          </div>
          <div className="mt-3 text-sm text-text-muted">{preview.stepCount} steps</div>
          <div className="mt-3 space-y-2">
            {preview.diagnostics.length ? preview.diagnostics.map((diagnostic) => (
              <div key={`${diagnostic.code}-${diagnostic.message}`} className="border border-border p-2 text-xs">
                <div className="font-medium text-text-main">{diagnostic.code}</div>
                <div className="mt-1 text-text-muted">{diagnostic.message}</div>
              </div>
            )) : (
              <div className="text-xs text-text-muted">No diagnostics.</div>
            )}
          </div>
        </section>

        <section className="border border-border bg-bg-main p-4">
          <div className="flex items-center gap-2">
            <GitBranch className="h-4 w-4 text-accent" />
            <h2 className="text-sm font-semibold text-text-main">Steps</h2>
          </div>
          <div className="mt-3 space-y-2">
            {steps.map((step, index) => (
              <div key={`${step.id}-${index}`} className="border border-border p-3">
                <div className="flex items-center justify-between gap-3">
                  <div className="min-w-0 truncate text-sm font-medium text-text-main">{step.id}</div>
                  <Badge variant={riskTone(step)}>
                    {riskTone(step) === 'success' ? 'permission' : riskTone(step) === 'warning' ? 'risk' : 'step'}
                  </Badge>
                </div>
                <div className="mt-1 truncate text-xs text-text-muted">{step.function}</div>
                {step.when && <div className="mt-2 text-xs text-text-muted">when {step.when}</div>}
              </div>
            ))}
          </div>
        </section>

        <section className="border border-border bg-bg-main p-4">
          <div className="flex items-center gap-2 text-sm font-semibold text-text-main">
            <ShieldAlert className="h-4 w-4 text-amber-600" />
            Permission/Risk
          </div>
          <p className="mt-2 text-xs text-text-muted">
            Profile permissions are defaults only; approval and capability enforcement remain final.
          </p>
        </section>
      </aside>
    </div>
  );
}
