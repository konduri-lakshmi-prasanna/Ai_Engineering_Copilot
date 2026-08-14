import { useState, useRef, useEffect } from "react";
import "./App.css";

const STAGES = ["github", "logs", "reasoning"];
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
  const [activeStage, setActiveStage] = useState(-1);

  // --- OAuth state ---
  const [oauthToken, setOauthToken] = useState(null);
  const [oauthLoading, setOauthLoading] = useState(false);
  const [oauthError, setOauthError] = useState("");

  // --- Conversation memory: last full analysis, so follow-up questions
  // don't re-run the whole pipeline from scratch. ---
  const [lastAnalysis, setLastAnalysis] = useState(null);

  const textareaRef = useRef(null);
  const threadEndRef = useRef(null);

  useEffect(() => {
    threadEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

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

  // Single logout/reset for BOTH paths: OAuth login and username lookup.
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
    const hasErrorSignal = /error|exception|traceback|fail|stack trace/i.test(text);
    return lineCount >= 2 && hasErrorSignal;
  };

  const handleNewAnalysis = () => {
    setLastAnalysis(null);
    setMessages([]);
  };

  const handleSend = async () => {
    const text = input.trim();
    if (!text || !repoName || loading) return;

    setMessages((prev) => [...prev, { role: "user", content: text }]);
    setInput("");
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
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

    setActiveStage(0);

    const stageTimer = setInterval(() => {
      setActiveStage((prev) => (prev < STAGES.length - 1 ? prev + 1 : prev));
    }, 700);

    try {
      const response = await fetch(`${API_BASE}/analyze`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ repo_name: repoName, log_text: text }),
      });

      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.detail || `Server error: ${response.status}`);
      }

      setLastAnalysis(data);

      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          type: "result",
          repo: data.repo,
          commitsScanned: data.commits_scanned,
          scanMode: data.scan_mode,
          implicatedCommits: data.implicated_commits,
          errorsFound: data.errors_found,
          rootCause: data.root_cause,
          fixSuggestion: data.fix_suggestion,
          whyItWorks: data.why_it_works,
          beginnerExplanation: data.beginner_explanation,
          interviewQuestions: data.interview_questions,
        },
      ]);
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        { role: "assistant", type: "error", content: err.message },
      ]);
    } finally {
      clearInterval(stageTimer);
      setActiveStage(-1);
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
            <h1 className="sidebar__title">Engineering Copilot</h1>
            <p className="sidebar__subtitle">Debug against a repo's real commit history.</p>
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
                ? `Paste an error or deploy log for ${repoName} below to get started.`
                : "Pick a repo on the left, then paste an error or deploy log below."}
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
                  <div className="result__body">{m.content}</div>
                </div>
              </div>
            ) : m.type === "error" ? (
              <div key={i} className="bubble bubble--assistant">
                <div className="result result--error">
                  <div className="result__label">Analysis failed</div>
                  <div className="result__body">{m.content}</div>
                </div>
              </div>
            ) : (
              <div key={i} className="bubble bubble--assistant">
                <div className="result">
                  <div className="result__meta">
                    <span>{m.repo}</span>
                    <span className="result__dot">·</span>
                    <span>
                      {m.commitsScanned} {m.scanMode === "targeted" ? "files scanned (targeted)" : "commits scanned"}
                    </span>
                    <span className="result__dot">·</span>
                    <span>{m.errorsFound} errors found</span>
                  </div>

                  {m.implicatedCommits && m.implicatedCommits.length > 0 ? (
                    <div className="implicated">
                      <div className="result__label result__label--success">
                        {m.implicatedCommits.length === 1
                          ? "Commit responsible"
                          : `${m.implicatedCommits.length} commits responsible`}
                      </div>
                      {m.implicatedCommits.map((c, ci) => (
                        <div key={ci} className="implicated__item">
                          <span className="implicated__sha">{c.sha}</span>
                          <span className="implicated__reason">{c.reason}</span>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div className="result__label">No commit in the scanned range looked responsible</div>
                  )}

                  <div className="result__label result__label--success" style={{ marginTop: 14 }}>
                    Root cause
                  </div>
                  <div className="result__body">{m.rootCause}</div>

                  {m.fixSuggestion && (
                    <>
                      <div className="result__label result__label--success" style={{ marginTop: 14 }}>
                        Suggested fix
                      </div>
                      <div className="result__body">{m.fixSuggestion}</div>
                    </>
                  )}

                  {m.whyItWorks && (
                    <>
                      <div className="result__label result__label--success" style={{ marginTop: 14 }}>
                        Why this fix works
                      </div>
                      <div className="result__body">{m.whyItWorks}</div>
                    </>
                  )}

                  {m.beginnerExplanation && (
                    <>
                      <div className="result__label result__label--success" style={{ marginTop: 14 }}>
                        Learn: what's going on here
                      </div>
                      <div className="result__body">{m.beginnerExplanation}</div>
                    </>
                  )}

                  {m.interviewQuestions && m.interviewQuestions.length > 0 && (
                    <>
                      <div className="result__label result__label--success" style={{ marginTop: 14 }}>
                        Related interview questions
                      </div>
                      <ul className="result__body" style={{ margin: 0, paddingLeft: 18 }}>
                        {m.interviewQuestions.map((q, qi) => (
                          <li key={qi}>{q}</li>
                        ))}
                      </ul>
                    </>
                  )}
                </div>
              </div>
            )
          )}

          {loading && (
            <div className="bubble bubble--assistant">
              <div className="trace">
                {STAGES.map((stage, i) => (
                  <div key={stage} className="trace__item">
                    <div
                      className={
                        "trace__dot" +
                        (i < activeStage ? " trace__dot--done" : "") +
                        (i === activeStage ? " trace__dot--active" : "")
                      }
                    />
                    <span className="trace__label">
                      {stage === "github" && "Reading commits"}
                      {stage === "logs" && "Parsing log"}
                      {stage === "reasoning" && "Reasoning"}
                    </span>
                    {i < STAGES.length - 1 && <div className="trace__line" />}
                  </div>
                ))}
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
                  ? "Paste a stack trace or deploy log..."
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