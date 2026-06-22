import { motion } from "framer-motion";
import { Zap } from "lucide-react";
import { useState } from "react";

import { CitationChip } from "@/components/domain/CitationChip";
import { cn } from "@/lib/utils";
import type { ChatMessage } from "@/types";

interface ChatBubbleProps {
  message: ChatMessage;
  streaming?: boolean;
  onCitationClick?: (index: number) => void;
}

/** A single chat message bubble — user (right/blue) or assistant (left/white). */
export function ChatBubble({ message, streaming, onCitationClick }: ChatBubbleProps) {
  const [toolsOpen, setToolsOpen] = useState(false);
  const isUser = message.role === "user";

  if (isUser) {
    return (
      <motion.div
        initial={{ opacity: 0, y: 6 }}
        animate={{ opacity: 1, y: 0 }}
        className="flex justify-end"
      >
        <div className="max-w-[70%] rounded-[16px_16px_4px_16px] bg-brand-primary px-3.5 py-2.5 text-body text-white">
          {message.content}
        </div>
      </motion.div>
    );
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      className="flex justify-start"
    >
      <div className="max-w-[80%] rounded-[4px_16px_16px_16px] border border-neutral-200 bg-white px-4 py-3 shadow-card">
        {message.tool_calls.length > 0 && (
          <button
            onClick={() => setToolsOpen((v) => !v)}
            className="mb-2 inline-flex items-center gap-1.5 rounded-md bg-neutral-100 px-2 py-1 text-caption text-neutral-600 transition-colors hover:bg-neutral-200"
          >
            <Zap size={12} className="text-brand-accent" />
            {message.tool_calls.length} tool call
            {message.tool_calls.length > 1 ? "s" : ""}
          </button>
        )}
        {toolsOpen && (
          <div className="mb-2 space-y-1 rounded-md bg-neutral-50 p-2 font-mono text-caption text-neutral-500">
            {message.tool_calls.map((tc, i) => (
              <div key={i}>⚡ {tc.tool}({JSON.stringify(tc.args)})</div>
            ))}
          </div>
        )}

        <div
          className={cn(
            "whitespace-pre-wrap text-body text-neutral-800",
            streaming && "streaming-cursor",
          )}
        >
          {renderWithCitations(message.content, onCitationClick)}
        </div>

        {message.citations.length > 0 && (
          <div className="mt-3 flex flex-wrap gap-1.5 border-t border-neutral-100 pt-2">
            {message.citations.map((c, i) => (
              <span
                key={i}
                className="inline-flex items-center gap-1 rounded-full bg-brand-accent/10 px-2 py-0.5 text-caption text-[#0891B2]"
              >
                <span className="font-semibold">{i + 1}</span>
                {c.source}
                {c.section ? ` ${c.section}` : ""}
              </span>
            ))}
          </div>
        )}
      </div>
    </motion.div>
  );
}

/** Replace [n] markers with interactive CitationChip components. */
function renderWithCitations(
  text: string,
  onClick?: (index: number) => void,
): React.ReactNode[] {
  const parts = text.split(/(\[\d+\])/g);
  return parts.map((part, i) => {
    const match = part.match(/^\[(\d+)\]$/);
    if (match) {
      const idx = Number(match[1]);
      return <CitationChip key={i} index={idx} onClick={() => onClick?.(idx)} />;
    }
    return <span key={i}>{part}</span>;
  });
}
