import pytest

from app.parsers.rules import parse
from app.scene import Layer, Scene, apply_ops


def run(text: str, scene: Scene | None = None, last_target: str | None = None) -> tuple[Scene, str | None]:
    scene = scene or Scene()
    result = parse(text, scene, last_target)
    new_scene, _, target = apply_ops(scene, result.ops)
    return new_scene, target


def test_add_rain():
    scene, target = run("add rain")
    assert scene.layer("rain") is not None
    assert target == "rain"


def test_add_multiple_sounds_with_pan():
    scene, _ = run("add rain and a fireplace on the left")
    assert scene.layer("rain")
    assert scene.layer("fire").pan < 0


def test_wind_chimes_does_not_add_wind():
    scene, _ = run("add wind chimes")
    assert scene.layer("chimes")
    assert scene.layer("wind") is None


def test_heavier_rain_raises_intensity():
    start = Scene(layers=[Layer(sound="rain", intensity=0.5)])
    scene, _ = run("make the rain heavier", start)
    assert scene.layer("rain").intensity > 0.5


def test_implicit_target_uses_last_touched():
    start = Scene(layers=[Layer(sound="fire", volume=0.5)])
    scene, _ = run("too much", start, last_target="fire")
    assert scene.layer("fire").volume < 0.5


def test_remove_thunder():
    start = Scene(layers=[Layer(sound="thunder"), Layer(sound="rain")])
    scene, _ = run("remove the thunder, it's too much", start)
    assert scene.layer("thunder") is None
    assert scene.layer("rain") is not None


def test_faster_with_no_target_speeds_up_binaural():
    start = Scene()
    scene, _ = run("go faster", start)
    assert scene.binaural.beat_hz > start.binaural.beat_hz


def test_binaural_band_and_hz():
    assert run("binaural for focus")[0].binaural.beat_hz == 16
    assert run("set the beat to 10 hz")[0].binaural.beat_hz == 10


def test_combined_preset():
    scene, _ = run("cabin in a storm")
    assert {"fire", "rain", "thunder"} <= {layer.sound for layer in scene.layers}


def test_clear():
    start = Scene(layers=[Layer(sound="rain")])
    scene, _ = run("start over", start)
    assert scene.layers == []


@pytest.mark.parametrize("text", ["add a distant train", "hello"])
def test_unknown_returns_help(text):
    result = parse(text, Scene())
    assert result.ops == []
    assert "Try" in result.reply


def test_values_stay_in_range():
    start = Scene(layers=[Layer(sound="rain", volume=0.95)])
    scene, _ = run("make the rain a lot louder", start)
    assert scene.layer("rain").volume == 1.0
