const API_BASE =
  process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") ?? "http://127.0.0.1:8000";

export type Stock = {
  name: string;
  symbol: string;
};

export type PriceRow = {
  date: string;
  close: number;
  open?: number | null;
  high?: number | null;
  low?: number | null;
  volume?: number | null;
};

export type ModelScore = {
  mae: number;
  rmse: number;
  r2: number;
};

export type Forecast = {
  id: number;
  symbol: string;
  horizon: number;
  method: string;
  future_price: number;
  mae: number;
  model_mae: number;
  rmse: number;
  baseline_mae: number;
  r2: number;
  directional_accuracy: number;
  actual: number[];
  predicted: number[];
  target_dates: string[];
  model_comparison: Record<string, ModelScore>;
  walk_forward: {
    folds: number;
    mae_by_model: Record<string, number>;
    baseline_mae: number;
  };
  created_at: string;
};

export type WatchlistItem = {
  symbol: string;
  created_at: string;
};

export type Account = {
  id: number;
  email: string;
  created_at: string;
};

type RequestOptions = {
  method?: string;
  token?: string | null;
  body?: unknown;
};

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      method: options.method ?? "GET",
      headers: {
        ...(options.body ? { "Content-Type": "application/json" } : {}),
        ...(options.token ? { Authorization: `Bearer ${options.token}` } : {}),
      },
      body: options.body ? JSON.stringify(options.body) : undefined,
      cache: "no-store",
    });
  } catch {
    throw new Error("Cannot reach the API. Start the FastAPI service and retry.");
  }

  if (!response.ok) {
    let detail = `Request failed (${response.status}).`;
    try {
      const body = await response.json();
      if (typeof body.detail === "string") detail = body.detail;
    } catch {
      // Use the status message when the server does not return JSON.
    }
    throw new Error(detail);
  }

  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export const api = {
  stocks: () => request<Stock[]>("/api/v1/stocks"),
  history: (symbol: string) =>
    request<{ symbol: string; data: PriceRow[] }>(
      `/api/v1/stocks/${encodeURIComponent(symbol)}/history?start=2019-01-01`,
    ),
  forecast: (symbol: string, horizon: number, token: string | null) =>
    request<Forecast>("/api/v1/forecasts", {
      method: "POST",
      token,
      body: { symbol, horizon, start: "2019-01-01" },
    }),
  recentForecasts: (symbol: string, token: string) =>
    request<Forecast[]>(
      `/api/v1/forecasts?symbol=${encodeURIComponent(symbol)}&limit=10`,
      { token },
    ),
  register: (email: string, password: string) =>
    request<Account>("/api/v1/auth/register", {
      method: "POST",
      body: { email, password },
    }),
  login: (email: string, password: string) =>
    request<{ access_token: string; expires_in: number }>("/api/v1/auth/login", {
      method: "POST",
      body: { email, password },
    }),
  me: (token: string) =>
    request<Account>("/api/v1/auth/me", { token }),
  watchlist: (token: string) =>
    request<WatchlistItem[]>("/api/v1/portfolio/watchlist", { token }),
  addWatchlist: (symbol: string, token: string) =>
    request<{ symbol: string }>("/api/v1/portfolio/watchlist", {
      method: "POST",
      token,
      body: { symbol },
    }),
  removeWatchlist: (symbol: string, token: string) =>
    request<void>(`/api/v1/portfolio/watchlist/${encodeURIComponent(symbol)}`, {
      method: "DELETE",
      token,
    }),
};

export function formatPrice(value: number): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 2,
  }).format(value);
}
