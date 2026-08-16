"use client"

import * as React from "react"
import { HelpCircle } from "lucide-react"

import { Label } from "@/components/ui/label"
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip"
import { cn } from "@/lib/utils"

interface FormFieldProps {
  label: string
  tooltip?: string
  children: React.ReactNode
  className?: string
  error?: string
}

export function FormField({ label, tooltip, children, className, error }: FormFieldProps) {
  return (
    <div className={cn("space-y-1.5", className)}>
      <div className="flex items-center gap-1.5">
        <Label className={cn("text-sm font-medium", error && "text-destructive")}>{label}</Label>
        {tooltip ? (
          <TooltipProvider delayDuration={100}>
            <Tooltip>
              <TooltipTrigger asChild>
                <HelpCircle className="h-4 w-4 text-slate-400 cursor-help hover:text-slate-600" />
              </TooltipTrigger>
              <TooltipContent
                side="top"
                align="start"
                className="max-w-xs bg-slate-800 text-slate-50"
              >
                <p>{tooltip}</p>
              </TooltipContent>
            </Tooltip>
          </TooltipProvider>
        ) : null}
      </div>
      {children}
      {error ? <p className="text-sm text-destructive">{error}</p> : null}
    </div>
  )
}
