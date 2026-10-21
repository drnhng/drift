from dataclasses import dataclass, field

from app.scene import Op


@dataclass
class Interpretation:
    ops: list[Op] = field(default_factory=list)
    reply: str = ""
    source: str = "rules"
