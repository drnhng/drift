import logging

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ValidationError

from app.config import settings
from app.scene import BINAURAL_BANDS, PRESETS, SOUND_CATALOG, OpList, Scene
from app.session import Interpreter, Session

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Drift API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

interpreter = Interpreter(settings)


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "parser": interpreter.mode}


@app.get("/api/catalog")
def catalog() -> dict:
    return {"sounds": SOUND_CATALOG, "binaural_bands": BINAURAL_BANDS, "presets": list(PRESETS)}


class SceneMessage(BaseModel):
    """Server → client. Sent on connect and after every change."""

    type: str = "scene"
    scene: Scene
    changes: list[str] = []
    reply: str = ""
    source: str = ""
    command: str | None = None


@app.websocket("/ws")
async def soundscape_socket(ws: WebSocket) -> None:
    """Client → server messages:

    {"type": "command", "text": "add rain"}   natural language
    {"type": "ops", "ops": [...]}              direct ops (sliders)
    {"type": "reset"}
    """
    await ws.accept()
    session = Session(interpreter)
    await ws.send_json({"type": "hello", "parser": interpreter.mode})
    await ws.send_text(SceneMessage(scene=session.scene, source="initial").model_dump_json())

    try:
        while True:
            data = await ws.receive_json()
            kind = data.get("type")

            if kind == "command":
                text = str(data.get("text", "")).strip()[:500]
                if not text:
                    continue
                await ws.send_json({"type": "thinking", "command": text})
                result, changes = await session.command(text)
                reply = result.reply or (", ".join(changes).capitalize() + "." if changes else "")
                message = SceneMessage(
                    scene=session.scene, changes=changes, reply=reply, source=result.source, command=text
                )
            elif kind == "ops":
                try:
                    ops = OpList.model_validate({"ops": data.get("ops", [])}).ops
                except ValidationError as exc:
                    await ws.send_json({"type": "error", "message": str(exc.errors()[0]["msg"])})
                    continue
                changes = session.apply(ops)
                message = SceneMessage(scene=session.scene, changes=changes, source="manual")
            elif kind == "reset":
                session.scene = Scene()
                session.last_target = None
                message = SceneMessage(scene=session.scene, changes=["reset"], source="manual")
            else:
                await ws.send_json({"type": "error", "message": f"unknown message type: {kind}"})
                continue

            await ws.send_text(message.model_dump_json())
    except WebSocketDisconnect:
        pass
