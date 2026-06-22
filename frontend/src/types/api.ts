// API envelope and request types.

export interface APIError {
  error: {
    code: number;
    message: string;
    details?: unknown;
  };
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
  refresh_token?: string | null;
}

export interface LoginRequest {
  email: string;
  password: string;
}

export interface RegisterRequest {
  email: string;
  password: string;
  full_name: string;
  organization_name: string;
}

export interface SendMessageRequest {
  content: string;
}

export interface CreateSessionRequest {
  title?: string;
  first_message?: string | null;
}

export interface RecommendationStatusUpdate {
  status: "pending" | "accepted" | "rejected" | "snoozed";
  snooze_hours?: number | null;
}
