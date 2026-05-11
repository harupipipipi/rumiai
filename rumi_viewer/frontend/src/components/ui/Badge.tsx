import * as React from "react"
import { cn } from "@/src/lib/utils"

export interface BadgeProps extends React.HTMLAttributes<HTMLDivElement> {
  variant?: "default" | "secondary" | "destructive" | "outline" | "success" | "warning"
}

function Badge({ className, variant = "default", ...props }: BadgeProps) {
  return (
    <div
      className={cn(
        "inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium transition-colors",
        {
          "bg-accent/10 text-accent": variant === "default",
          "bg-bg-hover text-text-muted": variant === "secondary",
          "bg-destructive/10 text-destructive": variant === "destructive",
          "border border-border text-text-muted": variant === "outline",
          "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400": variant === "success",
          "bg-amber-500/10 text-amber-600 dark:text-amber-400": variant === "warning",
        },
        className
      )}
      {...props}
    />
  )
}

export { Badge }
