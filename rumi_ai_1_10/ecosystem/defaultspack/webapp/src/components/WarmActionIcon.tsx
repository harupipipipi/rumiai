import {
  CalendarDays,
  FilePlus2,
  FolderPlus,
  MessageSquarePlus,
  Mic,
  Paperclip,
  Plus,
  SendHorizontal,
  Settings,
  Square,
  type LucideIcon,
} from "lucide-react";

import { cn } from "../lib/cn";

export type WarmActionIconKind =
  | "attach"
  | "calendar"
  | "group"
  | "menu"
  | "mic"
  | "newChat"
  | "send"
  | "settings"
  | "stop"
  | "tool";

const ICONS: Record<WarmActionIconKind, LucideIcon> = {
  attach: Paperclip,
  calendar: CalendarDays,
  group: FolderPlus,
  menu: Plus,
  mic: Mic,
  newChat: MessageSquarePlus,
  send: SendHorizontal,
  settings: Settings,
  stop: Square,
  tool: FilePlus2,
};

const TONES: Record<WarmActionIconKind, string> = {
  attach: "from-zinc-100/14 via-zinc-500/10 to-zinc-950/30 text-zinc-100 ring-zinc-400/10",
  calendar: "from-zinc-100/16 via-zinc-600/12 to-zinc-950/35 text-zinc-100 ring-zinc-300/12",
  group: "from-zinc-100/15 via-stone-400/12 to-zinc-950/35 text-zinc-100 ring-zinc-300/12",
  menu: "from-zinc-100/12 via-zinc-500/10 to-zinc-950/35 text-zinc-100 ring-zinc-400/10",
  mic: "from-zinc-100/14 via-stone-500/10 to-zinc-950/35 text-zinc-100 ring-zinc-400/10",
  newChat: "from-zinc-100/18 via-zinc-500/12 to-zinc-950/35 text-zinc-50 ring-zinc-300/14",
  send: "from-zinc-50 via-zinc-200 to-zinc-400 text-zinc-950 ring-white/30",
  settings: "from-zinc-100/10 via-zinc-500/10 to-zinc-950/30 text-zinc-100 ring-zinc-300/10",
  stop: "from-zinc-50 via-zinc-200 to-zinc-400 text-zinc-950 ring-white/30",
  tool: "from-zinc-100/14 via-zinc-500/10 to-zinc-950/35 text-zinc-100 ring-zinc-300/12",
};

type WarmActionIconProps = {
  kind: WarmActionIconKind;
  className?: string;
  iconClassName?: string;
  size?: "sm" | "md" | "lg";
};

const SIZE_CLASS: Record<NonNullable<WarmActionIconProps["size"]>, { shell: string; icon: number }> = {
  sm: { shell: "h-5 w-5 rounded-lg", icon: 12 },
  md: { shell: "h-7 w-7 rounded-xl", icon: 15 },
  lg: { shell: "h-9 w-9 rounded-2xl", icon: 18 },
};

export function WarmActionIcon({
  kind,
  className,
  iconClassName,
  size = "md",
}: WarmActionIconProps) {
  const Icon = ICONS[kind];
  const sizing = SIZE_CLASS[size];
  return (
    <span
      aria-hidden="true"
      className={cn(
        "inline-flex shrink-0 items-center justify-center bg-gradient-to-br shadow-[inset_0_1px_0_rgba(255,255,255,0.18),0_8px_18px_rgba(0,0,0,0.22)] ring-1",
        sizing.shell,
        TONES[kind],
        className,
      )}
    >
      <Icon
        size={sizing.icon}
        strokeWidth={kind === "send" || kind === "stop" ? 2.4 : 2}
        className={iconClassName}
        fill={kind === "stop" ? "currentColor" : "none"}
      />
    </span>
  );
}
