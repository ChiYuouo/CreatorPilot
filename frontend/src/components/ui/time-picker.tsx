import { Label } from "@/components/ui/label";
import { SelectField } from "@/components/ui/select";

const hours = Array.from({ length: 24 }, (_, hour) => ({ value: String(hour), label: String(hour).padStart(2, "0") }));
const minutes = Array.from({ length: 60 }, (_, minute) => ({ value: String(minute), label: String(minute).padStart(2, "0") }));

export function TimePicker({ id, value, onValueChange }: {
  id: string;
  value: string;
  onValueChange: (value: string) => void;
}) {
  const [hour = "0", minute = "0"] = value.split(":");
  const update = (nextHour: string, nextMinute: string) => onValueChange(
    `${nextHour.padStart(2, "0")}:${nextMinute.padStart(2, "0")}`,
  );

  return <div className="grid grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)] items-center gap-2">
    <SelectField id={`${id}-hour`} value={String(Number(hour))} onValueChange={(next) => update(next, minute)} options={hours} />
    <span className="text-lg font-medium text-stone-500">:</span>
    <Label htmlFor={`${id}-minute`} className="sr-only">分钟</Label>
    <SelectField id={`${id}-minute`} value={String(Number(minute))} onValueChange={(next) => update(hour, next)} options={minutes} />
  </div>;
}
