"""Keyword-based command parser.

Works with no API key, and is the fallback whenever the LLM is unavailable.
It handles the common phrasings ("add rain", "make the fire louder", "slower",
"remove thunder", "storm") and resolves pronoun-ish commands ("more", "too
much") against the last thing the user touched.
"""

import re

from app.parsers.base import Interpretation
from app.scene import (
    BINAURAL_BANDS,
    PRESETS,
    SOUND_CATALOG,
    AddLayer,
    AdjustLayer,
    ClearLayers,
    Op,
    RemoveLayer,
    Scene,
    SetBinaural,
    SetMaster,
    apply_ops,
)

# Order matters: longer / more specific phrases first ("wind chimes" before "wind").
SOUND_ALIASES: list[tuple[str, str]] = [
    (r"wind ?chimes?|chimes?|bells?", "chimes"),
    (r"white ?noise", "white_noise"),
    (r"pink ?noise", "pink_noise"),
    (r"brown(ian)? ?noise", "brown_noise"),
    (r"rain(fall|drops?)?|drizzle|downpour", "rain"),
    (r"thunder(storm)?|lightning|rumbles?", "thunder"),
    (r"wind|breeze|gusts?|gale", "wind"),
    (r"ocean|waves?|sea|surf|beach sounds?", "ocean"),
    (r"fire(place)?|camp ?fire|crackl\w*|hearth", "fire"),
    (r"stream|brook|river|creek|water", "stream"),
    (r"birds?(ong)?|chirp\w*", "birds"),
    (r"crickets?|insects?", "crickets"),
    (r"drone|pad|hum", "drone"),
]

BINAURAL_WORDS = r"binaural|beats?|frequency|hz|hertz"
MASTER_WORDS = r"everything|all of it|overall|master|whole thing|it all"

PRESET_ALIASES: list[tuple[str, str]] = [
    (r"storm|stormy", "storm"),
    (r"cabin|cozy|cosy", "cabin"),
    (r"beach|seaside|coast", "beach"),
    (r"forest|woods|jungle", "forest"),
    (r"night(time)?|evening", "night"),
    (r"focus|study|work|concentrat\w*", "focus"),
    (r"sleep|bedtime|drift off", "sleep"),
]

BAND_ALIASES: list[tuple[str, str]] = [
    (r"delta|deep sleep", "delta"),
    (r"theta|meditat\w*", "theta"),
    (r"alpha|relax\w*", "alpha"),
    (r"beta|focus\w*|study|alert", "beta"),
    (r"gamma", "gamma"),
]

REMOVE = r"remove|stop|no more|without|get rid of|take (out|away)|kill|mute|turn off|lose|drop|cut"
ADD = r"add|put|give me|include|bring( in| back)?|start|play|i want|let'?s have|turn on|throw in"
CLEAR = r"clear|silence|start over|reset|remove everything|stop everything|nothing"

LOUDER = r"louder|turn (it )?up|volume up|increase|raise|boost|more"
QUIETER = r"quieter|softer|turn (it )?down|volume down|lower|decrease|reduce|less|too (much|loud)|tone (it )?down"
STRONGER = r"heavier|stronger|harder|intense|denser|thicker|bigger|brighter"
WEAKER = r"lighter|gentler|weaker|calmer|lighter|thinner|smaller|duller|softer sounding"
FASTER = r"faster|quicker|speed (it )?up|more often|frequent"
SLOWER = r"slower|slow (it )?down|less often|lazier"
WARMER = r"warmer|cozier|cosier|muffled|darker|mellow"
BRIGHTER_MIX = r"crisper|clearer|less muffled"


def _has(pattern: str, text: str) -> bool:
    return re.search(rf"\b({pattern})\b", text) is not None


def _step(text: str) -> float:
    if _has(r"a (tiny|little) bit|a touch|slightly|a little|a bit|tad", text):
        return 0.1
    if _has(r"a lot|way|much|really|very|super|tons", text):
        return 0.35
    return 0.2


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return round(max(low, min(high, value)), 3)


def _find_sounds(text: str) -> list[str]:
    found: list[tuple[int, str]] = []
    remaining = text
    for pattern, sound in SOUND_ALIASES:
        match = re.search(rf"\b({pattern})\b", remaining)
        if match and sound not in [s for _, s in found]:
            found.append((match.start(), sound))
            # Blank out the match so "wind chimes" doesn't also match "wind".
            remaining = remaining[: match.start()] + " " * len(match.group(0)) + remaining[match.end():]
    return [sound for _, sound in sorted(found)]


def _pan(text: str) -> float | None:
    if _has(r"(on|to|in) the left|left side|left ear|left", text):
        return -0.6
    if _has(r"(on|to|in) the right|right side|right ear|right", text):
        return 0.6
    if _has(r"center|centre|middle", text):
        return 0.0
    return None


def _split_clauses(text: str) -> list[str]:
    verbs = r"add|remove|make|turn|bring|stop|put|give|more|less|get rid"
    parts = re.split(rf",|;|\bthen\b|\bplus\b|\balso\b|\band\b(?= (?:{verbs})\b)", text)
    return [p.strip() for p in parts if p.strip()]


class _Builder:
    def __init__(self, scene: Scene, last_target: str | None):
        self.scene = scene.model_copy(deep=True)
        self.last_target = last_target
        self.ops: list[Op] = []
        self.notes: list[str] = []

    def emit(self, op: Op) -> None:
        # Keep a working copy updated so later clauses see earlier changes.
        self.scene, _, target = apply_ops(self.scene, [op])
        self.ops.append(op)
        self.last_target = target

    def layer_value(self, sound: str, key: str) -> float:
        layer = self.scene.layer(sound)
        return getattr(layer, key) if layer else 0.0


def _handle_clause(clause: str, b: _Builder) -> bool:
    """Interpret one clause. Returns True if it produced any ops."""
    before = len(b.ops)
    sounds = _find_sounds(clause)
    step = _step(clause)
    pan = _pan(clause)
    mentions_binaural = _has(BINAURAL_WORDS, clause)
    mentions_master = _has(MASTER_WORDS, clause)

    hz_match = re.search(r"(\d+(?:\.\d+)?)\s*(hz|hertz)", clause)
    band = next((name for pattern, name in BAND_ALIASES if _has(pattern, clause)), None)

    # 1. Clear everything.
    if _has(CLEAR, clause) and not sounds:
        b.emit(ClearLayers())
        return True

    # 2. Presets / whole scenes ("make it a storm", "cabin vibes", "sleep mode").
    preset_hits = [(m.start(), name) for pattern, name in PRESET_ALIASES if (m := re.search(rf"\b({pattern})\b", clause))]
    presets = [name for _, name in sorted(preset_hits)]
    if presets and not sounds and not mentions_binaural:
        # "cabin in a storm": the first preset sets the base, the rest layer on top.
        for i, preset in enumerate(presets):
            for op in PRESETS[preset]:
                if i > 0 and isinstance(op, ClearLayers):
                    continue
                b.emit(op)
        b.notes.append(f"set up a {' + '.join(presets)} scene")
        return True

    # 3. Binaural beat.
    if mentions_binaural or (band and not sounds):
        if _has(REMOVE, clause):
            b.emit(SetBinaural(enabled=False))
        elif hz_match:
            b.emit(SetBinaural(enabled=True, beat_hz=_clamp(float(hz_match.group(1)), 0.5, 45.0)))
        elif band:
            b.emit(SetBinaural(enabled=True, beat_hz=BINAURAL_BANDS[band]))
        elif _has(FASTER, clause) or _has(SLOWER, clause):
            _speed_binaural(clause, b)
        elif _has(QUIETER, clause):
            b.emit(SetBinaural(volume=_clamp(b.scene.binaural.volume - step)))
        elif _has(LOUDER, clause):
            b.emit(SetBinaural(enabled=True, volume=_clamp(b.scene.binaural.volume + step)))
        else:
            b.emit(SetBinaural(enabled=True))
        return True

    # 4. Explicitly named sounds.
    if sounds:
        for sound in sounds:
            _handle_sound(clause, sound, step, pan, b)
        return len(b.ops) > before

    # 5. Overall mix ("everything quieter", "warmer").
    if mentions_master or _has(WARMER, clause) or _has(BRIGHTER_MIX, clause):
        if _has(WARMER, clause):
            b.emit(SetMaster(warmth=_clamp(b.scene.master.warmth + step)))
        elif _has(BRIGHTER_MIX, clause):
            b.emit(SetMaster(warmth=_clamp(b.scene.master.warmth - step)))
        elif _has(QUIETER, clause):
            b.emit(SetMaster(volume=_clamp(b.scene.master.volume - step)))
        elif _has(LOUDER, clause):
            b.emit(SetMaster(volume=_clamp(b.scene.master.volume + step)))
        return len(b.ops) > before

    # 6. No object: apply to whatever the user touched last.
    target = b.last_target
    if target in SOUND_CATALOG and b.scene.layer(target):
        _handle_sound(clause, target, step, pan, b, implicit=True)
    elif target == "binaural" or _has(FASTER, clause) or _has(SLOWER, clause):
        # Nothing rhythmic was touched last, so tempo words drive the binaural beat.
        if _has(FASTER, clause) or _has(SLOWER, clause):
            _speed_binaural(clause, b)
        elif _has(QUIETER, clause):
            b.emit(SetBinaural(volume=_clamp(b.scene.binaural.volume - step)))
        elif _has(LOUDER, clause):
            b.emit(SetBinaural(volume=_clamp(b.scene.binaural.volume + step)))
    elif _has(QUIETER, clause):
        b.emit(SetMaster(volume=_clamp(b.scene.master.volume - step)))
    elif _has(LOUDER, clause):
        b.emit(SetMaster(volume=_clamp(b.scene.master.volume + step)))
    return len(b.ops) > before


def _speed_binaural(clause: str, b: _Builder) -> None:
    beat = b.scene.binaural.beat_hz
    factor = 1.5 if _step(clause) > 0.2 else 1.25
    new_beat = beat * factor if _has(FASTER, clause) else beat / factor
    b.emit(SetBinaural(enabled=True, beat_hz=_clamp(round(new_beat, 1), 0.5, 45.0)))


def _handle_sound(clause: str, sound: str, step: float, pan: float | None, b: _Builder, implicit: bool = False) -> None:
    playing = b.scene.layer(sound) is not None

    if _has(REMOVE, clause) and not _has(r"less", clause):
        b.emit(RemoveLayer(sound=sound))
        return

    updates: dict[str, float] = {}
    if _has(QUIETER, clause):
        updates["volume"] = _clamp(b.layer_value(sound, "volume") - step)
    elif _has(LOUDER, clause) and playing:
        updates["volume"] = _clamp(b.layer_value(sound, "volume") + step)
    if _has(STRONGER, clause):
        updates["intensity"] = _clamp(b.layer_value(sound, "intensity") + step)
        if not playing:
            updates["intensity"] = _clamp(0.5 + step)
    elif _has(WEAKER, clause):
        updates["intensity"] = _clamp((b.layer_value(sound, "intensity") if playing else 0.5) - step)
    if _has(FASTER, clause):
        updates["speed"] = _clamp((b.layer_value(sound, "speed") if playing else 0.5) + step)
    elif _has(SLOWER, clause):
        updates["speed"] = _clamp((b.layer_value(sound, "speed") if playing else 0.5) - step)
    if pan is not None:
        updates["pan"] = pan

    if not playing:
        if implicit:
            return
        # "add rain", "rain please", "some heavy rain on the left" all add it.
        if _has(QUIETER, clause) and "volume" in updates:
            updates["volume"] = 0.3
        b.emit(AddLayer(sound=sound, **updates))
    elif updates:
        b.emit(AdjustLayer(sound=sound, **updates))
    elif _has(ADD, clause) or _has(LOUDER, clause):
        b.emit(AdjustLayer(sound=sound, volume=_clamp(b.layer_value(sound, "volume") + step)))


def parse(text: str, scene: Scene, last_target: str | None = None) -> Interpretation:
    normalized = re.sub(r"[^a-z0-9.,;' ]+", " ", text.lower()).strip()
    builder = _Builder(scene, last_target)

    for clause in _split_clauses(normalized) or [normalized]:
        _handle_clause(clause, builder)

    if not builder.ops:
        return Interpretation(
            reply="I didn't catch that. Try \"add rain\", \"make the fire louder\", \"slower\", or \"cabin in a storm\".",
        )
    return Interpretation(ops=builder.ops, reply="; ".join(builder.notes))
