import { useState, useRef, useEffect } from "react";
import "./App.css";

const STAGES = ["github", "logs", "reasoning"];

function App() {
  const [username, setUsername] = useState("");
  const [repos, setRepos] = useState([]);
  const [repoName, setRepoName] = useState("");
  const [repoLoading, setRepoLoading] = useState(false);
  const [repoError, setRepoError] = useState("");
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState([]);
  const [loading, setLoading] = useState(false);
  const [activeStage, setActiveStage] = useState(-1);

  const textareaRef = useRef(null);
  const threadEndRef = useRef(null);

  useEffect(() => {
    threadEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  const handleFetchRepos = async () => {
    const trimmed = username.trim();
    if (!trimmed) return;

    setRepoLoading(true);
    setRepoError("");
    setRepos([]);
    setRepoName("");

    try {
      const response = await fetch(
        `http://127.0.0.1:8000/github/repos?username=${encodeURIComponent(trimmed)}`
      );
      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.detail || `Server error: ${response.status}`);
      }

      setRepos(data);
      if (data.length > 0) {
        setRepoName(data[0].full_name);
      } else {
        setRepoError("No public repositories found for this user");
      }
    } catch (err) {
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

  const handleSend = async () => {
    const text = input.trim();
    if (!text || !repoName || loading) return;

    setMessages((prev) => [...prev, { role: "user", content: text }]);
    setInput("");
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
    }

    setLoading(true);
    setActiveStage(0);

    const stageTimer = setInterval(() => {
      setActiveStage((prev) => (prev < STAGES.length - 1 ? prev + 1 : prev));
    }, 700);

    try {
      const response = await fetch("http://127.0.0.1:8000/analyze", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ repo_name: repoName, log_text: text }),
      });

      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.detail || `Server error: ${response.status}`);
      }

      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          type: "result",
          repo: data.repo,
          commitsScanned: data.commits_scanned,
          implicatedCommits: data.implicated_commits,
          errorsFound: data.errors_found,
          rootCause: data.root_cause,
          fixSuggestion: data.fix_suggestion,
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
            <span className="field__index">01</span> GitHub username
          </label>
          <input
            className="field__input field__input--mono"
            type="text"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            onKeyDown={handleUsernameKeyDown}
            placeholder="e.g. octocat"
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
                  <span className="repo-list__name">{r.full_name}</span>
                  {r.private && <span className="repo-list__badge">private</span>}
                </button>
              ))}
            </div>
          </div>
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
                    <span>{m.commitsScanned} commits scanned</span>
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