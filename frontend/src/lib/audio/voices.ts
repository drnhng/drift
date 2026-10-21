// Procedural ambient voices. Every sound is synthesized from noise and oscillators,
// so there are no audio files and every parameter can change smoothly while playing.

import * as Tone from "tone";

import type { Layer, SoundName } from "@/lib/scene";

export type VoiceParams = Omit<Layer, "sound">;

const FADE_SECONDS = 2.5;

function lerp(a: number, b: number, t: number) {
  return a + (b - a) * t;
}

function rand(min: number, max: number) {
  return min + Math.random() * (max - min);
}

// Exponential mapping feels natural for frequencies.
function expLerp(a: number, b: number, t: number) {
  return a * Math.pow(b / a, t);
}

export abstract class Voice {
  readonly output: Tone.Gain;
  private readonly panner: Tone.Panner;
  protected params: VoiceParams;
  protected disposed = false;
  private readonly owned: { dispose(): unknown }[] = [];
  private readonly timers = new Set<ReturnType<typeof setTimeout>>();

  /** `trim` balances loudness between very different sounds. */
  constructor(
    destination: Tone.InputNode,
    params: VoiceParams,
    private readonly trim: number,
  ) {
    this.params = params;
    this.panner = new Tone.Panner(params.pan).connect(destination);
    this.output = new Tone.Gain(0).connect(this.panner);
  }

  /** Register nodes so they're cleaned up on dispose. */
  protected own<T extends { dispose(): unknown }>(node: T): T {
    this.owned.push(node);
    return node;
  }

  /** Run `tick` repeatedly; it returns the delay in ms until the next run. */
  protected loop(tick: () => number) {
    const run = () => {
      if (this.disposed) return;
      const delay = tick();
      const id = setTimeout(() => {
        this.timers.delete(id);
        run();
      }, delay);
      this.timers.add(id);
    };
    run();
  }

  protected gainFor(volume: number) {
    return this.trim * volume * volume;
  }

  fadeIn() {
    this.output.gain.rampTo(this.gainFor(this.params.volume), FADE_SECONDS);
  }

  update(params: VoiceParams, ramp = 1.5) {
    this.params = params;
    this.output.gain.rampTo(this.gainFor(params.volume), ramp);
    this.panner.pan.rampTo(params.pan, ramp);
    this.applyParams(params, ramp);
  }

  protected abstract applyParams(params: VoiceParams, ramp: number): void;

  fadeOutAndDispose() {
    this.output.gain.rampTo(0, FADE_SECONDS);
    setTimeout(() => this.dispose(), FADE_SECONDS * 1000 + 200);
  }

  dispose() {
    if (this.disposed) return;
    this.disposed = true;
    this.timers.forEach(clearTimeout);
    this.timers.clear();
    this.owned.forEach((node) => node.dispose());
    this.output.dispose();
    this.panner.dispose();
  }
}

// --- Continuous noise beds --------------------------------------------------

class ColoredNoise extends Voice {
  private readonly filter: Tone.Filter;

  constructor(dest: Tone.InputNode, params: VoiceParams, type: "white" | "pink" | "brown") {
    super(dest, params, type === "white" ? 0.25 : type === "pink" ? 0.45 : 0.9);
    this.filter = this.own(new Tone.Filter(this.cutoff(params), "lowpass")).connect(this.output);
    this.own(new Tone.Noise(type).start()).connect(this.filter);
  }

  private cutoff(p: VoiceParams) {
    return expLerp(400, 18000, p.intensity);
  }

  protected applyParams(p: VoiceParams, ramp: number) {
    this.filter.frequency.rampTo(this.cutoff(p), ramp);
  }
}

// --- Rain: filtered hiss plus individual droplets ---------------------------

class Rain extends Voice {
  private readonly hiss: Tone.Filter;
  private readonly hissGain: Tone.Gain;
  private readonly drops: Tone.NoiseSynth;
  private readonly dropFilter: Tone.Filter;

  constructor(dest: Tone.InputNode, params: VoiceParams) {
    super(dest, params, 0.8);
    this.hissGain = this.own(new Tone.Gain(1)).connect(this.output);
    this.hiss = this.own(new Tone.Filter(2000, "lowpass")).connect(this.hissGain);
    const highpass = this.own(new Tone.Filter(500, "highpass")).connect(this.hiss);
    this.own(new Tone.Noise("pink").start()).connect(highpass);

    this.dropFilter = this.own(new Tone.Filter(3000, "bandpass")).connect(this.output);
    this.drops = this.own(
      new Tone.NoiseSynth({ noise: { type: "white" }, envelope: { attack: 0.001, decay: 0.02, sustain: 0 } }),
    ).connect(this.dropFilter);
    this.applyParams(params, 0.01);

    this.loop(() => {
      const { intensity, speed } = this.params;
      this.dropFilter.frequency.value = rand(1500, 6000);
      this.drops.triggerAttackRelease(0.01, Tone.now(), rand(0.05, 0.25) * (0.4 + intensity));
      const perSecond = lerp(4, 45, speed) * lerp(0.5, 1.3, intensity);
      return rand(0.4, 1.6) * (1000 / perSecond);
    });
  }

  protected applyParams(p: VoiceParams, ramp: number) {
    this.hiss.frequency.rampTo(expLerp(1200, 9000, p.intensity), ramp);
    this.hissGain.gain.rampTo(lerp(0.5, 1, p.intensity), ramp);
  }
}

// --- Thunder: occasional low rumbles ----------------------------------------

class Thunder extends Voice {
  private readonly rumble: Tone.Gain;
  private readonly filter: Tone.Filter;

  constructor(dest: Tone.InputNode, params: VoiceParams) {
    super(dest, params, 1.4);
    this.rumble = this.own(new Tone.Gain(0)).connect(this.output);
    this.filter = this.own(new Tone.Filter({ frequency: 200, type: "lowpass", rolloff: -24 })).connect(this.rumble);
    this.own(new Tone.Noise("brown").start()).connect(this.filter);

    // First rumble comes fairly soon so the user hears that it worked.
    let first = true;
    this.loop(() => {
      const isFirst = first;
      first = false;
      if (!isFirst) this.strike();
      const gapSeconds = lerp(40, 7, this.params.speed);
      return rand(0.5, 1.4) * gapSeconds * 1000 * (isFirst ? 0.15 : 1);
    });
  }

  private strike() {
    const now = Tone.now();
    const peak = lerp(0.4, 1, this.params.intensity) * rand(0.6, 1);
    const attack = rand(0.2, 1.2);
    const decay = rand(3, 7);
    this.rumble.gain.cancelScheduledValues(now);
    this.rumble.gain.setValueAtTime(0.0001, now);
    this.rumble.gain.linearRampToValueAtTime(peak, now + attack);
    this.rumble.gain.exponentialRampToValueAtTime(0.0001, now + attack + decay);
    this.filter.frequency.cancelScheduledValues(now);
    this.filter.frequency.setValueAtTime(lerp(250, 600, this.params.intensity), now);
    this.filter.frequency.exponentialRampToValueAtTime(80, now + attack + decay);
  }

  protected applyParams() {}
}

// --- Wind: band-passed noise with slow gusts --------------------------------

class Wind extends Voice {
  private readonly sweep: Tone.LFO;
  private readonly gust: Tone.LFO;

  constructor(dest: Tone.InputNode, params: VoiceParams) {
    super(dest, params, 0.9);
    const gustGain = this.own(new Tone.Gain(0)).connect(this.output);
    const filter = this.own(new Tone.Filter({ frequency: 600, type: "bandpass", Q: 1.2 })).connect(gustGain);
    this.own(new Tone.Noise("pink").start()).connect(filter);

    this.sweep = this.own(new Tone.LFO({ frequency: 0.1, min: 250, max: 1200 }).start()).connect(filter.frequency);
    this.gust = this.own(new Tone.LFO({ frequency: 0.07, min: 0.35, max: 1, phase: 90 }).start()).connect(gustGain.gain);
    this.applyParams(params, 0.01);
  }

  protected applyParams(p: VoiceParams, ramp: number) {
    this.sweep.frequency.rampTo(lerp(0.03, 0.35, p.speed), ramp);
    this.gust.frequency.rampTo(lerp(0.02, 0.25, p.speed), ramp);
    this.sweep.max = lerp(700, 2600, p.intensity);
    this.gust.min = lerp(0.6, 0.15, p.intensity);
  }
}

// --- Ocean: slow swelling waves ---------------------------------------------

class Ocean extends Voice {
  private readonly swell: Tone.LFO;
  private readonly brightness: Tone.LFO;

  constructor(dest: Tone.InputNode, params: VoiceParams) {
    super(dest, params, 0.9);
    const waveGain = this.own(new Tone.Gain(0)).connect(this.output);
    const filter = this.own(new Tone.Filter({ frequency: 800, type: "lowpass", rolloff: -24 })).connect(waveGain);
    this.own(new Tone.Noise("pink").start()).connect(filter);
    this.own(new Tone.Noise("brown").start()).connect(filter);

    this.swell = this.own(new Tone.LFO({ frequency: 0.1, min: 0.05, max: 1 }).start()).connect(waveGain.gain);
    this.brightness = this.own(new Tone.LFO({ frequency: 0.1, min: 250, max: 2500 }).start()).connect(filter.frequency);
    this.applyParams(params, 0.01);
  }

  protected applyParams(p: VoiceParams, ramp: number) {
    // One wave every ~14s (slow) to ~4s (fast).
    const rate = 1 / lerp(14, 4, p.speed);
    this.swell.frequency.rampTo(rate, ramp);
    this.brightness.frequency.rampTo(rate, ramp);
    this.brightness.max = expLerp(900, 5000, p.intensity);
    this.swell.min = lerp(0.3, 0.02, p.intensity);
  }
}

// --- Fire: low roar plus random crackles ------------------------------------

class Fire extends Voice {
  private readonly crackle: Tone.NoiseSynth;
  private readonly crackleFilter: Tone.Filter;
  private readonly crackleGain: Tone.Gain;

  constructor(dest: Tone.InputNode, params: VoiceParams) {
    super(dest, params, 1);
    const roar = this.own(new Tone.Filter(350, "lowpass")).connect(this.own(new Tone.Gain(0.5)).connect(this.output));
    this.own(new Tone.Noise("brown").start()).connect(roar);

    this.crackleGain = this.own(new Tone.Gain(0.6)).connect(this.output);
    this.crackleFilter = this.own(new Tone.Filter(2500, "highpass")).connect(this.crackleGain);
    this.crackle = this.own(
      new Tone.NoiseSynth({ noise: { type: "white" }, envelope: { attack: 0.001, decay: 0.015, sustain: 0 } }),
    ).connect(this.crackleFilter);
    this.applyParams(params, 0.01);

    this.loop(() => {
      const pop = Math.random() < 0.12;
      this.crackleFilter.frequency.value = pop ? rand(500, 1200) : rand(1800, 6000);
      this.crackle.envelope.decay = pop ? rand(0.03, 0.08) : rand(0.004, 0.02);
      this.crackle.triggerAttackRelease(0.005, Tone.now(), rand(0.2, 1));
      // Crackles come in little clusters.
      const perSecond = lerp(2, 22, this.params.speed);
      return Math.random() < 0.3 ? rand(15, 60) : rand(0.3, 1.8) * (1000 / perSecond);
    });
  }

  protected applyParams(p: VoiceParams, ramp: number) {
    this.crackleGain.gain.rampTo(lerp(0.2, 1.1, p.intensity), ramp);
  }
}

// --- Stream: babbling band-passed noise -------------------------------------

class Stream extends Voice {
  private readonly bands: Tone.Filter[];
  private readonly bed: Tone.Filter;

  constructor(dest: Tone.InputNode, params: VoiceParams) {
    super(dest, params, 1.6);
    const noise = this.own(new Tone.Noise("white").start());
    this.bands = [0, 1, 2].map(() => {
      const filter = this.own(new Tone.Filter({ frequency: rand(600, 2400), type: "bandpass", Q: 6 }));
      noise.connect(filter);
      filter.connect(this.output);
      return filter;
    });
    this.bed = this.own(new Tone.Filter(1200, "lowpass")).connect(this.own(new Tone.Gain(0.15)).connect(this.output));
    noise.connect(this.bed);
    this.applyParams(params, 0.01);

    // Randomly wander each band to create the "babble".
    this.loop(() => {
      const { intensity, speed } = this.params;
      for (const band of this.bands) {
        band.frequency.rampTo(expLerp(500, 3500, Math.random()) * lerp(0.8, 1.2, intensity), rand(0.05, 0.2));
      }
      return lerp(260, 60, speed) * rand(0.6, 1.4);
    });
  }

  protected applyParams(p: VoiceParams, ramp: number) {
    const q = lerp(9, 2.5, p.intensity); // lower Q = wider bands = rushing water
    this.bands.forEach((band) => band.Q.rampTo(q, ramp));
    this.bed.frequency.rampTo(expLerp(600, 4000, p.intensity), ramp);
  }
}

// --- Birds: short chirping phrases ------------------------------------------

class Birds extends Voice {
  private readonly synth: Tone.Synth;
  private readonly birdPan: Tone.Panner;

  constructor(dest: Tone.InputNode, params: VoiceParams) {
    super(dest, params, 0.6);
    this.birdPan = this.own(new Tone.Panner(0)).connect(this.output);
    this.synth = this.own(
      new Tone.Synth({
        oscillator: { type: "sine" },
        envelope: { attack: 0.005, decay: 0.04, sustain: 0.4, release: 0.04 },
      }),
    ).connect(this.birdPan);

    this.loop(() => {
      this.phrase();
      const gapSeconds = lerp(9, 1.2, this.params.speed);
      return rand(0.4, 1.6) * gapSeconds * 1000;
    });
  }

  private phrase() {
    // Each phrase sounds like it comes from a different bird somewhere around you.
    this.birdPan.pan.value = rand(-0.8, 0.8);
    const base = rand(2200, 4200);
    const notes = Math.floor(rand(2, 7));
    const velocity = lerp(0.3, 1, this.params.intensity);
    let t = Tone.now() + 0.05;
    for (let i = 0; i < notes; i++) {
      const duration = rand(0.04, 0.12);
      const from = base * rand(0.85, 1.15);
      const to = from * (Math.random() < 0.5 ? rand(1.2, 1.6) : rand(0.6, 0.85));
      this.synth.triggerAttack(from, t, velocity);
      this.synth.frequency.exponentialRampToValueAtTime(to, t + duration);
      this.synth.triggerRelease(t + duration);
      t += duration + rand(0.04, 0.15);
    }
  }

  protected applyParams() {}
}

// --- Crickets: pulsed high tones ---------------------------------------------

class Crickets extends Voice {
  private readonly gates: Tone.Gain[];

  constructor(dest: Tone.InputNode, params: VoiceParams) {
    super(dest, params, 0.2);
    this.gates = [4100, 4500, 4800, 5200].map((hz, i) => {
      const panner = this.own(new Tone.Panner(lerp(-0.7, 0.7, i / 3))).connect(this.output);
      const gate = this.own(new Tone.Gain(0)).connect(panner);
      this.own(new Tone.Oscillator(hz, "sine").start()).connect(gate);
      return gate;
    });

    this.gates.forEach((gate, i) => {
      this.loop(() => {
        // Intensity decides how many crickets are singing.
        if (i / this.gates.length < lerp(0.3, 1, this.params.intensity)) this.chirp(gate);
        return lerp(1400, 350, this.params.speed) * rand(0.8, 1.25);
      });
    });
  }

  private chirp(gate: Tone.Gain) {
    let t = Tone.now() + 0.02;
    const pulses = Math.floor(rand(2, 5));
    for (let i = 0; i < pulses; i++) {
      gate.gain.setValueAtTime(0, t);
      gate.gain.linearRampToValueAtTime(1, t + 0.004);
      gate.gain.linearRampToValueAtTime(0, t + 0.018);
      t += 0.035;
    }
  }

  protected applyParams() {}
}

// --- Wind chimes: pentatonic bell tones -------------------------------------

class Chimes extends Voice {
  private readonly synth: Tone.PolySynth<Tone.FMSynth>;
  private static readonly NOTES = ["C6", "D6", "E6", "G6", "A6", "C7", "D7"];

  constructor(dest: Tone.InputNode, params: VoiceParams) {
    super(dest, params, 0.5);
    const reverb = this.own(new Tone.Reverb({ decay: 5, wet: 0.5 })).connect(this.output);
    this.synth = this.own(
      new Tone.PolySynth(Tone.FMSynth, {
        harmonicity: 3.01,
        modulationIndex: 4,
        envelope: { attack: 0.002, decay: 2.5, sustain: 0, release: 2 },
        modulationEnvelope: { attack: 0.002, decay: 0.6, sustain: 0, release: 0.5 },
      }),
    ).connect(reverb);
    this.applyParams(params);

    this.loop(() => {
      const strikes = Math.random() < 0.4 ? Math.floor(rand(2, 5)) : 1;
      let t = Tone.now() + 0.02;
      for (let i = 0; i < strikes; i++) {
        const note = Chimes.NOTES[Math.floor(Math.random() * Chimes.NOTES.length)];
        this.synth.triggerAttackRelease(note, 2, t, rand(0.2, 0.7));
        t += rand(0.08, 0.4);
      }
      return lerp(7000, 900, this.params.speed) * rand(0.5, 1.5);
    });
  }

  protected applyParams(p: VoiceParams) {
    this.synth.set({ modulationIndex: lerp(1.5, 10, p.intensity) });
  }
}

// --- Drone: warm detuned pad that slowly swells -----------------------------

class Drone extends Voice {
  private readonly filter: Tone.Filter;
  private readonly swell: Tone.LFO;

  constructor(dest: Tone.InputNode, params: VoiceParams) {
    super(dest, params, 0.22);
    const swellGain = this.own(new Tone.Gain(0)).connect(this.output);
    this.filter = this.own(new Tone.Filter({ frequency: 500, type: "lowpass", rolloff: -24 })).connect(swellGain);
    for (const [hz, type] of [
      [55, "sawtooth"],
      [82.4, "triangle"],
      [110.3, "sawtooth"],
      [164.8, "triangle"],
    ] as const) {
      this.own(new Tone.Oscillator({ frequency: hz, type, detune: rand(-8, 8) }).start()).connect(this.filter);
    }
    this.swell = this.own(new Tone.LFO({ frequency: 0.05, min: 0.45, max: 1 }).start()).connect(swellGain.gain);
    this.applyParams(params, 0.01);
  }

  protected applyParams(p: VoiceParams, ramp: number) {
    this.filter.frequency.rampTo(expLerp(180, 2200, p.intensity), ramp);
    this.swell.frequency.rampTo(lerp(0.02, 0.25, p.speed), ramp);
  }
}

export function createVoice(sound: SoundName, destination: Tone.InputNode, params: VoiceParams): Voice {
  switch (sound) {
    case "rain":
      return new Rain(destination, params);
    case "thunder":
      return new Thunder(destination, params);
    case "wind":
      return new Wind(destination, params);
    case "ocean":
      return new Ocean(destination, params);
    case "fire":
      return new Fire(destination, params);
    case "stream":
      return new Stream(destination, params);
    case "birds":
      return new Birds(destination, params);
    case "crickets":
      return new Crickets(destination, params);
    case "chimes":
      return new Chimes(destination, params);
    case "drone":
      return new Drone(destination, params);
    case "white_noise":
      return new ColoredNoise(destination, params, "white");
    case "pink_noise":
      return new ColoredNoise(destination, params, "pink");
    case "brown_noise":
      return new ColoredNoise(destination, params, "brown");
  }
}
