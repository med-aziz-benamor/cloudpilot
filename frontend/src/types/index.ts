// Core domain TypeScript interfaces shared across the app.

export type CloudProvider = "azure" | "aws" | "gcp";
export type AgentType = "cost" | "rightsizing" | "forecast" | "architect";
export type RecommendationStatus = "pending" | "accepted" | "rejected" | "snoozed";
export type UserRole = "admin" | "analyst" | "viewer";
export type CloudAccountStatus = "active" | "error" | "paused";
export type MessageRole = "user" | "assistant" | "system";

export interface User {
  id: string;
  email: string;
  full_name: string;
  role: UserRole;
  organization_id: string;
  mfa_enabled: boolean;
  is_active: boolean;
  last_login_at: string | null;
  created_at: string;
}

export interface CloudAccount {
  id: string;
  provider: CloudProvider;
  display_name: string;
  account_identifier: string;
  status: CloudAccountStatus;
  last_synced_at: string | null;
  error_message: string | null;
  created_at: string;
  resource_count: number;
  monthly_cost_usd: number;
}

export interface Resource {
  id: string;
  provider: CloudProvider;
  provider_resource_id: string;
  name: string;
  service: string;
  region: string;
  sku: string | null;
  tags: Record<string, string>;
  is_active: boolean;
  monthly_cost_usd: number;
  last_seen_at: string | null;
}

export interface MetricPoint {
  timestamp: string;
  value: number;
}

export interface ResourceMetricSeries {
  metric_name: string;
  unit: string;
  points: MetricPoint[];
}

export interface ResourceDetail extends Resource {
  metrics: ResourceMetricSeries[];
  cost_trend: MetricPoint[];
  recommendation_count: number;
}

export interface ResourceTreeNode {
  key: string;
  label: string;
  kind: "provider" | "region" | "service";
  count: number;
  monthly_cost_usd: number;
  children: ResourceTreeNode[];
}

export interface CostSummary {
  mtd_usd: number;
  projected_month_end_usd: number;
  last_month_usd: number;
  delta_pct: number;
  potential_savings_usd: number;
  optimization_score: number;
  connected_clouds: number;
  pending_recommendations: number;
}

export interface ProviderCost {
  provider: CloudProvider;
  cost_usd: number;
  pct_of_total: number;
}

export interface ServiceCost {
  service: string;
  provider: CloudProvider;
  cost_usd: number;
  vs_last_month_pct: number;
  pct_of_total: number;
}

export interface CostTimeseriesPoint {
  usage_date: string;
  azure: number;
  aws: number;
  gcp: number;
  total: number;
}

export interface CostBreakdown {
  by_provider: ProviderCost[];
  by_service: ServiceCost[];
  by_region: { region: string; cost_usd: number }[];
}

export interface TopCostDriver {
  resource_id: string;
  name: string;
  provider: CloudProvider;
  service: string;
  monthly_cost_usd: number;
  trend: number[];
}

export interface AnomalyEntry {
  usage_date: string;
  provider: CloudProvider;
  service: string;
  expected_usd: number;
  actual_usd: number;
  delta_usd: number;
  delta_pct: number;
}

export interface Recommendation {
  id: string;
  agent: AgentType;
  title: string;
  description: string;
  estimated_saving_usd: number | null;
  confidence: number;
  status: RecommendationStatus;
  snoozed_until: string | null;
  affected_resource_ids: string[];
  affected_resource_names: string[];
  metadata: Record<string, unknown>;
  created_at: string;
}

export interface SavingsSummary {
  total_potential_usd: number;
  accepted_usd: number;
  pending_count: number;
  accepted_count: number;
  rejected_count: number;
  snoozed_count: number;
}

export interface Citation {
  source: string;
  section: string | null;
  url: string | null;
}

export interface ToolCall {
  tool: string;
  args: Record<string, unknown>;
  result: Record<string, unknown> | null;
}

export interface ChatMessage {
  id: string;
  role: MessageRole;
  content: string;
  citations: Citation[];
  tool_calls: ToolCall[];
  tokens_used: number | null;
  created_at: string;
}

export interface ChatSession {
  id: string;
  title: string;
  is_archived: boolean;
  created_at: string;
  message_count: number;
}

export interface ChatSessionDetail extends ChatSession {
  messages: ChatMessage[];
}

export interface ForecastPoint {
  ds: string;
  yhat: number;
  yhat_lower: number;
  yhat_upper: number;
  trend: number;
}

export interface ForecastResponse {
  snapshot_date: string;
  horizon_days: number;
  current_mtd_usd: number;
  projected_month_end_usd: number;
  budget_usd: number;
  over_budget: boolean;
  overrun_pct: number;
  next_90d_usd: number;
  points: ForecastPoint[];
  actuals: { ds: string; y: number }[];
}
