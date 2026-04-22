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
  if (status === 'running') return 'ring-2 ring-sky-300/60 border-sky-300';
  if (status === 'success') return 'ring-2 ring-emerald-300/50 border-emerald-300';
  if (status === 'error') return 'ring-2 ring-rose-300/50 border-rose-300';
  return 'border-amber-500/30';
}

function PortHandle({ port, side }: { port: FlowPort; side: 'left' | 'right' }) {
  const isInput = port.direction === 'input';
  const position = side === 'left' ? Position.Left : Position.Right;

  return (
    <div className={cn(
      'relative flex items-center gap-2 rounded-md px-3 py-2 text-[11px] font-medium',
      side === 'left' ? 'justify-start text-amber-50/90' : 'justify-end text-amber-100',
      'bg-[rgba(255,190,74,0.10)]',
    )}>
      {isInput && (
        <Handle
          id={port.id}
          type="target"
          position={position}
          className="!h-3 !w-3 !border-2 !border-amber-300/70 !bg-[#ff8654]"
        />
      )}
      <div className={cn('flex min-w-0 flex-col', side === 'right' && 'items-end')}>
        <span className="truncate">{port.label}</span>
        {port.contracts.length > 0 && (
          <span className="truncate text-[10px] text-amber-100/60">{port.contracts.join(' | ')}</span>
        )}
      </div>
      {!isInput && (
        <Handle
          id={port.id}
          type="source"
          position={position}
          className="!h-3 !w-3 !border-2 !border-amber-300/70 !bg-[#ff8654]"
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
        'flow-node-shell min-w-[240px] rounded-[20px] border bg-[linear-gradient(180deg,rgba(255,197,92,0.92)_0%,rgba(255,173,68,0.82)_100%)] p-3 text-[#2d1702] shadow-[0_22px_50px_rgba(0,0,0,0.28)] transition-all duration-300',
        selected ? 'scale-[1.01] border-amber-100 shadow-[0_28px_70px_rgba(255,170,72,0.28)]' : statusAccent(status),
      )}
    >
      <div className="mb-3 rounded-[16px] border border-amber-100/40 bg-[rgba(120,55,0,0.14)] px-4 py-3 text-amber-950">
        <div className="flex items-center gap-2 text-sm font-semibold">
          {icon}
          <span>{title}</span>
        </div>
        {subtitle && <div className="mt-1 text-[11px] text-amber-950/70">{subtitle}</div>}
      </div>
      <div className="grid grid-cols-[1fr_1fr] gap-3">
        <PortRail ports={inputPorts} side="left" />
        <PortRail ports={outputPorts} side="right" />
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
        'rounded-full border border-amber-200/60 bg-[#ffb24a] p-2 shadow-[0_0_22px_rgba(255,178,74,0.34)]',
        selected && 'ring-2 ring-amber-100',
      )}>
        <Handle id="reroute-in" type="target" position={Position.Left} className="!h-3 !w-3 !border-2 !border-amber-100 !bg-[#6e3400]" />
        <Waypoints className="h-4 w-4 text-[#572400]" />
        <Handle id="reroute-out" type="source" position={Position.Right} className="!h-3 !w-3 !border-2 !border-amber-100 !bg-[#6e3400]" />
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
