import { Ban, Check, ChevronDown, ShieldCheck, SlidersHorizontal, Sparkles } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import type { ToolSelectionMode } from "./types";

const MODE_OPTIONS: Array<{
  mode: ToolSelectionMode;
  label: string;
  shortLabel: string;
  title: string;
  description: string;
  icon: typeof Sparkles;
}> = [
  { mode: "auto", label: "機能 自動", shortLabel: "自動", title: "自動で選ぶ", description: "依頼に必要な機能だけをRumiが選びます", icon: Sparkles },
  { mode: "review", label: "機能 確認", shortLabel: "確認", title: "使う前に確認", description: "候補を確認してから回答を開始します", icon: ShieldCheck },
  { mode: "manual", label: "機能 手動", shortLabel: "手動", title: "自分で選ぶ", description: "選んだ機能だけを候補にします", icon: SlidersHorizontal },
  { mode: "none", label: "機能 なし", shortLabel: "なし", title: "機能を使わない", description: "このメッセージでは外部機能を使いません", icon: Ban },
];

export function ToolModeControl({
  mode,
  manualCount = 0,
  disabled = false,
  surfaceClassName,
  tabIndex,
  onModeChange,
  onOpenPicker,
  onOpenHub,
}: {
  mode: ToolSelectionMode;
  manualCount?: number;
  disabled?: boolean;
  surfaceClassName: string;
  tabIndex?: number;
  onModeChange: (mode: ToolSelectionMode) => void;
  onOpenPicker?: () => void;
  onOpenHub?: () => void;
}) {
  const [open, setOpen] = useState(false);
  const triggerRef = useRef<HTMLButtonElement | null>(null);
  const current = MODE_OPTIONS.find((option) => option.mode === mode) ?? MODE_OPTIONS[0];
  const Icon = current.icon;

  useEffect(() => {
    if (!open) return;
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setOpen(false);
        triggerRef.current?.focus();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [open]);

  return (
    <div className="relative flex min-w-0">
      <button
        ref={triggerRef}
        type="button"
        tabIndex={tabIndex}
        disabled={disabled}
        aria-haspopup="dialog"
        aria-expanded={open}
        aria-label="機能の使い方"
        title="機能の使い方"
        onClick={() => setOpen((value) => !value)}
        className={`${surfaceClassName} min-w-[92px] max-w-[144px] gap-1.5 text-zinc-300 transition-colors hover:border-zinc-600 hover:text-zinc-100 disabled:opacity-50 max-[760px]:min-w-[72px]`}
      >
        <Icon size={15} className="flex-shrink-0" />
        <span className="min-w-0 truncate text-[12px] font-medium max-[760px]:hidden">
          {current.label}
        </span>
        <span className="hidden min-w-0 truncate text-[12px] font-medium max-[760px]:inline">
          {current.shortLabel}
        </span>
        {mode === "manual" && manualCount > 0 && (
          <span className="ml-0.5 rounded-full bg-zinc-700 px-1.5 text-[10px] text-zinc-100">{manualCount}</span>
        )}
        <ChevronDown size={12} className={`flex-shrink-0 text-zinc-500 transition-transform ${open ? "rotate-180" : ""}`} />
      </button>
      {open && (
        <>
          <button
            type="button"
            aria-label="機能メニューを閉じる"
            className="fixed inset-0 rumi-layer-local-popover cursor-default bg-black/20 min-[761px]:bg-transparent"
            onClick={() => {
              setOpen(false);
              triggerRef.current?.focus();
            }}
          />
          <div
            role="dialog"
            aria-label="機能の使い方"
            className="absolute bottom-full left-0 rumi-layer-command-palette mb-2 w-[336px] overflow-hidden rounded-2xl border border-zinc-800 bg-zinc-950 shadow-2xl max-[760px]:fixed max-[760px]:bottom-2 max-[760px]:left-2 max-[760px]:right-2 max-[760px]:mb-0 max-[760px]:max-h-[72vh] max-[760px]:w-auto"
          >
            <div className="hidden justify-center pt-2 max-[760px]:flex">
              <span className="h-1 w-10 rounded-full bg-zinc-700" />
            </div>
            <div className="border-b border-zinc-800 px-4 py-3">
              <p className="text-sm font-semibold text-zinc-100">機能の使い方</p>
              <p className="mt-0.5 text-[11px] text-zinc-500">このメッセージで外部機能をどう扱うか選びます</p>
            </div>
            <div role="radiogroup" className="grid gap-1 p-2">
              {MODE_OPTIONS.map((option) => {
                const OptionIcon = option.icon;
                const selected = option.mode === mode;
                return (
                  <button
                    key={option.mode}
                    type="button"
                    role="radio"
                    aria-checked={selected}
                    tabIndex={tabIndex}
                    onClick={() => {
                      onModeChange(option.mode);
                      setOpen(false);
                      triggerRef.current?.focus();
                    }}
                    className={`flex min-h-[58px] w-full items-center gap-3 rounded-xl px-3 py-2 text-left transition-colors ${
                      selected ? "bg-zinc-800 text-zinc-100" : "text-zinc-300 hover:bg-zinc-900"
                    }`}
                  >
                    <OptionIcon size={16} className="flex-shrink-0 text-zinc-400" />
                    <span className="min-w-0 flex-1">
                      <span className="block text-[13px] font-medium">{option.title}</span>
                      <span className="block text-[11px] text-zinc-500">{option.description}</span>
                    </span>
                    {selected && <Check size={15} className="flex-shrink-0 text-emerald-300" />}
                  </button>
                );
              })}
            </div>
            <div className="grid gap-1 border-t border-zinc-800 p-2">
              <button type="button" tabIndex={tabIndex} onClick={onOpenPicker} className="rounded-lg px-3 py-2 text-left text-xs text-zinc-300 hover:bg-zinc-900">
                今回使う機能を選ぶ
              </button>
              <button type="button" tabIndex={tabIndex} onClick={onOpenHub} className="rounded-lg px-3 py-2 text-left text-xs text-zinc-300 hover:bg-zinc-900">
                機能と接続を管理
              </button>
              <button type="button" tabIndex={tabIndex} onClick={() => setOpen(false)} className="hidden rounded-lg bg-zinc-100 px-3 py-2 text-center text-xs font-semibold text-zinc-950 max-[760px]:block">
                完了
              </button>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
