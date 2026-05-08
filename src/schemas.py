from pydantic import BaseModel, Field


class PlanOutput(BaseModel):
    """Decomposition of a research topic into focused sub-questions."""

    sub_questions: list[str] = Field(
        description="3-5 focused sub-questions covering the topic"
    )


class ReflectOutput(BaseModel):
    """Critic verdict on whether current summaries are sufficient."""

    sufficient: bool = Field(description="Whether summaries cover the topic well")
    gaps: list[str] = Field(
        default_factory=list,
        description="Follow-up questions if not sufficient (max 2)",
    )


class RerankOutput(BaseModel):
    """Per-hit relevance scores in original order, 0-10."""

    scores: list[float] = Field(description="Score per hit, 0-10")


class QueryRewrite(BaseModel):
    """A reformulated search query."""

    query: str = Field(description="A more specific, web-search-friendly rewrite")
    reason: str = Field(default="", description="Why this rewrite is better")


class SupervisorDecision(BaseModel):
    """Routing decision for the multi-agent supervisor."""

    next: str = Field(
        description="One of: researcher, critic, writer, END"
    )
    reason: str = Field(
        default="",
        description="Why this agent should run next (1 short sentence)"
    )


class WriterReview(BaseModel):
    """A self-review of a generated report."""

    needs_revision: bool = Field(description="True if the report should be revised")
    issues: list[str] = Field(
        default_factory=list,
        description="List of concrete issues found (max 5 short bullets)",
    )
    suggestions: str = Field(
        default="",
        description="Brief actionable revision instructions (1-3 sentences)",
    )


class VerifiedClaim(BaseModel):
    text: str = Field(description="The claim, paraphrased in <= 25 words")
    supported_by: list[int] = Field(
        default_factory=list,
        description="1-indexed source numbers that support this claim",
    )
    risk: str = Field(
        default="ok",
        description="One of: ok | single-source | unsupported | conflicting",
    )
    confidence: float = Field(
        default=5.0,
        description="0-10 confidence in this claim (10 = strongly supported by multiple authoritative sources, 0 = no evidence)",
        ge=0,
        le=10,
    )


class ClaimVerification(BaseModel):
    claims: list[VerifiedClaim] = Field(default_factory=list)
    summary: str = Field(default="", description="One-line overall verdict")


class ReflexionMemo(BaseModel):
    """Self-reflection memo generated after a research run."""

    topic: str = Field(description="The topic that was researched")
    what_worked: list[str] = Field(
        default_factory=list,
        description="2-3 things that went well in this run",
    )
    what_to_improve: list[str] = Field(
        default_factory=list,
        description="2-3 weaknesses or gaps to address next time",
    )
    strategy_for_next_time: str = Field(
        default="",
        description="One actionable strategy: what to do differently next run on similar topics",
    )


class JudgeScore(BaseModel):
    """LLM-as-judge evaluation of a research report."""

    accuracy: float = Field(description="Factual correctness, 0-10", ge=0, le=10)
    citations: float = Field(description="Proper source attribution, 0-10", ge=0, le=10)
    structure: float = Field(description="Organization and flow, 0-10", ge=0, le=10)
    readability: float = Field(description="Clarity and engagement, 0-10", ge=0, le=10)
    length_fit: float = Field(description="Length appropriate for topic, 0-10", ge=0, le=10)
    overall: float = Field(description="Overall quality, 0-10", ge=0, le=10)
    comment: str = Field(description="1-2 sentences on strengths and weaknesses")
