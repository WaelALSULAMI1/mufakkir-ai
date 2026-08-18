from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, Field, ValidationInfo, field_validator

from injection_guard import sanitize_field


class SuggestionInput(BaseModel):
    department: str = Field(min_length=2, max_length=100)
    title: str = Field(min_length=4, max_length=180)
    problem: str = Field(min_length=10, max_length=5000)
    employee_suggestion: str | None = Field(default=None, max_length=5000)
    resources: str | None = Field(default=None, max_length=2500)
    constraints: str | None = Field(default=None, max_length=2500)

    @field_validator("department", "title", "problem", "employee_suggestion", "resources", "constraints")
    @classmethod
    def clean_text(cls, value, info: ValidationInfo):
        cleaned = sanitize_field(info.field_name, value)
        if cleaned is None and info.field_name in {"department", "title", "problem"}:
            raise ValueError("الحقل فارغ بعد التنظيف")
        return cleaned


class Hypothesis(BaseModel):
    hypothesis: str
    evidence_status: str = "غير مثبت"
    verification: str


class MissingInformation(BaseModel):
    question: str
    why_it_matters: str


class ImmediateContainment(BaseModel):
    action: str
    mechanism: str
    requirements: list[str] = []
    risks: list[str] = []
    stop_condition: str


class EmployeeSuggestionEvaluation(BaseModel):
    suggestion: str
    strengths: list[str] = []
    risks: list[str] = []
    required_evidence: list[str] = []
    verdict: Literal["يُختبر", "يُعتمد", "يُعدل", "يُرفض", "لا يوجد اقتراح"]


class Alternative(BaseModel):
    kind: str = "فوري"
    name: str
    idea: str
    mechanism: str
    requirements: list[str] = []
    advantages: list[str] = []
    risks: list[str] = []
    failure_conditions: list[str] = []
    impact: str
    speed: str
    cost: str
    reversibility: str
    required_evidence: list[str] = []


class Comparison(BaseModel):
    criteria: list[str]
    best_immediate_option: str
    best_long_term_option: str
    tradeoffs: str


class Recommendation(BaseModel):
    decision: str
    why: str
    conditions: list[str] = []
    do_not_do: list[str] = []


class Pilot(BaseModel):
    scope: str
    steps: list[str] = []
    success_metrics: list[str] = []
    rollback_trigger: str


class NextAction(BaseModel):
    priority: int
    action: str
    owner: str
    timing: str


class Confidence(BaseModel):
    level: str
    reason: str


class ModelAnalysis(BaseModel):
    problem_summary: str
    facts: list[str] = []
    hypotheses: list[Hypothesis] = []
    missing_information: list[MissingInformation] = []
    immediate_containment: ImmediateContainment
    employee_suggestion_evaluation: EmployeeSuggestionEvaluation
    alternatives: list[Alternative]
    comparison: Comparison
    recommendation: Recommendation
    pilot: Pilot
    next_actions: list[NextAction] = []
    confidence: Confidence

    @field_validator("alternatives")
    @classmethod
    def exactly_four_alternatives(cls, value):
        if len(value) != 4:
            raise ValueError("alternatives must contain exactly four items")
        return value


class ScoreResult(BaseModel):
    problem_value: int = Field(ge=0, le=20)
    expected_impact: int = Field(ge=0, le=25)
    feasibility: int = Field(ge=0, le=20)
    urgency: int = Field(ge=0, le=10)
    reversibility: int = Field(ge=0, le=10)
    evidence_quality: int = Field(ge=0, le=15)

    @property
    def total(self) -> int:
        return (
            self.problem_value
            + self.expected_impact
            + self.feasibility
            + self.urgency
            + self.reversibility
            + self.evidence_quality
        )
