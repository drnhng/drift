// Renders a Scene to audio. Call `apply(scene)` whenever the scene changes; the
// engine diffs it against what's playing and ramps everything smoothly.

import * as Tone from "tone";

import type { Binaural, Scene, SoundName } from "@/lib/scene";
import { createVoice, type Voice } from "@/lib/audio/voices";

const RAMP_SECONDS = 1.5;

class BinauralBeat {
  readonly output: Tone.Gain;
  private readonly left: Tone.Oscillator;
  private readonly right: Tone.Oscillator;
  private readonly nodes: { dispose(): unknown }[] = [];

  constructor(destination: Tone.InputNode, settings: Binaural) {
    this.output = new Tone.Gain(0).connect(destination);
    // Hard-panned sine pair: the brain perceives the frequency difference as a beat.
    // Only works on headphones.
    const leftPan = new Tone.Panner(-1).connect(this.output);
    const rightPan = new Tone.Panner(1).connect(this.output);
    this.left = new Tone.Oscillator(settings.carrier_hz - settings.beat_hz / 2, "sine").connect(leftPan).start();
    this.right = new Tone.Oscillator(settings.carrier_hz + settings.beat_hz / 2, "sine").connect(rightPan).start();
    this.nodes.push(leftPan, rightPan, this.left, this.right);
  }

  update(settings: Binaural, ramp = RAMP_SECONDS) {
    this.left.frequency.rampTo(settings.carrier_hz - settings.beat_hz / 2, ramp);
    this.right.frequency.rampTo(settings.carrier_hz + settings.beat_hz / 2, ramp);
    const level = settings.enabled ? 0.35 * settings.volume * settings.volume : 0;
    this.output.gain.rampTo(level, ramp);
  }

  dispose() {
    this.nodes.forEach((n) => n.dispose());
    this.output.dispose();
  }
}

export class SoundEngine {
  private readonly bus: Tone.Gain;
  private readonly master: Tone.Gain;
  private readonly warmth: Tone.Filter;
  private readonly limiter: Tone.Limiter;
  readonly analyser: Tone.Analyser;
  private readonly binaural: BinauralBeat;
  private readonly voices = new Map<SoundName, Voice>();

  private constructor(scene: Scene) {
    this.limiter = new Tone.Limiter(-2).toDestination();
    this.analyser = new Tone.Analyser("fft", 64);
    this.master = new Tone.Gain(0).connect(this.limiter);
    this.master.connect(this.analyser);
    this.warmth = new Tone.Filter({ frequency: 18000, type: "lowpass", rolloff: -12 }).connect(this.master);
    this.bus = new Tone.Gain(1).connect(this.warmth);
    this.binaural = new BinauralBeat(this.master, scene.binaural);
    this.apply(scene, 3);
  }

  /** Must be called from a user gesture (browsers block audio until then). */
  static async create(scene: Scene): Promise<SoundEngine> {
    await Tone.start();
    return new SoundEngine(scene);
  }

  apply(scene: Scene, ramp = RAMP_SECONDS) {
    const wanted = new Set(scene.layers.map((l) => l.sound));

    for (const [sound, voice] of this.voices) {
      if (!wanted.has(sound)) {
        voice.fadeOutAndDispose();
        this.voices.delete(sound);
      }
    }

    for (const { sound, ...params } of scene.layers) {
      const existing = this.voices.get(sound);
      if (existing) {
        existing.update(params, ramp);
      } else {
        const voice = createVoice(sound, this.bus, params);
        voice.fadeIn();
        this.voices.set(sound, voice);
      }
    }

    this.binaural.update(scene.binaural, ramp);
    this.master.gain.rampTo(scene.master.volume * scene.master.volume, ramp);
    // warmth 0 → fully open (18 kHz), warmth 1 → muffled (~700 Hz).
    this.warmth.frequency.rampTo(18000 * Math.pow(700 / 18000, scene.master.warmth), ramp);
  }

  /** Fade everything out over `seconds`, then stop. */
  async stop(seconds = 1.5) {
    this.master.gain.rampTo(0, seconds);
    await new Promise((r) => setTimeout(r, seconds * 1000 + 100));
    this.voices.forEach((v) => v.dispose());
    this.voices.clear();
    this.binaural.dispose();
    [this.bus, this.warmth, this.master, this.analyser, this.limiter].forEach((n) => n.dispose());
  }
}
