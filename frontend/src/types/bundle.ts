export type EventCategory = "anomaly" | "threshold" | "recovery" | "intervention";

export interface TempRow {
  t: string;
  temperature_c: number | null;
  setpoint_c: number | null;
  status: string | null;
  event: string | null;
}

export interface ImpurityRow {
  t: string;
  impurity_ppm: number | null;
  saturation_pct: number | null;
  ph: number | null;
  status: string | null;
  event: string | null;
}

export interface MicroscopyRow {
  t: string;
  clarity_pct: number | null;
  defect_count: number | null;
  status: string | null;
  event: string | null;
}

export interface EventRange {
  panel: "temp" | "impurity" | "microscopy";
  tag: string;
  category: Exclude<EventCategory, "intervention">;
  start: string;
  end: string;
}

export interface Intervention {
  timestamp: string;
  action: string;
  reasoning: string;
  outcome?: string;
  instrument_id?: string;
}

export interface ThresholdBlock {
  target?: number;
  warning_above?: number;
  critical_above?: number;
  warning_below?: number;
  critical_below?: number;
}

export interface BundleResponse {
  run_id: string;
  metadata: {
    run_id: string;
    hypothesis: string;
    context?: string;
    experiment_type: string;
    instruments: string[];
    parameters: Record<string, unknown>;
    monitoring: Record<string, unknown>;
    start_time?: string;
    end_time?: string;
    status: string;
    outcome?: string;
    key_findings?: string[];
  };
  interventions: Intervention[];
  microscopy_snapshot: Record<string, unknown> | null;
  series: {
    temp: TempRow[];
    impurity: ImpurityRow[];
    microscopy: MicroscopyRow[];
  };
  event_ranges: EventRange[];
  thresholds: {
    temp: ThresholdBlock;
    impurity: ThresholdBlock;
    ph: ThresholdBlock;
  };
}
