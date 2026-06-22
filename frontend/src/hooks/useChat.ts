import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/lib/api";
import type { ChatMessage, ChatSession, ChatSessionDetail } from "@/types";
import type { CreateSessionRequest } from "@/types/api";

export function useChatSessions() {
  return useQuery({
    queryKey: ["chat-sessions"],
    queryFn: async () =>
      (await api.get<ChatSession[]>("/api/v1/chat/sessions")).data,
  });
}

export function useChatSession(sessionId: string | null) {
  return useQuery({
    queryKey: ["chat-session", sessionId],
    enabled: !!sessionId,
    queryFn: async () =>
      (
        await api.get<ChatSessionDetail>(`/api/v1/chat/sessions/${sessionId}`)
      ).data,
  });
}

export function useCreateSession() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (payload: CreateSessionRequest) =>
      (await api.post<ChatSessionDetail>("/api/v1/chat/sessions", payload)).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["chat-sessions"] }),
  });
}

export function useSendMessage(sessionId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (content: string) =>
      (
        await api.post<ChatMessage>(
          `/api/v1/chat/sessions/${sessionId}/messages`,
          { content },
        )
      ).data,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["chat-session", sessionId] });
      qc.invalidateQueries({ queryKey: ["chat-sessions"] });
    },
  });
}

export function useDeleteSession() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (sessionId: string) =>
      (await api.delete(`/api/v1/chat/sessions/${sessionId}`)).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["chat-sessions"] }),
  });
}
