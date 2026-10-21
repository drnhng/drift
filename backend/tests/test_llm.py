import json
from types import SimpleNamespace

import pytest

from app.config import Settings
from app.parsers.llm import LLMParser
from app.scene import AddLayer, Scene, SetMaster
from app.session import Interpreter


def fake_response(args: dict):
    call = SimpleNamespace(function=SimpleNamespace(arguments=json.dumps(args)))
    message = SimpleNamespace(tool_calls=[call], content=None)
    return SimpleNamespace(choices=[SimpleNamespace(message=message)])


@pytest.fixture
def parser(monkeypatch):
    parser = LLMParser(Settings(llm_api_key="test"))

    def install(args: dict):
        async def create(**_kwargs):
            return fake_response(args)

        monkeypatch.setattr(parser.client.chat.completions, "create", create)

    return parser, install


async def test_valid_ops_are_parsed(parser):
    llm, install = parser
    install({
        "ops": [
            {"op": "add_layer", "sound": "rain", "volume": 0.4, "pan": None},
            {"op": "set_master", "warmth": 0.8},
        ],
        "reply": "Soft rain, warmer mix.",
    })
    result = await llm.parse("cozy rain", Scene(), None)
    assert result.ops == [AddLayer(sound="rain", volume=0.4), SetMaster(warmth=0.8)]
    assert result.reply == "Soft rain, warmer mix."


async def test_invalid_ops_are_dropped(parser):
    llm, install = parser
    install({
        "ops": [
            {"op": "add_layer", "sound": "lasers"},
            {"op": "adjust_layer", "sound": "fire", "volume": 7},
            {"op": "add_layer", "sound": "wind"},
        ],
        "reply": "ok",
    })
    result = await llm.parse("whatever", Scene(), None)
    assert result.ops == [AddLayer(sound="wind")]


async def test_interpreter_falls_back_to_rules_on_llm_failure(monkeypatch):
    interpreter = Interpreter(Settings(llm_api_key="test"))

    async def boom(**_kwargs):
        raise RuntimeError("rate limited")

    monkeypatch.setattr(interpreter.llm.client.chat.completions, "create", boom)
    result = await interpreter.interpret("add rain", Scene(), None)
    assert result.source == "rules"
    assert result.ops == [AddLayer(sound="rain")]
