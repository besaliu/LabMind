import type { TooltipProps } from "recharts";
import { narrativeFor, CATEGORY_STYLES } from "../lib/categories";
import { snakeToTitleCase } from "../lib/format";
import type { EventCategory } from "../types/bundle";
import { fmtHMS } from "../lib/time";

interface RowField {
  key: string;
  name: string;
  unit?: string;
  precision?: number;
}

interface Props extends TooltipProps<number, string> {
  fields: RowField[];
  /** Event tag category from the hovered row's event, if any. */
  resolveCategory?: (tag: string) => EventCategory | undefined;
}

export function ChartTooltip({ active, payload, label, fields, resolveCategory }: Props) {
  if (!active || !payload?.length) return null;

  const row = payload[0]?.payload as Record<string, unknown> | undefined;
  if (!row) return null;

  const tag = (row.event as string | null) ?? null;
  const cat = tag && resolveCategory ? resolveCategory(tag) : undefined;
  const color =
    cat === "intervention"
      ? CATEGORY_STYLES.intervention.color
      : cat
        ? CATEGORY_STYLES[cat].color
        : undefined;

  const tIso = typeof label === "number" ? new Date(label).toISOString() : String(label);

  return (
    <div className="tip" style={{ ["--tip-event-color" as never]: color }}>
      <div className="tip__t">{fmtHMS(tIso)}</div>
      {fields.map((f) => {
        const v = row[f.key];
        if (v === null || v === undefined) return null;
        const num = typeof v === "number" ? v : Number(v);
        const formatted = Number.isFinite(num)
          ? num.toFixed(f.precision ?? 1)
          : "—";
        return (
          <div className="tip__row" key={f.key}>
            <span className="tip__row-name">{f.name}</span>
            <span className="tip__row-val">
              {formatted}
              {f.unit ? <span style={{ color: "var(--ink-3)", marginLeft: 4 }}>{f.unit}</span> : null}
            </span>
          </div>
        );
      })}
      {tag ? <div className="tip__event">▌ {snakeToTitleCase(tag)}{cat ? `  · ${narrativeFor(tag)}` : ""}</div> : null}
    </div>
  );
}
