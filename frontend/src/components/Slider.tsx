"use client";

type SliderProps = {
  label: string;
  value: number;
  onChange: (value: number) => void;
  min?: number;
  max?: number;
  step?: number;
  format?: (value: number) => string;
  accent?: string;
};

export function Slider({ label, value, onChange, min = 0, max = 1, step = 0.01, format, accent }: SliderProps) {
  return (
    <label className="flex flex-col gap-1 text-xs">
      <span className="flex justify-between text-muted">
        <span>{label}</span>
        <span className="tabular-nums">{format ? format(value) : Math.round(((value - min) / (max - min)) * 100)}</span>
      </span>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className="drift-range"
        style={accent ? ({ "--accent": accent } as React.CSSProperties) : undefined}
      />
    </label>
  );
}
