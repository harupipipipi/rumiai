import {
  CalendarDays,
  FilePlus2,
  Mic,
  Paperclip,
  Plus,
  SendHorizontal,
  Settings,
  Square,
  type LucideProps,
} from "lucide-react";
import type { ElementType } from "react";

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

function NewChatIcon({ size = 24, strokeWidth = 2, ...props }: LucideProps) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={strokeWidth}
      strokeLinecap="round"
      strokeLinejoin="round"
      {...props}
    >
      <path d="M11 4H7.5C5.57 4 4 5.57 4 7.5v9C4 18.43 5.57 20 7.5 20h9c1.93 0 3.5-1.57 3.5-3.5V13" />
      <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z" />
    </svg>
  );
}

function NewFolderIcon({ size = 24, strokeWidth = 2, ...props }: LucideProps) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={strokeWidth}
      strokeLinecap="round"
      strokeLinejoin="round"
      {...props}
    >
      <path d="M13 19H6.5C4.57 19 3 17.43 3 15.5V7.5C3 5.57 4.57 4 6.5 4H9.5C10.8 4 11.2 7 12.5 7H18.5C20.43 7 22 8.57 22 10.5V12.5" />
      <path d="M15 16.5H21M18 13.5V19.5" />
    </svg>
  );
}

const ICONS: Record<WarmActionIconKind, ElementType<LucideProps>> = {
  attach: Paperclip,
  calendar: CalendarDays,
  group: NewFolderIcon,
  menu: Plus,
  mic: Mic,
  newChat: NewChatIcon,
  send: SendHorizontal,
  settings: Settings,
  stop: Square,
  tool: FilePlus2,
};

const TONES: Record<WarmActionIconKind, string> = {
  attach: "text-zinc-100",
  calendar: "text-zinc-100",
  group: "text-zinc-100",
  menu: "text-zinc-100",
  mic: "text-zinc-100",
  newChat: "text-zinc-50",
  send: "bg-zinc-100 text-zinc-950",
  settings: "text-zinc-100",
  stop: "bg-zinc-100 text-zinc-950",
  tool: "text-zinc-100",
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
        "inline-flex shrink-0 items-center justify-center bg-transparent",
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
