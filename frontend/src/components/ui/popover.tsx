import type { ComponentProps } from "react";
import * as PopoverPrimitive from "@radix-ui/react-popover";

import { cn } from "@/lib/utils";

export const Popover = PopoverPrimitive.Root;
export const PopoverTrigger = PopoverPrimitive.Trigger;

export function PopoverContent({ className, align = "start", sideOffset = 6, ...props }: ComponentProps<typeof PopoverPrimitive.Content>) {
  return <PopoverPrimitive.Portal>
    <PopoverPrimitive.Content
      data-slot="popover-content"
      align={align}
      sideOffset={sideOffset}
      collisionPadding={8}
      className={cn("z-[60] w-auto rounded-lg border border-border bg-popover p-2 text-popover-foreground shadow-lg outline-none", className)}
      {...props}
    />
  </PopoverPrimitive.Portal>;
}
