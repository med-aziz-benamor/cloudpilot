import {
  DollarSign,
  LayoutDashboard,
  Lightbulb,
  MessageSquare,
  Server,
  Settings2,
  TrendingUp,
  type LucideIcon,
} from "lucide-react";

import type { AgentType, CloudProvider } from "@/types";

export const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

export const DEMO_CREDENTIALS = {
  email: "demo@cloudpilot.dev",
  password: "demo1234",
};

export interface NavItem {
  label: string;
  path: string;
  icon: LucideIcon;
  section: "OVERVIEW" | "INTELLIGENCE" | "WORKSPACE";
  badge?: "count" | "ai";
}

export const NAV_ITEMS: NavItem[] = [
  { label: "Overview", path: "/", icon: LayoutDashboard, section: "OVERVIEW" },
  { label: "Resources", path: "/resources", icon: Server, section: "OVERVIEW" },
  { label: "Costs", path: "/costs", icon: DollarSign, section: "OVERVIEW" },
  {
    label: "Recommendations",
    path: "/recommendations",
    icon: Lightbulb,
    section: "INTELLIGENCE",
    badge: "count",
  },
  { label: "Forecast", path: "/forecast", icon: TrendingUp, section: "INTELLIGENCE" },
  {
    label: "Cloud Advisor",
    path: "/chat",
    icon: MessageSquare,
    section: "INTELLIGENCE",
    badge: "ai",
  },
  { label: "Settings", path: "/settings", icon: Settings2, section: "WORKSPACE" },
];

export const PROVIDER_META: Record<
  CloudProvider,
  { label: string; color: string; chartColor: string }
> = {
  azure: { label: "Azure", color: "#0078D4", chartColor: "#0078D4" },
  aws: { label: "AWS", color: "#FF9900", chartColor: "#FF9900" },
  gcp: { label: "GCP", color: "#4285F4", chartColor: "#EA4335" },
};

export const AGENT_META: Record<
  AgentType,
  { label: string; color: string; bg: string }
> = {
  cost: { label: "CostAgent", color: "#0D6EFD", bg: "rgba(13,110,253,0.1)" },
  rightsizing: { label: "RightSizing", color: "#0DCAF0", bg: "rgba(13,202,240,0.12)" },
  forecast: { label: "ForecastAgent", color: "#7C3AED", bg: "rgba(124,58,237,0.1)" },
  architect: { label: "ArchitectAgent", color: "#10B981", bg: "rgba(16,185,129,0.1)" },
};

export const KEYBOARD_SHORTCUTS = [
  { keys: "⌘ K", action: "Open command palette" },
  { keys: "G then O", action: "Go to Overview" },
  { keys: "G then R", action: "Go to Resources" },
  { keys: "G then C", action: "Go to Costs" },
  { keys: "G then A", action: "Go to Cloud Advisor" },
  { keys: "/", action: "Focus search" },
  { keys: "Esc", action: "Close dialogs" },
];
