"""LLM command parser using tool calling.

The model gets the current scene and must call `update_soundscape` with a list
of ops. Every op is validated by Pydantic before it can touch the scene; invalid
ops are dropped rather than trusted.
"""

import json
import logging

from openai import AsyncOpenAI
from pydantic import TypeAdapter, ValidationError

from app.config import Settings
from app.parsers.base import Interpretation
from app.scene import BINAURAL_BANDS, SOUND_CATALOG, Op, Scene

logger = logging.getLogger(__name__)

_op_adapter: TypeAdapter[Op] = TypeAdapter(Op)

UPDATE_TOOL = {
    "type": "function",
    "function": {
        "name": "update_soundscape",
        "description": "Apply changes to the live soundscape. Values are absolute (not deltas).",
        "parameters": {
            "type": "object",
            "properties": {
                "ops": {
                    "type": "array",
                    "description": "Operations applied in order.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "op": {
                                "type": "string",
                                "enum": ["add_layer", "remove_layer", "adjust_layer", "set_binaural", "set_master", "clear_layers"],
                            },
                            "sound": {"type": "string", "enum": list(SOUND_CATALOG)},
                            "volume": {"type": "number", "description": "0 to 1"},
                            "intensity": {"type": "number", "description": "0 to 1"},
                            "speed": {"type": "number", "description": "0 to 1"},
                            "pan": {"type": "number", "description": "-1 (left) to 1 (right)"},
                            "enabled": {"type": "boolean", "description": "set_binaural only"},
                            "beat_hz": {"type": "number", "description": "set_binaural only, 0.5 to 45"},
                            "carrier_hz": {"type": "number", "description": "set_binaural only, 60 to 600"},
                            "warmth": {"type": "number", "description": "set_master only, 0 bright to 1 muffled"},
                        },
                        "required": ["op"],
                    },
                },
                "reply": {
                    "type": "string",
                    "description": "One short, calm sentence telling the user what changed.",
                },
            },
            "required": ["ops", "reply"],
        },
    },
}


def _system_prompt(scene: Scene, last_target: str | None) -> str:
    sounds = "\n".join(
        f"- {name}: {info['label']} (intensity = {info['intensity']}; speed = {info['speed']})"
        for name, info in SOUND_CATALOG.items()
    )
    bands = ", ".join(f"{band} ≈ {hz:g} Hz" for band, hz in BINAURAL_BANDS.items())
    return f"""You control a live ambient soundscape app called Drift. Translate the user's request into operations by calling update_soundscape.

Available sounds (you cannot add anything else):
{sounds}

Binaural beat: a separate always-available layer. beat_hz bands: {bands}.
Master: overall volume and warmth (low-pass, cozy/muffled).

Rules:
- Values are absolute. Read the current scene and compute new values. Default step is 0.2; "a bit"/"slightly" is 0.1; "a lot"/"much" is 0.35. Stay within ranges.
- "faster"/"slower" with no named sound applies to the last touched target; if that is the binaural beat or nothing, change beat_hz (multiply or divide by ~1.25).
- Vague words ("more", "too much", "louder") with no named sound refer to the last touched target: {last_target or "none"}.
- Never refuse and never return zero ops. Any prompt (a place, memory, mood, color, smell, person, song, movie, abstract idea, even nonsense) gets your most evocative interpretation with the available sounds.
- For whole scenes or moods ("cabin in a storm", "grandma's house", "a volcano", "feeling anxious") compose 2-5 layers with clear_layers first, and set warmth and the binaural band to suit the mood.
- If they ask for a sound that isn't available, approximate it creatively (a train = brown noise + wind, a crowd = pink noise, a volcano = fire + thunder + brown noise) and say so briefly in the reply.
- Keep the reply under 20 words.

Current scene:
{scene.model_dump_json()}"""


class LLMParser:
    def __init__(self, settings: Settings):
        self.model = settings.llm_model
        self.client = AsyncOpenAI(
            api_key=settings.llm_api_key,
            base_url=settings.llm_base_url,
            timeout=settings.llm_timeout_seconds,
            max_retries=0,
        )

    async def parse(self, text: str, scene: Scene, last_target: str | None) -> Interpretation:
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": _system_prompt(scene, last_target)},
                {"role": "user", "content": text},
            ],
            tools=[UPDATE_TOOL],
            tool_choice="required",
            temperature=0.2,
        )
        message = response.choices[0].message
        if not message.tool_calls:
            return Interpretation(reply=message.content or "", source="llm")

        args = json.loads(message.tool_calls[0].function.arguments or "{}")
        ops: list[Op] = []
        for raw in args.get("ops", []):
            # Models sometimes send null for unused fields; drop them before validating.
            cleaned = {k: v for k, v in raw.items() if v is not None}
            try:
                ops.append(_op_adapter.validate_python(cleaned))
            except ValidationError as exc:
                logger.warning("Dropping invalid op from LLM: %s (%s)", raw, exc.errors()[0]["msg"])
        return Interpretation(ops=ops, reply=args.get("reply", ""), source="llm")
