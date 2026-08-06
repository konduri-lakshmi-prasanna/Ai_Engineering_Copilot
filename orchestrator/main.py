from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from graph import build_graph

app = FastAPI(title="AI Engineering Copilot")

# Allow the React frontend (running on a different port) to call this API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten this later
    allow_methods=["*"],
    allow_headers=["*"],
)

copilot_graph = build_graph()

class AnalyzeRequest(BaseModel):
    repo_name: str
    log_text: str

@app.post("/analyze")
def analyze(request: AnalyzeRequest):
    result = copilot_graph.invoke({
        "repo_name": request.repo_name,
        "log_text": request.log_text,
    })
    return {"root_cause": result["root_cause"]}

@app.get("/")
def health_check():
    return {"status": "AI Engineering Copilot API is running"}