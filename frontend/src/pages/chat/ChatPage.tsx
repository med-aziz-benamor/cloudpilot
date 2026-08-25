import { Loader2, Plus, SendHorizontal, Trash2 } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { ChatBubble } from "@/components/domain/ChatBubble";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { cn } from "@/lib/utils";
import {
  useChatSession,
  useChatSessions,
  useCreateSession,
  useDeleteSession,
  useSendMessage,
} from "@/hooks/useChat";

const SUGGESTED = [
  "Is my AKS cluster correctly sized?",
  "Why did my Azure costs spike?",
  "Will I stay within my July budget?",
];

export function ChatPage() {
  const sessions = useChatSessions();
  const createSession = useCreateSession();
  const deleteSession = useDeleteSession();
  const [activeId, setActiveId] = useState<string | null>(null);
  const detail = useChatSession(activeId);
  const sendMessage = useSendMessage();
  const [draft, setDraft] = useState("");
  const [pendingDeleteId, setPendingDeleteId] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  // Select the first session by default.
  useEffect(() => {
    if (!activeId && sessions.data?.length) setActiveId(sessions.data[0].id);
  }, [sessions.data, activeId]);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [detail.data?.messages.length, sendMessage.isPending]);

  const startNew = async () => {
    const session = await createSession.mutateAsync({ title: "New Conversation" });
    setActiveId(session.id);
  };

  const submit = async (content: string) => {
    const text = content.trim();
    if (!text) return;
    setDraft("");
    let sessionId = activeId;
    if (!sessionId) {
      const session = await createSession.mutateAsync({ title: text.slice(0, 60) });
      sessionId = session.id;
      setActiveId(sessionId);
    }
    await sendMessage.mutateAsync({ sessionId, content: text });
  };

  return (
    <div className="flex h-[calc(100vh-7rem)] gap-4">
      {/* Sessions */}
      <div className="hidden w-72 flex-col rounded-card border border-neutral-200 bg-white md:flex">
        <div className="p-3">
          <Button className="w-full" onClick={startNew} disabled={createSession.isPending}>
            <Plus size={16} /> New conversation
          </Button>
        </div>
        <div className="flex-1 overflow-y-auto px-2">
          {sessions.data?.map((s) => (
            <div
              key={s.id}
              className={cn(
                "group flex items-center gap-2 rounded-md px-3 py-2 transition-colors",
                activeId === s.id ? "bg-brand-primary/[0.07]" : "hover:bg-neutral-50",
              )}
            >
              <button
                onClick={() => setActiveId(s.id)}
                className="min-w-0 flex-1 text-left"
              >
                <p
                  className={cn(
                    "truncate text-body-sm",
                    activeId === s.id ? "font-semibold text-brand-primary" : "text-neutral-700",
                  )}
                >
                  {s.title}
                </p>
                <p className="text-caption text-neutral-400">{s.message_count} messages</p>
              </button>
              <button
                onClick={() => setPendingDeleteId(s.id)}
                disabled={deleteSession.isPending}
                className="text-neutral-300 opacity-0 transition-opacity hover:text-status-danger group-hover:opacity-100 disabled:opacity-50"
                aria-label="Delete conversation"
              >
                <Trash2 size={14} />
              </button>
            </div>
          ))}
        </div>
      </div>

      {/* Conversation */}
      <div className="flex flex-1 flex-col rounded-card border border-neutral-200 bg-white">
        <div className="border-b border-neutral-200 px-5 py-3">
          <h2 className="text-h4 font-semibold text-neutral-900">
            {detail.data?.title ?? "Cloud Advisor"}
          </h2>
          <p className="text-caption text-neutral-400">
            RAG-powered · grounded in your live infrastructure
          </p>
        </div>

        <div ref={scrollRef} className="flex-1 space-y-4 overflow-y-auto p-5">
          {detail.data?.messages.map((m) => (
            <ChatBubble key={m.id} message={m} />
          ))}
          {sendMessage.isPending && (
            <div className="flex items-center gap-2 text-body-sm text-neutral-400">
              <Loader2 size={14} className="animate-spin" /> ArchitectAgent is thinking…
            </div>
          )}
          {!detail.data?.messages.length && !sendMessage.isPending && (
            <div className="flex h-full flex-col items-center justify-center text-center">
              <p className="text-h3 font-semibold text-neutral-900">
                Ask the Cloud Advisor
              </p>
              <p className="mt-1 max-w-sm text-body-sm text-neutral-500">
                Get cited answers about your infrastructure, costs and architecture.
              </p>
            </div>
          )}
        </div>

        {/* Input */}
        <div className="border-t border-neutral-200 p-4">
          <div className="mb-2 flex flex-wrap gap-2">
            {SUGGESTED.map((s) => (
              <button
                key={s}
                onClick={() => submit(s)}
                className="rounded-full border border-neutral-200 px-3 py-1 text-caption text-neutral-600 transition-colors hover:border-brand-primary hover:text-brand-primary"
              >
                {s}
              </button>
            ))}
          </div>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              submit(draft);
            }}
            className="flex items-end gap-2"
          >
            <textarea
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  submit(draft);
                }
              }}
              rows={1}
              maxLength={4000}
              placeholder="Ask about your cloud infrastructure…"
              className="max-h-32 flex-1 resize-none rounded-lg border border-neutral-200 px-3 py-2.5 text-body outline-none focus:border-brand-primary focus:shadow-glow-brand"
            />
            <Button
              type="submit"
              size="icon"
              disabled={sendMessage.isPending || !draft.trim()}
              className="h-10 w-10"
            >
              <SendHorizontal size={18} />
            </Button>
          </form>
        </div>
      </div>

      <ConfirmDialog
        open={pendingDeleteId !== null}
        onOpenChange={(open) => !open && setPendingDeleteId(null)}
        title="Delete conversation"
        description="This permanently deletes the conversation and its messages."
        confirmLabel="Delete"
        isPending={deleteSession.isPending}
        onConfirm={() => {
          if (!pendingDeleteId) return;
          const id = pendingDeleteId;
          deleteSession.mutate(id, {
            onSuccess: () => {
              setPendingDeleteId(null);
              if (activeId === id) setActiveId(null);
            },
          });
        }}
      />
    </div>
  );
}
