from graph import build_graph
from agents.github_agent import github_agent

# Quick check: what commits are we actually pulling?
debug_data = github_agent("konduri-lakshmi-prasanna/Ai_Engineering_Copilot", limit=3)
print("--- COMMITS BEING FETCHED ---")
for c in debug_data["commits"]:
    print(c["sha"], "-", c["message"])
print()

sample_log = """
2026-08-06 10:00:01 INFO Starting deployment
2026-08-06 10:00:02 INFO Loading db_config module
2026-08-06 10:00:03 ERROR ValueError: Database URL is null — connection failed
2026-08-06 10:00:03 Traceback (most recent call last):
2026-08-06 10:00:03   File "sample_app/db_config.py", line 8, in connect
2026-08-06 10:00:03     raise ValueError("Database URL is null — connection failed")
2026-08-06 10:00:04 INFO Deployment failed, rolling back
"""

if __name__ == "__main__":
    app = build_graph()
    result = app.invoke({
        "repo_name": "konduri-lakshmi-prasanna/Ai_Engineering_Copilot",
        "log_text": sample_log,
    })
    print("\n--- ROOT CAUSE ANALYSIS ---\n")
    print(result["root_cause"])