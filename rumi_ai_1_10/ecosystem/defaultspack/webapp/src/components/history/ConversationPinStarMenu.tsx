import { MoreHorizontal, Pin, PinOff, Star } from "lucide-react";
import { useEffect, useRef, useState } from "react";

export function ConversationPinStarMenu({
  isPinned = false,
  isStarred = false,
  onTogglePinned,
  onToggleStarred,
}: {
  isPinned?: boolean;
  isStarred?: boolean;
  onTogglePinned?: () => void;
  onToggleStarred?: () => void;
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!open) return;
    const close = (event: PointerEvent) => {
      const target = event.target;
      if (target instanceof Node && ref.current?.contains(target)) return;
      setOpen(false);
    };
    document.addEventListener("pointerdown", close);
    return () => document.removeEventListener("pointerdown", close);
  }, [open]);

  return (
    <div ref={ref} className="relative flex flex-shrink-0 items-center gap-0.5">
      {isPinned && <Pin size={10} className="text-sky-300" />}
      {isStarred && <Star size={10} className="fill-current text-amber-300" />}
      {(onTogglePinned || onToggleStarred) && (
        <button
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
        <div
          className="absolute right-0 top-full z-40 mt-1 w-36 overflow-hidden rounded-md border border-zinc-800 bg-zinc-950 shadow-xl"
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
        </div>
      )}
    </div>
  );
}
