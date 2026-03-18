"""
Lean Multi-Agent Debate Engine — Pydantic v2 Data Models
"""

from pydantic import BaseModel, field_validator


class InitialTake(BaseModel):
    """Output from Phase 1: one model's initial response."""
    model_id: str
    role: str  # "logical_analysis" | "factual_context" | "PRO Advocate" | "CONTRA Advocate"
    content: str
    chain_of_thought: str = ""
    confidence: float  # 0.0–1.0
    known_unknowns: list[str] = []   # Epistemic uncertainty: what the model doesn't know
    sources: list[str] = []          # Grounded search: cited URLs/titles
    aggregated_from: list[str] = []  # MoA: list of model IDs that contributed to this take

    @field_validator("confidence")
    @classmethod
    def clamp_confidence(cls, v: float) -> float:
        return max(0.0, min(1.0, v))


class SubQuestion(BaseModel):
    """A sub-question derived from problem decomposition (Phase 0)."""
    question: str
    aspect: str  # e.g. "technical", "economic", "ethical", "empirical"


class ProblemDecomposition(BaseModel):
    """Claude's structured breakdown of the problem into sub-questions (Phase 0)."""
    sub_questions: list[SubQuestion]
    reasoning: str      # Why this decomposition
    complexity: str     # "simple" | "moderate" | "complex"


class AtomicClaim(BaseModel):
    """A single verifiable claim extracted from Phase 1 analyses."""
    claim: str
    source_role: str    # which agent made this claim
    status: str         # "confirmed" | "refuted" | "uncertain"
    evidence: str       # supporting or contradicting evidence
    confidence: float   # 0.0–1.0

    @field_validator("confidence")
    @classmethod
    def clamp(cls, v: float) -> float:
        return max(0.0, min(1.0, v))


class FactCheckResult(BaseModel):
    """Claim-level fact-check of Phase 1 analyses (Phase 1.5)."""
    claims: list[AtomicClaim]
    overall_reliability: float  # fraction of confirmed claims
    summary: str

    @field_validator("overall_reliability")
    @classmethod
    def clamp(cls, v: float) -> float:
        return max(0.0, min(1.0, v))

    @property
    def confirmed_count(self) -> int:
        return sum(1 for c in self.claims if c.status == "confirmed")

    @property
    def refuted_count(self) -> int:
        return sum(1 for c in self.claims if c.status == "refuted")

    @property
    def uncertain_count(self) -> int:
        return sum(1 for c in self.claims if c.status == "uncertain")


class Contradiction(BaseModel):
    """A detected conflict between logical and factual takes."""
    claim_a: str   # claim from analysis A
    claim_b: str   # conflicting claim from analysis B
    severity: str  # "minor" | "major"


class RubricScore(BaseModel):
    """Multi-dimensional quality assessment of one analysis (1–5 ordinal scale)."""
    logical_coherence: int = 3    # Arguments internally consistent?
    evidence_quality: int = 3     # Supported by facts / data?
    completeness: int = 3         # Full scope of the problem addressed?
    reasoning_depth: int = 3      # Depth of chain-of-thought?

    @field_validator("logical_coherence", "evidence_quality", "completeness", "reasoning_depth")
    @classmethod
    def clamp_int(cls, v: int) -> int:
        return max(1, min(5, v))

    @property
    def normalized(self) -> float:
        """Average score normalized to 0.0–1.0."""
        return (self.logical_coherence + self.evidence_quality +
                self.completeness + self.reasoning_depth) / 20.0


class ClaudeSynthesis(BaseModel):
    """Claude Opus adversarial critique output (Phase 2a)."""
    contradictions: list[Contradiction]
    assumptions_challenged: list[str]
    synthesis_draft: str
    agreement_score: float  # 0.0–1.0, Claude's self-assessment of model convergence
    rubric_logical: RubricScore = RubricScore()
    rubric_factual: RubricScore = RubricScore()
    semantic_similarity: float | None = None  # v1.7: TF-IDF cosine similarity between Phase 1 outputs

    @field_validator("agreement_score")
    @classmethod
    def clamp_score(cls, v: float) -> float:
        return max(0.0, min(1.0, v))


class GeminiRebuttal(BaseModel):
    """Gemini's defense against Claude's critique (Phase 2b in multi-turn mode)."""
    rebuttal_content: str
    points_conceded: list[str]      # Where Claude's critique was correct
    points_maintained: list[str]    # Where original analysis holds despite critique
    rebuttal_score: float           # 0.0 = position fully refuted, 1.0 = fully maintained

    @field_validator("rebuttal_score")
    @classmethod
    def clamp(cls, v: float) -> float:
        return max(0.0, min(1.0, v))


class GeminiVerification(BaseModel):
    """Gemini Thinking's check of Claude's synthesis for new logical errors (Phase 2c)."""
    logical_errors: list[str]
    wishful_thinking: list[str]
    verified: bool
    verification_notes: str


class JudgeVerdict(BaseModel):
    """Independent skeptical judge's evaluation of the full debate (Phase 4)."""
    judgment: str
    bias_flags: list[str]           # Cognitive biases detected across all agents
    missed_perspectives: list[str]  # Important angles all agents overlooked
    reliability_score: float        # 0.0–1.0: how trustworthy is the final answer?
    reasoning: str

    @field_validator("reliability_score")
    @classmethod
    def clamp(cls, v: float) -> float:
        return max(0.0, min(1.0, v))


class FinalAnswer(BaseModel):
    """Claude Opus final consensus answer (Phase 3)."""
    content: str
    key_disagreements: list[str]
    consensus_score: float  # C = Σ(Confidence × Agreement) / n
    confidence: float
    # v1.4: Action-oriented fields
    recommendation: str = ""           # Single clear recommendation or verdict
    key_uncertainties: list[str] = []  # What would need to be resolved to increase confidence
    next_steps: list[str] = []         # Concrete actions the decision-maker should take
    # v1.7: Divergence explanation (only populated when consensus_score < 0.4)
    divergence_explanation: str | None = None

    @field_validator("consensus_score", "confidence")
    @classmethod
    def clamp(cls, v: float) -> float:
        return max(0.0, min(1.0, v))


# ─── Tier 2: Argument Graph ───────────────────────────────────────────────────

class ArgumentNode(BaseModel):
    """A node in the argument graph — premise, conclusion, evidence, or assumption."""
    id: str          # "A1", "B2", etc. (A = Analysis A, B = Analysis B)
    node_type: str   # "premise" | "conclusion" | "evidence" | "assumption"
    content: str
    source_role: str


class ArgumentEdge(BaseModel):
    """A directed relationship between two argument nodes."""
    from_id: str
    to_id: str
    edge_type: str   # "supports" | "contradicts" | "derives"
    label: str = ""


class ArgumentGraph(BaseModel):
    """Formal argument structure extracted from Phase 1 analyses (Phase 1.6)."""
    nodes: list[ArgumentNode]
    edges: list[ArgumentEdge]
    summary: str

    @property
    def contradiction_edges(self) -> list[ArgumentEdge]:
        return [e for e in self.edges if e.edge_type == "contradicts"]

    def to_mermaid(self) -> str:
        """Generate a Mermaid flowchart diagram."""
        type_icons = {"premise": "P", "conclusion": "C", "evidence": "E", "assumption": "A"}
        lines = ["flowchart LR"]
        for n in self.nodes:
            icon = type_icons.get(n.node_type, "?")
            label = n.content[:45].replace('"', "'")
            src = n.source_role[:1].upper()
            lines.append(f'    {n.id}["{src}-{icon}: {label}"]')
        for e in self.edges:
            if e.edge_type == "contradicts":
                lines.append(f'    {e.from_id} -.-|contradicts| {e.to_id}')
            elif e.edge_type == "derives":
                lines.append(f'    {e.from_id} ==>|derives| {e.to_id}')
            else:
                lbl = f"|{e.label}|" if e.label else ""
                lines.append(f'    {e.from_id} -->{lbl} {e.to_id}')
        return "\n".join(lines)


# ─── Tier 2: Delphi Method ────────────────────────────────────────────────────

class DelphiRound(BaseModel):
    """One round of Delphi iterative refinement."""
    round_n: int
    position_a: str         # Brief summary of Analysis A's position this round
    position_b: str         # Brief summary of Analysis B's position this round
    confidence_a: float
    confidence_b: float
    consensus_summary: str  # Anonymized group consensus shown to agents next round
    delta: float            # Average absolute confidence change from previous round (0 if round 1)

    @field_validator("confidence_a", "confidence_b", "delta")
    @classmethod
    def clamp(cls, v: float) -> float:
        return max(0.0, min(1.0, v))


class DelphiProcess(BaseModel):
    """Full record of a Delphi iterative refinement process."""
    rounds: list[DelphiRound]
    converged: bool
    convergence_round: int | None = None


# ─── Tier 2: Calibration Tracking ────────────────────────────────────────────

class ConfidenceClaim(BaseModel):
    """A measurable probabilistic claim extracted from Phase 1 analyses."""
    claim: str
    probability: float      # Stated probability 0.0–1.0
    ci_lower: float = 0.0   # 90% CI lower bound
    ci_upper: float = 1.0   # 90% CI upper bound
    model_id: str
    source_role: str
    time_horizon: str = "unknown"  # "1 year", "5 years", "10 years"
    # v1.4: Outcome tracking
    outcome: bool | None = None   # True=correct, False=wrong, None=unresolved
    outcome_note: str = ""        # Free-text explanation of outcome

    @field_validator("probability", "ci_lower", "ci_upper")
    @classmethod
    def clamp(cls, v: float) -> float:
        return max(0.0, min(1.0, v))


class CalibrationRecord(BaseModel):
    """Calibration data extracted from a single debate for long-term tracking."""
    debate_id: str
    date: str
    problem: str
    claims: list[ConfidenceClaim]
    # If --fact-check was also run: cross-referenced accuracy
    fact_check_alignment: float | None = None  # fraction of claims consistent with fact-check


class DebateResult(BaseModel):
    """Full debate record for a single problem."""
    problem: str
    decomposition: ProblemDecomposition | None = None     # Phase 0
    logical_analysis: InitialTake
    factual_context: InitialTake
    fact_check: FactCheckResult | None = None             # Phase 1.5
    argument_graph: ArgumentGraph | None = None           # Phase 1.6
    delphi_process: DelphiProcess | None = None           # Phase 1 (Delphi mode)
    calibration: CalibrationRecord | None = None          # Calibration tracking
    critique: ClaudeSynthesis
    rebuttal: GeminiRebuttal | None = None
    verification: GeminiVerification
    final_answer: FinalAnswer
    judge: JudgeVerdict | None = None
