import * as React from "react"
import { cn } from "@/src/lib/utils"
import { viewerLayers } from "@/src/lib/layers"

const Popover = ({ children }: { children: React.ReactNode }) => {
  const [isOpen, setIsOpen] = React.useState(false)
  const triggerRef = React.useRef<HTMLButtonElement>(null)
  const contentRef = React.useRef<HTMLDivElement>(null)
  const close = React.useCallback(() => {
    setIsOpen(false)
    window.setTimeout(() => triggerRef.current?.focus(), 0)
  }, [])

  React.useEffect(() => {
    if (!isOpen) return

    const timer = window.setTimeout(() => {
      const firstFocusable = contentRef.current?.querySelector<HTMLElement>(
        'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
      )
      firstFocusable?.focus()
    }, 0)

    const handlePointerDown = (event: PointerEvent) => {
      const target = event.target as Node
      if (
        contentRef.current?.contains(target) ||
        triggerRef.current?.contains(target)
      ) {
        return
      }
      close()
    }

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault()
        close()
      }
    }

    document.addEventListener("pointerdown", handlePointerDown)
    window.addEventListener("keydown", handleKeyDown)
    return () => {
      window.clearTimeout(timer)
      document.removeEventListener("pointerdown", handlePointerDown)
      window.removeEventListener("keydown", handleKeyDown)
    }
  }, [isOpen, close])

  return (
    <div className="relative inline-block">
      {React.Children.map(children, (child) => {
        if (React.isValidElement(child)) {
          if (child.type === PopoverTrigger) {
            return React.cloneElement(child as React.ReactElement<any>, {
              ref: triggerRef,
              onClick: () => setIsOpen((open) => !open),
              isOpen
            })
          }
          if (child.type === PopoverContent) {
            return isOpen ? React.cloneElement(child as React.ReactElement<any>, {
              ref: contentRef,
              onClose: close
            }) : null
          }
        }
        return child
      })}
    </div>
  )
}

type PopoverTriggerProps = React.ButtonHTMLAttributes<HTMLButtonElement> & {
  isOpen?: boolean;
};

const PopoverTrigger = React.forwardRef<HTMLButtonElement, PopoverTriggerProps>(
  ({ children, onClick, className, isOpen, type = "button", ...props }, ref) => (
  <button
    ref={ref}
    type={type}
    onClick={onClick}
    aria-haspopup="menu"
    aria-expanded={Boolean(isOpen)}
    className={cn("cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--ring-color)]", className)}
    {...props}
  >
    {children}
  </button>
))
PopoverTrigger.displayName = "PopoverTrigger"

type PopoverContentProps = React.HTMLAttributes<HTMLDivElement> & {
  align?: "left" | "right";
  onClose?: () => void;
};

const PopoverContent = React.forwardRef<HTMLDivElement, PopoverContentProps>(
  ({ children, className, align = "right", onClose, onClick, ...props }, ref) => {
  return (
    <div
      ref={ref}
      role="menu"
      tabIndex={-1}
      onClick={(event) => {
        onClick?.(event)
        if ((event.target as HTMLElement).closest('a,button')) {
          onClose?.()
        }
      }}
      className={cn(
        "absolute mt-2 min-w-[12rem] overflow-hidden rounded-xl border border-border bg-bg-card p-1 text-text-main shadow-xl animate-in fade-in zoom-in-95 duration-200 outline-none",
        viewerLayers.popover,
        align === "right" ? "right-0" : "left-0",
        className
      )}
      {...props}
    >
      {children}
    </div>
  )
})
PopoverContent.displayName = "PopoverContent"

export { Popover, PopoverTrigger, PopoverContent }
