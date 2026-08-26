import { MoreHorizontal, Pin, PinOff, Star, Copy } from "lucide-react";
import { useEffect, useLayoutEffect, useRef, useState } from "react";

import { LayerPortal } from "../../ui/layers/LayerPortal";

type MenuPosition = {
  left: number;
  top: number;
};

export function ConversationPinStarMenu({
  isPinned = false,
  isStarred = false,
  onTogglePinned,
  onToggleStarred,
  onCopyConversationId,
}: {
  isPinned?: boolean;
  isStarred?: boolean;
  onTogglePinned?: () => void;
  onToggleStarred?: () => void;
  onCopyConversationId?: () => void;
}) {
  const [open, setOpen] = useState(false);
  const [menuPosition, setMenuPosition] = useState<MenuPosition | null>(null);
  const containerRef = useRef<HTMLDivElement | null>(null);
  const triggerRef = useRef<HTMLButtonElement | null>(null);
  const menuRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!open) return;
    const close = (event: PointerEvent) => {
      const target = event.target;
      if (!(target instanceof Node)) return;
      if (containerRef.current?.contains(target)) return;
      if (menuRef.current?.contains(target)) return;
      setOpen(false);
    };
    document.addEventListener("pointerdown", close);
    return () => document.removeEventListener("pointerdown", close);
  }, [open]);

  useLayoutEffect(() => {
    if (!open) {
      setMenuPosition(null);
      return;
    }

    const updatePosition = () => {
      const trigger = triggerRef.current?.getBoundingClientRect();
      const menu = menuRef.current;
      if (!trigger || !menu) return;

      const menuRect = menu.getBoundingClientRect();
      const menuWidth = Math.max(menuRect.width || 176, 176);
      const menuHeight = Math.max(menuRect.height || 0, 72);
      const viewportMargin = 8;
      const gap = 6;
      const preferredLeft = Math.min(
        Math.max(viewportMargin, trigger.right - menuWidth),
        Math.max(viewportMargin, window.innerWidth - menuWidth - viewportMargin),
      );
      const belowTop = trigger.bottom + gap;
      const aboveTop = Math.max(viewportMargin, trigger.top - menuHeight - gap);
      const preferredTop = belowTop + menuHeight <= window.innerHeight - viewportMargin ? belowTop : aboveTop;

      setMenuPosition({
        left: preferredLeft,
        top: preferredTop,
      });
    };

    updatePosition();
    window.addEventListener("resize", updatePosition);
    window.addEventListener("scroll", updatePosition, true);
    return () => {
      window.removeEventListener("resize", updatePosition);
      window.removeEventListener("scroll", updatePosition, true);
    };
  }, [open]);

  return (
    <div ref={containerRef} className="relative flex flex-shrink-0 items-center gap-0.5">
      {isPinned && <Pin size={10} className="text-sky-300" />}
      {isStarred && <Star size={10} className="fill-current text-amber-300" />}
      {(onTogglePinned || onToggleStarred || onCopyConversationId) && (
        <button
          ref={triggerRef}
          type="button"
          onClick={(event) => {
            event.stopPropagation();
            setOpen((value) => !value);
          }}
          className="hidden h-5 w-5 items-center justify-center rounded text-zinc-600 hover:bg-zinc-800 hover:text-zinc-200 group-hover/chat:flex"
          title="Conversation actions"
        >
          <MoreHorizontal size={13} />
        </button>
      )}
      {open && (
        <LayerPortal layer="localPopover">
          <div
            ref={menuRef}
            className="fixed rumi-layer-global-overlay w-44 overflow-hidden rounded-md border border-zinc-800 bg-zinc-950 shadow-xl"
            style={menuPosition ? { left: `${menuPosition.left}px`, top: `${menuPosition.top}px` } : { visibility: "hidden" }}
            onClick={(event) => event.stopPropagation()}
          >
            {onTogglePinned && (
              <button
                type="button"
                onClick={() => {
                  onTogglePinned();
                  setOpen(false);
                }}
                className="flex w-full items-center gap-2 px-2.5 py-1.5 text-left text-[11px] text-zinc-300 hover:bg-zinc-800"
              >
                {isPinned ? <PinOff size={12} /> : <Pin size={12} />}
                {isPinned ? "Unpin" : "Pin"}
              </button>
            )}
            {onToggleStarred && (
              <button
                type="button"
                onClick={() => {
                  onToggleStarred();
                  setOpen(false);
                }}
                className="flex w-full items-center gap-2 px-2.5 py-1.5 text-left text-[11px] text-zinc-300 hover:bg-zinc-800"
              >
                <Star size={12} className={isStarred ? "fill-current text-amber-300" : undefined} />
                {isStarred ? "Unstar" : "Star"}
              </button>
            )}
            {onCopyConversationId && (
              <button
                type="button"
                onClick={() => {
                  onCopyConversationId();
                  setOpen(false);
                }}
                className="flex w-full items-center gap-2 px-2.5 py-1.5 text-left text-[11px] text-zinc-300 hover:bg-zinc-800"
              >
                <Copy size={12} />
                Copy chat ID
              </button>
            )}
          </div>
        </LayerPortal>
      )}
    </div>
  );
}
