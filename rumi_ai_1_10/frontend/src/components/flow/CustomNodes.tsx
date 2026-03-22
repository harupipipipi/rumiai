/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import { Handle, Position, type NodeProps } from '@xyflow/react';
import { Play, Settings2, Square, CheckCircle2, XCircle, Loader2 } from 'lucide-react';
import { cn } from '@/src/lib/utils';
import type {
  TriggerNode as TriggerNodeType,
  StepNode as StepNodeType,
  EndNode as EndNodeType,
  ExecutionStatus,
} from '@/src/lib/types';

function getStatusBorderClass(
  status: ExecutionStatus,
  selectedClass: string,
  defaultClass: string,
): string {
  if (status === 'running') return "border-white shadow-[0_0_10px_rgba(255,255,255,0.5)]";
  if (status === 'success') return "border-green-300";
  return selectedClass || defaultClass;
}

export function TriggerNode({ data, selected }: NodeProps<TriggerNodeType>) {
  const status = data.executionStatus;
  const borderClass = getStatusBorderClass(
    status,
    selected ? "border-indigo-300" : "border-transparent",
    "border-transparent"
  );

  return (
    <div className={cn(
      "px-2.5 py-1.5 shadow-sm rounded bg-indigo-500 text-white border transition-all duration-300",
      borderClass
    )}>
      <div className="flex items-center gap-1.5">
        {status === 'running' ? <Loader2 className="w-3 h-3 animate-spin" /> :
         status === 'success' ? <CheckCircle2 className="w-3 h-3" /> :
         <Play className="w-3 h-3" />}
        <div className="font-bold text-xs">Trigger</div>
      </div>
      <div className="text-[10px] opacity-80 mt-0.5">{data.type || 'on_setup'}</div>
      <Handle type="source" position={Position.Bottom} className="w-2 h-2 bg-indigo-200" />
    </div>
  );
}

export function StepNode({ data, selected }: NodeProps<StepNodeType>) {
  if (data.type === 'reroute') {
    return (
      <div className={cn(
        "w-4 h-4 rounded-full bg-text-muted border-2 transition-all duration-300",
        selected ? "border-accent shadow-[0_0_10px_rgba(99,102,241,0.5)]" : "border-bg-card"
      )}>
        <Handle type="target" position={Position.Top} className="w-1 h-1 opacity-0" />
        <Handle type="source" position={Position.Bottom} className="w-1 h-1 opacity-0" />
      </div>
    );
  }

  const status = data.executionStatus;

  let borderClass = selected ? "border-accent" : "border-border";
  let bgClass = "bg-bg-card";

  if (status === 'running') {
    borderClass = "border-blue-500 shadow-[0_0_10px_rgba(59,130,246,0.5)]";
    bgClass = "bg-blue-500/10";
  } else if (status === 'success') {
    borderClass = "border-green-500";
    bgClass = "bg-green-500/10";
  } else if (status === 'error') {
    borderClass = "border-red-500";
    bgClass = "bg-red-500/10";
  }

  return (
    <div className={cn(
      "px-2.5 py-1.5 shadow-sm rounded text-text-main border min-w-[100px] transition-all duration-300",
      bgClass,
      borderClass
    )}>
      <Handle type="target" position={Position.Top} className="w-2 h-2 bg-text-muted" />
      <div className="flex items-center gap-1.5 mb-0.5">
        {status === 'running' ? (
           <Loader2 className="w-3 h-3 text-blue-500 animate-spin" />
        ) : status === 'success' ? (
           <CheckCircle2 className="w-3 h-3 text-green-500" />
        ) : status === 'error' ? (
           <XCircle className="w-3 h-3 text-red-500" />
        ) : (
           <Settings2 className="w-3 h-3 text-accent" />
        )}
        <div className="font-bold text-xs">{data.id || 'step'}</div>
      </div>
      <div className="text-[10px] text-text-muted">{data.type || 'action'}</div>
      <Handle type="source" position={Position.Bottom} className="w-2 h-2 bg-text-muted" />
    </div>
  );
}

export function EndNode({ data, selected }: NodeProps<EndNodeType>) {
  const status = data.executionStatus;
  const borderClass = getStatusBorderClass(
    status,
    selected ? "border-rose-300" : "border-transparent",
    "border-transparent"
  );

  return (
    <div className={cn(
      "px-2.5 py-1.5 shadow-sm rounded bg-rose-500 text-white border transition-all duration-300",
      borderClass
    )}>
      <Handle type="target" position={Position.Top} className="w-2 h-2 bg-rose-200" />
      <div className="flex items-center gap-1.5">
        {status === 'success' ? <CheckCircle2 className="w-3 h-3" /> : <Square className="w-3 h-3" />}
        <div className="font-bold text-xs">End</div>
      </div>
    </div>
  );
}

/** Module-scope nodeTypes — must NOT be recreated per render */
export const nodeTypes = {
  trigger: TriggerNode,
  step: StepNode,
  end: EndNode,
} as const;
