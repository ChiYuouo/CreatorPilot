import type { ReactNode } from "react";
import * as DialogPrimitive from "@radix-ui/react-dialog";
import { X } from "lucide-react";

export function Dialog({ open, onOpenChange, title, description, children, className = "" }: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description?: string;
  children: ReactNode;
  className?: string;
}) {
  return <DialogPrimitive.Root open={open} onOpenChange={onOpenChange}>
    <DialogPrimitive.Portal>
      <DialogPrimitive.Overlay className="fixed inset-0 z-50 bg-black/40" />
      <DialogPrimitive.Content className={`cp-dialog fixed left-1/2 top-1/2 z-50 flex max-h-[min(90vh,900px)] w-[min(94vw,760px)] -translate-x-1/2 -translate-y-1/2 flex-col overflow-hidden rounded-lg border border-border bg-card shadow-xl ${className}`}>
        <div className="flex items-start justify-between gap-4 border-b border-border px-6 py-5">
          <div>
            <DialogPrimitive.Title className="text-lg font-semibold text-foreground">{title}</DialogPrimitive.Title>
            {description && <DialogPrimitive.Description className="mt-1 text-sm text-muted-foreground">{description}</DialogPrimitive.Description>}
          </div>
          <DialogPrimitive.Close className="rounded-md p-2 text-muted-foreground hover:bg-accent" aria-label="关闭弹窗"><X className="size-5" /></DialogPrimitive.Close>
        </div>
        <div className="overflow-y-auto px-6 py-5">{children}</div>
      </DialogPrimitive.Content>
    </DialogPrimitive.Portal>
  </DialogPrimitive.Root>;
}
