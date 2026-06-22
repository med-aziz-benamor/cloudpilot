import { LogOut, Search } from "lucide-react";
import { useNavigate } from "react-router-dom";

import {
  Avatar,
  AvatarFallback,
} from "@/components/ui/avatar";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { initials } from "@/lib/utils";
import { useAuthStore } from "@/stores/auth.store";
import { useUIStore } from "@/stores/ui.store";

export function TopBar() {
  const setPaletteOpen = useUIStore((s) => s.setCommandPaletteOpen);
  const user = useAuthStore((s) => s.user);
  const logout = useAuthStore((s) => s.logout);
  const navigate = useNavigate();

  return (
    <header className="sticky top-0 z-20 flex h-14 items-center justify-between border-b border-neutral-200 bg-white/80 px-6 backdrop-blur-md">
      <button
        onClick={() => setPaletteOpen(true)}
        className="flex h-9 w-72 items-center gap-2 rounded-md border border-neutral-200 bg-neutral-50 px-3 text-body-sm text-neutral-400 transition-colors hover:border-neutral-300"
      >
        <Search size={15} />
        <span>Search or jump to…</span>
        <kbd className="ml-auto rounded bg-white px-1.5 py-0.5 font-mono text-[10px] text-neutral-400 shadow-sm">
          ⌘K
        </kbd>
      </button>

      <div className="flex items-center gap-3">
        <div className="flex items-center gap-1.5 rounded-full bg-status-success/10 px-2.5 py-1 text-caption font-medium text-status-success">
          <span className="h-1.5 w-1.5 animate-pulse-dot rounded-full bg-status-success" />
          Live
        </div>

        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <button className="rounded-full focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-primary/40">
              <Avatar>
                <AvatarFallback>{initials(user?.full_name || "User")}</AvatarFallback>
              </Avatar>
            </button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuLabel>{user?.email}</DropdownMenuLabel>
            <DropdownMenuSeparator />
            <DropdownMenuItem onClick={() => navigate("/settings")}>
              Settings
            </DropdownMenuItem>
            <DropdownMenuItem
              onClick={async () => {
                await logout();
                navigate("/login");
              }}
              className="text-status-danger"
            >
              <LogOut size={15} /> Sign out
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>

        <Button variant="ghost" size="sm" className="hidden md:inline-flex" disabled>
          v1.0
        </Button>
      </div>
    </header>
  );
}
