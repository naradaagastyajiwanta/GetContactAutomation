import { useState, useCallback } from "react";

export interface Notification {
  id: string;
  type:
    | "agent_completed"
    | "got_number"
    | "blast_completed"
    | "quota_reached"
    | "quota_exhausted"
    | "marketing_quota_exhausted"
    | "openai_quota_exhausted"
    | "conversation_changed"
    | "university_updated";
  title: string;
  body: string;
  time: Date;
  read: boolean;
}

export function useNotifications() {
  const [notifications, setNotifications] = useState<Notification[]>([]);

  const add = useCallback((n: Omit<Notification, "id" | "time" | "read">) => {
    const notif: Notification = {
      ...n,
      id: `${Date.now()}-${Math.random().toString(36).slice(2)}`,
      time: new Date(),
      read: false,
    };
    setNotifications((prev) => [notif, ...prev].slice(0, 50));
  }, []);

  const markRead = useCallback((id: string) => {
    setNotifications((prev) =>
      prev.map((n) => (n.id === id ? { ...n, read: true } : n)),
    );
  }, []);

  const markAllRead = useCallback(() => {
    setNotifications((prev) => prev.map((n) => ({ ...n, read: true })));
  }, []);

  const clear = useCallback((id: string) => {
    setNotifications((prev) => prev.filter((n) => n.id !== id));
  }, []);

  const unread = notifications.filter((n) => !n.read).length;

  return { notifications, unread, add, markRead, markAllRead, clear };
}
