import { useState } from "react";

function App() {
  const [repoName, setRepoName] = useState("konduri-lakshmi-prasanna/Ai_Engineering_Copilot");
  const [logText, setLogText] = useState("");
  const [result, setResult] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const handleAnalyze = async () => {
    setLoading(true);
    setError("");
    setResult("");

    try {
      const response = await fetch("http://127.0.0.1:8000/analyze", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ repo_name: repoName, log_text: logText }),
      });

      if (!response.ok) {
        throw new Error(`Server error: ${response.status}`);
      }

      const data = await response.json();
      setResult(data.root_cause);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ maxWidth: 700, margin: "40px auto", fontFamily: "sans-serif", padding: "0 20px" }}>
      <h1>AI Engineering Copilot</h1>
      <p>Paste a deployment log and let the copilot find the root cause.</p>

      <label style={{ display: "block", marginTop: 20, fontWeight: "bold" }}>
        GitHub Repo (owner/repo)
      </label>
      <input
        type="text"
        value={repoName}
        onChange={(e) => setRepoName(e.target.value)}
        style={{ width: "100%", padding: 8, marginTop: 4 }}
      />

      <label style={{ display: "block", marginTop: 20, fontWeight: "bold" }}>
        Deployment Log
      </label>
      <textarea
        value={logText}
        onChange={(e) => setLogText(e.target.value)}
        rows={8}
        placeholder="Paste your error log here..."
        style={{ width: "100%", padding: 8, marginTop: 4, fontFamily: "monospace" }}
      />

      <button
        onClick={handleAnalyze}
        disabled={loading || !logText}
        style={{
          marginTop: 20,
          padding: "10px 20px",
          background: "#2563eb",
          color: "white",
          border: "none",
          borderRadius: 6,
          cursor: loading ? "not-allowed" : "pointer",
        }}
      >
        {loading ? "Analyzing..." : "Analyze Root Cause"}
      </button>

      {error && (
        <div style={{ marginTop: 20, padding: 12, background: "#fee2e2", color: "#991b1b", borderRadius: 6 }}>
          Error: {error}
        </div>
      )}

      {result && (
        <div style={{ marginTop: 20, padding: 16, background: "#f3f4f6", borderRadius: 6, whiteSpace: "pre-wrap" }}>
          <strong>Root Cause Analysis:</strong>
          <p>{result}</p>
        </div>
      )}
    </div>
  );
}

export default App;