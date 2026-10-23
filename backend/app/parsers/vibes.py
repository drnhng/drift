"""Best-effort mapping from places, moods and memories to a mix of sounds.

Used by the rule parser when a prompt names no sound directly ("make it feel
like grandma's house", "volcano"). Each vibe is a recipe of layers; when a
prompt matches several vibes their recipes are blended.
"""

import re
from dataclasses import dataclass, field

from app.scene import BINAURAL_BANDS, AddLayer, ClearLayers, Op, SetBinaural, SetMaster

# sound -> (volume, intensity, speed)
Recipe = dict[str, tuple[float, float, float]]


@dataclass
class Vibe:
    name: str
    pattern: str
    layers: Recipe
    warmth: float | None = None
    beat_hz: float | None = None
    aliases: list[str] = field(default_factory=list)


VIBES: list[Vibe] = [
    Vibe("storm", r"storm|stormy|thunderstorm|hurricane|typhoon|monsoon",
         {"rain": (0.7, 0.85, 0.7), "thunder": (0.55, 0.6, 0.4), "wind": (0.4, 0.6, 0.5)}),
    Vibe("beach", r"beach|seaside|coast|shore|tide",
         {"ocean": (0.7, 0.5, 0.4), "wind": (0.2, 0.3, 0.4), "birds": (0.15, 0.3, 0.2)}),
    Vibe("forest", r"forest|woodland|grove|jungle floor",
         {"birds": (0.45, 0.5, 0.5), "stream": (0.4, 0.4, 0.5), "wind": (0.2, 0.25, 0.3)}),
    Vibe("night", r"night(time)?|evening|midnight|late|bedroom",
         {"crickets": (0.4, 0.5, 0.5), "wind": (0.15, 0.2, 0.2), "drone": (0.2, 0.2, 0.2)}, warmth=0.7),
    Vibe("sleep", r"sleep\w*|bedtime|nap|drift off|insomnia|tired",
         {"rain": (0.35, 0.35, 0.35), "drone": (0.25, 0.15, 0.15)}, warmth=0.85, beat_hz=BINAURAL_BANDS["delta"]),
    Vibe("volcano", r"volcan\w*|lava|magma|erupt\w*|inferno|hell",
         {"fire": (0.65, 0.9, 0.8), "brown_noise": (0.5, 0.3, 0.5), "thunder": (0.5, 0.8, 0.7), "drone": (0.3, 0.2, 0.3)},
         warmth=0.75),
    Vibe("home", r"grand(ma|pa|mother|father|parents)'?s?|nana'?s?|home|house|cottage|kitchen|living ?room|"
         r"nostalgi\w*|childhood|cozy|cosy|hygge|blanket|cocoa|tea",
         {"fire": (0.4, 0.4, 0.4), "rain": (0.25, 0.3, 0.3), "chimes": (0.12, 0.3, 0.15), "drone": (0.15, 0.15, 0.2)},
         warmth=0.85),
    Vibe("space", r"space|cosmos|cosmic|stars?|galaxy|universe|nebula|astronaut|orbit|planet|moon",
         {"drone": (0.5, 0.25, 0.15), "brown_noise": (0.2, 0.2, 0.5), "chimes": (0.1, 0.8, 0.1)},
         warmth=0.6, beat_hz=BINAURAL_BANDS["theta"]),
    Vibe("underwater", r"under ?water|ocean floor|deep sea|submarine|scuba|diving|aquarium|whale",
         {"ocean": (0.45, 0.3, 0.2), "brown_noise": (0.45, 0.15, 0.5), "drone": (0.3, 0.1, 0.1)},
         warmth=0.95),
    Vibe("travel", r"train|plane|airplane|flight|car ride|road ?trip|bus|subway|commute|cabin pressure",
         {"brown_noise": (0.55, 0.35, 0.5), "wind": (0.2, 0.3, 0.3), "drone": (0.15, 0.2, 0.2)},
         warmth=0.7),
    Vibe("city", r"city|street|urban|traffic|downtown|tokyo|new york|london|paris|apartment|rooftop",
         {"pink_noise": (0.3, 0.4, 0.5), "rain": (0.3, 0.4, 0.4), "wind": (0.15, 0.3, 0.3)},
         warmth=0.6),
    Vibe("cafe", r"caf[eé]|coffee( shop)?|bakery|diner|restaurant|bar|pub",
         {"pink_noise": (0.35, 0.35, 0.5), "rain": (0.2, 0.3, 0.3), "chimes": (0.08, 0.3, 0.1)},
         warmth=0.75),
    Vibe("jungle", r"jungle|rain ?forest|tropic\w*|amazon|island|paradise",
         {"rain": (0.35, 0.4, 0.5), "birds": (0.4, 0.6, 0.6), "crickets": (0.3, 0.5, 0.5), "stream": (0.3, 0.5, 0.5)}),
    Vibe("desert", r"desert|sahara|dunes?|canyon|wasteland",
         {"wind": (0.55, 0.6, 0.4), "crickets": (0.15, 0.3, 0.3)}, warmth=0.4),
    Vibe("winter", r"snow\w*|winter|blizzard|cold|arctic|ice|icy|frozen|mountain|alps|christmas",
         {"wind": (0.55, 0.7, 0.5), "chimes": (0.12, 0.5, 0.2), "fire": (0.2, 0.3, 0.3)}, warmth=0.45),
    Vibe("meadow", r"summer|meadow|garden|park|spring|picnic|field|farm|countryside|sunny",
         {"birds": (0.45, 0.5, 0.5), "wind": (0.15, 0.2, 0.3), "crickets": (0.15, 0.3, 0.4), "stream": (0.2, 0.3, 0.4)}),
    Vibe("temple", r"temple|monastery|zen|shrine|spa|yoga|massage|sauna|buddh\w*",
         {"chimes": (0.3, 0.4, 0.25), "drone": (0.35, 0.2, 0.15), "stream": (0.25, 0.3, 0.4)},
         warmth=0.7, beat_hz=BINAURAL_BANDS["theta"]),
    Vibe("camping", r"camp\w*|tent|bonfire|cabin|lodge|woods|hike|hiking|treehouse",
         {"fire": (0.5, 0.5, 0.5), "crickets": (0.35, 0.5, 0.5), "wind": (0.2, 0.3, 0.3)}, warmth=0.7),
    Vibe("lake", r"lake|pond|dock|riverbank|canoe|kayak|fishing",
         {"stream": (0.3, 0.3, 0.4), "birds": (0.25, 0.4, 0.3), "crickets": (0.2, 0.4, 0.4)}),
    Vibe("waterfall", r"waterfalls?|falls|rapids|niagara",
         {"stream": (0.6, 0.95, 0.8), "white_noise": (0.25, 0.6, 0.5), "birds": (0.15, 0.3, 0.3)}),
    Vibe("sea", r"ship|boat|sailing|sail|pirate|harbou?r|port|pier|lighthouse|cruise|seagull",
         {"ocean": (0.6, 0.6, 0.5), "wind": (0.35, 0.5, 0.5), "chimes": (0.1, 0.2, 0.15)}),
    Vibe("library", r"library|study(ing)?|homework|exam|reading|book|office|work(ing)?|coding|productiv\w*",
         {"brown_noise": (0.4, 0.35, 0.5), "rain": (0.25, 0.3, 0.3)}, beat_hz=BINAURAL_BANDS["beta"]),
    Vibe("dream", r"dream\w*|ethereal|heaven\w*|clouds?|float\w*|angel\w*|magic\w*|fairy|enchant\w*",
         {"drone": (0.4, 0.3, 0.15), "chimes": (0.25, 0.6, 0.25), "wind": (0.1, 0.2, 0.2)},
         warmth=0.65, beat_hz=BINAURAL_BANDS["alpha"]),
    Vibe("spooky", r"spook\w*|haunt\w*|horror|creepy|scary|halloween|ghost\w*|graveyard|eerie|dark",
         {"wind": (0.45, 0.6, 0.3), "drone": (0.3, 0.1, 0.1), "thunder": (0.3, 0.5, 0.3), "crickets": (0.15, 0.3, 0.3)},
         warmth=0.8),
    Vibe("calm", r"anxi\w*|stress\w*|overwhelm\w*|overstimulat\w*|panic\w*|calm( down)?|chill|peace\w*|"
         r"breathe|safe|soothing|gentle|quiet",
         {"rain": (0.3, 0.3, 0.3), "brown_noise": (0.25, 0.25, 0.5), "drone": (0.15, 0.15, 0.15)},
         warmth=0.85, beat_hz=BINAURAL_BANDS["alpha"]),
    Vibe("happy", r"happy|joy\w*|cheer\w*|upbeat|bright|morning|sunrise|fresh|hopeful",
         {"birds": (0.45, 0.6, 0.6), "stream": (0.3, 0.4, 0.6), "chimes": (0.2, 0.6, 0.4)}, warmth=0.35),
    Vibe("sad", r"sad|melanchol\w*|lonely|grief|blue|heartbreak|cry\w*|miss(ing)? (someone|you|them)",
         {"rain": (0.45, 0.4, 0.4), "drone": (0.25, 0.15, 0.1)}, warmth=0.8),
    Vibe("energy", r"energ\w*|workout|gym|hype|pump\w*|motivat\w*|power",
         {"white_noise": (0.25, 0.6, 0.5), "wind": (0.25, 0.6, 0.7)}, beat_hz=BINAURAL_BANDS["gamma"]),
    Vibe("tokyo-rain", r"neon|cyberpunk|blade runner|lo-?fi|lofi|vaporwave",
         {"rain": (0.5, 0.55, 0.5), "drone": (0.3, 0.4, 0.2), "thunder": (0.15, 0.3, 0.2)}, warmth=0.6),
]

# Used when nothing at all is recognized: a soft, neutral bed people can steer from.
FALLBACK = Vibe("ambient", "", {"rain": (0.3, 0.35, 0.35), "wind": (0.15, 0.25, 0.3), "drone": (0.2, 0.2, 0.15)},
                warmth=0.7)


def match_vibes(text: str) -> list[Vibe]:
    hits = []
    for vibe in VIBES:
        match = re.search(rf"\b({vibe.pattern})\b", text)
        if match:
            hits.append((match.start(), vibe))
    return [vibe for _, vibe in sorted(hits, key=lambda h: h[0])]


def blend(vibes: list[Vibe], extra_sounds: list[str] = ()) -> list[Op]:
    """Merge recipes: the loudest version of each sound wins; settings are averaged.

    `extra_sounds` are sounds the prompt named directly ("rainy ..."); they always make the cut.
    """
    layers: Recipe = {sound: (0.5, 0.5, 0.5) for sound in extra_sounds}
    for vibe in vibes:
        for sound, (volume, intensity, speed) in vibe.layers.items():
            if sound not in layers or volume > layers[sound][0]:
                layers[sound] = (volume, intensity, speed)

    # Keep it from getting muddy when many vibes stack up.
    loudest = sorted(layers.items(), key=lambda item: (item[0] not in extra_sounds, -item[1][0]))[:5]

    ops: list[Op] = [ClearLayers()]
    for sound, (volume, intensity, speed) in loudest:
        ops.append(AddLayer(sound=sound, volume=volume, intensity=intensity, speed=speed))

    warmths = [v.warmth for v in vibes if v.warmth is not None]
    if warmths:
        ops.append(SetMaster(warmth=round(sum(warmths) / len(warmths), 2)))
    beat = next((v.beat_hz for v in vibes if v.beat_hz is not None), None)
    if beat is not None:
        ops.append(SetBinaural(enabled=True, beat_hz=beat))
    return ops
