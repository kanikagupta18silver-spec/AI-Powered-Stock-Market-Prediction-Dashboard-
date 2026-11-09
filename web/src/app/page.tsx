"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import {
  Account,
  api,
  Forecast,
  formatPrice,
  PriceRow,
  Stock,
  WatchlistItem,
} from "@/lib/api";

type AuthMode = "login" | "register";
type Panel = "overview" | "forecast" | "portfolio";

function PriceChart({
  values,
  forecast,
}: {
  values: { date: string; close: number }[];
  forecast?: Forecast | null;
}) {
  const points = useMemo(() => {
    const visible = values.slice(-180);
    if (visible.length < 2) return [];
    const numbers = visible.map((item) => item.close);
    const minimum = Math.min(...numbers);
    const maximum = Math.max(...numbers);
    const spread = maximum - minimum || 1;
    return numbers.map((value, index) => {
      const x = 20 + (index / (numbers.length - 1)) * 960;
      const y = 250 - ((value - minimum) / spread) * 210;
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    });
  }, [values]);
  const line = points.join(" ");
  const area = points.length
    ? `20,270 ${line} 980,270`
    : "";

  return (
    <div className="chart-wrap">
      {points.length ? (
        <svg
          aria-label="Adjusted stock close over time"
          className="price-chart"
          role="img"
          viewBox="0 0 1000 300"
          preserveAspectRatio="none"
        >
          <defs>
            <linearGradient id="chartFill" x1="0" x2="0" y1="0" y2="1">
              <stop offset="0%" stopColor="#6482f5" stopOpacity=".23" />
              <stop offset="100%" stopColor="#6482f5" stopOpacity="0" />
            </linearGradient>
          </defs>
          {[65, 125, 185, 245].map((y) => (
            <line
              key={y}
              x1="20"
              x2="980"
              y1={y}
              y2={y}
              stroke="#e9edf4"
              strokeDasharray="4 8"
            />
          ))}
          <polygon points={area} fill="url(#chartFill)" />
          <polyline
            fill="none"
            points={line}
            stroke="#5875ef"
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth="3"
          />
        </svg>
      ) : (
        <div className="chart-empty">Price history will appear here.</div>
      )}
      <div className="chart-footer">
        <span>{values.at(-180)?.date.slice(0, 10) ?? "—"}</span>
        <span>{values.at(-1)?.date.slice(0, 10) ?? "—"}</span>
      </div>
      {forecast && (
        <div className="forecast-result">
          <span>
            <span className="live-dot" /> {forecast.horizon}-day estimate
          </span>
          <strong>{formatPrice(forecast.future_price)}</strong>
        </div>
      )}
    </div>
  );
}

function Metric({
  label,
  value,
  change,
  positive,
}: {
  label: string;
  value: string;
  change?: string;
  positive?: boolean;
}) {
  return (
    <article className="metric-card">
      <span className="metric-label">{label}</span>
      <div className="metric-value">{value}</div>
      {change && (
        <span className={`metric-change ${positive ? "positive" : "negative"}`}>
          {positive ? "↗" : "↘"} {change}
        </span>
      )}
    </article>
  );
}

export default function Home() {
  const [stocks, setStocks] = useState<Stock[]>([]);
  const [symbol, setSymbol] = useState("AAPL");
  const [history, setHistory] = useState<PriceRow[]>([]);
  const [historyVersion, setHistoryVersion] = useState(0);
  const [forecast, setForecast] = useState<Forecast | null>(null);
  const [savedForecasts, setSavedForecasts] = useState<Forecast[]>([]);
  const [watchlist, setWatchlist] = useState<WatchlistItem[]>([]);
  const [account, setAccount] = useState<Account | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [panel, setPanel] = useState<Panel>("overview");
  const [horizon, setHorizon] = useState(30);
  const [authMode, setAuthMode] = useState<AuthMode | null>(null);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [loadingHistory, setLoadingHistory] = useState(true);
  const [error, setError] = useState("");

  const selectedStock = stocks.find((item) => item.symbol === symbol);
  const latestClose = history.at(-1)?.close ?? 0;
  const previousClose = history.at(-2)?.close ?? latestClose;
  const dayChange = latestClose - previousClose;
  const yearAgoClose = history.at(-252)?.close ?? history[0]?.close ?? latestClose;
  const yearChange =
    yearAgoClose > 0 ? ((latestClose / yearAgoClose) - 1) * 100 : 0;

  function selectSymbol(nextSymbol: string) {
    setSymbol(nextSymbol);
    setHistory([]);
    setLoadingHistory(true);
    setForecast(null);
    setError("");
  }

  useEffect(() => {
    api.stocks().then(setStocks).catch((cause: Error) => setError(cause.message));
  }, []);

  useEffect(() => {
    let active = true;
    api
      .history(symbol)
      .then(({ data }) => {
        if (active) setHistory(data);
      })
      .catch((cause: Error) => {
        if (active) setError(cause.message);
      })
      .finally(() => {
        if (active) setLoadingHistory(false);
      });
    return () => {
      active = false;
    };
  }, [symbol, historyVersion]);

  useEffect(() => {
    let active = true;
    if (!token) return;
    Promise.all([api.watchlist(token), api.recentForecasts(symbol, token)])
      .then(([items, recent]) => {
        if (active) {
          setWatchlist(items);
          setSavedForecasts(recent);
        }
      })
      .catch((cause: Error) => {
        if (active) setError(cause.message);
      });
    return () => {
      active = false;
    };
  }, [symbol, token]);

  async function submitAuth(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      if (authMode === "register") await api.register(email, password);
      const session = await api.login(email, password);
      const user = await api.me(session.access_token);
      const items = await api.watchlist(session.access_token);
      setToken(session.access_token);
      setAccount(user);
      setWatchlist(items);
      setAuthMode(null);
      setPassword("");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Sign-in failed.");
    } finally {
      setBusy(false);
    }
  }

  async function runForecast() {
    setBusy(true);
    setError("");
    try {
      setForecast(await api.forecast(symbol, horizon, token));
      if (token) setSavedForecasts(await api.recentForecasts(symbol, token));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Forecast failed.");
    } finally {
      setBusy(false);
    }
  }

  async function toggleWatchlist() {
    if (!token) {
      setAuthMode("login");
      return;
    }
    const isSaved = watchlist.some((item) => item.symbol === symbol);
    setError("");
    try {
      if (isSaved) {
        await api.removeWatchlist(symbol, token);
        setWatchlist((current) =>
          current.filter((item) => item.symbol !== symbol),
        );
      } else {
        await api.addWatchlist(symbol, token);
        setWatchlist((current) => [...current, { symbol, created_at: "" }]);
      }
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Portfolio update failed.");
    }
  }

  function signOut() {
    setAccount(null);
    setToken(null);
    setWatchlist([]);
    setSavedForecasts([]);
  }

  const modelScores = forecast ? Object.entries(forecast.model_comparison) : [];

  return (
    <main className="app-shell">
      <aside className="sidebar">
        <a className="brand" href="#" aria-label="MarketLens home">
          <span className="brand-mark">M</span>
          <span>market<span className="brand-light">lens</span></span>
        </a>
        <div className="workspace-label">WORKSPACE</div>
        <nav className="main-nav" aria-label="Main navigation">
          {(
            [
              ["overview", "◫", "Overview"],
              ["forecast", "⌁", "Forecast lab"],
              ["portfolio", "☆", "My portfolio"],
            ] as const
          ).map(([key, icon, label]) => (
            <button
              className={`nav-item ${panel === key ? "active" : ""}`}
              key={key}
              onClick={() => setPanel(key)}
              type="button"
            >
              <span className="nav-icon">{icon}</span>
              {label}
              {key === "portfolio" && watchlist.length > 0 && (
                <span className="nav-count">{watchlist.length}</span>
              )}
            </button>
          ))}
        </nav>
        <div className="sidebar-spacer" />
        <div className="sidebar-note">
          <span className="note-icon">i</span>
          Market data and forecasts are for research and education, not
          investment advice.
        </div>
        {account ? (
          <div className="account-row">
            <span className="avatar">{account.email[0].toUpperCase()}</span>
            <span className="account-name">{account.email}</span>
            <button
              aria-label="Sign out"
              className="icon-button"
              onClick={signOut}
              title="Sign out"
              type="button"
            >
              ↗
            </button>
          </div>
        ) : (
          <button
            className="sidebar-signin"
            onClick={() => setAuthMode("login")}
            type="button"
          >
            <span className="avatar">G</span>
            <span>Sign in to save your portfolio</span>
          </button>
        )}
      </aside>

      <section className="main-column">
        <header className="topbar">
          <div className="breadcrumb">
            <span>Markets</span>
            <span className="breadcrumb-divider">/</span>
            <strong>{panel === "portfolio" ? "My portfolio" : selectedStock?.name ?? "Overview"}</strong>
          </div>
          <div className="topbar-actions">
            <span className="market-status"><span className="live-dot" /> Daily data</span>
            <button
              className="profile-button"
              onClick={() => (account ? signOut() : setAuthMode("login"))}
              type="button"
            >
              {account ? account.email[0].toUpperCase() : "Sign in"}
            </button>
          </div>
        </header>

        <div className="content">
          {error && (
            <div className="alert" role="alert">
              <span>{error}</span>
              <button onClick={() => setError("")} type="button" aria-label="Dismiss error">×</button>
            </div>
          )}

          <section className="page-heading">
            <div>
              <div className="eyebrow">MARKET OVERVIEW <span>·</span> DAILY</div>
              <h1>
                {panel === "portfolio"
                  ? "Your watchlist"
                  : panel === "forecast"
                    ? "Forecast lab"
                    : "Good market morning"}
              </h1>
              <p>
                {panel === "portfolio"
                  ? account
                    ? "A clear view of the companies you follow."
                    : "Sign in to build and sync your personal watchlist."
                  : "Track price action and compare forecasts against a transparent baseline."}
              </p>
            </div>
            <div className="market-date">
              <span className="calendar-icon">▦</span>
              <span>{history.at(-1)?.date.slice(0, 10) ?? "Daily close"}</span>
            </div>
          </section>

          {panel === "portfolio" ? (
            <section className="surface portfolio-panel">
              <div className="section-title-row">
                <div>
                  <h2>Tracked stocks</h2>
                  <p>Your saved symbols, available across your signed-in sessions.</p>
                </div>
                {!account && <button className="primary-button" onClick={() => setAuthMode("login")} type="button">Sign in</button>}
              </div>
              {watchlist.length ? (
                <div className="watchlist-table">
                  {watchlist.map((item) => {
                    const stock = stocks.find((entry) => entry.symbol === item.symbol);
                    return (
                      <button className="watchlist-row" key={item.symbol} onClick={() => { selectSymbol(item.symbol); setPanel("overview"); }} type="button">
                        <span className="ticker-avatar">{item.symbol.slice(0, 1)}</span>
                        <span className="watchlist-name"><strong>{item.symbol}</strong><small>{stock?.name}</small></span>
                        <span className="watchlist-price">{item.symbol === symbol && latestClose ? formatPrice(latestClose) : "View details"}</span>
                        <span className="row-chevron">→</span>
                      </button>
                    );
                  })}
                </div>
              ) : (
                <div className="empty-state">
                  <span className="empty-icon">☆</span>
                  <h3>{account ? "Your watchlist is ready" : "Sign in to start a watchlist"}</h3>
                  <p>{account ? "Add a company from its overview page to track it here." : "Your saved symbols will be private to your account."}</p>
                </div>
              )}
              {account && savedForecasts.length > 0 && (
                <div className="saved-forecasts">
                  <h3>Recent forecasts</h3>
                  {savedForecasts.slice(0, 5).map((item) => (
                    <div className="saved-row" key={item.id}>
                      <span>{item.symbol} · {item.horizon} trading days</span>
                      <strong>{formatPrice(item.future_price)}</strong>
                      <small>{item.method}</small>
                    </div>
                  ))}
                </div>
              )}
            </section>
          ) : (
            <>
              <section className="filter-bar">
                <label className="stock-select-wrap">
                  <span>COMPANY</span>
                  <select value={symbol} onChange={(event) => selectSymbol(event.target.value)}>
                    {stocks.map((stock) => (
                      <option key={stock.symbol} value={stock.symbol}>{stock.name}</option>
                    ))}
                    {!stocks.length && <option value="AAPL">Apple (AAPL)</option>}
                  </select>
                </label>
                <div className="filter-divider" />
                <div className="time-range">
                  <span>PERIOD</span>
                  <strong>5 years</strong>
                </div>
                <div className="filter-spacer" />
                <button className="secondary-button" onClick={toggleWatchlist} type="button">
                  {watchlist.some((item) => item.symbol === symbol) ? "★ Saved" : "☆ Add to watchlist"}
                </button>
                <button className="icon-button refresh-button" onClick={() => { setHistory([]); setLoadingHistory(true); setForecast(null); setError(""); setHistoryVersion((version) => version + 1); }} title="Refresh data" type="button">↻</button>
              </section>

              <section className="metrics-grid">
                <Metric label="Latest adjusted close" value={latestClose ? formatPrice(latestClose) : "—"} change={dayChange ? `${dayChange >= 0 ? "+" : ""}${formatPrice(dayChange)}` : undefined} positive={dayChange >= 0} />
                <Metric label="1-year performance" value={`${yearChange >= 0 ? "+" : ""}${yearChange.toFixed(2)}%`} change="Adjusted close" positive={yearChange >= 0} />
                <Metric label="Market trend" value={history.length > 50 && latestClose >= (history.at(-50)?.close ?? latestClose) ? "Positive" : "Tracking"} change="50-day comparison" positive={latestClose >= (history.at(-50)?.close ?? latestClose)} />
                <Metric label="Data coverage" value={history.length ? `${history.length.toLocaleString()} days` : "—"} change="Yahoo Finance" positive />
              </section>

              <section className="surface chart-card">
                <div className="section-title-row chart-heading">
                  <div>
                    <div className="chart-title"><h2>{symbol} price history</h2><span className="market-tag">US / INDIA</span></div>
                    <p>Daily adjusted closing price · Last 180 sessions</p>
                  </div>
                  <div className="legend"><span /> Adjusted close</div>
                </div>
                {loadingHistory ? <div className="chart-loading">Loading market history…</div> : <PriceChart values={history} forecast={forecast} />}
              </section>

              <div className="lower-grid">
                <section className="surface forecast-card">
                  <div className="section-title-row">
                    <div>
                      <div className="section-overline">MODEL RESEARCH</div>
                      <h2>Forecast evaluation</h2>
                    </div>
                    <span className="research-pill">Out-of-sample</span>
                  </div>
                  <p className="card-description">Compare three models to a last-close baseline before viewing a future estimate.</p>
                  <div className="forecast-controls">
                    <label>
                      <span>TRADING DAYS AHEAD</span>
                      <select value={horizon} onChange={(event) => setHorizon(Number(event.target.value))}>
                        {[5, 10, 20, 30, 60].map((days) => <option key={days} value={days}>{days} days</option>)}
                      </select>
                    </label>
                    <button className="primary-button" disabled={busy || loadingHistory || history.length < 100} onClick={runForecast} type="button">
                      {busy ? "Evaluating…" : "Run forecast"} <span>→</span>
                    </button>
                  </div>
                  {forecast ? (
                    <div className="forecast-details">
                      <div className="forecast-summary">
                        <div><small>SELECTED METHOD</small><strong>{forecast.method}</strong></div>
                        <div><small>HOLDOUT MAE</small><strong>{formatPrice(forecast.mae)}</strong></div>
                        <div><small>WALK-FORWARD FOLDS</small><strong>{forecast.walk_forward.folds}</strong></div>
                      </div>
                      <div className="model-table">
                        <div className="model-row model-header"><span>Model</span><span>MAE</span><span>RMSE</span><span>R²</span></div>
                        {modelScores.map(([name, score]) => (
                          <div className="model-row" key={name}><span>{name}</span><span>{formatPrice(score.mae)}</span><span>{formatPrice(score.rmse)}</span><span>{score.r2.toFixed(3)}</span></div>
                        ))}
                        <div className="model-row baseline-row"><span>Last-close baseline</span><span>{formatPrice(forecast.baseline_mae)}</span><span>—</span><span>—</span></div>
                      </div>
                      <p className="disclaimer">A historical holdout does not guarantee future performance or investment returns.</p>
                    </div>
                  ) : (
                    <div className="forecast-placeholder"><span>⌁</span><div><strong>One-click, leakage-aware evaluation</strong><small>Uses expanding walk-forward selection and a separate chronological test.</small></div></div>
                  )}
                </section>

                <section className="surface activity-card">
                  <div className="section-title-row">
                    <div>
                      <div className="section-overline">YOUR RESEARCH</div>
                      <h2>Recent forecasts</h2>
                    </div>
                    <button className="text-button" onClick={() => setPanel("portfolio")} type="button">View all →</button>
                  </div>
                  {account ? (
                    savedForecasts.length ? savedForecasts.slice(0, 4).map((item) => (
                      <div className="activity-row" key={item.id}>
                        <span className="activity-symbol">{item.symbol.slice(0, 1)}</span>
                        <span className="activity-main"><strong>{item.symbol}</strong><small>{item.horizon} trading days · {item.method}</small></span>
                        <strong>{formatPrice(item.future_price)}</strong>
                      </div>
                    )) : <div className="empty-compact">Your saved forecast history will appear here.</div>
                  ) : (
                    <div className="sign-in-prompt"><span>◷</span><strong>Keep your research in one place</strong><small>Sign in to save forecasts and build a private watchlist.</small><button className="text-button" onClick={() => setAuthMode("login")} type="button">Create a free account →</button></div>
                  )}
                </section>
              </div>
              <footer className="page-footer"><span>MarketLens research workspace</span><span>Data: Yahoo Finance <span className="footer-dot">·</span> Educational use only</span></footer>
            </>
          )}
        </div>
      </section>

      {authMode && (
        <div className="modal-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) setAuthMode(null); }}>
          <section aria-labelledby="auth-title" aria-modal="true" className="auth-modal" role="dialog">
            <button className="modal-close" onClick={() => setAuthMode(null)} type="button" aria-label="Close dialog">×</button>
            <div className="brand-mark modal-brand">M</div>
            <div className="section-overline">PERSONAL RESEARCH SPACE</div>
            <h2 id="auth-title">{authMode === "login" ? "Welcome back" : "Create your account"}</h2>
            <p>Save your watchlist and keep forecast runs together.</p>
            <form className="auth-form" onSubmit={submitAuth}>
              <label>Email address<input autoComplete="email" onChange={(event) => setEmail(event.target.value)} required type="email" value={email} /></label>
              <label>Password<input autoComplete={authMode === "login" ? "current-password" : "new-password"} minLength={authMode === "register" ? 12 : 1} onChange={(event) => setPassword(event.target.value)} required type="password" value={password} /></label>
              {authMode === "register" && <small className="password-hint">Use at least 12 characters.</small>}
              <button className="primary-button auth-submit" disabled={busy} type="submit">{busy ? "Please wait…" : authMode === "login" ? "Sign in" : "Create account"} <span>→</span></button>
            </form>
            <p className="auth-switch">{authMode === "login" ? "New to MarketLens?" : "Already have an account?"}{" "}<button className="text-button" onClick={() => { setError(""); setAuthMode(authMode === "login" ? "register" : "login"); }} type="button">{authMode === "login" ? "Create an account" : "Sign in"}</button></p>
          </section>
        </div>
      )}
    </main>
  );
}
