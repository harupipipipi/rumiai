import { Check, ChevronDown, Loader2, Plus, Search, Star, X } from "lucide-react";
import { useEffect, useMemo, useRef, useState, type KeyboardEvent } from "react";

import {
  filterEntityPickerItems,
  type EntityPickerItem,
  type EntityPickerPage,
  type EntityPickerPageRequest,
  type EntityPickerSelectionRequest,
  type ResolvedEntityPicker,
} from "../lib/entityPicker";

export type EntityPickerHostProps = {
  picker: ResolvedEntityPicker;
  open?: boolean;
  initialQuery?: string;
  selectedIds?: string[];
  onClose?: () => void;
  onSelect?: (request: EntityPickerSelectionRequest) => Promise<unknown> | unknown;
  onCreate?: (request: EntityPickerSelectionRequest) => Promise<unknown> | unknown;
  onLoadPage?: (request: EntityPickerPageRequest) => Promise<EntityPickerPage>;
};

function message(reason: unknown): string {
  return reason instanceof Error && reason.message.trim()
    ? reason.message.slice(0, 300)
    : "The backend rejected the selection. The previous value was restored.";
}

function mergeItems(current: EntityPickerItem[], incoming: EntityPickerItem[]): EntityPickerItem[] {
  const byId = new Map(current.map((item) => [item.id, item]));
  incoming.forEach((item) => byId.set(item.id, item));
  return [...byId.values()];
}

function groupLabel(item: EntityPickerItem): string {
  if (item.create) return "Actions";
  if (item.favorite) return "Favorites";
  if (item.recent) return "Recent";
  return item.group ?? "Items";
}

function PickerBody({
  picker,
  initialQuery = "",
  selectedIds,
  onClose,
  onSelect,
  onCreate,
  onLoadPage,
}: EntityPickerHostProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const previousFocusRef = useRef<HTMLElement | null>(null);
  const [query, setQuery] = useState(initialQuery);
  const [items, setItems] = useState(picker.items);
  const [selection, setSelection] = useState(() => new Set(selectedIds ?? picker.selectedIds));
  const committedSelectionRef = useRef(new Set(selectedIds ?? picker.selectedIds));
  const [activeIndex, setActiveIndex] = useState(0);
  const [loading, setLoading] = useState(false);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [nextCursor, setNextCursor] = useState(picker.nextCursor);
  const [sourceRevision, setSourceRevision] = useState(picker.sourceRevision);

  useEffect(() => {
    previousFocusRef.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    inputRef.current?.focus();
    return () => previousFocusRef.current?.focus();
  }, []);

  useEffect(() => {
    const next = new Set(selectedIds ?? picker.selectedIds);
    committedSelectionRef.current = next;
    setSelection(next);
  }, [picker.selectedIds, selectedIds]);

  useEffect(() => {
    if (!picker.remote || !onLoadPage) return undefined;
    let active = true;
    const timer = window.setTimeout(() => {
      setLoading(true);
      setError(null);
      void onLoadPage({
        pickerId: picker.id,
        actionId: picker.loadActionId,
        query,
        dataSourceId: picker.dataSourceId,
        sourceRevision: picker.sourceRevision,
      }).then((page) => {
        if (!active) return;
        const fixed = picker.items.filter((item) => item.fixed);
        setItems(mergeItems(fixed, page.items));
        setNextCursor(page.nextCursor);
        setSourceRevision(page.sourceRevision ?? picker.sourceRevision);
      }).catch((reason) => {
        if (active) setError(message(reason));
      }).finally(() => {
        if (active) setLoading(false);
      });
    }, 180);
    return () => {
      active = false;
      window.clearTimeout(timer);
    };
  }, [onLoadPage, picker, query]);

  const visible = useMemo(
    () => filterEntityPickerItems(items, picker.remote && onLoadPage ? "" : query),
    [items, onLoadPage, picker.remote, query],
  );
  const groups = useMemo(() => {
    const result: Array<{ label: string; items: EntityPickerItem[] }> = [];
    for (const item of visible) {
      const label = groupLabel(item);
      const group = result.find((candidate) => candidate.label === label);
      if (group) group.items.push(item);
      else result.push({ label, items: [item] });
    }
    return result;
  }, [visible]);

  useEffect(() => setActiveIndex((current) => Math.min(current, Math.max(0, visible.length - 1))), [visible.length]);

  const request = (ids: string[], actionId = picker.selectActionId): EntityPickerSelectionRequest => ({
    pickerId: picker.id,
    selectedIds: ids,
    actionId,
    valueScope: picker.valueScope,
    dataSourceId: picker.dataSourceId,
    sourceRevision,
    query,
  });

  const commit = async (ids: string[]) => {
    const previous = new Set(committedSelectionRef.current);
    setSelection(new Set(ids));
    setPending(true);
    setError(null);
    try {
      await onSelect?.(request(ids));
      committedSelectionRef.current = new Set(ids);
      if (picker.selectionMode === "single") onClose?.();
    } catch (reason) {
      setSelection(previous);
      setError(message(reason));
    } finally {
      setPending(false);
    }
  };

  const choose = (item: EntityPickerItem) => {
    if (item.disabled || pending) return;
    if (item.create) {
      setPending(true);
      setError(null);
      void Promise.resolve(onCreate?.(request([], picker.createActionId))).catch((reason) => setError(message(reason))).finally(() => setPending(false));
      return;
    }
    if (picker.selectionMode === "single") {
      void commit([item.id]);
      return;
    }
    setSelection((current) => {
      const next = new Set(current);
      if (next.has(item.id)) next.delete(item.id);
      else next.add(item.id);
      return next;
    });
  };

  const loadMore = async () => {
    if (!picker.remote || !onLoadPage || !nextCursor || loading) return;
    setLoading(true);
    setError(null);
    try {
      const page = await onLoadPage({ pickerId: picker.id, actionId: picker.loadActionId, query, cursor: nextCursor, dataSourceId: picker.dataSourceId, sourceRevision });
      setItems((current) => mergeItems(current, page.items));
      setNextCursor(page.nextCursor);
      setSourceRevision(page.sourceRevision ?? sourceRevision);
    } catch (reason) {
      setError(message(reason));
    } finally {
      setLoading(false);
    }
  };

  const handleInputKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      const delta = event.key === "ArrowDown" ? 1 : -1;
      setActiveIndex((current) => (current + delta + Math.max(1, visible.length)) % Math.max(1, visible.length));
    } else if (event.key === "Enter" && visible[activeIndex]) {
      event.preventDefault();
      choose(visible[activeIndex]);
    } else if (event.key === "Escape") {
      event.preventDefault();
      onClose?.();
    }
  };

  if (picker.unsupported) {
    return (
      <div role="alert" className="rounded-xl border border-rose-500/35 bg-rose-500/10 p-4 text-sm text-rose-100" data-entity-picker-unsupported="true">
        <strong>{picker.label}</strong>
        <p className="mt-1 text-xs">{picker.description}</p>
        <p className="mt-2 text-[10px] opacity-70">{picker.diagnostics[0]?.code} · {picker.templateId ?? "unknown template"} · {picker.trustLevel ?? "unknown trust"}</p>
      </div>
    );
  }

  return (
    <div className="grid max-h-[min(80vh,42rem)] min-h-0 w-full max-w-xl grid-rows-[auto_auto_minmax(0,1fr)_auto] overflow-hidden rounded-2xl border border-zinc-700 bg-zinc-950 text-zinc-100 shadow-2xl" data-entity-picker-id={picker.id}>
      <div className="flex items-start justify-between gap-3 border-b border-zinc-800 px-4 py-3">
        <div className="min-w-0"><h2 id={`entity-picker-title-${picker.id}`} className="truncate text-base font-semibold">{picker.label}</h2>{picker.description && <p className="mt-0.5 text-xs text-zinc-400">{picker.description}</p>}</div>
        {onClose && <button type="button" aria-label={`Close ${picker.label}`} className="rounded p-1.5 hover:bg-zinc-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400" onClick={onClose}><X size={16} /></button>}
      </div>
      <label className="relative m-3 mb-2 block">
        <Search size={15} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-zinc-500" aria-hidden="true" />
        <input
          ref={inputRef}
          type="search"
          role="combobox"
          className="h-10 w-full rounded-lg border border-zinc-700 bg-zinc-900 pl-9 pr-3 text-sm outline-none focus:border-cyan-500"
          aria-label={`Search ${picker.label}`}
          aria-controls={`entity-picker-list-${picker.id}`}
          aria-expanded="true"
          aria-activedescendant={visible[activeIndex] ? `entity-picker-option-${picker.id}-${visible[activeIndex].id}` : undefined}
          placeholder={picker.placeholder}
          value={query}
          readOnly={!picker.searchable}
          aria-readonly={!picker.searchable}
          onChange={(event) => { setQuery(event.target.value); setActiveIndex(0); }}
          onKeyDown={handleInputKeyDown}
        />
      </label>
      <div id={`entity-picker-list-${picker.id}`} role="listbox" aria-label={picker.label} aria-multiselectable={picker.selectionMode === "multi"} className="min-h-24 overflow-y-auto px-2 pb-2">
        {groups.map((group) => <div key={group.label} role="group" aria-label={group.label} className="py-1"><p className="sticky top-0 bg-zinc-950/95 px-2 py-1 text-[10px] font-semibold uppercase tracking-wide text-zinc-500">{group.label}</p>{group.items.map((item) => {
          const index = visible.findIndex((candidate) => candidate.id === item.id);
          const selected = selection.has(item.id);
          return <button
            id={`entity-picker-option-${picker.id}-${item.id}`}
            key={item.id}
            type="button"
            role="option"
            aria-selected={selected}
            aria-disabled={item.disabled}
            disabled={item.disabled || pending}
            title={item.disabledReason}
            className={`flex w-full items-start gap-2 rounded-lg px-2 py-2 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400 ${index === activeIndex ? "bg-zinc-800" : "hover:bg-zinc-900"} disabled:cursor-not-allowed disabled:opacity-45`}
            onMouseMove={() => setActiveIndex(index)}
            onClick={() => choose(item)}
          >
            <span className="mt-0.5 flex h-5 w-5 flex-none items-center justify-center rounded border border-zinc-700">{item.create ? <Plus size={13} /> : selected ? <Check size={13} /> : item.favorite ? <Star size={12} /> : null}</span>
            <span className="min-w-0 flex-1"><span className="block truncate text-sm font-medium">{item.label}</span>{item.description && <span className="mt-0.5 block line-clamp-2 text-xs text-zinc-400">{item.description}</span>}{item.disabledReason && <span className="mt-0.5 block text-[10px] text-amber-300">{item.disabledReason}</span>}</span>
            {item.badges.length > 0 && <span className="flex max-w-32 flex-wrap justify-end gap-1">{item.badges.map((badge) => <span key={badge} className="rounded-full bg-zinc-800 px-1.5 py-0.5 text-[9px] text-zinc-400">{badge}</span>)}</span>}
          </button>;
        })}</div>)}
        {!loading && visible.length === 0 && <p role="status" className="px-3 py-8 text-center text-sm text-zinc-500">No matching items.</p>}
        {loading && <p role="status" className="flex items-center justify-center gap-2 px-3 py-5 text-sm text-zinc-400"><Loader2 size={15} className="animate-spin" />Loading items…</p>}
        {nextCursor && <button type="button" className="mx-auto flex items-center gap-1 rounded px-3 py-2 text-xs text-cyan-300 hover:bg-zinc-900" disabled={loading} onClick={() => void loadMore()}>Load more <ChevronDown size={13} /></button>}
      </div>
      <div className="flex min-h-12 items-center justify-between gap-2 border-t border-zinc-800 px-3 py-2">
        <div aria-live="polite" className="min-w-0 flex-1 text-xs">{error ? <p role="alert" className="truncate text-rose-300" title={error}>{error}</p> : <p className="text-zinc-500">{selection.size} selected</p>}</div>
        {picker.selectionMode === "multi" && <button type="button" className="rounded-lg bg-cyan-600 px-3 py-2 text-xs font-semibold text-white hover:bg-cyan-500 disabled:opacity-50" disabled={pending} onClick={() => void commit([...selection])}>{pending && <Loader2 size={13} className="mr-1 inline animate-spin" />}Apply</button>}
      </div>
    </div>
  );
}

export function EntityPickerHost(props: EntityPickerHostProps) {
  if (props.open === false) return null;
  if (props.picker.presentation === "inline" || props.picker.presentation === "settings" || props.picker.presentation === "status_surface") {
    return <PickerBody {...props} />;
  }
  return (
    <div
      className="rumi-layer-modal-backdrop fixed inset-0 grid place-items-center bg-black/70 p-3"
      role="dialog"
      aria-modal="true"
      aria-labelledby={`entity-picker-title-${props.picker.id}`}
      onKeyDown={(event) => {
        if (event.key === "Escape") {
          event.preventDefault();
          props.onClose?.();
          return;
        }
        if (event.key !== "Tab") return;
        const focusable = [...event.currentTarget.querySelectorAll<HTMLElement>(
          'button:not([disabled]):not([tabindex="-1"]), input:not([disabled]), [href], [tabindex]:not([tabindex="-1"])',
        )].filter((item) => item.offsetParent !== null);
        if (focusable.length === 0) return;
        const first = focusable[0]!;
        const last = focusable[focusable.length - 1]!;
        if (event.shiftKey && document.activeElement === first) {
          event.preventDefault();
          last.focus();
        } else if (!event.shiftKey && document.activeElement === last) {
          event.preventDefault();
          first.focus();
        }
      }}
    >
      <button type="button" tabIndex={-1} aria-hidden="true" className="absolute inset-0 cursor-default" onClick={props.onClose} />
      <div className="rumi-layer-modal relative flex w-full justify-center"><PickerBody {...props} /></div>
    </div>
  );
}
