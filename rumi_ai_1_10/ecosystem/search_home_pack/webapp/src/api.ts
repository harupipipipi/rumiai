import type { AskResponse, RouteDecision } from "./routerTypes";

async function readJson<T>(response: Response): Promise<T> {
  const data = (await response.json()) as T;
  if (!response.ok) {
    throw new Error(
      (data as { error?: { message?: string } }).error?.message ?? "Request failed",
    );
  }
  return data;
}

export async function routeInput(input: string): Promise<RouteDecision> {
  const response = await fetch("/api/route", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ input }),
  });
  return readJson<RouteDecision>(response);
}

export async function askAi(query: string, withSearch: boolean): Promise<AskResponse> {
  const response = await fetch("/api/ask", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query, with_search: withSearch }),
  });
  return readJson<AskResponse>(response);
}
