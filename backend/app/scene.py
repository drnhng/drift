"""Scene model: the single source of truth for what the user hears.

The LLM and the rule parser never touch audio. They emit validated `Op`s,
and `apply_ops` turns those into a new `Scene`. The frontend renders the
scene with smooth ramps.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, Field

# Every sound is synthesized procedurally in the browser, so the catalog is
# just names plus what each parameter means for that sound.
SOUND_CATALOG: dict[str, dict[str, str]] = {
    "rain": {"label": "Rain", "intensity": "drizzle → downpour", "speed": "drop rate"},
    "thunder": {"label": "Thunder", "intensity": "how loud the rumbles get", "speed": "how often it rumbles"},
    "wind": {"label": "Wind", "intensity": "breeze → gale", "speed": "how fast gusts come and go"},
    "ocean": {"label": "Ocean waves", "intensity": "wave size", "speed": "wave tempo"},
    "fire": {"label": "Fireplace", "intensity": "crackle loudness", "speed": "crackle rate"},
    "stream": {"label": "Stream", "intensity": "trickle → rushing river", "speed": "flow speed"},
    "birds": {"label": "Birds", "intensity": "chirp loudness", "speed": "how often birds sing"},
    "crickets": {"label": "Crickets", "intensity": "chorus density", "speed": "chirp rate"},
    "chimes": {"label": "Wind chimes", "intensity": "brightness", "speed": "how often they ring"},
    "drone": {"label": "Warm drone", "intensity": "brightness", "speed": "slow swell rate"},
    "white_noise": {"label": "White noise", "intensity": "brightness", "speed": "unused"},
    "pink_noise": {"label": "Pink noise", "intensity": "brightness", "speed": "unused"},
    "brown_noise": {"label": "Brown noise", "intensity": "brightness", "speed": "unused"},
}

SoundName = Literal[
    "rain", "thunder", "wind", "ocean", "fire", "stream", "birds",
    "crickets", "chimes", "drone", "white_noise", "pink_noise", "brown_noise",
]

# Brainwave bands commonly associated with binaural beat frequencies.
BINAURAL_BANDS: dict[str, float] = {
    "delta": 2.0,   # deep sleep
    "theta": 6.0,   # meditation
    "alpha": 10.0,  # relaxed
    "beta": 16.0,   # focus
    "gamma": 40.0,
}

Unit = Annotated[float, Field(ge=0.0, le=1.0)]
Pan = Annotated[float, Field(ge=-1.0, le=1.0)]


class Layer(BaseModel):
    sound: SoundName
    volume: Unit = 0.5
    intensity: Unit = 0.5
    speed: Unit = 0.5
    pan: Pan = 0.0


class Binaural(BaseModel):
    enabled: bool = True
    carrier_hz: Annotated[float, Field(ge=60.0, le=600.0)] = 200.0
    beat_hz: Annotated[float, Field(ge=0.5, le=45.0)] = 6.0
    volume: Unit = 0.25


class Master(BaseModel):
    volume: Unit = 0.8
    warmth: Unit = 0.5  # 0 = bright, 1 = muffled/cozy (low-pass filter)


class Scene(BaseModel):
    binaural: Binaural = Field(default_factory=Binaural)
    layers: list[Layer] = Field(default_factory=list)
    master: Master = Field(default_factory=Master)

    def layer(self, sound: str) -> Layer | None:
        return next((layer for layer in self.layers if layer.sound == sound), None)


# --- Operations -------------------------------------------------------------


class AddLayer(BaseModel):
    op: Literal["add_layer"] = "add_layer"
    sound: SoundName
    volume: Unit | None = None
    intensity: Unit | None = None
    speed: Unit | None = None
    pan: Pan | None = None


class RemoveLayer(BaseModel):
    op: Literal["remove_layer"] = "remove_layer"
    sound: SoundName


class AdjustLayer(BaseModel):
    op: Literal["adjust_layer"] = "adjust_layer"
    sound: SoundName
    volume: Unit | None = None
    intensity: Unit | None = None
    speed: Unit | None = None
    pan: Pan | None = None


class SetBinaural(BaseModel):
    op: Literal["set_binaural"] = "set_binaural"
    enabled: bool | None = None
    carrier_hz: Annotated[float, Field(ge=60.0, le=600.0)] | None = None
    beat_hz: Annotated[float, Field(ge=0.5, le=45.0)] | None = None
    volume: Unit | None = None


class SetMaster(BaseModel):
    op: Literal["set_master"] = "set_master"
    volume: Unit | None = None
    warmth: Unit | None = None


class ClearLayers(BaseModel):
    op: Literal["clear_layers"] = "clear_layers"


Op = Annotated[
    AddLayer | RemoveLayer | AdjustLayer | SetBinaural | SetMaster | ClearLayers,
    Field(discriminator="op"),
]


class OpList(BaseModel):
    ops: list[Op]


def _fields(op: BaseModel, exclude: set[str]) -> dict:
    return {k: v for k, v in op.model_dump(exclude=exclude).items() if v is not None}


def _label(sound: str) -> str:
    return SOUND_CATALOG[sound]["label"].lower()


def apply_ops(scene: Scene, ops: list[Op]) -> tuple[Scene, list[str], str | None]:
    """Apply ops to a copy of the scene.

    Returns (new_scene, human-readable changes, last touched target).
    """
    scene = scene.model_copy(deep=True)
    changes: list[str] = []
    target: str | None = None

    for op in ops:
        match op:
            case AddLayer():
                existing = scene.layer(op.sound)
                updates = _fields(op, {"op", "sound"})
                if existing:
                    for key, value in updates.items():
                        setattr(existing, key, value)
                    changes.append(f"adjusted {_label(op.sound)}")
                else:
                    scene.layers.append(Layer(sound=op.sound, **updates))
                    changes.append(f"added {_label(op.sound)}")
                target = op.sound
            case RemoveLayer():
                if scene.layer(op.sound):
                    scene.layers = [layer for layer in scene.layers if layer.sound != op.sound]
                    changes.append(f"removed {_label(op.sound)}")
                target = None
            case AdjustLayer():
                existing = scene.layer(op.sound)
                updates = _fields(op, {"op", "sound"})
                if existing is None:
                    # Adjusting a sound that isn't playing yet means "bring it in".
                    scene.layers.append(Layer(sound=op.sound, **updates))
                    changes.append(f"added {_label(op.sound)}")
                else:
                    for key, value in updates.items():
                        setattr(existing, key, value)
                    changes.append(f"adjusted {_label(op.sound)}")
                target = op.sound
            case SetBinaural():
                was_enabled = scene.binaural.enabled
                for key, value in _fields(op, {"op"}).items():
                    setattr(scene.binaural, key, value)
                if scene.binaural.enabled != was_enabled:
                    changes.append("binaural beat " + ("on" if scene.binaural.enabled else "off"))
                else:
                    changes.append(f"binaural beat at {scene.binaural.beat_hz:g} Hz")
                target = "binaural"
            case SetMaster():
                for key, value in _fields(op, {"op"}).items():
                    setattr(scene.master, key, value)
                changes.append("adjusted overall mix")
                target = "master"
            case ClearLayers():
                scene.layers = []
                changes.append("cleared all layers")
                target = None

    # Re-validate so out-of-range values can never reach the client.
    return Scene.model_validate(scene.model_dump()), changes, target


# --- Presets ----------------------------------------------------------------

PRESETS: dict[str, list[Op]] = {
    "storm": [
        ClearLayers(),
        AddLayer(sound="rain", volume=0.7, intensity=0.85, speed=0.7),
        AddLayer(sound="thunder", volume=0.55, intensity=0.6, speed=0.4),
        AddLayer(sound="wind", volume=0.4, intensity=0.6, speed=0.5),
    ],
    "cabin": [
        ClearLayers(),
        AddLayer(sound="rain", volume=0.45, intensity=0.5, speed=0.5),
        AddLayer(sound="fire", volume=0.55, intensity=0.5, speed=0.5, pan=-0.3),
        AddLayer(sound="wind", volume=0.2, intensity=0.3, speed=0.3),
        SetMaster(warmth=0.75),
    ],
    "beach": [
        ClearLayers(),
        AddLayer(sound="ocean", volume=0.7, intensity=0.5, speed=0.4),
        AddLayer(sound="wind", volume=0.2, intensity=0.3, speed=0.4),
        AddLayer(sound="birds", volume=0.15, intensity=0.3, speed=0.2, pan=0.4),
    ],
    "forest": [
        ClearLayers(),
        AddLayer(sound="birds", volume=0.45, intensity=0.5, speed=0.5),
        AddLayer(sound="stream", volume=0.4, intensity=0.4, speed=0.5, pan=-0.3),
        AddLayer(sound="wind", volume=0.2, intensity=0.25, speed=0.3),
    ],
    "night": [
        ClearLayers(),
        AddLayer(sound="crickets", volume=0.45, intensity=0.5, speed=0.5),
        AddLayer(sound="wind", volume=0.15, intensity=0.2, speed=0.2),
        AddLayer(sound="drone", volume=0.2, intensity=0.2, speed=0.2),
        SetMaster(warmth=0.7),
    ],
    "focus": [
        ClearLayers(),
        AddLayer(sound="brown_noise", volume=0.45, intensity=0.4),
        SetBinaural(enabled=True, beat_hz=BINAURAL_BANDS["beta"], volume=0.2),
    ],
    "sleep": [
        ClearLayers(),
        AddLayer(sound="rain", volume=0.35, intensity=0.35, speed=0.35),
        AddLayer(sound="drone", volume=0.25, intensity=0.15, speed=0.15),
        SetBinaural(enabled=True, beat_hz=BINAURAL_BANDS["delta"], volume=0.2),
        SetMaster(warmth=0.85),
    ],
}
