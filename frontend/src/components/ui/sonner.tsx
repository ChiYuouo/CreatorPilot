import type { ComponentProps } from "react";
import { Toaster as Sonner } from "sonner";

type ToasterProps = ComponentProps<typeof Sonner>;

/**
 * 全局 toast 容器。配色跟随 index.css 的主题变量（对齐 antd 色板）。
 */
function Toaster({ ...props }: ToasterProps) {
  return (
    <Sonner
      theme="light"
      className="toaster group"
      toastOptions={{
        style: {
          background: "var(--card)",
          color: "var(--card-foreground)",
          border: "1px solid var(--border)",
        },
      }}
      {...props}
    />
  );
}

export { Toaster };
