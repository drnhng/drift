"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { LayerCard } from "@/components/LayerCard";
import { Slider } from "@/components/Slider";
import { Visualizer } from "@/components/Visualizer";
import { useDriftSocket } from "@/hooks/useDriftSocket";
import type { SoundEngine } from "@/lib/audio/engine";
import { BINAURAL_BANDS, SOUNDS, SOUND_COLORS, SOUND_LABELS } from "@/lib/scene";

const WS_URL = process.env.NEXT_PUBLIC_WS_URL ?? "ws://localhost:8000/ws";

const SUGGESTIONS = [
  "add rain",
  "make it heavier",
  "fireplace on the left",
  "slower",
  "cabin in a storm",
  "grandma's house",
  "floating in space",
  "I'm overstimulated",
];

export function DriftApp() {
  const { status, parser, scene, ramp, log, thinking, error, sendCommand, sendOps, reset } = useDriftSocket(WS_URL);
  const engineRef = useRef<SoundEngine | null>(null);
  const [playing, setPlaying] = useState(false);
  const [starting, setStarting] = useState(false);
  const [text, setText] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  // Keep the audio engine in sync with the scene.
  useEffect(() => {
    engineRef.current?.apply(scene, ramp);
  }, [scene, ramp]);

  const start = async () => {
    setStarting(true);
    // Tone.js touches browser audio APIs, so load it only on the client, on demand.
    const { SoundEngine } = await import("@/lib/audio/engine");
    engineRef.current = await SoundEngine.create(scene);
    setStarting(false);
    setPlaying(true);
    inputRef.current?.focus();
  };

  const stop = async () => {
    const engine = engineRef.current;
    engineRef.current = null;
    setPlaying(false);
    await engine?.stop();
  };

  useEffect(() => () => void engineRef.current?.stop(0.1), []);

  const getSpectrum = useCallback(() => {
    const value = engineRef.current?.analyser.getValue();
    return value instanceof Float32Array ? value : null;
  }, []);

  const submit = (command: string) => {
    const trimmed = command.trim();
    if (!trimmed) return;
    sendCommand(trimmed);
    setText("");
  };

  const available = SOUNDS.filter((s) => !scene.layers.some((l) => l.sound === s));

  return (
    <div className="mx-auto flex w-full max-w-5xl flex-1 flex-col gap-6 px-4 py-6 sm:px-6">
      <header className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold tracking-tight">Drift</h1>
          <p className="text-sm text-muted">A soundscape you shape by talking to it.</p>
        </div>
        <div className="flex items-center gap-3 text-xs text-muted">
          {parser && (
            <span className="whitespace-nowrap rounded-full border border-line px-2.5 py-1">
              {parser === "llm" ? "AI parser" : "Built-in parser"}
            </span>
          )}
          <span className="flex items-center gap-1.5">
            <span
              className={`h-2 w-2 rounded-full ${
                status === "open" ? "bg-emerald-400" : status === "connecting" ? "bg-amber-400" : "bg-rose-500"
              }`}
            />
            {status === "open" ? "connected" : status}
          </span>
        </div>
      </header>

      <section className="relative h-64 overflow-hidden rounded-3xl border border-line bg-panel sm:h-80">
        <Visualizer scene={scene} getSpectrum={getSpectrum} />
        {!playing && (
          <div className="absolute inset-0 flex flex-col items-center justify-center gap-3 bg-background/60 backdrop-blur-sm">
            <button
              onClick={start}
              disabled={starting}
              className="rounded-full bg-foreground px-6 py-3 text-sm font-medium text-background transition hover:opacity-90 disabled:opacity-60"
            >
              {starting ? "Starting…" : "Begin listening"}
            </button>
            <p className="text-xs text-muted">Headphones recommended for binaural beats</p>
          </div>
        )}
        {playing && (
          <button
            onClick={stop}
            className="absolute right-3 top-3 rounded-full border border-line bg-background/60 px-3 py-1 text-xs text-muted backdrop-blur hover:text-foreground"
          >
            Stop
          </button>
        )}
      </section>

      <section className="flex flex-col gap-3">
        <form
          onSubmit={(e) => {
            e.preventDefault();
            submit(text);
          }}
          className="flex gap-2"
        >
          <input
            ref={inputRef}
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder='Try "add rain" or "make it feel like a cabin in a storm"'
            maxLength={500}
            className="min-w-0 flex-1 rounded-full border border-line bg-panel px-5 py-3 text-sm outline-none placeholder:text-muted focus:border-white/30"
          />
          <button
            type="submit"
            disabled={status !== "open" || thinking || !text.trim()}
            className="rounded-full bg-foreground px-5 text-sm font-medium text-background transition disabled:opacity-40"
          >
            {thinking ? "…" : "Send"}
          </button>
        </form>
        <div className="flex flex-wrap gap-2">
          {SUGGESTIONS.map((s) => (
            <button
              key={s}
              onClick={() => submit(s)}
              disabled={status !== "open"}
              className="rounded-full border border-line px-3 py-1 text-xs text-muted transition hover:border-white/30 hover:text-foreground"
            >
              {s}
            </button>
          ))}
        </div>
        {(log.length > 0 || error) && (
          <ol className="flex flex-col gap-1.5 text-sm" aria-live="polite">
            {log.slice(-3).map((entry) => (
              <li key={entry.id} className="flex flex-wrap gap-x-2">
                <span className="text-muted">› {entry.command}</span>
                <span>{entry.reply}</span>
              </li>
            ))}
            {error && <li className="text-rose-400">{error}</li>}
          </ol>
        )}
      </section>

      <section className="flex flex-col gap-3">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-medium">Layers</h2>
          {scene.layers.length > 0 && (
            <button onClick={reset} className="text-xs text-muted hover:text-foreground">
              Reset
            </button>
          )}
        </div>
        {scene.layers.length === 0 ? (
          <p className="text-sm text-muted">Just the binaural beat for now. Ask for a sound, or tap one below.</p>
        ) : (
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {scene.layers.map((layer) => (
              <LayerCard key={layer.sound} layer={layer} onOps={sendOps} />
            ))}
          </div>
        )}
        {available.length > 0 && (
          <div className="flex flex-wrap gap-2">
            {available.map((sound) => (
              <button
                key={sound}
                onClick={() => sendOps([{ op: "add_layer", sound }])}
                className="flex items-center gap-1.5 rounded-full border border-dashed border-line px-3 py-1 text-xs text-muted transition hover:border-white/30 hover:text-foreground"
              >
                <span className="h-1.5 w-1.5 rounded-full" style={{ background: SOUND_COLORS[sound] }} />+ {SOUND_LABELS[sound]}
              </button>
            ))}
          </div>
        )}
      </section>

      <section className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <div className="flex flex-col gap-3 rounded-2xl border border-line bg-panel p-4">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-medium">Binaural beat</h2>
            <button
              onClick={() => sendOps([{ op: "set_binaural", enabled: !scene.binaural.enabled }])}
              className={`rounded-full px-3 py-0.5 text-xs ${
                scene.binaural.enabled ? "bg-violet-400/20 text-violet-200" : "border border-line text-muted"
              }`}
            >
              {scene.binaural.enabled ? "On" : "Off"}
            </button>
          </div>
          <Slider
            label="Beat frequency"
            value={scene.binaural.beat_hz}
            min={0.5}
            max={40}
            step={0.5}
            format={(v) => `${v} Hz`}
            onChange={(beat_hz) => sendOps([{ op: "set_binaural", beat_hz }])}
            accent="#a78bfa"
          />
          <Slider
            label="Volume"
            value={scene.binaural.volume}
            onChange={(volume) => sendOps([{ op: "set_binaural", volume }])}
            accent="#a78bfa"
          />
          <div className="flex flex-wrap gap-2">
            {BINAURAL_BANDS.map((band) => (
              <button
                key={band.name}
                onClick={() => sendOps([{ op: "set_binaural", enabled: true, beat_hz: band.hz }])}
                className={`rounded-full border px-2.5 py-0.5 text-xs transition ${
                  scene.binaural.beat_hz === band.hz ? "border-violet-300/60 text-violet-200" : "border-line text-muted"
                }`}
              >
                {band.name} · {band.hint}
              </button>
            ))}
          </div>
        </div>

        <div className="flex flex-col gap-3 rounded-2xl border border-line bg-panel p-4">
          <h2 className="text-sm font-medium">Mix</h2>
          <Slider
            label="Master volume"
            value={scene.master.volume}
            onChange={(volume) => sendOps([{ op: "set_master", volume }])}
          />
          <Slider
            label="Warmth"
            value={scene.master.warmth}
            onChange={(warmth) => sendOps([{ op: "set_master", warmth }])}
          />
        </div>
      </section>
    </div>
  );
}
