import * as CheckboxPrimitive from "@radix-ui/react-checkbox";
import { Check } from "lucide-react";

import { cn } from "@/lib/utils";

export function Checkbox({ className, ...props }: React.ComponentProps<typeof CheckboxPrimitive.Root>) {
  return (
    <CheckboxPrimitive.Root data-slot="checkbox" className={cn("inline-flex size-4 shrink-0 items-center justify-center rounded border border-input outline-none disabled:cursor-not-allowed disabled:opacity-50", className)} {...props}>
      <CheckboxPrimitive.Indicator><Check className="size-3" /></CheckboxPrimitive.Indicator>
    </CheckboxPrimitive.Root>
  );
}
