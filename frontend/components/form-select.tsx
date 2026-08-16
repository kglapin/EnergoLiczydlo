"use client"

import * as React from "react"
import { Controller, Control, FieldPath, FieldValues } from "react-hook-form"

import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { FormField } from "@/components/form-field"
import { cn } from "@/lib/utils"

interface Option {
  value: string
  label: string
}

interface FormSelectProps<T extends FieldValues> {
  name: FieldPath<T>
  control: Control<T>
  label: string
  tooltip?: string
  options: Option[]
  placeholder?: string
  className?: string
  onChange?: (value: string) => void
}

export function FormSelect<T extends FieldValues>({
  name,
  control,
  label,
  tooltip,
  options,
  placeholder = "Wybierz...",
  className,
  onChange,
}: FormSelectProps<T>) {
  return (
    <Controller
      name={name}
      control={control}
      render={({ field, fieldState }) => (
        <FormField label={label} tooltip={tooltip} error={fieldState.error?.message}>
          <Select
            name={field.name}
            value={field.value}
            onValueChange={(value) => {
              field.onChange(value)
              onChange?.(value)
            }}
          >
            <SelectTrigger
              className={cn(className, fieldState.invalid && "border-destructive ring-1 ring-destructive")}
              aria-invalid={fieldState.invalid}
              data-field-path={field.name}
            >
              <SelectValue placeholder={placeholder} />
            </SelectTrigger>
            <SelectContent>
              {options.map((opt) => (
                <SelectItem key={opt.value} value={opt.value}>
                  {opt.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </FormField>
      )}
    />
  )
}
