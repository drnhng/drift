from fastapi.testclient import TestClient

from app.main import app


def test_websocket_command_round_trip():
    client = TestClient(app)
    with client.websocket_connect("/ws") as ws:
        assert ws.receive_json()["type"] == "hello"
        initial = ws.receive_json()
        assert initial["type"] == "scene"
        assert initial["scene"]["layers"] == []

        ws.send_json({"type": "command", "text": "add rain"})
        assert ws.receive_json()["type"] == "thinking"
        update = ws.receive_json()
        assert [layer["sound"] for layer in update["scene"]["layers"]] == ["rain"]
        assert update["reply"]


def test_websocket_direct_ops_are_validated():
    client = TestClient(app)
    with client.websocket_connect("/ws") as ws:
        ws.receive_json()
        ws.receive_json()
        ws.send_json({"type": "ops", "ops": [{"op": "add_layer", "sound": "lasers"}]})
        assert ws.receive_json()["type"] == "error"

        ws.send_json({"type": "ops", "ops": [{"op": "add_layer", "sound": "ocean", "volume": 0.3}]})
        scene = ws.receive_json()["scene"]
        assert scene["layers"][0]["volume"] == 0.3
