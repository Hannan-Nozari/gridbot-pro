"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type {
  BotStatusChange,
  PortfolioUpdate,
  PriceUpdate,
  TradeExecuted,
  WSMessage,
  WSMessageType,
} from "@/types";

const WS_URL =
  process.env.NEXT_PUBLIC_WS_URL ?? "ws://localhost:8000/ws";

const RECONNECT_INTERVAL = 3000;
const MAX_RECONNECT_INTERVAL = 30000;

interface UseWebSocketReturn {
  isConnected: boolean;
  lastMessage: WSMessage | null;
  priceUpdates: Map<string, PriceUpdate>;
  lastTrade: TradeExecuted | null;
  lastStatusChange: BotStatusChange | null;
  lastPortfolioUpdate: PortfolioUpdate | null;
}

export function useWebSocket(): UseWebSocketReturn {
  const [isConnected, setIsConnected] = useState(false);
  const [lastMessage, setLastMessage] = useState<WSMessage | null>(null);
  const [priceUpdates, setPriceUpdates] = useState<Map<string, PriceUpdate>>(
    () => new Map(),
  );
  const [lastTrade, setLastTrade] = useState<TradeExecuted | null>(null);
  const [lastStatusChange, setLastStatusChange] =
    useState<BotStatusChange | null>(null);
  const [lastPortfolioUpdate, setLastPortfolioUpdate] =
    useState<PortfolioUpdate | null>(null);

  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<ReturnType<typeof setTimeout>>(undefined);
  const reconnectDelayRef = useRef(RECONNECT_INTERVAL);

  const handleMessage = useCallback((event: MessageEvent) => {
    try {
      const msg: WSMessage = JSON.parse(event.data);
      setLastMessage(msg);

      switch (msg.type as WSMessageType) {
        case "price_update":
          setPriceUpdates((prev) => {
            const next = new Map(prev);
            const data = msg.data as PriceUpdate;
            next.set(data.symbol, data);
            return next;
          });
          break;
        case "trade_executed":
          setLastTrade(msg.data as TradeExecuted);
          break;
        case "bot_status_change":
          setLastStatusChange(msg.data as BotStatusChange);
          break;
        case "portfolio_update":
          setLastPortfolioUpdate(msg.data as PortfolioUpdate);
          break;
      }
    } catch {
      // ignore malformed messages
    }
  }, []);

  const connect = useCallback(() => {
    const token = localStorage.getItem("auth_token");
    if (!token) return;

    const url = `${WS_URL}?token=${encodeURIComponent(token)}`;
    const ws = new WebSocket(url);

    ws.onopen = () => {
      setIsConnected(true);
      reconnectDelayRef.current = RECONNECT_INTERVAL;
    };

    ws.onmessage = handleMessage;

    ws.onclose = () => {
      setIsConnected(false);
      wsRef.current = null;

      // Auto-reconnect with exponential backoff
      reconnectTimeoutRef.current = setTimeout(() => {
        reconnectDelayRef.current = Math.min(
          reconnectDelayRef.current * 2,
          MAX_RECONNECT_INTERVAL,
        );
        connect();
      }, reconnectDelayRef.current);
    };

    ws.onerror = () => {
      ws.close();
    };

    wsRef.current = ws;
  }, [handleMessage]);

  useEffect(() => {
    connect();

    return () => {
      clearTimeout(reconnectTimeoutRef.current);
      wsRef.current?.close();
    };
  }, [connect]);

  return {
    isConnected,
    lastMessage,
    priceUpdates,
    lastTrade,
    lastStatusChange,
    lastPortfolioUpdate,
  };
}
