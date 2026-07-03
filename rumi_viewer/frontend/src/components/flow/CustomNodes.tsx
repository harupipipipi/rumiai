import type { CSSProperties, ReactNode } from 'react';
import { Handle, Position, type NodeProps } from '@xyflow/react';
import { Play, Settings2, Square, CheckCircle2, XCircle, Loader2, Waypoints } from 'lucide-react';
import { cn } from '@/src/lib/utils';
import { useT } from '@/src/lib/i18n';
import type {
  EndNode as EndNodeType,
  ExecutionStatus,
  FlowPort,
  StepNode as StepNodeType,
  TriggerNode as TriggerNodeType,
} from '@/src/lib/types';

function statusAccent(status: ExecutionStatus): string {
  if (status === 'running') return 'is-running';
  if (status === 'success') return 'is-success';
  if (status === 'error') return 'is-error';
  return 'is-idle';
}

function localizePortLabel(port: FlowPort, t: ReturnType<typeof useT>): string {
  const keyById: Record<string, string> = {
    'start-out': 'flows.port.boot',
    'boot-in': 'flows.port.boot',
    'profile-in': 'flows.port.boot',
    'end-in': 'flows.port.done',
    'mounts-in': 'flows.port.mounts',
    'mounts-out': 'flows.port.mounts',
    'registry-in': 'flows.port.registry',
    'registry-out': 'flows.port.registry',
    'profile-out': 'flows.port.profile',
    'event-in': 'flows.port.event',
    'event-out': 'flows.port.signal',
    'exec-in': 'flows.port.command',
    'exec-out': 'flows.port.result',
    'http-in': 'flows.port.request',
    'http-out': 'flows.port.response',
    'http-post-in': 'flows.port.request',
    'http-post-out': 'flows.port.response',
    'log-in': 'flows.port.text',
    'log-out': 'flows.port.signal',
    'input-main': 'flows.port.input',
    'output-main': 'flows.port.output',
  };

  const translationKey = keyById[port.id];
  return translationKey ? t(translationKey) : port.label;
}

function localizeNodeTitle(value: string | undefined, fallbackKey: string, t: ReturnType<typeof useT>): string {
  if (!value) {
    return t(fallbackKey);
  }

  if (fallbackKey === 'flows.node.start_title' && value === 'rumi_start') {
    return t(fallbackKey);
  }
  if (fallbackKey === 'flows.node.finish_title' && value === 'finish') {
    return t(fallbackKey);
  }
  return value;
}

function localizeNodeKind(value: string | undefined, t: ReturnType<typeof useT>): string {
  if (!value || value === 'action') {
    return t('flows.node.action');
  }
  return value;
}

function contractSummary(contracts: string[]): string {
  if (contracts.length === 0) {
    return '';
  }
  const [first, ...rest] = contracts;
  return rest.length > 0 ? `${first} +${rest.length}` : first;
}

function portDisclosureLabel(port: FlowPort, label: string): string {
  const details = [label];
  if (port.id && port.id !== label) {
    details.push(`id: ${port.id}`);
  }
  if (port.contracts.length > 0) {
    details.push(`contracts: ${port.contracts.join(', ')}`);
  }
  if (port.description) {
    details.push(port.description);
  }
  return details.join('\n');
}

function nodeDisclosureLabel(parts: Array<string | undefined>): string {
  return parts.filter((part): part is string => Boolean(part?.trim())).join('\n');
}

type FlowNodeStyle = CSSProperties & {
  '--flow-node-min-height'?: string;
};

function PortHandle({ port, side }: { port: FlowPort; side: 'left' | 'right' }) {
  const t = useT();
  const position = side === 'left' ? Position.Left : Position.Right;
  const type = side === 'left' ? 'target' : 'source';
  const label = localizePortLabel(port, t);
  const contracts = contractSummary(port.contracts);
  const disclosureLabel = portDisclosureLabel(port, label);

  return (
    <div className={cn('flow-port-item', side === 'left' ? 'flow-port-item-left' : 'flow-port-item-right')}>
      {side === 'left' && (
        <Handle
          id={port.id}
          type={type}
          position={position}
          className="flow-port-handle !border-2 !shadow-none"
        />
      )}
      <div
        className="flow-port-tag"
        title={disclosureLabel}
        aria-label={disclosureLabel}
        data-flow-port-label={label}
      >
        <span className="flow-port-label">{label}</span>
        {contracts ? (
          <span
            className="flow-port-contract"
            title={port.contracts.join(', ')}
            aria-label={`contracts: ${port.contracts.join(', ')}`}
          >
            {contracts}
          </span>
        ) : null}
      </div>
      {side === 'right' && (
        <Handle
          id={port.id}
          type={type}
          position={position}
          className="flow-port-handle !border-2 !shadow-none"
        />
      )}
    </div>
  );
}

function PortStack({ ports, side }: { ports: FlowPort[]; side: 'left' | 'right' }) {
  if (ports.length === 0) return null;

  return (
    <div className={cn('flow-port-stack', side === 'left' ? 'flow-port-stack-left' : 'flow-port-stack-right')}>
      {ports.map((port) => (
        <PortHandle key={port.id} port={port} side={side} />
      ))}
    </div>
  );
}

function NodeShell({
  title,
  subtitle,
  tokenTitle,
  tokenSubtitle,
  status,
  selected,
  icon,
  ports,
}: {
  title: string;
  subtitle?: string;
  tokenTitle: string;
  tokenSubtitle?: string;
  status: ExecutionStatus;
  selected: boolean;
  icon: ReactNode;
  ports: FlowPort[];
}) {
  const inputPorts = ports.filter((port) => port.direction === 'input');
  const outputPorts = ports.filter((port) => port.direction === 'output');
  const portRows = Math.max(inputPorts.length, outputPorts.length);
  const style: FlowNodeStyle = {
    '--flow-node-min-height': `${Math.max(156, 112 + portRows * 42)}px`,
  };
  const disclosureLabel = nodeDisclosureLabel([title, subtitle, tokenTitle, tokenSubtitle]);

  return (
    <div
      className={cn(
        'flow-node-shell transition-transform duration-150',
        selected && 'is-selected scale-[1.01]',
        statusAccent(status),
      )}
      style={style}
      role="group"
      aria-label={disclosureLabel}
      title={disclosureLabel}
      data-flow-node-label={title}
    >
      <div className="flow-node-cap" title={title} aria-label={title}>
        <div className="flow-node-cap-content">
          {icon}
          <span className="flow-node-cap-label">{title}</span>
        </div>
      </div>

      <div className="flow-node-card">
        <PortStack ports={inputPorts} side="left" />
        <PortStack ports={outputPorts} side="right" />

        <div className="flow-node-body">
          <div className="flow-node-core">
            {subtitle ? <div className="flow-node-subtitle" title={subtitle} aria-label={subtitle}>{subtitle}</div> : null}
            <div className="flow-node-token" title={nodeDisclosureLabel([tokenTitle, tokenSubtitle])} aria-label={nodeDisclosureLabel([tokenTitle, tokenSubtitle])}>
              <div className="flow-node-token-title" title={tokenTitle} aria-label={tokenTitle}>{tokenTitle}</div>
              {tokenSubtitle ? <div className="flow-node-token-subtext" title={tokenSubtitle} aria-label={tokenSubtitle}>{tokenSubtitle}</div> : null}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

export function TriggerNode({ data, selected }: NodeProps<TriggerNodeType>) {
  const t = useT();
  const status = data.executionStatus;
  const icon = status === 'running'
    ? <Loader2 className="h-4 w-4 animate-spin" />
    : status === 'success'
      ? <CheckCircle2 className="h-4 w-4" />
      : <Play className="h-4 w-4" />;
  const startPort = (data.ports || []).find((port) => port.direction === 'output');

  return (
    <NodeShell
      title={localizeNodeTitle(data.title, 'flows.node.start_title', t)}
      subtitle={`${t('flows.node.basepack')}: ${(data.basePack || 'basepack').toUpperCase()}`}
      tokenTitle={startPort ? localizePortLabel(startPort, t) : t('flows.port.boot')}
      tokenSubtitle={startPort?.contracts[0] || String(data.type || 'flow.start')}
      status={status}
      selected={selected}
      icon={icon}
      ports={data.ports || []}
    />
  );
}

export function StepNode({ data, selected }: NodeProps<StepNodeType>) {
  const t = useT();
  if (data.type === 'reroute') {
    return (
      <div className={cn(
        'flow-reroute-node rounded-full border p-2',
        selected && 'ring-2',
      )}>
        <Handle id="reroute-in" type="target" position={Position.Left} className="flow-port-handle !border-2 !shadow-none" />
        <Waypoints className="h-4 w-4" />
        <Handle id="reroute-out" type="source" position={Position.Right} className="flow-port-handle !border-2 !shadow-none" />
      </div>
    );
  }

  let icon: ReactNode = <Settings2 className="h-4 w-4" />;
  if (data.executionStatus === 'running') icon = <Loader2 className="h-4 w-4 animate-spin" />;
  if (data.executionStatus === 'success') icon = <CheckCircle2 className="h-4 w-4" />;
  if (data.executionStatus === 'error') icon = <XCircle className="h-4 w-4" />;

  return (
    <NodeShell
      title={data.title || data.id || 'step'}
      subtitle={`${localizeNodeKind(data.type, t)}${data.phase ? ` / ${data.phase}` : ''}`}
      tokenTitle={data.id || 'step'}
      tokenSubtitle={data.description || t('flows.node.configured_step')}
      status={data.executionStatus}
      selected={selected}
      icon={icon}
      ports={data.ports || []}
    />
  );
}

export function EndNode({ data, selected }: NodeProps<EndNodeType>) {
  const t = useT();
  const icon = data.executionStatus === 'success'
    ? <CheckCircle2 className="h-4 w-4" />
    : <Square className="h-4 w-4" />;
  const endPort = (data.ports || []).find((port) => port.direction === 'input');

  return (
    <NodeShell
      title={localizeNodeTitle(data.title, 'flows.node.finish_title', t)}
      subtitle={t('flows.node.terminal')}
      tokenTitle={endPort ? localizePortLabel(endPort, t) : t('flows.port.done')}
      tokenSubtitle="flow.complete"
      status={data.executionStatus}
      selected={selected}
      icon={icon}
      ports={data.ports || []}
    />
  );
}

export const nodeTypes = {
  trigger: TriggerNode,
  step: StepNode,
  end: EndNode,
} as const;
