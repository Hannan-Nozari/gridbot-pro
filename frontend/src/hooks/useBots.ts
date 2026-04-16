"use client";

import useSWR from "swr";
import { getBots, getBotDetail } from "@/lib/api";
import type { Bot } from "@/types";

const POLL_INTERVAL = 5000;

export function useBots() {
  const { data, error, isLoading, mutate } = useSWR<Bot[]>(
    "/bots",
    () => getBots(),
    {
      refreshInterval: POLL_INTERVAL,
      revalidateOnFocus: true,
    },
  );

  return {
    bots: data ?? [],
    isLoading,
    error,
    mutate,
  };
}

export function useBot(id: string | null) {
  const { data, error, isLoading, mutate } = useSWR<Bot>(
    id ? `/bots/${id}` : null,
    () => getBotDetail(id!),
    {
      refreshInterval: POLL_INTERVAL,
      revalidateOnFocus: true,
    },
  );

  return {
    bot: data ?? null,
    isLoading,
    error,
    mutate,
  };
}
