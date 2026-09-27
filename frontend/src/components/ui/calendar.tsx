import type { ComponentProps } from "react";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { DayPicker } from "react-day-picker";
import { zhCN } from "react-day-picker/locale";

import { cn } from "@/lib/utils";

export function Calendar({ className, classNames, ...props }: ComponentProps<typeof DayPicker>) {
  return <DayPicker
    locale={zhCN}
    showOutsideDays
    className={cn("p-3", className)}
    classNames={{
      months: "relative",
      month: "space-y-4",
      month_caption: "flex h-9 items-center justify-center font-semibold text-sm",
      caption_label: "text-sm font-semibold",
      nav: "absolute inset-x-0 top-0 flex items-center justify-between",
      button_previous: "flex size-9 items-center justify-center rounded-md hover:bg-accent",
      button_next: "flex size-9 items-center justify-center rounded-md hover:bg-accent",
      month_grid: "w-full border-collapse",
      weekdays: "grid grid-cols-7",
      weekday: "w-9 text-center text-xs font-normal text-muted-foreground",
      week: "mt-1 grid grid-cols-7",
      day: "size-9 p-0 text-center",
      day_button: "size-9 rounded-md text-sm hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
      selected: "[&_button]:bg-primary [&_button]:font-semibold [&_button]:text-primary-foreground",
      today: "[&_button]:border [&_button]:border-ring",
      outside: "text-muted-foreground opacity-50",
      disabled: "opacity-40",
      ...classNames,
    }}
    components={{
      Chevron: ({ orientation, ...chevronProps }) => orientation === "left"
        ? <ChevronLeft {...chevronProps} className="size-4" />
        : <ChevronRight {...chevronProps} className="size-4" />,
    }}
    {...props}
  />;
}
