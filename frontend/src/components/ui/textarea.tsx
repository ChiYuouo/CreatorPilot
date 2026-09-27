import * as React from "react";

import { cn } from "@/lib/utils";

export function Textarea({ className, ...props }: React.ComponentProps<"textarea">) {
  return <textarea data-slot="textarea" className={cn("flex min-h-20 w-full rounded-md border border-input bg-card px-3 py-2 text-sm shadow-sm outline-none disabled:cursor-not-allowed disabled:opacity-50", className)} {...props} />;
}
