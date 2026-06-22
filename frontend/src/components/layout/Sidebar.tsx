import { ChevronLeft } from "lucide-react";
import { NavLink } from "react-router-dom";

import { Logo, LogoMark } from "@/components/layout/Logo";
import {
  Avatar,
  AvatarFallback,
} from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { useRecommendations } from "@/hooks/useRecommendations";
import { NAV_ITEMS, type NavItem } from "@/lib/constants";
import { cn, initials } from "@/lib/utils";
import { useAuthStore } from "@/stores/auth.store";
import { useUIStore } from "@/stores/ui.store";

const SECTIONS: NavItem["section"][] = ["OVERVIEW", "INTELLIGENCE", "WORKSPACE"];

export function Sidebar() {
  const collapsed = useUIStore((s) => s.sidebarCollapsed);
  const toggle = useUIStore((s) => s.toggleSidebar);
  const user = useAuthStore((s) => s.user);
  const { data: recs } = useRecommendations({ status: "pending" });
  const pendingCount = recs?.length ?? 0;

  return (
    <aside
      className={cn(
        "glass sticky top-0 z-30 flex h-screen flex-col border-r border-neutral-200/60 transition-[width] duration-[250ms] ease-spring",
        collapsed ? "w-16" : "w-60",
      )}
    >
      {/* Logo */}
      <div className="flex h-14 items-center px-4">
        {collapsed ? <LogoMark /> : <Logo />}
      </div>

      {/* Navigation */}
      <nav className="flex-1 overflow-y-auto py-2">
        {SECTIONS.map((section) => (
          <div key={section} className="mb-2">
            {!collapsed && (
              <p className="px-4 pb-1 pt-4 text-label uppercase text-neutral-400">
                {section}
              </p>
            )}
            {NAV_ITEMS.filter((i) => i.section === section).map((item) => (
              <NavItemLink
                key={item.path}
                item={item}
                collapsed={collapsed}
                badgeCount={item.badge === "count" ? pendingCount : undefined}
              />
            ))}
          </div>
        ))}
      </nav>

      {/* Bottom: sync + user + collapse */}
      <div className="border-t border-neutral-200/60 p-3">
        {!collapsed && (
          <div className="mb-2 flex items-center gap-2 px-1 text-caption text-neutral-500">
            <span className="h-2 w-2 animate-pulse-dot rounded-full bg-status-success" />
            Live · synced
          </div>
        )}
        <div className="flex items-center gap-2">
          <Avatar>
            <AvatarFallback>{initials(user?.full_name || "User")}</AvatarFallback>
          </Avatar>
          {!collapsed && (
            <div className="min-w-0 flex-1">
              <p className="truncate text-body-sm font-medium text-neutral-900">
                {user?.full_name}
              </p>
              <p className="truncate text-caption capitalize text-neutral-400">
                {user?.role}
              </p>
            </div>
          )}
          <button
            onClick={toggle}
            className="rounded-md p-1.5 text-neutral-400 transition-colors hover:bg-neutral-100 hover:text-neutral-700"
            aria-label="Toggle sidebar"
          >
            <ChevronLeft
              size={16}
              className={cn("transition-transform", collapsed && "rotate-180")}
            />
          </button>
        </div>
      </div>
    </aside>
  );
}

function NavItemLink({
  item,
  collapsed,
  badgeCount,
}: {
  item: NavItem;
  collapsed: boolean;
  badgeCount?: number;
}) {
  const Icon = item.icon;
  const link = (
    <NavLink
      to={item.path}
      end={item.path === "/"}
      className={({ isActive }) =>
        cn(
          "relative mx-2 flex h-9 items-center gap-2.5 rounded-md px-3 transition-colors duration-150",
          isActive
            ? "bg-brand-primary/[0.07] text-brand-primary"
            : "text-neutral-700 hover:bg-neutral-100",
          collapsed && "justify-center px-0",
        )
      }
    >
      {({ isActive }) => (
        <>
          {isActive && (
            <span className="absolute left-0 h-5 w-0.5 rounded-full bg-brand-primary" />
          )}
          <Icon
            size={18}
            strokeWidth={1.75}
            className={isActive ? "text-brand-primary" : "text-neutral-500"}
          />
          {!collapsed && (
            <span className={cn("flex-1 text-body-sm", isActive && "font-semibold")}>
              {item.label}
            </span>
          )}
          {!collapsed && item.badge === "ai" && (
            <Badge variant="info" className="px-1.5 py-0">
              AI
            </Badge>
          )}
          {!collapsed && item.badge === "count" && badgeCount ? (
            <span className="rounded-full bg-brand-primary px-1.5 text-[10px] font-semibold text-white">
              {badgeCount}
            </span>
          ) : null}
        </>
      )}
    </NavLink>
  );

  if (collapsed) {
    return (
      <Tooltip>
        <TooltipTrigger asChild>{link}</TooltipTrigger>
        <TooltipContent side="right">{item.label}</TooltipContent>
      </Tooltip>
    );
  }
  return link;
}
