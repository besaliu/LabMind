import { useMemo } from "react";

interface Props {
  fraction: number;            // 0..1 position within data area
  label: string;
  delayMs?: number;
  leftMargin: number;          // chart left margin in px
  rightMargin: number;         // chart right margin in px
  onEnter: () => void;
  onClick: () => void;
}

/** Absolute-positioned intervention marker. The fraction is mapped into the
 *  chart's data area (excluding the y-axis gutter and right padding) using
 *  CSS calc so the marker tracks resizing without JS measurement. */
export function InterventionPin({ fraction, label, delayMs = 600, leftMargin, rightMargin, onEnter, onClick }: Props) {
  const leftCss = useMemo(() => {
    const pxOffset = leftMargin - fraction * (leftMargin + rightMargin);
    return `calc(${pxOffset}px + ${(fraction * 100).toFixed(3)}%)`;
  }, [fraction, leftMargin, rightMargin]);

  return (
    <div
      className="pin"
      style={{ left: leftCss, ["--pin-delay" as never]: `${delayMs}ms` }}
    >
      {/* 30px-wide hit area, visually empty except for the dot + label */}
      <div
        style={{
          width: 30,
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          pointerEvents: "auto",
          cursor: "pointer",
        }}
        onMouseEnter={onEnter}
        onClick={(e) => { e.stopPropagation(); onClick(); }}
      >
        <span className="pin__dot" />
        <span className="pin__label">{label}</span>
      </div>
    </div>
  );
}
