"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { DEFAULT_SCENE, applyOpLocally, type Op, type Scene, type ServerMessage } from "@/lib/scene";

export type ConnectionStatus = "connecting" | "open" | "closed";

export type LogEntry = {
  id: number;
  command: string;
  reply: string;
  source: string;
};

export type SceneState = {
  scene: Scene;
  /** Seconds the audio engine should take to reach this scene. */
  ramp: number;
};

const SLIDER_RAMP = 0.15;
const COMMAND_RAMP = 2.5;
// Ignore server echoes of slider moves briefly so a dragged slider doesn't jitter.
const LOCAL_EDIT_GRACE_MS = 400;

export function useDriftSocket(url: string) {
  const [status, setStatus] = useState<ConnectionStatus>("connecting");
  const [parser, setParser] = useState<"llm" | "rules" | null>(null);
  const [state, setState] = useState<SceneState>({ scene: DEFAULT_SCENE, ramp: COMMAND_RAMP });
  const [log, setLog] = useState<LogEntry[]>([]);
  const [thinking, setThinking] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const wsRef = useRef<WebSocket | null>(null);
  const lastLocalEdit = useRef(0);
  const logId = useRef(0);

  useEffect(() => {
    let cancelled = false;
    let retry = 0;
    let timer: ReturnType<typeof setTimeout> | undefined;

    const connect = () => {
      setStatus("connecting");
      const ws = new WebSocket(url);
      wsRef.current = ws;

      ws.onopen = () => {
        retry = 0;
        setStatus("open");
        setError(null);
      };

      ws.onmessage = (event) => {
        const msg = JSON.parse(event.data) as ServerMessage;
        switch (msg.type) {
          case "hello":
            setParser(msg.parser);
            break;
          case "thinking":
            setThinking(true);
            break;
          case "error":
            setThinking(false);
            setError(msg.message);
            break;
          case "scene": {
            const isEcho = msg.source === "manual" && Date.now() - lastLocalEdit.current < LOCAL_EDIT_GRACE_MS;
            if (!isEcho) setState({ scene: msg.scene, ramp: msg.source === "manual" ? SLIDER_RAMP : COMMAND_RAMP });
            if (msg.command) {
              setThinking(false);
              setLog((prev) =>
                [...prev, { id: ++logId.current, command: msg.command!, reply: msg.reply, source: msg.source }].slice(-6),
              );
            }
            break;
          }
        }
      };

      ws.onclose = () => {
        if (cancelled) return;
        setStatus("closed");
        setThinking(false);
        // Exponential backoff, capped at 10s.
        timer = setTimeout(connect, Math.min(10000, 500 * 2 ** retry++));
      };
    };

    connect();
    return () => {
      cancelled = true;
      clearTimeout(timer);
      wsRef.current?.close();
    };
  }, [url]);

  const send = useCallback((payload: object) => {
    const ws = wsRef.current;
    if (ws?.readyState === WebSocket.OPEN) ws.send(JSON.stringify(payload));
  }, []);

  const sendCommand = useCallback(
    (text: string) => {
      setError(null);
      send({ type: "command", text });
    },
    [send],
  );

  const sendOps = useCallback(
    (ops: Op[]) => {
      lastLocalEdit.current = Date.now();
      setState((prev) => ({ scene: ops.reduce(applyOpLocally, prev.scene), ramp: SLIDER_RAMP }));
      send({ type: "ops", ops });
    },
    [send],
  );

  const reset = useCallback(() => send({ type: "reset" }), [send]);

  return { status, parser, ...state, log, thinking, error, sendCommand, sendOps, reset };
}
