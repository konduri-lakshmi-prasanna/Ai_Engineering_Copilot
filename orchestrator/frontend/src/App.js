import { useState, useRef, useEffect } from "react";
import "./App.css";

const AGENTS = [
  { id: "orchestrator", label: "Orchestrator Agent", icon: "🧠" },
  { id: "github", label: "GitHub Code Agent", icon: "🐙" },
  { id: "logs", label: "Log Analysis Agent", icon: "📋" },
  { id: "cicd", label: "CI/CD Investigation Agent", icon: "⚙️" },
  { id: "infra", label: "Infrastructure Agent", icon: "🐳" },
  { id: "docs", label: "Knowledge & Docs Agent", icon: "📚" },
  { id: "verification", label: "Verification Agent", icon: "🛡️" },
];

const API_BASE = "http://127.0.0.1:8000";

function App() {
  const [username, setUsername] = useState("");
  const [resolvedUsername, setResolvedUsername] = useState("");
  const [repos, setRepos] = useState([]);
  const [repoName, setRepoName] = useState("");
  const [repoLoading, setRepoLoading] = useState(false);
  const [repoError, setRepoError] = useState("");
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState([]);
  const [loading, setLoading] = useState(false);
  const [agentStatuses, setAgentStatuses] = useState({});
  const [activeTab, setActiveTab] = useState("report");

  // OAuth state
  const [oauthToken, setOauthToken] = useState(null);
  const [oauthLoading, setOauthLoading] = useState(false);
  const [oauthError, setOauthError] = useState("");

  // Context memory for follow-up chat
  const [lastAnalysis, setLastAnalysis] = useState(null);

  const textareaRef = useRef(null);
  const threadEndRef = useRef(null);

  useEffect(() => {
    threadEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading, agentStatuses]);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const token = params.get("token");
    if (token) {
      setOauthToken(token);
      window.history.replaceState({}, document.title, window.location.pathname);
    }
  }, []);

  useEffect(() => {
    if (!oauthToken) return;

    const fetchOwnRepos = async () => {
      setOauthLoading(true);
      setOauthError("");
      setRepos([]);
      setRepoName("");
      setResolvedUsername("");

      try {
        const response = await fetch(
          `${API_BASE}/auth/repos?token=${encodeURIComponent(oauthToken)}`
        );
        const data = await response.json();
        if (!response.ok) {
          throw new Error(data.detail || `Server error: ${response.status}`);
        }
        setRepos(data);
        setResolvedUsername("your GitHub account");
        if (data.length > 0) {
          setRepoName(data[0].full_name);
        } else {
          setOauthError("No repositories found on your account");
        }
      } catch (err) {
        setOauthError(err.message);
      } finally {
        setOauthLoading(false);
      }
    };

    fetchOwnRepos();
  }, [oauthToken]);

  const handleGitHubLogin = () => {
    window.location.href = `${API_BASE}/auth/login`;
  };

  const handleLogout = () => {
    setOauthToken(null);
    setOauthError("");
    setUsername("");
    setResolvedUsername("");
    setRepos([]);
    setRepoName("");
    setRepoError("");
  };

  const handleFetchRepos = async () => {
    const trimmed = username.trim();
    if (!trimmed) return;

    setRepoLoading(true);
    setRepoError("");
    setRepos([]);
    setRepoName("");
    setResolvedUsername("");

    try {
      const response = await fetch(
        `${API_BASE}/github/repos?username=${encodeURIComponent(trimmed)}`
      );
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.detail || `Server error: ${response.status}`);
      }
      setResolvedUsername(data.username);
      setRepos(data.repos);
      if (data.repos.length > 0) {
        setRepoName(data.repos[0].full_name);
      } else {
        setRepoError("No public repositories found for this user");
      }
    } catch (err) {
      setResolvedUsername("");
      setRepoError(err.message);
    } finally {
      setRepoLoading(false);
    }
  };

  const handleUsernameKeyDown = (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      handleFetchRepos();
    }
  };

  const autoGrow = (el) => {
    el.style.height = "auto";
    el.style.height = Math.min(el.scrollHeight, 200) + "px";
  };

  const looksLikeNewLog = (text) => {
    const lineCount = text.split("\n").length;
    const hasErrorSignal = /error|exception|traceback|fail|stack trace|crashloop|oom/i.test(text);
    return lineCount >= 2 && hasErrorSignal;
  };

  const handleNewAnalysis = () => {
    setLastAnalysis(null);
    setMessages([]);
    setAgentStatuses({});
  };

  const handleSend = async () => {
    const text = input.trim();
    if (!text || !repoName || loading) return;

    setMessages((prev) => [...prev, { role: "user", content: text }]);
    setInput("");
    if (textareaRef.current) textareaRef.current.style.height = "auto";

    if (!lastAnalysis && !/error|exception|traceback|fail|stack trace|npm err|crashloop|oom|\bat .+:\d+/i.test(text)) {
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          type: "error",
          content: "Paste a deployment failure log, stack trace, or container error first. Once analyzed, you can ask follow-up questions.",
        },
      ]);
      return;
    }

    setLoading(true);

    const isFollowUp = lastAnalysis && !looksLikeNewLog(text);

    if (isFollowUp) {
      try {
        const response = await fetch(`${API_BASE}/chat`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            repo_name: repoName,
            context: lastAnalysis,
            question: text,
          }),
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.detail || `Server error: ${response.status}`);

        setMessages((prev) => [
          ...prev,
          { role: "assistant", type: "chat", content: data.answer },
        ]);
      } catch (err) {
        setMessages((prev) => [
          ...prev,
          { role: "assistant", type: "error", content: err.message },
        ]);
      } finally {
        setLoading(false);
      }
      return;
    }

    // Initialize agent statuses
    const initialStatuses = {};
    AGENTS.forEach((a) => {
      initialStatuses[a.id] = "RUNNING";
    });
    setAgentStatuses(initialStatuses);

    try {
      const response = await fetch(`${API_BASE}/analyze`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          repo_name: repoName,
          log_text: text,
          github_token: oauthToken || null,
        }),
      });

      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.detail || `Server error: ${response.status}`);
      }

      setLastAnalysis(data);

      const finalStatuses = {};
      AGENTS.forEach((a) => {
        finalStatuses[a.id] = "COMPLETED";
      });
      setAgentStatuses(finalStatuses);

      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          type: "multi_agent_result",
          repo: data.repo,
          incidentId: data.incident_id,
          rounds: data.investigation_rounds,
          rootCause: data.root_cause,
          fixSuggestion: data.fix_suggestion,
          whyItWorks: data.why_it_works,
          beginnerExplanation: data.beginner_explanation,
          interviewQuestions: data.interview_questions,
          documentationLinks: data.documentation_links,
          implicatedCommits: data.implicated_commits,
          errorsFound: data.errors_found,
          agentOutputs: data.agent_outputs || {},
          verification: data.verification || {},
          finalReport: data.final_report || {},
        },
      ]);
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        { role: "assistant", type: "error", content: err.message },
      ]);
      setAgentStatuses({});
    } finally {
      setLoading(false);
    }
  };

  const handleComposerKeyDown = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const isConnected = Boolean(oauthToken || resolvedUsername);

  return (
    <div className="app">
      <div className="particles" aria-hidden="true">
        {Array.from({ length: 16 }).map((_, i) => (
          <span key={i} className="particle" />
        ))}
      </div>

      <aside className="sidebar">
        <div className="sidebar__brand">
          <div className="header__mark">
            <span className="header__mark-ring" />
            <span className="header__mark-core" />
            <span className="header__mark-satellite" />
          </div>
          <div>
            <h1 className="sidebar__title">AI Engineering Copilot</h1>
            <p className="sidebar__subtitle">Multi-Agent Investigation System</p>
          </div>
        </div>

        <div className="field">
          <label className="field__label">
            <span className="field__index">01</span> Connect a repo
          </label>

          {isConnected ? (
            <div className="field__connected">
              <span className="field__connected-status">
                <span className="field__connected-dot" />
                {oauthToken ? "Connected via GitHub" : <>Matched: <strong>{resolvedUsername}</strong></>}
              </span>
              <button type="button" className="logout-button" onClick={handleLogout}>
                Log out
              </button>
            </div>
          ) : (
            <>
              <button
                type="button"
                className="fetch-button fetch-button--full"
                onClick={handleGitHubLogin}
              >
                Login with GitHub
              </button>

              <div style={{ margin: "12px 0", opacity: 0.6, fontSize: 12, textAlign: "center" }}>
                or browse public repos by username
              </div>

              <input
                className="field__input field__input--mono"
                type="text"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                onKeyDown={handleUsernameKeyDown}
                placeholder="e.g. octocat or you@email.com"
                spellCheck={false}
              />
              <button
                type="button"
                className="fetch-button fetch-button--full"
                onClick={handleFetchRepos}
                disabled={repoLoading || !username.trim()}
              >
                {repoLoading ? "Loading..." : "Fetch repos"}
              </button>
              {repoError && <div className="field__error">{repoError}</div>}
            </>
          )}

          {oauthLoading && <div className="field__resolved">Loading your repos...</div>}
          {oauthError && <div className="field__error">{oauthError}</div>}
        </div>

        {repos.length > 0 && (
          <div className="field field--grow">
            <label className="field__label">
              <span className="field__index">02</span> Repository
            </label>
            <div className="repo-list">
              {repos.map((r) => (
                <button
                  key={r.full_name}
                  type="button"
                  className={
                    "repo-list__item" +
                    (r.full_name === repoName ? " repo-list__item--active" : "")
                  }
                  onClick={() => setRepoName(r.full_name)}
                >
                  <span className="repo-list__name-wrap">
                    <span className="repo-list__name">{r.full_name}</span>
                  </span>
                  {r.private && <span className="repo-list__badge">private</span>}
                </button>
              ))}
            </div>
          </div>
        )}

        <div className="field" style={{ marginTop: "auto" }}>
          <label className="field__label">
            <span className="field__index">03</span> Specialist Agents
          </label>
          <div style={{ display: "flex", flexDirection: "column", gap: "6px", fontSize: "12px" }}>
            {AGENTS.map((agent) => (
              <div
                key={agent.id}
                style={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  padding: "5px 8px",
                  borderRadius: "4px",
                  background: "rgba(255,255,255,0.03)",
                }}
              >
                <span>{agent.icon} {agent.label}</span>
                <span
                  style={{
                    fontSize: "10px",
                    fontWeight: 600,
                    padding: "2px 6px",
                    borderRadius: "3px",
                    color:
                      agentStatuses[agent.id] === "RUNNING"
                        ? "#6ffbe0"
                        : agentStatuses[agent.id] === "COMPLETED"
                        ? "#9b8cff"
                        : "#8b93ab",
                  }}
                >
                  {agentStatuses[agent.id] || "IDLE"}
                </span>
              </div>
            ))}
          </div>
        </div>

        {messages.length > 0 && (
          <button
            type="button"
            className="fetch-button fetch-button--full"
            onClick={handleNewAnalysis}
            style={{ marginTop: 12 }}
          >
            New analysis
          </button>
        )}
      </aside>

      <main className="chat">
        <div className="chat__thread">
          {messages.length === 0 && (
            <div className="chat__empty">
              {repoName
                ? `Paste a deployment log or stack trace for ${repoName} below to trigger the multi-agent investigation.`
                : "Pick a repo on the left, then paste an error or deployment log below."}
            </div>
          )}

          {messages.map((m, i) =>
            m.role === "user" ? (
              <div key={i} className="bubble bubble--user">
                <div className="bubble__content">{m.content}</div>
              </div>
            ) : m.type === "chat" ? (
              <div key={i} className="bubble bubble--assistant">
                <div className="result">
                  <div className="result__body" style={{ whiteSpace: "pre-wrap" }}>{m.content}</div>
                </div>
              </div>
            ) : m.type === "error" ? (
              <div key={i} className="bubble bubble--assistant">
                <div className="result result--error">
                  <div className="result__label">Investigation Failed</div>
                  <div className="result__body">{m.content}</div>
                </div>
              </div>
            ) : (
              <div key={i} className="bubble bubble--assistant">
                <div className="result">
                  <div className="result__meta">
                    <span>{m.repo}</span>
                    <span className="result__dot">·</span>
                    <span>Round {m.rounds || 1}</span>
                    <span className="result__dot">·</span>
                    <span>{m.errorsFound} error signals</span>
                  </div>

                  {/* Tabs */}
                  <div style={{ display: "flex", gap: "8px", margin: "14px 0", borderBottom: "1px solid rgba(255,255,255,0.1)", paddingBottom: "6px" }}>
                    <button
                      type="button"
                      style={{
                        background: "none",
                        border: "none",
                        color: activeTab === "report" ? "#6ffbe0" : "#8b93ab",
                        fontWeight: activeTab === "report" ? 600 : 400,
                        cursor: "pointer",
                        padding: "4px 8px",
                      }}
                      onClick={() => setActiveTab("report")}
                    >
                      Root Cause & Fix
                    </button>
                    <button
                      type="button"
                      style={{
                        background: "none",
                        border: "none",
                        color: activeTab === "verification" ? "#6ffbe0" : "#8b93ab",
                        fontWeight: activeTab === "verification" ? 600 : 400,
                        cursor: "pointer",
                        padding: "4px 8px",
                      }}
                      onClick={() => setActiveTab("verification")}
                    >
                      Verification & Evidence
                    </button>
                    <button
                      type="button"
                      style={{
                        background: "none",
                        border: "none",
                        color: activeTab === "agents" ? "#6ffbe0" : "#8b93ab",
                        fontWeight: activeTab === "agents" ? 600 : 400,
                        cursor: "pointer",
                        padding: "4px 8px",
                      }}
                      onClick={() => setActiveTab("agents")}
                    >
                      Specialist Agents ({Object.keys(m.agentOutputs || {}).length})
                    </button>
                  </div>

                  {activeTab === "report" && (
                    <>
                      <div className="result__label result__label--success">
                        Most Likely Root Cause
                      </div>
                      <div className="result__body">{m.rootCause}</div>

                      {m.fixSuggestion && (
                        <>
                          <div className="result__label result__label--success" style={{ marginTop: 14 }}>
                            Recommended Fix
                          </div>
                          <div className="result__body" style={{ whiteSpace: "pre-wrap" }}>{m.fixSuggestion}</div>
                        </>
                      )}

                      {m.whyItWorks && (
                        <>
                          <div className="result__label result__label--success" style={{ marginTop: 14 }}>
                            Why This Fix Works
                          </div>
                          <div className="result__body">{m.whyItWorks}</div>
                        </>
                      )}

                      {m.finalReport?.preventive_measures?.length > 0 && (
                        <>
                          <div className="result__label result__label--success" style={{ marginTop: 14 }}>
                            Preventive Measures
                          </div>
                          <ul className="result__body" style={{ margin: 0, paddingLeft: 18 }}>
                            {m.finalReport.preventive_measures.map((p, pi) => (
                              <li key={pi}>{p}</li>
                            ))}
                          </ul>
                        </>
                      )}

                      {m.beginnerExplanation && (
                        <>
                          <div className="result__label result__label--success" style={{ marginTop: 14 }}>
                            Underlying Concept
                          </div>
                          <div className="result__body">{m.beginnerExplanation}</div>
                        </>
                      )}

                      {m.interviewQuestions?.length > 0 && (
                        <>
                          <div className="result__label result__label--success" style={{ marginTop: 14 }}>
                            Related Interview Questions
                          </div>
                          <ul className="result__body" style={{ margin: 0, paddingLeft: 18 }}>
                            {m.interviewQuestions.map((q, qi) => (
                              <li key={qi}>{q}</li>
                            ))}
                          </ul>
                        </>
                      )}
                    </>
                  )}

                  {activeTab === "verification" && (
                    <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
                      <div>
                        <div className="result__label result__label--success">Confirmed Facts</div>
                        <ul className="result__body" style={{ margin: 0, paddingLeft: 18 }}>
                          {(m.verification?.confirmed_facts || ["Log error line identified."]).map((f, fi) => (
                            <li key={fi}>{f}</li>
                          ))}
                        </ul>
                      </div>

                      {m.verification?.contradictions_found?.length > 0 && (
                        <div>
                          <div className="result__label" style={{ color: "#ff7a90" }}>Contradictions & Gaps Found</div>
                          <ul className="result__body" style={{ margin: 0, paddingLeft: 18 }}>
                            {m.verification.contradictions_found.map((c, ci) => (
                              <li key={ci}>{c}</li>
                            ))}
                          </ul>
                        </div>
                      )}

                      <div>
                        <div className="result__label result__label--success">Validation Performed</div>
                        <div className="result__body">{m.verification?.validation_performed || "Automated cross-agent verification"}</div>
                      </div>

                      {m.finalReport?.supporting_evidence?.length > 0 && (
                        <div>
                          <div className="result__label result__label--success">Supporting Evidence Items</div>
                          <div style={{ display: "flex", flexDirection: "column", gap: "8px", marginTop: "8px" }}>
                            {m.finalReport.supporting_evidence.map((ev, evi) => (
                              <div
                                key={evi}
                                style={{
                                  background: "rgba(255,255,255,0.03)",
                                  padding: "8px 12px",
                                  borderRadius: "6px",
                                  borderLeft: "3px solid #6ffbe0",
                                }}
                              >
                                <div style={{ fontSize: "11px", color: "#6ffbe0", fontFamily: "JetBrains Mono" }}>
                                  [{ev.source_type}] {ev.reference}
                                </div>
                                <div style={{ fontSize: "12px", color: "#eef1f8", marginTop: "4px" }}>
                                  {ev.snippet}
                                </div>
                                <div style={{ fontSize: "11px", color: "#8b93ab", marginTop: "2px" }}>
                                  {ev.relevance}
                                </div>
                              </div>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>
                  )}

                  {activeTab === "agents" && (
                    <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
                      {Object.entries(m.agentOutputs || {}).map(([key, out]) => (
                        <div
                          key={key}
                          style={{
                            background: "rgba(255,255,255,0.02)",
                            padding: "10px 14px",
                            borderRadius: "6px",
                            border: "1px solid rgba(255,255,255,0.06)",
                          }}
                        >
                          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                            <strong style={{ color: "#6ffbe0" }}>{out.agent_name || key}</strong>
                            <span
                              style={{
                                fontSize: "10px",
                                padding: "2px 6px",
                                borderRadius: "3px",
                                background: out.status === "COMPLETED" ? "rgba(111,251,224,0.1)" : "rgba(255,122,144,0.1)",
                                color: out.status === "COMPLETED" ? "#6ffbe0" : "#ff7a90",
                              }}
                            >
                              {out.status}
                            </span>
                          </div>
                          <p style={{ fontSize: "12px", color: "#eef1f8", margin: "6px 0" }}>{out.summary}</p>
                          {out.findings?.length > 0 && (
                            <div style={{ fontSize: "11px", color: "#8b93ab" }}>
                              <strong>Findings ({out.findings.length}):</strong>
                              {out.findings.map((f, fi) => (
                                <div key={fi} style={{ marginTop: "2px" }}>• [{f.severity}] {f.description}</div>
                              ))}
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            )
          )}

          {loading && (
            <div className="bubble bubble--assistant">
              <div style={{ padding: "12px" }}>
                <div style={{ display: "flex", alignItems: "center", gap: "8px", marginBottom: "10px" }}>
                  <span className="composer__spinner" />
                  <span style={{ fontSize: "13px", fontWeight: 600, color: "#6ffbe0" }}>
                    Multi-Agent Orchestrator Dispatching Specialists...
                  </span>
                </div>
                <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))", gap: "8px" }}>
                  {AGENTS.map((agent) => (
                    <div
                      key={agent.id}
                      style={{
                        padding: "8px",
                        borderRadius: "4px",
                        background: "rgba(255,255,255,0.03)",
                        fontSize: "12px",
                        display: "flex",
                        alignItems: "center",
                        gap: "6px",
                      }}
                    >
                      <span>{agent.icon}</span>
                      <span>{agent.label}</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}

          <div ref={threadEndRef} />
        </div>

        <div className="composer">
          <div className="composer__field-glow" />
          <div className={"composer__box" + (!repoName ? " composer__box--disabled" : "")}>
            <textarea
              ref={textareaRef}
              className="composer__input"
              value={input}
              onChange={(e) => {
                setInput(e.target.value);
                autoGrow(e.target);
              }}
              onKeyDown={handleComposerKeyDown}
              placeholder={
                repoName
                  ? "Paste deployment log, container crash, or stack trace..."
                  : "Pick a repo on the left first..."
              }
              rows={1}
              disabled={!repoName}
              spellCheck={false}
            />
            <button
              type="button"
              className="composer__send"
              onClick={handleSend}
              disabled={loading || !input.trim() || !repoName}
              aria-label="Send"
            >
              {loading ? (
                <span className="composer__spinner" />
              ) : (
                <svg viewBox="0 0 24 24" width="16" height="16" fill="none">
                  <path d="M4 12L20 4L13 20L11 13L4 12Z" fill="currentColor" />
                </svg>
              )}
            </button>
          </div>
          <div className="composer__hint">Enter to send · Shift + Enter for a new line</div>
        </div>
      </main>
    </div>
  );
}

export default App;