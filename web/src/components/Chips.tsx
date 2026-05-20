import { splitMulti } from "../lib/loadPublications";

interface Props {
  value: string | undefined;
  max?: number;
  delimiter?: string;
}

export function Chips({ value, max = 3, delimiter }: Props) {
  const items = splitMulti(value, delimiter).slice(0, max);
  if (items.length === 0) return null;
  return (
    <div className="flex flex-wrap gap-1">
      {items.map((d) => (
        <span
          key={d}
          className="px-1.5 py-0.5 text-[10px] rounded bg-slate-100 text-slate-700"
        >
          {d}
        </span>
      ))}
    </div>
  );
}
