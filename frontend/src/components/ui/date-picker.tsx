import { useState } from "react";
import { format } from "date-fns";
import { CalendarDays } from "lucide-react";

import { buttonVariants } from "@/components/ui/button";
import { Calendar } from "@/components/ui/calendar";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { cn } from "@/lib/utils";

function localDate(value: string): Date | undefined {
  const [year, month, day] = value.split("-").map(Number);
  if (!year || !month || !day) return undefined;
  const date = new Date(year, month - 1, day);
  return date.getFullYear() === year && date.getMonth() === month - 1 && date.getDate() === day ? date : undefined;
}

export function DatePicker({ id, value, onValueChange, className }: {
  id: string;
  value: string;
  onValueChange: (value: string) => void;
  className?: string;
}) {
  const [open, setOpen] = useState(false);
  const selected = localDate(value);

  return <Popover open={open} onOpenChange={setOpen}>
    <PopoverTrigger id={id} type="button" className={cn(buttonVariants({ variant: "outline" }), "min-h-[42px] w-full justify-between rounded-md border-border bg-background px-3 text-left font-normal", className)}>
      <span>{selected ? format(selected, "yyyy/MM/dd") : "选择日期"}</span><CalendarDays className="size-4 text-muted-foreground" />
    </PopoverTrigger>
    <PopoverContent>
      <Calendar mode="single" selected={selected} onSelect={(date) => {
        if (!date) return;
        onValueChange(format(date, "yyyy-MM-dd"));
        setOpen(false);
      }} />
    </PopoverContent>
  </Popover>;
}
