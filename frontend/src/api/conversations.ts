import { apiClient } from "./client";
import type { Conversation, Message } from "../lib/types";

interface ConversationParams {
  state?: string;
  is_test?: boolean;
  limit?: number;
  offset?: number;
}

export async function getConversations(
  params?: ConversationParams,
): Promise<Conversation[]> {
  const { data } = await apiClient.get<Conversation[]>("/conversations", {
    params,
  });
  return data;
}

interface RawConversation extends Omit<Conversation, "message_history"> {
  message_history: string | Message[];
}

export async function getConversation(id: number): Promise<Conversation> {
  const { data } = await apiClient.get<RawConversation>(`/conversations/${id}`);
  return {
    ...data,
    message_history:
      typeof data.message_history === "string"
        ? JSON.parse(data.message_history)
        : data.message_history,
  };
}

export async function startTestConversation(
  phone: string,
  universityName?: string,
  force?: boolean,
  deviceId = "device_1",
): Promise<{ id: number; phone: string; message: string; state: string }> {
  const { data } = await apiClient.post("/conversations/test", {
    phone,
    university_name: universityName || "Universitas Test",
    force: force ?? false,
    device_id: deviceId,
  });
  return data;
}
