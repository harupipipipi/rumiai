import { Camera, Hand, Mic, MicOff, PauseCircle, Radio, ShieldAlert } from "lucide-react";

import { cn } from "../lib/cn";

export type AmbientIconKind = "mic" | "camera" | "listening" | "denied" | "paused" | "pinch";

type Props = {
  kind: AmbientIconKind;
  active?: boolean;
  title?: string;
  className?: string;
};

const icons = {
  mic: Mic,
  camera: Camera,
  listening: Radio,
  denied: ShieldAlert,
  paused: PauseCircle,
  pinch: Hand,
};

export function AmbientTriggerStatusIcon({ kind, active = false, title, className }: Props) {
  const Icon = active && kind === "mic" ? Mic : !active && kind === "mic" ? MicOff : icons[kind];
  return (
    <span
      title={title ?? kind}
      className={cn(
        "inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-lg border text-[13px]",
        active
          ? "border-emerald-400/35 bg-emerald-400/10 text-emerald-200"
          : "border-zinc-800 bg-zinc-950 text-zinc-500",
        kind === "denied" && "border-red-400/35 bg-red-500/10 text-red-200",
        className,
      )}
    >
      <Icon size={15} strokeWidth={2.2} />
    </span>
  );
}
