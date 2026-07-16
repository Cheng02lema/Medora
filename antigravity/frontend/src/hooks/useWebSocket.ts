import { useEffect, useRef, useState } from "react";
import { connectProgressSocket, type WSMessage } from "../api/client";

interface UseWebSocketOptions {
  onMessage: (msg: WSMessage) => void;
}

/**
 * WebSocket 连接管理 + 自动重连。
 *
 * - 连接成功 → onMessage(msg)
 * - 连接断开 → 1s/2s/4s/8s 指数退避重连，最多 5 次
 * - 重连中 → 返回 isReconnecting
 * - 彻底失败 → 返回 isDisconnected
 */
export function useWebSocket({ onMessage }: UseWebSocketOptions) {
  const [isReconnecting, setIsReconnecting] = useState(false);
  const [isDisconnected, setIsDisconnected] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);
  const retryCount = useRef(0);
  const retryTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const wasConnectedOnce = useRef(false);
  const onMessageRef = useRef(onMessage);

  useEffect(() => {
    onMessageRef.current = onMessage;
  }, [onMessage]);

  useEffect(() => {
    const connect = () => {
      const ws = connectProgressSocket((msg) => {
        onMessageRef.current(msg);
      });

      wsRef.current = ws;

      ws.onopen = () => {
        retryCount.current = 0;
        setIsReconnecting(false);
        setIsDisconnected(false);
        // 重连后触发数据刷新
        if (wasConnectedOnce.current) {
          document.dispatchEvent(new CustomEvent("medora:reconnected"));
        }
        wasConnectedOnce.current = true;
      };

      ws.onclose = () => {
        if (retryCount.current >= 5) {
          setIsDisconnected(true);
          setIsReconnecting(false);
          return;
        }
        setIsReconnecting(true);
        const delay = Math.pow(2, retryCount.current) * 1000; // 1s, 2s, 4s, 8s, 16s
        retryCount.current++;
        retryTimer.current = setTimeout(connect, delay);
      };

      ws.onerror = () => {
        // onclose 会处理重连
      };
    };

    connect();

    return () => {
      if (retryTimer.current) clearTimeout(retryTimer.current);
      wsRef.current?.close();
    };
  }, []);

  return { isReconnecting, isDisconnected };
}
