import * as React from "react"
import { cn } from "@/src/lib/utils"

const Popover = ({ children }: { children: React.ReactNode }) => {
  const [isOpen, setIsOpen] = React.useState(false)
  return (
    <div className="relative inline-block">
      {React.Children.map(children, (child) => {
        if (React.isValidElement(child)) {
          if (child.type === PopoverTrigger) {
            return React.cloneElement(child as React.ReactElement<any>, { 
              onClick: () => setIsOpen(!isOpen),
              isOpen 
            })
          }
          if (child.type === PopoverContent) {
            return isOpen ? React.cloneElement(child as React.ReactElement<any>, { 
              onClose: () => setIsOpen(false) 
            }) : null
          }
        }
        return child
      })}
    </div>
  )
}

const PopoverTrigger = ({ children, onClick, className }: any) => (
  <div onClick={onClick} className={cn("cursor-pointer", className)}>
    {children}
  </div>
)

const PopoverContent = ({ children, className, align = "right", onClose }: any) => {
  const ref = React.useRef<HTMLDivElement>(null)
  
  React.useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (ref.current && !ref.current.contains(event.target as Node)) {
        onClose()
      }
    }
    document.addEventListener("mousedown", handleClickOutside)
    return () => document.removeEventListener("mousedown", handleClickOutside)
  }, [onClose])

  return (
    <div
      ref={ref}
      className={cn(
        "absolute z-50 mt-2 min-w-[12rem] overflow-hidden rounded-xl border border-border bg-bg-card p-1 text-text-main shadow-xl animate-in fade-in zoom-in-95 duration-200",
        align === "right" ? "right-0" : "left-0",
        className
      )}
    >
      {children}
    </div>
  )
}

export { Popover, PopoverTrigger, PopoverContent }
