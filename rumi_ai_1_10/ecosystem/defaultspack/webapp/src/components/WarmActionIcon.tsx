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
  attach: "from-stone-200/15 via-amber-200/10 to-orange-300/15 text-amber-100 ring-amber-200/10",
  calendar: "from-amber-200/20 via-orange-300/10 to-rose-300/15 text-amber-100 ring-orange-200/15",
  group: "from-orange-200/20 via-amber-300/15 to-yellow-200/10 text-orange-100 ring-amber-200/15",
  menu: "from-stone-200/15 via-orange-200/10 to-amber-300/15 text-stone-100 ring-orange-200/10",
  mic: "from-rose-200/15 via-orange-300/10 to-amber-200/10 text-rose-100 ring-rose-200/10",
  newChat: "from-yellow-200/20 via-orange-300/15 to-rose-300/10 text-yellow-100 ring-orange-200/15",
  send: "from-amber-100 via-orange-200 to-yellow-300 text-zinc-950 ring-amber-100/30",
  settings: "from-stone-200/10 via-amber-200/10 to-orange-300/10 text-stone-100 ring-stone-200/10",
  stop: "from-zinc-100 via-stone-200 to-amber-100 text-zinc-950 ring-stone-100/30",
  tool: "from-orange-200/15 via-amber-300/10 to-stone-200/10 text-orange-100 ring-amber-200/15",
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
