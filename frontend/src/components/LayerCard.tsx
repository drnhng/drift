"use client";

import { Slider } from "@/components/Slider";
import { SOUND_COLORS, SOUND_LABELS, type Layer, type Op } from "@/lib/scene";

const NOISE = new Set(["white_noise", "pink_noise", "brown_noise"]);

function panLabel(pan: number) {
  if (Math.abs(pan) < 0.1) return "center";
  return `${Math.round(Math.abs(pan) * 100)}% ${pan < 0 ? "L" : "R"}`;
}

export function LayerCard({ layer, onOps }: { layer: Layer; onOps: (ops: Op[]) => void }) {
  const color = SOUND_COLORS[layer.sound];
  const adjust = (updates: Partial<Layer>) => onOps([{ op: "adjust_layer", sound: layer.sound, ...updates }]);

  return (
    <div className="flex flex-col gap-3 rounded-2xl border border-line bg-panel p-4">
      <div className="flex items-center justify-between">
        <span className="flex items-center gap-2 text-sm font-medium">
          <span className="h-2.5 w-2.5 rounded-full" style={{ background: color, boxShadow: `0 0 12px ${color}` }} />
          {SOUND_LABELS[layer.sound]}
        </span>
        <button
          onClick={() => onOps([{ op: "remove_layer", sound: layer.sound }])}
          className="rounded-full px-2 text-muted transition hover:bg-white/10 hover:text-foreground"
          aria-label={`Remove ${SOUND_LABELS[layer.sound]}`}
        >
          ×
        </button>
      </div>
      <Slider label="Volume" value={layer.volume} onChange={(volume) => adjust({ volume })} accent={color} />
      <Slider
        label={NOISE.has(layer.sound) ? "Brightness" : "Intensity"}
        value={layer.intensity}
        onChange={(intensity) => adjust({ intensity })}
        accent={color}
      />
      {!NOISE.has(layer.sound) && (
        <Slider label="Speed" value={layer.speed} onChange={(speed) => adjust({ speed })} accent={color} />
      )}
      <Slider label="Pan" value={layer.pan} min={-1} max={1} onChange={(pan) => adjust({ pan })} format={panLabel} accent={color} />
    </div>
  );
}
