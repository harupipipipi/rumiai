import { Check, ChevronDown, Hand, Settings, Shield, ShieldCheck, ShieldAlert } from "lucide-react";
import { useCallback, useEffect, useLayoutEffect, useRef, useState, type CSSProperties } from "react";
import { createPortal } from "react-dom";

export type ActionApprovalMode = "ask" | "agent" | "full" | "custom";

const MENU_WIDTH = 560;
const MENU_HEIGHT_ESTIMATE = 318;
const MENU_GAP = 10;
const MENU_MARGIN = 8;

const OPTIONS: Array<{
  mode: ActionApprovalMode;
  label: string;
  shortLabel: string;
  description: string;
  icon: typeof Hand;
}> = [
  {
    mode: "ask",
    label: "承認を求める",
    shortLabel: "承認",
    description: "外部ファイルの編集やインターネットの利用について、常に確認を求めます",
    icon: Hand,
  },
  {
    mode: "agent",
    label: "代理で承認",
    shortLabel: "代理承認",
    description: "安全でない可能性があると検出された操作についてのみ確認を求めます",
    icon: ShieldCheck,
  },
  {
    mode: "full",
    label: "フルアクセス",
    shortLabel: "フル",
    description: "インターネットとコンピュータ上のすべてのファイルに無制限でアクセスします",
    icon: ShieldAlert,
  },
  {
    mode: "custom",
    label: "カスタム（設定）",
    shortLabel: "カスタム",
    description: "Settingsで定義された権限を使用します",
    icon: Settings,
  },
];

export function ActionApprovalControl({
  mode,
  disabled = false,
  surfaceClassName,
  tabIndex,
  onModeChange,
  onOpenSettings,
}: {
  mode: ActionApprovalMode;
  disabled?: boolean;
  surfaceClassName: string;
  tabIndex?: number;
  onModeChange: (mode: ActionApprovalMode) => void;
  onOpenSettings?: () => void;
}) {
  const [open, setOpen] = useState(false);
  const [menuStyle, setMenuStyle] = useState<CSSProperties | null>(null);
  const triggerRef = useRef<HTMLButtonElement | null>(null);
  const current = OPTIONS.find((option) => option.mode === mode) ?? OPTIONS[0];
  const Icon = current.mode === "custom" ? Shield : current.icon;

  const closeMenu = useCallback(() => {
    setOpen(false);
    triggerRef.current?.focus();
  }, []);

  const updateMenuStyle = useCallback(() => {
    if (typeof window === "undefined" || !triggerRef.current) return;
    const rect = triggerRef.current.getBoundingClientRect();
    if (window.innerWidth <= 760) {
      setMenuStyle({
        left: MENU_MARGIN,
        right: MENU_MARGIN,
        bottom: MENU_MARGIN,
        maxHeight: "72vh",
      });
      return;
    }

    const menuWidth = Math.min(MENU_WIDTH, window.innerWidth - MENU_MARGIN * 2);
    const minLeft = MENU_MARGIN;
    const maxLeft = window.innerWidth - menuWidth - MENU_MARGIN;
    const preferredLeft = rect.left + rect.width / 2 - menuWidth / 2;
    const left = Math.min(Math.max(preferredLeft, minLeft), maxLeft);
    const spaceAbove = rect.top - MENU_MARGIN;
    const spaceBelow = window.innerHeight - rect.bottom - MENU_MARGIN;
    const placeBelow = spaceBelow >= MENU_HEIGHT_ESTIMATE || spaceBelow > spaceAbove;
    const preferredTop = placeBelow ? rect.bottom + MENU_GAP : rect.top - MENU_HEIGHT_ESTIMATE - MENU_GAP;
    const maxTop = window.innerHeight - MENU_HEIGHT_ESTIMATE - MENU_MARGIN;
    const top = Math.min(Math.max(preferredTop, MENU_MARGIN), Math.max(MENU_MARGIN, maxTop));
    setMenuStyle({
      left,
      top,
      width: menuWidth,
      maxHeight: Math.min(MENU_HEIGHT_ESTIMATE, window.innerHeight - MENU_MARGIN * 2),
    });
  }, []);

  useLayoutEffect(() => {
    if (!open) {
      setMenuStyle(null);
      return;
    }
    updateMenuStyle();
    if (typeof window === "undefined") return;
    window.addEventListener("resize", updateMenuStyle);
    window.addEventListener("scroll", updateMenuStyle, true);
    return () => {
      window.removeEventListener("resize", updateMenuStyle);
      window.removeEventListener("scroll", updateMenuStyle, true);
    };
  }, [open, updateMenuStyle]);

  useEffect(() => {
    if (!open) return;
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") closeMenu();
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [closeMenu, open]);

  const menu = open && typeof document !== "undefined" ? createPortal(
    <>
      <button
        type="button"
        aria-label="承認方法メニューを閉じる"
        className="fixed inset-0 rumi-layer-local-popover cursor-default bg-transparent"
        onClick={closeMenu}
      />
      <div
        role="menu"
        aria-label="アクションの承認方法"
        style={menuStyle ?? undefined}
        className="fixed rumi-layer-command-palette overflow-y-auto rounded-[1.35rem] border border-zinc-700/70 bg-[#2b2b2b] p-2 shadow-2xl shadow-black/40 max-[760px]:rounded-[1.6rem]"
      >
        <div className="flex items-center justify-between gap-3 px-4 pb-2 pt-1 text-zinc-400">
          <span className="text-[13px]">Codex アクションの承認方法</span>
          <button
            type="button"
            tabIndex={tabIndex}
            onClick={() => {
              closeMenu();
              onOpenSettings?.();
            }}
            className="text-[13px] underline underline-offset-4 hover:text-zinc-100"
          >
            詳細はこちら
          </button>
        </div>
        {OPTIONS.map((option) => {
          const OptionIcon = option.icon;
          const selected = option.mode === mode;
          return (
            <button
              key={option.mode}
              type="button"
              role="menuitemradio"
              aria-checked={selected}
              tabIndex={tabIndex}
              onClick={() => {
                if (option.mode === "custom") {
                  closeMenu();
                  onOpenSettings?.();
                  return;
                }
                onModeChange(option.mode);
                setOpen(false);
              }}
              className={`flex min-h-[68px] w-full items-center gap-4 rounded-[1rem] px-4 py-2.5 text-left transition-colors ${
                selected ? "bg-zinc-700/55 text-zinc-50" : "text-zinc-200 hover:bg-zinc-700/35"
              }`}
            >
              <OptionIcon size={24} className="flex-shrink-0 text-zinc-300" />
              <span className="min-w-0 flex-1">
                <span className="block text-[15px] font-medium leading-5">{option.label}</span>
                <span className="block text-[13px] leading-5 text-zinc-400">{option.description}</span>
              </span>
              {selected && <Check size={22} className="flex-shrink-0 text-zinc-200" />}
            </button>
          );
        })}
      </div>
    </>,
    document.body,
  ) : null;

  return (
    <div className="relative flex min-w-0">
      <button
        ref={triggerRef}
        type="button"
        tabIndex={tabIndex}
        disabled={disabled}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label="アクションの承認方法"
        title="アクションの承認方法"
        onClick={() => setOpen((value) => !value)}
        className={`${surfaceClassName} min-w-[86px] max-w-[132px] gap-1.5 text-zinc-300 transition-colors hover:border-zinc-600 hover:text-zinc-100 disabled:opacity-50 max-[760px]:min-w-[64px]`}
      >
        <Icon size={15} className="flex-shrink-0" />
        <span className="min-w-0 truncate text-[12px] font-medium max-[760px]:hidden">
          {current.shortLabel}
        </span>
        <ChevronDown size={12} className={`flex-shrink-0 text-zinc-500 transition-transform ${open ? "rotate-180" : ""}`} />
      </button>
      {menu}
    </div>
  );
}
