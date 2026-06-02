import { FormEvent, startTransition, useState } from "react";

import { askAi, routeInput } from "./api";
import type { AskResponse, RouteDecision, RouteKind } from "./routerTypes";

const examples = [
  "github.com/harupipipipi/rumiai",
  "rumiai PR156 mergeどうする",
  "Go fmtって必要？",
  "!g rumiai startup profile",
];

function routeLabel(route: RouteKind): string {
  switch (route) {
    case "URL_NAVIGATE":
      return "Navigate";
    case "GOOGLE_REDIRECT":
      return "Google";
    case "ASK_AI":
      return "AI";
    case "ASK_AI_WITH_SEARCH":
      return "AI + Search";
    case "BLOCKED":
      return "Blocked";
  }
}

export default function App() {
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [decision, setDecision] = useState<RouteDecision | null>(null);
  const [answer, setAnswer] = useState<AskResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const query = input.trim();
    if (!query || loading) {
      return;
    }

    setLoading(true);
    setError(null);
    setAnswer(null);

    try {
      const nextDecision = await routeInput(query);
      startTransition(() => setDecision(nextDecision));

      if (nextDecision.route === "URL_NAVIGATE" || nextDecision.route === "GOOGLE_REDIRECT") {
        if (nextDecision.target_url) {
          window.location.href = nextDecision.target_url;
          return;
        }
        throw new Error("target URL is missing");
      }

      if (nextDecision.route === "BLOCKED") {
        setError(nextDecision.reason);
        return;
      }

      const nextAnswer = await askAi(query, nextDecision.route === "ASK_AI_WITH_SEARCH");
      startTransition(() => setAnswer(nextAnswer));
    } catch (submitError) {
      setError(submitError instanceof Error ? submitError.message : "Request failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="shell">
      <div className="orb orb-left" />
      <div className="orb orb-right" />
      <section className="hero">
        <p className="eyebrow">Search Home Surface</p>
        <h1>Rumi Search</h1>
        <p className="lede">
          URL はそのまま移動。質問は AI に送る。新しい情報が必要そうなものだけ検索付きに寄せます。
        </p>

        <form className="search-form" onSubmit={handleSubmit}>
          <label className="sr-only" htmlFor="search-input">
            Search
          </label>
          <input
            id="search-input"
            className="search-input"
            value={input}
            onChange={(event) => setInput(event.target.value)}
            placeholder="URL / 調べたいこと / !g / !ai / !url"
            autoComplete="off"
            spellCheck={false}
          />
          <button className="search-button" type="submit" disabled={loading}>
            {loading ? "Routing..." : "Go"}
          </button>
        </form>

        <div className="example-row">
          {examples.map((example) => (
            <button
              key={example}
              type="button"
              className="example-chip"
              onClick={() => setInput(example)}
            >
              {example}
            </button>
          ))}
        </div>
      </section>

      <section className="panel-grid">
        <article className="panel route-panel">
          <div className="panel-header">
            <span>Route</span>
            {decision ? <span className={`badge badge-${decision.route.toLowerCase()}`}>{routeLabel(decision.route)}</span> : null}
          </div>
          {decision ? (
            <div className="panel-body">
              <dl className="stats">
                <div>
                  <dt>Confidence</dt>
                  <dd>{Math.round(decision.confidence * 100)}%</dd>
                </div>
                <div>
                  <dt>Source</dt>
                  <dd>{decision.source}</dd>
                </div>
              </dl>
              <p className="reason">{decision.reason}</p>
              <p className="query-preview">{decision.normalized_query}</p>
            </div>
          ) : (
            <p className="placeholder">まだ route は出ていません。</p>
          )}
        </article>

        <article className="panel answer-panel">
          <div className="panel-header">
            <span>Answer</span>
            {answer?.model ? <span className="badge badge-model">{answer.model}</span> : null}
          </div>
          {error ? (
            <p className="error-message">{error}</p>
          ) : answer?.answer ? (
            <div className="panel-body">
              <p className="answer-text">{answer.answer}</p>
              {answer.used_tools && answer.used_tools.length > 0 ? (
                <div className="tool-row">
                  {answer.used_tools.map((tool) => (
                    <span key={tool} className="tool-chip">
                      {tool}
                    </span>
                  ))}
                </div>
              ) : null}
            </div>
          ) : (
            <p className="placeholder">AI 回答はここに表示されます。</p>
          )}
        </article>
      </section>
    </main>
  );
}
