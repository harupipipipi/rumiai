import { AlertTriangle, Hand, Loader2, Mic, Play, Radio, Square, Video, X } from "lucide-react";

import { cn } from "../lib/cn";
import { ambientCopyJa, ambientStateVisuals, type AmbientUiState, type AmbientVisualIcon } from "./ambientUiState";

export function StatusGlyph({ uiState }: { uiState: AmbientUiState }) {
  const visual = ambientStateVisuals[uiState];
  return (
    <span className={cn("inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border", visual.glyphClass)}>
      <VisualIcon icon={visual.glyphIcon} size={20} />
    </span>
  );
}

export function StateBadge({ state }: { state: AmbientUiState }) {
  const copy = ambientCopyJa.states[state];
  const visual = ambientStateVisuals[state];
  return (
    <span className={cn("shrink-0 rounded-md border px-1.5 py-0.5 text-[10px] font-semibold leading-4", visual.badgeClass)}>
      {copy.badge}
    </span>
  );
}

export function PrimaryActionIcon({ uiState }: { uiState: AmbientUiState }) {
  return <VisualIcon icon={ambientStateVisuals[uiState].primaryIcon} size={uiState === "monitoring" ? 14 : 15} />;
}

export function primaryButtonClass(uiState: AmbientUiState): string {
  return ambientStateVisuals[uiState].primaryButtonClass;
}

function VisualIcon({ icon, size }: { icon: AmbientVisualIcon; size: number }) {
  if (icon === "alert") return <AlertTriangle size={size} />;
  if (icon === "hand") return <Hand size={size} />;
  if (icon === "loader") return <Loader2 size={size} className="animate-spin" />;
  if (icon === "mic") return <Mic size={size} />;
  if (icon === "play") return <Play size={size} />;
  if (icon === "square") return <Square size={size} />;
  if (icon === "video") return <Video size={size} />;
  if (icon === "x") return <X size={size} />;
  return <Radio size={size} />;
}
