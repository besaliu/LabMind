import type { EventCategory } from "../types/bundle";
import { CATEGORY_STYLES } from "../lib/categories";

interface Props {
  active: Set<EventCategory>;
  counts: Record<EventCategory, number>;
  onToggle: (cat: EventCategory) => void;
  showImpurity: boolean;
  showPh: boolean;
  onToggleImpurity: () => void;
  onTogglePh: () => void;
}

const ORDER: EventCategory[] = ["anomaly", "threshold", "recovery", "intervention"];

export function FilterBar({
  active, counts, onToggle, showImpurity, showPh, onToggleImpurity, onTogglePh,
}: Props) {
  return (
    <div className="filterbar">
      <span className="filterbar__label">Filter</span>
      {ORDER.map((key) => {
        const style = CATEGORY_STYLES[key];
        const isActive = active.has(key);
        return (
          <button
            key={key}
            type="button"
            className="chip"
            data-active={isActive}
            style={{
              ["--led-color" as never]: style.color,
              ["--led-glow" as never]: isActive ? style.color + "88" : "transparent",
            }}
            onClick={() => onToggle(key)}
            aria-pressed={isActive}
          >
            <span className="chip__led" />
            <span>{style.label}</span>
            <span className="chip__count">[{counts[key] ?? 0}]</span>
          </button>
        );
      })}

      <div className="toggles" aria-label="Series visibility">
        <button
          type="button"
          className="toggle"
          data-active={showImpurity}
          onClick={onToggleImpurity}
        >
          Impurity
        </button>
        <button
          type="button"
          className="toggle"
          data-active={showPh}
          onClick={onTogglePh}
        >
          pH
        </button>
      </div>
    </div>
  );
}
