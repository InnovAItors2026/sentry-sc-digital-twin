import type { CompareResponse, NetworkResponse, ScenarioSummary, SimulateResponse } from "./types";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(init?.headers || {}) },
    ...init,
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail ? JSON.stringify(body.detail) : JSON.stringify(body);
    } catch {
      /* ignore */
    }
    throw new Error(detail);
  }
  return res.json() as Promise<T>;
}

export const api = {
  health: () => request<{ status: string }>("/api/health"),
  network: () => request<NetworkResponse>("/api/network"),
  node: (id: string) => request<Record<string, unknown>>(`/api/network/${id}`),
  scenarios: () => request<ScenarioSummary[]>("/api/scenarios"),
  scenario: (id: string) => request<Record<string, unknown>>(`/api/scenarios/${id}`),
  createScenario: (body: Record<string, unknown>) =>
    request<ScenarioSummary>("/api/scenarios", { method: "POST", body: JSON.stringify(body) }),
  simulate: (id: string) =>
    request<SimulateResponse>(`/api/scenarios/${id}/simulate`, { method: "POST" }),
  results: (id: string) => request<SimulateResponse>(`/api/scenarios/${id}/results`),
  compare: (ids: string[]) =>
    request<CompareResponse>("/api/scenarios/compare", {
      method: "POST",
      body: JSON.stringify({ scenario_ids: ids }),
    }),
};
