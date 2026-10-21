// Mirrors backend/app/scene.py. The server is the source of truth.

export const SOUNDS = [
  "rain",
  "thunder",
  "wind",
  "ocean",
  "fire",
  "stream",
  "birds",
  "crickets",
  "chimes",
  "drone",
  "white_noise",
  "pink_noise",
  "brown_noise",
] as const;

export type SoundName = (typeof SOUNDS)[number];

export const SOUND_LABELS: Record<SoundName, string> = {
  rain: "Rain",
  thunder: "Thunder",
  wind: "Wind",
  ocean: "Ocean",
  fire: "Fireplace",
  stream: "Stream",
  birds: "Birds",
  crickets: "Crickets",
  chimes: "Wind chimes",
  drone: "Warm drone",
  white_noise: "White noise",
  pink_noise: "Pink noise",
  brown_noise: "Brown noise",
};

// Accent color per sound, used by the visualizer and layer cards.
export const SOUND_COLORS: Record<SoundName, string> = {
  rain: "#7aa7ff",
  thunder: "#a78bfa",
  wind: "#cbd5e1",
  ocean: "#38bdf8",
  fire: "#fb923c",
  stream: "#5eead4",
  birds: "#facc15",
  crickets: "#a3e635",
  chimes: "#f0abfc",
  drone: "#f9a8d4",
  white_noise: "#e5e7eb",
  pink_noise: "#fda4af",
  brown_noise: "#d6a77a",
};

export const BINAURAL_BANDS = [
  { name: "Delta", hz: 2, hint: "sleep" },
  { name: "Theta", hz: 6, hint: "meditate" },
  { name: "Alpha", hz: 10, hint: "relax" },
  { name: "Beta", hz: 16, hint: "focus" },
] as const;

export type Layer = {
  sound: SoundName;
  volume: number;
  intensity: number;
  speed: number;
  pan: number;
};

export type Binaural = {
  enabled: boolean;
  carrier_hz: number;
  beat_hz: number;
  volume: number;
};

export type Master = {
  volume: number;
  warmth: number;
};

export type Scene = {
  binaural: Binaural;
  layers: Layer[];
  master: Master;
};

export type Op =
  | ({ op: "add_layer"; sound: SoundName } & Partial<Omit<Layer, "sound">>)
  | { op: "remove_layer"; sound: SoundName }
  | ({ op: "adjust_layer"; sound: SoundName } & Partial<Omit<Layer, "sound">>)
  | ({ op: "set_binaural" } & Partial<Binaural>)
  | ({ op: "set_master" } & Partial<Master>)
  | { op: "clear_layers" };

export type ServerMessage =
  | {
      type: "scene";
      scene: Scene;
      changes: string[];
      reply: string;
      source: string;
      command: string | null;
    }
  | { type: "hello"; parser: "llm" | "rules" }
  | { type: "thinking"; command: string }
  | { type: "error"; message: string };

export const DEFAULT_SCENE: Scene = {
  binaural: { enabled: true, carrier_hz: 200, beat_hz: 6, volume: 0.25 },
  layers: [],
  master: { volume: 0.8, warmth: 0.5 },
};

// Optimistic local version of the server's apply_ops, so sliders feel instant.
export function applyOpLocally(scene: Scene, op: Op): Scene {
  const next: Scene = structuredClone(scene);
  switch (op.op) {
    case "add_layer":
    case "adjust_layer": {
      const { op: _kind, sound, ...updates } = op;
      const existing = next.layers.find((l) => l.sound === sound);
      if (existing) Object.assign(existing, updates);
      else next.layers.push({ sound, volume: 0.5, intensity: 0.5, speed: 0.5, pan: 0, ...updates });
      break;
    }
    case "remove_layer":
      next.layers = next.layers.filter((l) => l.sound !== op.sound);
      break;
    case "set_binaural": {
      const { op: _kind, ...updates } = op;
      Object.assign(next.binaural, updates);
      break;
    }
    case "set_master": {
      const { op: _kind, ...updates } = op;
      Object.assign(next.master, updates);
      break;
    }
    case "clear_layers":
      next.layers = [];
      break;
  }
  return next;
}
