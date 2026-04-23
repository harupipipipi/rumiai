import React, { type ReactNode } from 'react';
import { Handle, Position, type NodeProps } from '@xyflow/react';
import { Play, Settings2, Square, CheckCircle2, XCircle, Loader2, Waypoints } from 'lucide-react';
import { cn } from '@/src/lib/utils';
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

function PortHandle({ port, side }: { port: FlowPort; side: 'left' | 'right' }) {
  const isInput = port.direction === 'input';
  const position = side === 'left' ? Position.Left : Position.Right;

  return (
    <div
      className={cn(
        'flow-port-row relative flex min-h-10 items-center',
        side === 'left' ? 'justify-start pl-4 pr-2 text-left' : 'justify-end pl-2 pr-4 text-right',
      )}
    >
      {isInput && (
        <Handle
          id={port.id}
          type="target"
          position={position}
          className="flow-port-handle !top-1/2 !-translate-y-1/2 !border-[3px] !shadow-none"
        />
      )}
      <div
        className={cn(
          'flow-port-pill flex min-w-0 flex-1 flex-col rounded-2xl border px-3 py-2',
          side === 'right' && 'items-end',
        )}
      >
        <span className="truncate text-[12px] font-semibold">{port.label}</span>
        {port.contracts.length > 0 && (
          <span className="truncate text-[10px] opacity-70">{port.contracts.join(' | ')}</span>
        )}
      </div>
      {!isInput && (
        <Handle
          id={port.id}
          type="source"
          position={position}
          className="flow-port-handle !top-1/2 !-translate-y-1/2 !border-[3px] !shadow-none"
        />
      )}
    </div>
  );
}

function PortRail({ ports, side }: { ports: FlowPort[]; side: 'left' | 'right' }) {
  if (ports.length === 0) {
    return null;
  }
  return (
    <div className="flex flex-1 flex-col gap-2">
      {ports.map((port) => (
        <div key={port.id}>
          <PortHandle port={port} side={side} />
        </div>
      ))}
    </div>
  );
}

function NodeShell({
  title,
  subtitle,
  status,
  selected,
  icon,
  ports,
}: {
  title: string;
  subtitle?: string;
  status: ExecutionStatus;
  selected: boolean;
  icon: ReactNode;
  ports: FlowPort[];
}) {
  const inputPorts = ports.filter((port) => port.direction === 'input');
  const outputPorts = ports.filter((port) => port.direction === 'output');

  return (
    <div
      className={cn(
        'flow-node-shell min-w-[220px] transition-transform duration-150',
        selected && 'is-selected scale-[1.01]',
        statusAccent(status),
      )}
    >
      <div className="flow-node-cap">
        <div className="flex items-center gap-2 truncate">
          {icon}
          <span className="truncate">{title}</span>
        </div>
      </div>

      <div className="flow-node-card">
        <div className="flow-node-body">
          {subtitle ? <div className="flow-node-subtitle">{subtitle}</div> : null}
          <div className="grid grid-cols-[minmax(0,1fr)_minmax(0,1fr)] gap-3">
            <PortRail ports={inputPorts} side="left" />
            <PortRail ports={outputPorts} side="right" />
          </div>
        </div>
      </div>
    </div>
  );
}

export function TriggerNode({ data, selected }: NodeProps<TriggerNodeType>) {
  const status = data.executionStatus;
  const icon = status === 'running'
    ? <Loader2 className="h-4 w-4 animate-spin" />
    : status === 'success'
      ? <CheckCircle2 className="h-4 w-4" />
      : <Play className="h-4 w-4" />;

  return (
    <NodeShell
      title={data.title || 'rumi_start'}
      subtitle={`basepack: ${data.basePack || 'basepack'}`}
      status={status}
      selected={selected}
      icon={icon}
      ports={data.ports || []}
    />
  );
}

export function StepNode({ data, selected }: NodeProps<StepNodeType>) {
  if (data.type === 'reroute') {
    return (
      <div className={cn(
        'flow-reroute-node rounded-full border p-2',
        selected && 'ring-2',
      )}>
        <Handle id="reroute-in" type="target" position={Position.Left} className="flow-port-handle !top-1/2 !-translate-y-1/2 !border-[3px] !shadow-none" />
        <Waypoints className="h-4 w-4" />
        <Handle id="reroute-out" type="source" position={Position.Right} className="flow-port-handle !top-1/2 !-translate-y-1/2 !border-[3px] !shadow-none" />
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
      subtitle={`${data.type || 'action'}${data.phase ? ` / ${data.phase}` : ''}`}
      status={data.executionStatus}
      selected={selected}
      icon={icon}
      ports={data.ports || []}
    />
  );
}

export function EndNode({ data, selected }: NodeProps<EndNodeType>) {
  const icon = data.executionStatus === 'success'
    ? <CheckCircle2 className="h-4 w-4" />
    : <Square className="h-4 w-4" />;

  return (
    <NodeShell
      title={data.title || 'finish'}
      subtitle="terminal"
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
