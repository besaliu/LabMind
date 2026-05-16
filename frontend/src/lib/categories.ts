import type { EventCategory } from "../types/bundle";

export interface CategoryStyle {
  key: EventCategory;
  label: string;
  abbrev: string;
  color: string;
  fillOpacity: number;
}

export const CATEGORY_STYLES: Record<EventCategory, CategoryStyle> = {
  anomaly: {
    key: "anomaly",
    label: "Anomaly",
    abbrev: "ANM",
    color: "#b45309",
    fillOpacity: 0.13,
  },
  threshold: {
    key: "threshold",
    label: "Threshold breach",
    abbrev: "THR",
    color: "#b91c1c",
    fillOpacity: 0.15,
  },
  recovery: {
    key: "recovery",
    label: "Recovery",
    abbrev: "RCV",
    color: "#0f766e",
    fillOpacity: 0.13,
  },
  intervention: {
    key: "intervention",
    label: "Intervention",
    abbrev: "INT",
    color: "#4d7c0f",
    fillOpacity: 1,
  },
};

const TAG_NARRATIVE: Record<string, string> = {
  impurity_rising_nominal_range:
    "Impurity climbing within nominal band — pre-event acceleration.",
  impurity_spike_rate_5ppm_per_min:
    "Rate of change exceeds 5 ppm/min — the run_003 leading indicator for sensor-lag thermal events.",
  impurity_above_warning_threshold:
    "Impurity has crossed the 35 ppm warning threshold.",
  impurity_recovering:
    "Impurity falling back through warning toward nominal after intervention.",
  ph_monotonic_drift_detected:
    "Sustained one-direction pH creep — matches the run_004 hydrolysis signature.",
  ph_drift_arrested:
    "Monotonic drift reversed — buffer addition holding.",
  temp_probe_lag_suspected:
    "Temperature reading flat while impurity spikes — probe is likely lagging actual solution temperature.",
  temp_dip_confirmed_post_intervention:
    "Predicted dip now visible in the instrument — confirms the sensor-lag inference.",
  minor_surface_stress_observed:
    "Microscopy snapshot shows minor surface stress; no cracking — agent's intervention prevented visible damage.",
};

export const narrativeFor = (tag: string): string =>
  TAG_NARRATIVE[tag] ?? tag.replace(/_/g, " ");
