import * as React from "react"
import { createPortal } from "react-dom"
import { cn } from "@/src/lib/utils"
import { viewerLayers } from "@/src/lib/layers"

type PopoverMode = "popover" | "menu" | "dialog"
type PopoverAlign = "left" | "center" | "right"
type InitialFocus = "first" | "content" | "none"

type PopoverPosition = {
  left: number;
  top: number;
  placement: "top" | "bottom";
};

type PopoverViewport = {
  height: number;
  left?: number;
  top?: number;
  width: number;
};

type Rect = Pick<DOMRect, "bottom" | "height" | "left" | "right" | "top" | "width">;

const VIEWPORT_PADDING = 8
const POPOVER_GAP = 8
const MENU_ITEM_SELECTOR = [
  "[role='menuitem']",
  "[role='menuitemcheckbox']",
  "[role='menuitemradio']",
].join(",")

/** Return a viewport-safe anchored position after measuring both elements. */
function computePopoverPosition(
  trigger: Rect,
  content: Pick<Rect, "height" | "width">,
  viewport: PopoverViewport,
  align: PopoverAlign,
): PopoverPosition {
  const viewportLeft = viewport.left ?? 0
  const viewportTop = viewport.top ?? 0
  const viewportRight = viewportLeft + viewport.width
  const viewportBottom = viewportTop + viewport.height
  const availableBelow = viewportBottom - trigger.bottom - VIEWPORT_PADDING
  const availableAbove = trigger.top - viewportTop - VIEWPORT_PADDING
  const placeAbove = content.height + POPOVER_GAP > availableBelow
    && availableAbove > availableBelow
  const desiredTop = placeAbove
    ? trigger.top - POPOVER_GAP - content.height
    : trigger.bottom + POPOVER_GAP
  const minTop = viewportTop + VIEWPORT_PADDING
  const maxTop = Math.max(minTop, viewportBottom - VIEWPORT_PADDING - content.height)
  const top = Math.min(Math.max(desiredTop, minTop), maxTop)

  const desiredLeft = align === "right"
    ? trigger.right - content.width
    : align === "center"
      ? trigger.left + (trigger.width - content.width) / 2
      : trigger.left
  const minLeft = viewportLeft + VIEWPORT_PADDING
  const maxLeft = Math.max(minLeft, viewportRight - VIEWPORT_PADDING - content.width)
  const left = Math.min(Math.max(desiredLeft, minLeft), maxLeft)

  return { left, top, placement: placeAbove ? "top" : "bottom" }
}

type RestoreCandidates = {
  after: HTMLElement | null;
  before: HTMLElement | null;
};

type PopoverContextValue = {
  close: (restoreFocus?: boolean) => void;
  contentId: string;
  contentRef: React.RefObject<HTMLDivElement | null>;
  isOpen: boolean;
  mode: PopoverMode;
  open: () => void;
  parentContentId: string | null;
  rootRef: React.RefObject<HTMLDivElement | null>;
  setIsOpen: React.Dispatch<React.SetStateAction<boolean>>;
  triggerId: string;
  triggerRef: React.RefObject<HTMLButtonElement | null>;
};

const PopoverContext = React.createContext<PopoverContextValue | null>(null)
const openLayers: string[] = []

function usePopoverContext(component: string): PopoverContextValue {
  const context = React.useContext(PopoverContext)
  if (!context) {
    throw new Error(`${component} must be rendered inside Popover`)
  }
  return context
}

function visibleFocusableElements(root: ParentNode): HTMLElement[] {
  const ownerDocument = root.nodeType === 9
    ? root as Document
    : (root as Node).ownerDocument
  if (!ownerDocument) return []
  const showElement = ownerDocument.defaultView?.NodeFilter.SHOW_ELEMENT ?? 1
  const walker = ownerDocument.createTreeWalker(root, showElement)
  const focusable: HTMLElement[] = []
  let current = walker.nextNode()
  while (current) {
    const element = current as HTMLElement
    const tagName = element.tagName
    const hasNativeFocus = (
      (tagName === "A" && element.hasAttribute("href"))
      || ["BUTTON", "INPUT", "SELECT", "TEXTAREA"].includes(tagName)
    ) && !element.hasAttribute("disabled")
    const tabIndex = element.getAttribute("tabindex")
    const hasExplicitFocus = tabIndex !== null && tabIndex !== "-1"
    if (
      (hasNativeFocus || hasExplicitFocus)
      && element.getAttribute("aria-hidden") !== "true"
      && !element.hasAttribute("hidden")
    ) {
      focusable.push(element)
    }
    current = walker.nextNode()
  }
  return focusable
}

function captureRestoreCandidates(trigger: HTMLElement): RestoreCandidates {
  const focusables = visibleFocusableElements(document)
  const index = focusables.indexOf(trigger)
  return {
    before: index > 0 ? focusables[index - 1] : null,
    after: index >= 0 ? focusables[index + 1] ?? null : null,
  }
}

function isInNestedPopover(target: Node, ancestorContentId: string): boolean {
  if (target.nodeType !== 1) return false
  let content = (target as HTMLElement).closest<HTMLElement>("[data-popover-parent-content]")
  while (content) {
    const parentId = content.dataset.popoverParentContent
    if (parentId === ancestorContentId) return true
    content = parentId ? document.getElementById(parentId) : null
  }
  return false
}

type PopoverProps = {
  children: React.ReactNode;
  className?: string;
  mode?: PopoverMode;
  onOpenChange?: (open: boolean) => void;
};

/**
 * Anchored disclosure root with explicit generic, menu, and non-modal dialog modes.
 */
const Popover = ({
  children,
  className,
  mode = "popover",
  onOpenChange,
}: PopoverProps) => {
  const parentContext = React.useContext(PopoverContext)
  const [isOpen, setIsOpenState] = React.useState(false)
  const contentId = React.useId()
  const triggerId = React.useId()
  const triggerRef = React.useRef<HTMLButtonElement>(null)
  const contentRef = React.useRef<HTMLDivElement>(null)
  const rootRef = React.useRef<HTMLDivElement>(null)
  const restoreCandidatesRef = React.useRef<RestoreCandidates>({ before: null, after: null })

  const setIsOpen = React.useCallback<React.Dispatch<React.SetStateAction<boolean>>>((next) => {
    setIsOpenState((current) => {
      const resolved = typeof next === "function" ? next(current) : next
      if (resolved !== current) onOpenChange?.(resolved)
      return resolved
    })
  }, [onOpenChange])

  const restoreFocus = React.useCallback(() => {
    const trigger = triggerRef.current
    if (trigger?.isConnected) {
      trigger.focus()
      return
    }
    const { after, before } = restoreCandidatesRef.current
    const fallback = after?.isConnected ? after : before?.isConnected ? before : null
    fallback?.focus()
  }, [])

  const close = React.useCallback((shouldRestoreFocus = true) => {
    setIsOpen(false)
    if (shouldRestoreFocus) {
      window.setTimeout(restoreFocus, 0)
    }
  }, [restoreFocus, setIsOpen])

  const open = React.useCallback(() => {
    const trigger = triggerRef.current
    if (trigger) restoreCandidatesRef.current = captureRestoreCandidates(trigger)
    setIsOpen(true)
  }, [setIsOpen])

  const context = React.useMemo<PopoverContextValue>(() => ({
    close,
    contentId,
    contentRef,
    isOpen,
    mode,
    open,
    parentContentId: parentContext?.contentId ?? null,
    rootRef,
    setIsOpen,
    triggerId,
    triggerRef,
  }), [close, contentId, isOpen, mode, open, parentContext?.contentId, setIsOpen, triggerId])

  return (
    <PopoverContext.Provider value={context}>
      <div ref={rootRef} className={cn("relative inline-block", className)}>
        {children}
      </div>
    </PopoverContext.Provider>
  )
}

type PopoverTriggerProps = React.ButtonHTMLAttributes<HTMLButtonElement>

const PopoverTrigger = React.forwardRef<HTMLButtonElement, PopoverTriggerProps>(
  ({ children, className, onClick, onKeyDown, type = "button", ...props }, forwardedRef) => {
    const context = usePopoverContext("PopoverTrigger")
    const setRefs = React.useCallback((node: HTMLButtonElement | null) => {
      context.triggerRef.current = node
      if (typeof forwardedRef === "function") forwardedRef(node)
      else if (forwardedRef) forwardedRef.current = node
    }, [context.triggerRef, forwardedRef])

    const hasPopup = context.mode === "menu"
      ? "menu"
      : context.mode === "dialog"
        ? "dialog"
        : undefined

    return (
      <button
        {...props}
        ref={setRefs}
        id={context.triggerId}
        type={type}
        aria-haspopup={hasPopup}
        aria-controls={context.contentId}
        aria-expanded={context.isOpen}
        onClick={(event) => {
          onClick?.(event)
          if (event.defaultPrevented) return
          if (context.isOpen) context.close()
          else context.open()
        }}
        onKeyDown={(event) => {
          onKeyDown?.(event)
          if (event.defaultPrevented || context.mode !== "menu" || context.isOpen) return
          if (event.key === "ArrowDown" || event.key === "ArrowUp") {
            event.preventDefault()
            context.open()
            const focusLast = event.key === "ArrowUp"
            window.setTimeout(() => {
              const items = menuItems(context.contentRef.current)
              items[focusLast ? items.length - 1 : 0]?.focus()
            }, 0)
          }
        }}
        className={cn(
          "cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--ring-color)]",
          className,
        )}
      >
        {children}
      </button>
    )
  },
)
PopoverTrigger.displayName = "PopoverTrigger"

function menuItems(content: HTMLElement | null): HTMLElement[] {
  if (!content) return []
  return Array.from(content.querySelectorAll<HTMLElement>(MENU_ITEM_SELECTOR))
}

function focusMenuItem(items: HTMLElement[], current: Element | null, offset: number): void {
  if (items.length === 0) return
  const currentIndex = items.indexOf(current as HTMLElement)
  const nextIndex = currentIndex < 0
    ? offset > 0 ? 0 : items.length - 1
    : (currentIndex + offset + items.length) % items.length
  items[nextIndex]?.focus()
}

type PopoverContentProps = Omit<React.HTMLAttributes<HTMLDivElement>, "role"> & {
  align?: PopoverAlign;
  initialFocus?: InitialFocus;
  role?: React.AriaRole;
};

const PopoverContent = React.forwardRef<HTMLDivElement, PopoverContentProps>(
  ({
    "aria-label": ariaLabel,
    "aria-labelledby": ariaLabelledBy,
    align = "right",
    children,
    className,
    initialFocus,
    onBlur,
    onClick,
    onKeyDown,
    role,
    style,
    ...props
  }, forwardedRef) => {
    const context = usePopoverContext("PopoverContent")
    const localRef = React.useRef<HTMLDivElement | null>(null)
    const [position, setPosition] = React.useState<PopoverPosition | null>(null)
    const [viewportSize, setViewportSize] = React.useState({ height: 0, width: 0 })
    const layerId = React.useId()

    const setRefs = React.useCallback((node: HTMLDivElement | null) => {
      localRef.current = node
      context.contentRef.current = node
      if (typeof forwardedRef === "function") forwardedRef(node)
      else if (forwardedRef) forwardedRef.current = node
    }, [context.contentRef, forwardedRef])

    const updatePosition = React.useCallback(() => {
      const trigger = context.triggerRef.current
      const content = localRef.current
      if (!trigger?.isConnected || !content) return
      const visualViewport = window.visualViewport
      const viewport = {
        height: visualViewport?.height ?? window.innerHeight,
        left: visualViewport?.offsetLeft ?? 0,
        top: visualViewport?.offsetTop ?? 0,
        width: visualViewport?.width ?? window.innerWidth,
      }
      setViewportSize((current) => (
        current.height === viewport.height && current.width === viewport.width
          ? current
          : { height: viewport.height, width: viewport.width }
      ))
      const nextPosition = computePopoverPosition(
        trigger.getBoundingClientRect(),
        content.getBoundingClientRect(),
        viewport,
        align,
      )
      setPosition((current) => (
        current?.left === nextPosition.left
        && current.top === nextPosition.top
        && current.placement === nextPosition.placement
          ? current
          : nextPosition
      ))
    }, [align, context.triggerRef])

    React.useLayoutEffect(() => {
      if (!context.isOpen) return
      updatePosition()
      const content = localRef.current
      const preferredFocus = initialFocus
        ?? (context.mode === "popover" ? "none" : "first")
      if (preferredFocus === "content") content?.focus()
      else if (preferredFocus === "first") {
        const target = context.mode === "menu"
          ? menuItems(content)[0]
          : visibleFocusableElements(content ?? document)[0]
        target?.focus()
      }
    }, [context.isOpen, context.mode, initialFocus, updatePosition])

    React.useEffect(() => {
      if (!context.isOpen) return
      openLayers.push(layerId)
      let frame = 0
      const schedulePosition = () => {
        if (typeof window.requestAnimationFrame !== "function") {
          updatePosition()
          return
        }
        window.cancelAnimationFrame(frame)
        frame = window.requestAnimationFrame(updatePosition)
      }
      const resizeObserver = typeof ResizeObserver === "undefined"
        ? null
        : new ResizeObserver(schedulePosition)
      if (context.triggerRef.current) resizeObserver?.observe(context.triggerRef.current)
      if (localRef.current) resizeObserver?.observe(localRef.current)
      const mutationObserver = typeof MutationObserver === "undefined"
        ? null
        : new MutationObserver(() => {
          if (!context.triggerRef.current?.isConnected) context.close()
        })
      mutationObserver?.observe(document.body, { childList: true, subtree: true })

      const handleKeyDown = (event: KeyboardEvent) => {
        if (event.key !== "Escape" || openLayers.at(-1) !== layerId) return
        event.preventDefault()
        event.stopImmediatePropagation()
        context.close()
      }
      const handlePointerDown = (event: PointerEvent) => {
        if (openLayers.at(-1) !== layerId) return
        const path = event.composedPath()
        if (
          (localRef.current && path.includes(localRef.current))
          || (context.triggerRef.current && path.includes(context.triggerRef.current))
        ) return
        context.close()
      }
      document.addEventListener("keydown", handleKeyDown)
      document.addEventListener("pointerdown", handlePointerDown)
      window.addEventListener("resize", schedulePosition)
      window.addEventListener("scroll", schedulePosition, true)
      window.visualViewport?.addEventListener("resize", schedulePosition)
      window.visualViewport?.addEventListener("scroll", schedulePosition)
      return () => {
        const index = openLayers.lastIndexOf(layerId)
        if (index >= 0) openLayers.splice(index, 1)
        if (typeof window.cancelAnimationFrame === "function") {
          window.cancelAnimationFrame(frame)
        }
        resizeObserver?.disconnect()
        mutationObserver?.disconnect()
        document.removeEventListener("keydown", handleKeyDown)
        document.removeEventListener("pointerdown", handlePointerDown)
        window.removeEventListener("resize", schedulePosition)
        window.removeEventListener("scroll", schedulePosition, true)
        window.visualViewport?.removeEventListener("resize", schedulePosition)
        window.visualViewport?.removeEventListener("scroll", schedulePosition)
      }
    }, [context, layerId, updatePosition])

    if (!context.isOpen) return null

    const resolvedRole = context.mode === "menu"
      ? "menu"
      : context.mode === "dialog"
        ? "dialog"
        : role
    const resolvedLabelledBy = ariaLabel || ariaLabelledBy
      ? ariaLabelledBy
      : context.triggerId

    return createPortal(
      <div
        {...props}
        ref={setRefs}
        id={context.contentId}
        role={resolvedRole}
        aria-label={ariaLabel}
        aria-labelledby={resolvedLabelledBy}
        tabIndex={-1}
        data-placement={position?.placement}
        data-popover-parent-content={context.parentContentId ?? undefined}
        onBlur={(event) => {
          onBlur?.(event)
          if (event.defaultPrevented || context.mode === "menu") return
          const next = event.relatedTarget as Node | null
          if (
            next
            && !event.currentTarget.contains(next)
            && !context.triggerRef.current?.contains(next)
            && !isInNestedPopover(next, context.contentId)
          ) {
            context.close(false)
          }
        }}
        onClick={(event) => {
          onClick?.(event)
          const closeTarget = (event.target as HTMLElement).closest("[data-popover-close]")
          if (closeTarget && event.currentTarget.contains(closeTarget)) context.close()
        }}
        onKeyDown={(event) => {
          onKeyDown?.(event)
          if (event.defaultPrevented || context.mode !== "menu") return
          const items = menuItems(event.currentTarget)
          if (event.key === "ArrowDown" || event.key === "ArrowUp") {
            event.preventDefault()
            focusMenuItem(items, document.activeElement, event.key === "ArrowDown" ? 1 : -1)
          } else if (event.key === "Home" || event.key === "End") {
            event.preventDefault()
            items[event.key === "Home" ? 0 : items.length - 1]?.focus()
          } else if (event.key === "Tab") {
            window.setTimeout(() => context.close(false), 0)
          } else if (
            event.key.length === 1
            && !event.altKey
            && !event.ctrlKey
            && !event.metaKey
          ) {
            const key = event.key.toLocaleLowerCase()
            const currentIndex = items.indexOf(document.activeElement as HTMLElement)
            const ordered = [...items.slice(currentIndex + 1), ...items.slice(0, currentIndex + 1)]
            const match = ordered.find((item) => item.textContent?.trim().toLocaleLowerCase().startsWith(key))
            if (match) {
              event.preventDefault()
              match.focus()
            }
          }
        }}
        style={{
          position: "fixed",
          left: position?.left ?? VIEWPORT_PADDING,
          top: position?.top ?? VIEWPORT_PADDING,
          maxHeight: viewportSize.height > 0
            ? Math.max(0, viewportSize.height - VIEWPORT_PADDING * 2)
            : `calc(100vh - ${VIEWPORT_PADDING * 2}px)`,
          maxWidth: viewportSize.width > 0
            ? Math.max(0, viewportSize.width - VIEWPORT_PADDING * 2)
            : `calc(100vw - ${VIEWPORT_PADDING * 2}px)`,
          minWidth: viewportSize.width > 0
            ? Math.min(192, Math.max(0, viewportSize.width - VIEWPORT_PADDING * 2))
            : undefined,
          visibility: position ? "visible" : "hidden",
          ...style,
        }}
        className={cn(
          "min-w-[12rem] overflow-auto rounded-xl border border-border bg-bg-card p-1 text-text-main shadow-xl animate-in fade-in zoom-in-95 duration-200 outline-none",
          viewerLayers.popover,
          className,
        )}
      >
        {children}
      </div>,
      document.body,
    )
  },
)
PopoverContent.displayName = "PopoverContent"

type PopoverMenuItemProps = React.ButtonHTMLAttributes<HTMLButtonElement>

/** Menu item with the role and tab-stop contract required by the menu mode. */
const PopoverMenuItem = React.forwardRef<HTMLButtonElement, PopoverMenuItemProps>(
  ({
    "aria-disabled": ariaDisabled,
    children,
    disabled,
    onClick,
    tabIndex = -1,
    type = "button",
    ...props
  }, ref) => {
    const context = usePopoverContext("PopoverMenuItem")
    const isDisabled = disabled || ariaDisabled === true || ariaDisabled === "true"
    return (
      <button
        {...props}
        ref={ref}
        type={type}
        role="menuitem"
        aria-disabled={isDisabled || undefined}
        tabIndex={tabIndex}
        onClick={(event) => {
          if (isDisabled) {
            event.preventDefault()
            return
          }
          onClick?.(event)
          if (!event.defaultPrevented) context.close()
        }}
      >
        {children}
      </button>
    )
  },
)
PopoverMenuItem.displayName = "PopoverMenuItem"

export {
  Popover,
  PopoverContent,
  PopoverMenuItem,
  PopoverTrigger,
  computePopoverPosition,
}
export type { PopoverAlign, PopoverMode, PopoverPosition }
