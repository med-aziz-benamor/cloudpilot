import { cn } from "@/lib/utils";

interface CitationChipProps {
  index: number;
  onClick?: () => void;
  active?: boolean;
}

/** A small superscript citation chip rendered inline in assistant chat messages. */
export function CitationChip({ index, onClick, active }: CitationChipProps) {
  return (
    <button
      onClick={onClick}
      className={cn(
        "mx-0.5 inline-flex h-4 min-w-[1rem] items-center justify-center rounded-full px-1 align-super text-[10px] font-semibold transition-colors",
        active
          ? "bg-brand-accent text-white"
          : "bg-brand-accent/15 text-[#0891B2] hover:bg-brand-accent/25",
      )}
      aria-label={`Citation ${index}`}
    >
      {index}
    </button>
  );
}
