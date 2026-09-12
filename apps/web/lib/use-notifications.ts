"use client";
/**
 * React binding for the notification store.
 *
 * useSyncExternalStore keeps every consumer — the top-bar badge and the
 * notifications page — showing the same state without either polling.
 */
import { useCallback, useSyncExternalStore } from "react";

import {
  getNotifications,
  getUnreadCount,
  subscribe,
  type AppNotification,
} from "./notifications";

/** Stable empty array so the server snapshot never triggers a re-render loop. */
const EMPTY: AppNotification[] = [];

export function useNotifications(): AppNotification[] {
  // getNotifications() parses JSON and returns a fresh array each call, which
  // useSyncExternalStore would treat as a change forever. Cache per version.
  const getSnapshot = useCallback(() => cachedSnapshot(), []);
  return useSyncExternalStore(subscribe, getSnapshot, () => EMPTY);
}

export function useUnreadCount(): number {
  return useSyncExternalStore(subscribe, getUnreadCount, () => 0);
}

let cache: AppNotification[] = EMPTY;
let cacheKey = "";

function cachedSnapshot(): AppNotification[] {
  const next = getNotifications();
  // Cheap identity: count plus the newest id and read-flags signature.
  const key = `${next.length}:${next.map((n) => `${n.id}${n.read ? "1" : "0"}`).join(",")}`;
  if (key !== cacheKey) {
    cacheKey = key;
    cache = next;
  }
  return cache;
}
