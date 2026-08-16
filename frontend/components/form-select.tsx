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
}

export function FormSelect<T extends FieldValues>({
  name,
  control,
  label,
  tooltip,
  options,
  placeholder = "Wybierz...",
  className,
}: FormSelectProps<T>) {
  return (
    <FormField label={label} tooltip={tooltip}>
      <Controller
        name={name}
        control={control}
        render={({ field }) => (
          <Select value={field.value} onValueChange={field.onChange}>
            <SelectTrigger className={className}>
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
        )}
      />
    </FormField>
  )
}
