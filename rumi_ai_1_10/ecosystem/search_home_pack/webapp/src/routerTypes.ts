export type RouteKind =
  | "URL_NAVIGATE"
  | "GOOGLE_REDIRECT"
  | "ASK_AI"
  | "ASK_AI_WITH_SEARCH"
  | "BLOCKED";

export type RouteDecision = {
  route: RouteKind;
  confidence: number;
  normalized_query: string;
  target_url: string | null;
  reason: string;
  source: string;
};

export type AskResponse = {
  status: "ok" | "error";
  conversation_id?: string;
  answer?: string;
  model?: string | null;
  used_tools?: string[];
  routing?: Record<string, unknown>;
  error?: {
    code?: string;
    message?: string;
  };
};
