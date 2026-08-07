import { useState } from "react";
import "./App.css";

const STAGES = ["github", "logs", "reasoning"];

function App() {
  const [repoName, setRepoName] = useState("facebook/react");
  const [logText, setLogText] = useState("");
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [activeStage, setActiveStage] = useState(-1);

  const handleAnalyze = async () => {
    setLoading(true);
    setError("");
    setResult(null);
    setActiveStage(0);

    const stageTimer = setInterval(() => {
      setActiveStage((prev) => (prev < STAGES.length - 1 ? prev + 1 : prev));
    }, 700);

    try {
      const response = await fetch("http://127.0.0.1:8000/analyze", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ repo_name: repoName, log_text: logText }),
      });

      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.detail || `Server error: ${response.status}`);
      }

      setResult(data);
    } catch (err) {
      setError(err.message);
    } finally {
      clearInterval(stageTimer);
      setActiveStage(STAGES.length);
      setLoading(false);
    }
  };

  return (
    <div className="app">
      <div className="app__glow" />

      <header className="header">
        <div className="header__mark">◆</div>
        <div>
          <h1 className="header__title">Engineering Copilot</h1>
          <p className="header__subtitle">
            Point it at any public repo. It reads the commits, reads the log, tells you what broke.
          </p>
        </div>
      </header>

      <main className="panel">
        <div className="field">
          <label className="field__label">
            <span className="field__index">01</span> Repository
          </label>
          <input
            className="field__input field__input--mono"
            type="text"
            value={repoName}
            onChange={(e) => setRepoName(e.target.value)}
            placeholder="owner/repo"
            spellCheck={false}
          />
        </div>

        <div className="field">
          <label className="field__label">
            <span className="field__index">02</span> Deployment log
          </label>
          <textarea
            className="field__input field__input--mono field__input--area"
            value={logText}
            onChange={(e) => setLogText(e.target.value)}
            rows={9}
            placeholder="Paste stack traces, error lines, or a full deploy log..."
            spellCheck={false}
          />
        </div>

        <button
          className="run-button"
          onClick={handleAnalyze}
          disabled={loading || !logText || !repoName}
        >
          {loading ? "Analyzing" : "Run analysis"}
          <span className="run-button__arrow">→</span>
        </button>

        {activeStage >= 0 && (
          <div className="trace">
            {STAGES.map((stage, i) => (
              <div key={stage} className="trace__item">
                <div
                  className={
                    "trace__dot" +
                    (i < activeStage ? " trace__dot--done" : "") +
                    (i === activeStage && loading ? " trace__dot--active" : "")
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
        )}

        {error && (
          <div className="result result--error">
            <div className="result__label">Analysis failed</div>
            <div className="result__body">{error}</div>
          </div>
        )}

        {result && (
          <div className="result">
            <div className="result__meta">
              <span>{result.repo}</span>
              <span className="result__dot">·</span>
              <span>{result.commits_analyzed.length} commits checked</span>
              <span className="result__dot">·</span>
              <span>{result.errors_found} errors found</span>
            </div>
            <div className="result__label result__label--success">Root cause</div>
            <div className="result__body">{result.root_cause}</div>
          </div>
        )}
      </main>
    </div>
  );
}

export default App;