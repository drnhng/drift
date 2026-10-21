import logging

from app.config import Settings
from app.parsers import rules
from app.parsers.base import Interpretation
from app.parsers.llm import LLMParser
from app.scene import Op, Scene, apply_ops

logger = logging.getLogger(__name__)


class Interpreter:
    """Uses the LLM when configured, and falls back to rules on any failure."""

    def __init__(self, settings: Settings):
        self.llm = LLMParser(settings) if settings.llm_api_key else None

    @property
    def mode(self) -> str:
        return "llm" if self.llm else "rules"

    async def interpret(self, text: str, scene: Scene, last_target: str | None) -> Interpretation:
        if self.llm:
            try:
                result = await self.llm.parse(text, scene, last_target)
                if result.ops:
                    return result
            except Exception:  # network errors, rate limits, malformed output
                logger.exception("LLM parse failed; falling back to rules")
        return rules.parse(text, scene, last_target)


class Session:
    """State for one connected listener."""

    def __init__(self, interpreter: Interpreter):
        self.interpreter = interpreter
        self.scene = Scene()
        self.last_target: str | None = None

    def apply(self, ops: list[Op]) -> list[str]:
        self.scene, changes, target = apply_ops(self.scene, ops)
        self.last_target = target
        return changes

    async def command(self, text: str) -> tuple[Interpretation, list[str]]:
        result = await self.interpreter.interpret(text, self.scene, self.last_target)
        changes = self.apply(result.ops) if result.ops else []
        return result, changes
