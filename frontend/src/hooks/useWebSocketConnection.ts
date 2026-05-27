import { useCallback, useEffect, useRef } from "react";
import { type WsClientMessage, type WsServerMessage } from "../lib/api";
import { createLogger } from "../lib/logger";

type MessageHandler = (payload: WsServerMessage) => void;
type SendOptions = {
  queueIfDisconnected?: boolean;
};

const KNOWN_SERVER_MESSAGE_TYPES = new Set<WsServerMessage["type"]>([
  "snapshot",
  "status",
  "notification",
  "conversation_turn",
  "close_window_after",
  "feedback_processing",
  "recognized_action",
  "transcript_partial",
  "transcript_final",
  "protocol_error",
  "pong",
]);

const logger = createLogger("useWebSocketConnection");

function parseServerMessage(raw: string): WsServerMessage | null {
  const payload = JSON.parse(raw) as Partial<WsServerMessage>;
  if (!payload || typeof payload !== "object" || typeof payload.type !== "string") {
    throw new Error("WebSocket payload is missing a string type field.");
  }
  if (!KNOWN_SERVER_MESSAGE_TYPES.has(payload.type as WsServerMessage["type"])) {
    throw new Error(`Unknown WebSocket server message type: ${payload.type}`);
  }
  return payload as WsServerMessage;
}

export function useWebSocketConnection(
  onMessage: MessageHandler,
  getWebSocketUrl: () => Promise<string>,
  enabled = true,
) {
  const wsRef = useRef<WebSocket | null>(null);
  const onMessageRef = useRef<MessageHandler>(onMessage);
  const queuedMessagesRef = useRef<Array<{ key: string; message: WsClientMessage }>>([]);
  const reconnectAttemptRef = useRef(0);

  useEffect(() => {
    onMessageRef.current = onMessage;
  }, [onMessage]);

  const sendWsMessage = useCallback((message: WsClientMessage, options?: SendOptions) => {
    const ws = wsRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN) {
      if (options?.queueIfDisconnected) {
        const key = JSON.stringify(message);
        const alreadyQueued = queuedMessagesRef.current.some((entry) => entry.key === key);
        if (!alreadyQueued) {
          queuedMessagesRef.current.push({ key, message });
        }
        logger.warn("Queueing websocket message until socket reconnects.", {
          messageType: message.type,
          queuedCount: queuedMessagesRef.current.length,
          reconnectAttempt: reconnectAttemptRef.current,
        });
        return;
      }

      logger.warn("Dropping websocket message because socket is not open.", {
        messageType: message.type,
        readyState: ws?.readyState ?? "missing",
        reconnectAttempt: reconnectAttemptRef.current,
      });
      return;
    }
    ws.send(JSON.stringify(message));
  }, []);

  useEffect(() => {
    if (!enabled) {
      wsRef.current?.close();
      wsRef.current = null;
      return;
    }

    let shouldReconnect = true;
    let reconnectTimer: number | undefined;

    const scheduleReconnect = () => {
      if (!shouldReconnect) {
        return;
      }
      reconnectAttemptRef.current += 1;
      const baseDelayMs = Math.min(15000, 1000 * (2 ** Math.max(0, reconnectAttemptRef.current - 1)));
      const jitterMultiplier = 0.85 + Math.random() * 0.3;
      const delayMs = Math.round(baseDelayMs * jitterMultiplier);
      logger.info("Scheduling websocket reconnect.", {
        attempt: reconnectAttemptRef.current,
        delayMs,
      });
      reconnectTimer = window.setTimeout(() => {
        void connect();
      }, delayMs);
    };

    const connect = async () => {
      let websocketUrl: string;
      try {
        websocketUrl = await getWebSocketUrl();
      } catch (error) {
        logger.error("Failed to obtain websocket URL.", error, {
          reconnectAttempt: reconnectAttemptRef.current,
        });
        scheduleReconnect();
        return;
      }

      if (!shouldReconnect) {
        return;
      }

      const ws = new WebSocket(websocketUrl);
      wsRef.current = ws;
      logger.info("Opening websocket connection.", {
        reconnectAttempt: reconnectAttemptRef.current,
      });

      ws.onopen = () => {
        reconnectAttemptRef.current = 0;
        ws.send(JSON.stringify({ type: "ping" } satisfies WsClientMessage));
        logger.info("Websocket connection opened.");
        if (queuedMessagesRef.current.length > 0) {
          const queued = [...queuedMessagesRef.current];
          queuedMessagesRef.current = [];
          logger.info("Flushing queued websocket messages.", {
            queuedCount: queued.length,
          });
          queued.forEach(({ message }) => {
            ws.send(JSON.stringify(message));
          });
        }
      };

      ws.onmessage = (event) => {
        try {
          const payload = parseServerMessage(String(event.data));
          if (payload === null) {
            return;
          }
          onMessageRef.current(payload);
        } catch (error) {
          logger.error("Failed to parse websocket message.", error, {
            rawPayloadType: typeof event.data,
            rawPayloadPreview: String(event.data).slice(0, 240),
          });
        }
      };

      ws.onerror = () => {
        ws.close();
      };

      ws.onclose = () => {
        if (!shouldReconnect) {
          return;
        }
        scheduleReconnect();
      };
    };

    void connect();

    return () => {
      shouldReconnect = false;
      if (reconnectTimer) {
        window.clearTimeout(reconnectTimer);
      }
      wsRef.current?.close();
      wsRef.current = null;
    };
  }, [enabled, getWebSocketUrl]);

  return { sendWsMessage };
}
