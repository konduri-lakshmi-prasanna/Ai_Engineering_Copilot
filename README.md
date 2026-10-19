# AI Engineering Copilot — Genuine Multi-Agent System

An autonomous multi-agent AI engineering assistant that investigates software deployment failures, correlates code changes, deployment logs, CI/CD pipelines, container runtime events, and technical documentation, rigorously verifies candidate root causes, and delivers actionable incident reports with concrete remediation instructions.

---

## 1. System Architecture

The copilot coordinates 7 specialized agents via a compiled **LangGraph** state graph with parallel fan-out execution, cross-agent evidence consolidation, verification validation, and a bounded re-investigation loop.

```
                              [ Incident Request ]
                                       │
                                       ▼
                            [ Orchestrator Agent ]
                          (Plan & Specialist Dispatch)
                                       │
                 ┌─────────────┬───────┴───────┬─────────────┐
                 ▼             ▼               ▼             ▼
          [ GitHub Agent ] [ Logs Agent ] [ CI/CD Agent ] [ Infra Agent ]
                 │             │               │             │
                 └─────────────┼───────────────┴─────────────┘
                               ▼ (Parallel Fan-In)
                           [ Merge Node ]
                               │
                               ▼
                    [ Knowledge / Docs Agent ]
                     (Local Curated Corpus RAG)
                               │
                               ▼
                     [ Verification Agent ]
                 (Fact Checking & Contradictions)
                               │
                      Evidence Sufficient?
                     ┌─────────┴─────────┐
                  No │                   │ Yes
                     ▼                   ▼
         [ Re-investigation Node ]  [ Final Incident Report ]
           (Loop up to Max Rounds)       │
                                         ▼
                                       [ END ]
```

---

## 2. Specialized Agents

| Agent | Module | Primary Responsibilities | Evidence Generated |
|---|---|---|---|
| **1. Orchestrator Agent** | `agents/orchestrator_agent.py` | Analyzes incident input, formulates an `InvestigationPlan`, dispatches specialists in parallel, merges findings, triggers verification, bounds retries, synthesizes `IncidentReport`. | Investigation plan, final report, agent summaries. |
| **2. GitHub Code Investigation Agent** | `agents/github_agent.py` | Connects via **Model Context Protocol (MCP)** or PyGithub API fallback. Analyzes commits, code changes, `package.json`, `Dockerfile`, and stack-trace implicated files. | `github_code`, `github_commit` with commit SHAs, line numbers, diffs. |
| **3. Log Analysis Agent** | `agents/logs_agent.py` | Deterministic parsing of stack traces and error lines via `log_parser.py`. Distinguishes primary root errors from cascading failures and rollback notices. | `log_line` citations with exact line numbers and exception signatures. |
| **4. CI/CD Investigation Agent** | `agents/cicd_agent.py` | Inspects `.github/workflows/` YAML workflow configs, build/test exit codes, and pipeline failure signals. | `cicd_step` references and workflow definitions. |
| **5. Infrastructure Investigation Agent** | `agents/infra_agent.py` | Inspects container configs (`Dockerfile`, `docker-compose.yml`), container lifecycle errors (CrashLoopBackOff, OOMKilled, port allocation conflicts). | `infra_event` records. |
| **6. Knowledge & Documentation Agent** | `agents/docs_rag_agent.py` | Fast offline TF-IDF RAG retrieval over curated playbooks in `agents/docs/`. Never fabricates external citations. | `documentation` citations with similarity scores and reference URLs. |
| **7. Verification Agent** | `agents/verification_agent.py` | Evaluates proposed hypotheses against tangible code/log facts. Detects contradictions, unsupported assumptions, runs deterministic validations, decides if evidence is sufficient. | Confirmed facts list, contradictions, fix validation status. |

---

## 3. Model Context Protocol (MCP) Integration

The project includes genuine **Model Context Protocol (MCP)** support via the official `mcp` SDK:
- **Client Implementation**: Located at `orchestrator/mcp_clients/github_mcp_client.py`.
- **Transport**: Standard stdio transport connecting to the official GitHub MCP server (`@modelcontextprotocol/server-github`).
- **Safety**: Read-only tools are enforced by default (`get_file_contents`, `list_commits`, `search_code`).
- **Resilience**: If the MCP server is not running or disabled (`GITHUB_MCP_ENABLED=false`), the system automatically falls back to direct GitHub API calls via `PyGithub`, with integration status reported in `/health` and in agent outputs.

### Setting up the GitHub MCP Server
1. Ensure Node.js (`npx`) is installed.
2. In `orchestrator/.env`, configure:
   ```env
   GITHUB_MCP_ENABLED=true
   GITHUB_MCP_SERVER_COMMAND=npx -y @modelcontextprotocol/server-github
   GITHUB_TOKEN=ghp_your_personal_access_token_here
   ```

---

## 4. API Endpoints

FastAPI server runs on port `8000`:

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/analyze` | Executes the LangGraph multi-agent investigation synchronously and returns the complete structured incident report, specialist findings, and verified evidence. |
| `POST` | `/analyze/stream` | Server-Sent Events (SSE) streaming endpoint streaming live agent progress events as each specialist executes. |
| `POST` | `/chat` | Context-aware follow-up engineering chat grounded in the completed multi-agent investigation. |
| `GET` | `/health` | Health & readiness check returning MCP connection status and registered agents. |
| `GET` | `/github/repos` | Fetches repositories for a given GitHub username. |
| `GET` | `/auth/login` | Initiates GitHub OAuth authentication. |
| `GET` | `/auth/callback` | OAuth redirect callback receiving access token. |
| `GET` | `/auth/repos` | Lists repositories for authenticated OAuth user. |
| `GET` | `/` | API status message. |

---

## 5. Security & Input Sanitization

- **No Hardcoded Credentials**: Real API keys and tokens are loaded strictly via environment variables.
- **Log Payload Caps**: Logs are capped at `500,000` characters (`MAX_LOG_SIZE_CHARS`) to eliminate denial-of-service memory exhaustion.
- **Configurable CORS**: CORS is restricted to configurable origins via `CORS_ORIGINS` (defaults to `http://localhost:3000,http://127.0.0.1:3000,http://localhost:5173`).
- **Read-Only Invariants**: Agents never execute arbitrary bash scripts or write unverified changes without explicit engineer action.
- **Prompt Injection Defense**: Raw logs and repository files are handled strictly as untrusted data inputs rather than agent instructions.

---

## 6. Setup & Execution

### Prerequisites
- Python 3.11+
- Node.js 18+ & npm

### Backend Setup
```bash
cd orchestrator
pip install -r requirements.txt
cp .env.example .env
# Edit .env with your GROQ_API_KEY and GITHUB_TOKEN
uvicorn main:app --reload --port 8000
```

### Frontend Setup
```bash
cd orchestrator/frontend
npm install
npm start
```
Frontend runs at `http://localhost:3000`.

### Running Automated Tests
```bash
cd orchestrator
python -m pytest tests/ -v
```
All 15 automated test cases validate agents, LangGraph orchestration, API validation, and MCP fallback.

---

## 7. Milestone Roadmap to 25 October 2026

| Phase / Day | Target Date | Milestone & Deliverable | Status |
|---|---|---|---|
| **Phase 1** | **11 Oct 2026** | Existing codebase audit, schema design, and core multi-agent contracts (`schemas.py`). | Completed |
| **Phase 2** | **12 Oct 2026** | Genuine MCP GitHub client implementation with stdio transport & graceful PyGithub fallback. | Completed |
| **Phase 3** | **13 Oct 2026** | CI/CD & Infrastructure investigation specialist agents implementation. | Completed |
| **Phase 4** | **14 Oct 2026** | Log analysis & Knowledge RAG agents upgraded to structured evidence schemas. | Completed |
| **Phase 5** | **15 Oct 2026** | Verification Agent & Orchestrator Agent planning & synthesis implementation. | Completed |
| **Phase 6** | **16 Oct 2026** | LangGraph StateGraph compiled with parallel fan-out, fan-in, and bounded retry loop. | Completed |
| **Phase 7** | **17 Oct 2026** | FastAPI endpoints upgraded: `/analyze`, SSE streaming `/analyze/stream`, context `/chat`, `/health`. | Completed |
| **Phase 8** | **18 Oct 2026** | React frontend upgraded with multi-agent cards, tabbed report, and live agent indicators. | Completed |
| **Phase 9 (Today)** | **19 Oct 2026** | End-to-end integration testing, LangGraph channel fix, 100% pytest suite pass, React production build. | **Completed & Verified** |
| **Phase 10** | **20 Oct 2026** | Docker containerization (`Dockerfile` and `docker-compose.yml`) for seamless local execution. | Scheduled |
| **Phase 11** | **21 Oct 2026** | Multi-fixture log corpus expansion (adding sample logs for Kubernetes CrashLoop, OOM, and npm scripts). | Scheduled |
| **Phase 12** | **22 Oct 2026** | Advanced MCP tool enhancements (code search tool and git diff range inspection). | Scheduled |
| **Phase 13** | **23 Oct 2026** | End-to-end security audit, input validation stress testing, and rate limiting verification. | Scheduled |
| **Phase 14** | **24 Oct 2026** | User acceptance testing (UAT), cross-browser responsiveness check, and staging deployment. | Scheduled |
| **Phase 15 (Final)** | **25 Oct 2026** | **Final Release Milestone**: Production deployment readiness, final delivery sign-off, demo verification. | **Target Date** |
