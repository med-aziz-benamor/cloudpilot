import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ConfirmDialog } from "@/components/ui/confirm-dialog";

describe("ConfirmDialog", () => {
  it("does not call onConfirm until the confirm button is clicked", () => {
    const onConfirm = vi.fn();
    render(
      <ConfirmDialog
        open
        onOpenChange={() => {}}
        title="Delete conversation"
        description="This permanently deletes it."
        onConfirm={onConfirm}
      />,
    );

    expect(onConfirm).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: /delete/i }));
    expect(onConfirm).toHaveBeenCalledTimes(1);
  });

  it("cancel closes without confirming", () => {
    const onConfirm = vi.fn();
    const onOpenChange = vi.fn();
    render(
      <ConfirmDialog
        open
        onOpenChange={onOpenChange}
        title="Delete conversation"
        description="This permanently deletes it."
        onConfirm={onConfirm}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /cancel/i }));
    expect(onConfirm).not.toHaveBeenCalled();
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  it("renders nothing interactive when closed", () => {
    render(
      <ConfirmDialog
        open={false}
        onOpenChange={() => {}}
        title="Delete conversation"
        description="This permanently deletes it."
        onConfirm={() => {}}
      />,
    );
    expect(screen.queryByRole("button", { name: /delete/i })).not.toBeInTheDocument();
  });
});
