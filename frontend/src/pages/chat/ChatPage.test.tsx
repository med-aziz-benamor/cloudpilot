import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ChatPage } from "@/pages/chat/ChatPage";

const mutateAsyncCreateSession = vi.fn();
const mutateAsyncSendMessage = vi.fn();
const mutateDeleteSession = vi.fn();

vi.mock("@/hooks/useChat", () => ({
  useChatSessions: () => ({ data: [] }),
  useChatSession: () => ({ data: undefined, isLoading: false }),
  useCreateSession: () => ({
    mutateAsync: mutateAsyncCreateSession,
    isPending: false,
  }),
  useSendMessage: () => ({
    mutateAsync: mutateAsyncSendMessage,
    isPending: false,
  }),
  useDeleteSession: () => ({ mutate: mutateDeleteSession, isPending: false }),
}));

describe("ChatPage — first message in a new conversation", () => {
  beforeEach(() => {
    mutateAsyncCreateSession.mockReset();
    mutateAsyncSendMessage.mockReset();
    mutateAsyncCreateSession.mockResolvedValue({
      id: "brand-new-session-id",
      title: "hello there",
      is_archived: false,
      created_at: new Date().toISOString(),
      message_count: 0,
    });
    mutateAsyncSendMessage.mockResolvedValue({});
  });

  it("sends the message to the freshly-created session, not a stale empty id", async () => {
    const user = userEvent.setup();
    render(<ChatPage />);

    const textarea = screen.getByPlaceholderText(/ask about your cloud infrastructure/i);
    await user.type(textarea, "hello there");
    await user.keyboard("{Enter}");

    await vi.waitFor(() => {
      expect(mutateAsyncSendMessage).toHaveBeenCalled();
    });

    expect(mutateAsyncCreateSession).toHaveBeenCalledTimes(1);
    expect(mutateAsyncSendMessage).toHaveBeenCalledWith({
      sessionId: "brand-new-session-id",
      content: "hello there",
    });
  });
});
