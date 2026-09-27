import * as SelectPrimitive from "@radix-ui/react-select";
import { Check, ChevronDown } from "lucide-react";

import { cn } from "@/lib/utils";

type SelectOption = { value: string; label: string };

/** 项目统一的 shadcn 风格选择器，提供一致的菜单和键盘交互。 */
export function SelectField({
  id,
  value,
  onValueChange,
  options,
  placeholder = "请选择",
  className,
  disabled,
  required,
}: {
  id: string;
  value: string;
  onValueChange: (value: string) => void;
  options: SelectOption[];
  placeholder?: string;
  className?: string;
  disabled?: boolean;
  required?: boolean;
}) {
  return (
    <SelectPrimitive.Root value={value} onValueChange={onValueChange} disabled={disabled || options.length === 0} required={required}>
      <SelectPrimitive.Trigger
        id={id}
        data-slot="select-trigger"
        className={cn("flex h-9 w-full items-center justify-between gap-2 rounded-md border border-input bg-card px-3 text-left text-sm shadow-sm outline-none disabled:cursor-not-allowed disabled:opacity-50", className)}
      >
        <SelectPrimitive.Value placeholder={placeholder} className="min-w-0 truncate" />
        <SelectPrimitive.Icon asChild><ChevronDown className="size-4 shrink-0 opacity-65" /></SelectPrimitive.Icon>
      </SelectPrimitive.Trigger>
      <SelectPrimitive.Portal>
        <SelectPrimitive.Content data-slot="select-content" position="popper" sideOffset={5} collisionPadding={8} className="cp-select-content z-50 max-h-72 w-[var(--radix-select-trigger-width)] overflow-hidden rounded-lg border shadow-xl">
          <SelectPrimitive.Viewport className="max-h-64 w-full overflow-y-auto p-1">
            {options.map((option) => (
              <SelectPrimitive.Item key={option.value} value={option.value} className="cp-select-item relative flex w-full min-w-0 cursor-pointer select-none items-center overflow-hidden rounded-md py-2 pl-3 pr-9 text-sm outline-none">
                <SelectPrimitive.ItemText className="block max-w-full truncate">{option.label}</SelectPrimitive.ItemText>
                <SelectPrimitive.ItemIndicator className="absolute right-3"><Check className="size-4" /></SelectPrimitive.ItemIndicator>
              </SelectPrimitive.Item>
            ))}
          </SelectPrimitive.Viewport>
        </SelectPrimitive.Content>
      </SelectPrimitive.Portal>
    </SelectPrimitive.Root>
  );
}
