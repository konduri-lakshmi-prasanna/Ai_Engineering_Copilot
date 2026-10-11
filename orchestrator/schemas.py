from enum import Enum
from typing import List, Dict, Any, Optional, TypedDict
from pydantic import BaseModel, Field


class EvidenceType(str, Enum):
    GITHUB_CODE = "github_code"
    GITHUB_COMMIT = "github_commit"
    LOG_LINE = "log_line"
    CICD_STEP = "cicd_step"
    INFRA_EVENT = "infra_event"
    DOCUMENTATION = "documentation"


class EvidenceItem(BaseModel):
    source_type: EvidenceType
    reference: str = Field(..., description="e.g. 'sample_app/db_config.py#L8', 'commit:3a8f1b', 'log:line 14', 'workflow:deploy.yml'")
    snippet: str = Field(..., description="Excerpt or code snippet demonstrating the evidence")
    relevance: str = Field(..., description="Explanation of how this item supports or refutes an hypothesis")


class FindingSeverity(str, Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    INFO = "INFO"


class SpecialistFinding(BaseModel):
    category: str = Field(..., description="e.g. 'Configuration Error', 'Dependency Missing', 'Database Failure'")
    description: str = Field(..., description="Detailed description of the finding")
    severity: FindingSeverity = FindingSeverity.MEDIUM
    confidence: float = Field(0.0, ge=0.0, le=1.0, description="Estimated confidence between 0.0 and 1.0")
    evidence_items: List[EvidenceItem] = Field(default_factory=list)


class AgentExecutionStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


class AgentOutput(BaseModel):
    agent_name: str
    status: AgentExecutionStatus = AgentExecutionStatus.COMPLETED
    summary: str
    findings: List[SpecialistFinding] = Field(default_factory=list)
    supporting_evidence: List[EvidenceItem] = Field(default_factory=list)
    confidence_estimate: float = Field(0.0, ge=0.0, le=1.0)
    unresolved_questions: List[str] = Field(default_factory=list)
    recommended_next_steps: List[str] = Field(default_factory=list)
    integration_status: Dict[str, Any] = Field(default_factory=dict)
    error_message: Optional[str] = None


class VerificationResult(BaseModel):
    is_sufficient: bool = Field(..., description="True if evidence sufficiently confirms or refutes root cause")
    needs_reinvestigation: bool = Field(False, description="True if more evidence is needed from specialists")
    reinvestigation_focus: List[str] = Field(default_factory=list, description="Specific questions or paths for specialists to investigate")
    confirmed_facts: List[str] = Field(default_factory=list, description="Facts verified against concrete code/log evidence")
    contradictions_found: List[str] = Field(default_factory=list, description="Conflicts discovered between specialist findings")
    unsupported_assumptions: List[str] = Field(default_factory=list, description="Hypotheses lacking tangible evidence")
    validation_performed: str = Field("", description="Safe bounded validation performed")
    fix_validation_result: str = Field("", description="Whether suggested fix matches root cause mechanism")


class InvestigationPlan(BaseModel):
    plan_id: str
    incident_summary: str
    required_specialists: List[str] = Field(default_factory=list, description="Agents selected: 'github', 'logs', 'cicd', 'infra', 'docs'")
    initial_hypotheses: List[str] = Field(default_factory=list)
    focus_areas: Dict[str, str] = Field(default_factory=dict)


class IncidentReport(BaseModel):
    incident_id: str
    repo: str
    confirmed_facts: List[str]
    most_likely_root_cause: str
    supporting_evidence: List[EvidenceItem]
    contradictory_or_missing_evidence: List[str]
    recommended_fix: str
    why_it_works: str
    validation_performed: str
    validation_result: str
    preventive_measures: List[str]
    remaining_uncertainty: str
    beginner_explanation: str
    interview_questions: List[str]
    investigation_rounds: int = 1
    agent_summaries: Dict[str, str] = Field(default_factory=dict)


class CopilotState(TypedDict):
    incident_id: str
    repo_name: str
    log_text: str
    github_token: str
    active_plan: Dict[str, Any]
    investigation_round: int
    max_rounds: int
    agent_outputs: Dict[str, Dict[str, Any]]
    merged_findings: List[Dict[str, Any]]
    verification: Optional[Dict[str, Any]]
    final_report: Optional[Dict[str, Any]]
    events: List[Dict[str, Any]]
