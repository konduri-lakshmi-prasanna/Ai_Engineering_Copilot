from agents.github_agent import github_agent
import json

if __name__ == "__main__":
    repo = "konduri-lakshmi-prasanna/Ai_Engineering_Copilot"
    data = github_agent(repo, limit=5)
    print(json.dumps(data, indent=2))