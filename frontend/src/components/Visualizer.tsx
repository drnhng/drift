"use client";

import { useEffect, useRef } from "react";

import { SOUNDS, SOUND_COLORS, type Scene } from "@/lib/scene";

type Props = {
  scene: Scene;
  /** Returns the current FFT in dB, or null when audio isn't running. */
  getSpectrum: () => Float32Array | null;
};

// Soft glowing orbs: one per layer, placed by pan, sized by volume,
// breathing with the sound's speed and the live audio energy.
export function Visualizer({ scene, getSpectrum }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  // The animation loop reads the latest scene without restarting.
  const sceneRef = useRef(scene);
  useEffect(() => {
    sceneRef.current = scene;
  }, [scene]);

  useEffect(() => {
    const canvas = canvasRef.current;
    const ctx = canvas?.getContext("2d");
    if (!canvas || !ctx) return;

    let frame = 0;
    const smoothed = new Map<string, { x: number; r: number }>();
    let energy = 0;

    const draw = (time: number) => {
      const t = time / 1000;
      const dpr = window.devicePixelRatio || 1;
      const { width, height } = canvas.getBoundingClientRect();
      if (canvas.width !== Math.round(width * dpr)) {
        canvas.width = Math.round(width * dpr);
        canvas.height = Math.round(height * dpr);
      }
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, width, height);

      const spectrum = getSpectrum();
      if (spectrum) {
        let sum = 0;
        for (const db of spectrum) sum += Math.max(0, (db + 100) / 100);
        energy += (sum / spectrum.length - energy) * 0.1;
      } else {
        energy *= 0.95;
      }

      const { layers, binaural } = sceneRef.current;
      ctx.globalCompositeOperation = "lighter";

      // Binaural beat: a faint ring that pulses at (a slowed-down version of) the beat rate.
      if (binaural.enabled) {
        const pulse = 0.5 + 0.5 * Math.sin(t * Math.PI * 2 * Math.min(binaural.beat_hz, 12) * 0.25);
        const radius = Math.min(width, height) * (0.32 + 0.03 * pulse);
        ctx.strokeStyle = `rgba(167, 139, 250, ${0.08 + 0.25 * binaural.volume * (0.6 + 0.4 * pulse)})`;
        ctx.lineWidth = 1.5;
        ctx.beginPath();
        ctx.arc(width / 2, height / 2, radius, 0, Math.PI * 2);
        ctx.stroke();
      }

      layers.forEach((layer, i) => {
        // Fan sounds out a little so centered layers don't stack on one spot.
        const spread = ((SOUNDS.indexOf(layer.sound) % 5) - 2) * width * 0.07;
        const targetX = width / 2 + layer.pan * width * 0.3 + spread;
        const targetR = Math.min(width, height) * (0.08 + 0.22 * layer.volume);
        const prev = smoothed.get(layer.sound) ?? { x: targetX, r: 0 };
        const next = { x: prev.x + (targetX - prev.x) * 0.05, r: prev.r + (targetR - prev.r) * 0.04 };
        smoothed.set(layer.sound, next);

        const breathe = 1 + 0.08 * Math.sin(t * (0.3 + layer.speed * 1.5) + i * 1.7) + energy * 0.25;
        const lane = ((SOUNDS.indexOf(layer.sound) % 3) - 1) * height * 0.14;
        const y = height / 2 + lane + Math.sin(t * 0.2 + i * 2.1) * height * 0.06;
        const r = next.r * breathe;
        const color = SOUND_COLORS[layer.sound];

        const gradient = ctx.createRadialGradient(next.x, y, 0, next.x, y, r);
        gradient.addColorStop(0, `${color}88`);
        gradient.addColorStop(0.4, `${color}33`);
        gradient.addColorStop(1, `${color}00`);
        ctx.fillStyle = gradient;
        ctx.beginPath();
        ctx.arc(next.x, y, r, 0, Math.PI * 2);
        ctx.fill();
      });

      for (const key of smoothed.keys()) {
        if (!layers.some((l) => l.sound === key)) smoothed.delete(key);
      }

      frame = requestAnimationFrame(draw);
    };

    frame = requestAnimationFrame(draw);
    return () => cancelAnimationFrame(frame);
  }, [getSpectrum]);

  return <canvas ref={canvasRef} className="h-full w-full" aria-hidden />;
}
