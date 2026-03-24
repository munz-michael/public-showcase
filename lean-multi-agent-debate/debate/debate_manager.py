"""
Lean Multi-Agent Debate Engine — Orchestrator (v1.3 — Tier 1 Extensions)

Phase 0 — Problem Decomposition [--decompose]:
  Claude Opus  →  breaks problem into 3–5 sub-questions with aspects

Phase 1 — Initial Thesis (Parallel):
  Gemini Thinking  →  logical chain-of-thought  [MoA: multiple models aggregated]
  Gemini Pro       →  factual context / RAG     [MoA: multiple models aggregated]
                                                 [--grounded: Google Search]
                                                 [--adversarial: PRO/CONTRA locked]

Phase 1.5 — Claim-Level Fact-Check [--fact-check]:
  Claude Opus  →  extracts atomic claims, verifies each as confirmed/refuted/uncertain

Phase 2 — Adversarial Critique Loop:
  Phase 2a: Claude Opus       →  contradictions, assumptions, rubric scores
  Phase 2b: Gemini Thinking   →  multi-turn rebuttal  [--multi-turn]
  Phase 2c: Gemini Thinking   →  logical verification

Phase 3 — Final Consensus:
  Claude Opus  →  definitive answer + consensus score C

Phase 4 — Skeptical Judge [--judge]:
  Claude Opus  →  independent adversarial evaluation
"""

import asyncio
import json
import math
import re
import sys
import time

import anthropic
from google import genai
from google.genai import types as genai_types

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "config"))
try:
    from sanitization import sanitize_input
except ImportError:
    def sanitize_input(text: str, max_length: int = 10_000) -> str:
        return text[:max_length]

from .config import settings
import uuid
from pathlib import Path

from .models import (
    ArgumentEdge,
    ArgumentGraph,
    ArgumentNode,
    AtomicClaim,
    CalibrationRecord,
    ClaudeSynthesis,
    ConfidenceClaim,
    Contradiction,
    DebateResult,
    DelphiProcess,
    DelphiRound,
    FactCheckResult,
    FinalAnswer,
    GeminiRebuttal,
    GeminiVerification,
    InitialTake,
    JudgeVerdict,
    ProblemDecomposition,
    RubricScore,
    SubQuestion,
)

# ─── API clients ───────────────────────────────────────────────────────────────
_gemini_client = genai.Client(api_key=settings.google_api_key)
_claude = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)


# ─── Retry helpers ─────────────────────────────────────────────────────────────

async def _retry_async(coro_fn, *args, max_retries: int = 3, base_delay: float = 2.0, **kwargs):
    for attempt in range(max_retries):
        try:
            return await coro_fn(*args, **kwargs)
        except Exception as e:
            is_transient = any(s in str(e) for s in ("429", "rate", "quota", "overloaded", "529"))
            if attempt == max_retries - 1 or not is_transient:
                raise
            await asyncio.sleep(base_delay * (2 ** attempt))


def _retry_sync(fn, *args, max_retries: int = 3, base_delay: float = 2.0, **kwargs):
    for attempt in range(max_retries):
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            is_transient = any(s in str(e) for s in ("429", "rate", "quota", "overloaded"))
            if attempt == max_retries - 1 or not is_transient:
                raise
            time.sleep(base_delay * (2 ** attempt))


# ─── JSON parsing ─────────────────────────────────────────────────────────────

def _extract_outermost_json(s: str) -> str:
    start = s.find("{")
    if start == -1:
        raise ValueError("No JSON object found")
    depth, in_string, escape_next = 0, False, False
    for i, ch in enumerate(s[start:], start):
        if escape_next:
            escape_next = False
            continue
        if ch == "\\" and in_string:
            escape_next = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return s[start : i + 1]
    raise ValueError("Unbalanced braces in JSON")


def _parse_json_response(raw: str) -> dict:
    raw = raw.strip()
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
    if match:
        raw = match.group(1)

    def _try(s: str) -> dict:
        return json.loads(re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", s))

    try:
        return _try(raw)
    except json.JSONDecodeError:
        pass
    try:
        return _try(_extract_outermost_json(raw))
    except (ValueError, json.JSONDecodeError):
        pass
    raise ValueError(f"Cannot parse JSON from model response: {raw[:300]}")


# ─── Gemini sync helpers ───────────────────────────────────────────────────────

def _gemini_thinking_call(prompt: str, system: str, max_tokens: int, model: str | None = None) -> str:
    r = _retry_sync(
        _gemini_client.models.generate_content,
        model=model or settings.gemini_thinking_model,
        contents=prompt,
        config=genai_types.GenerateContentConfig(system_instruction=system, max_output_tokens=max_tokens),
    )
    return r.text


def _gemini_pro_call(prompt: str, system: str, max_tokens: int, model: str | None = None) -> str:
    r = _retry_sync(
        _gemini_client.models.generate_content,
        model=model or settings.gemini_pro_model,
        contents=prompt,
        config=genai_types.GenerateContentConfig(system_instruction=system, max_output_tokens=max_tokens),
    )
    return r.text


def _gemini_pro_call_grounded(prompt: str, system: str, max_tokens: int, model: str | None = None) -> tuple[str, list[str]]:
    """Gemini Pro with Google Search grounding. Returns (text, sources)."""
    search_tool = genai_types.Tool(google_search=genai_types.GoogleSearch())
    r = _retry_sync(
        _gemini_client.models.generate_content,
        model=model or settings.gemini_pro_model,
        contents=prompt,
        config=genai_types.GenerateContentConfig(
            system_instruction=system,
            max_output_tokens=max_tokens,
            tools=[search_tool],
        ),
    )
    sources: list[str] = []
    try:
        for candidate in (r.candidates or []):
            gm = getattr(candidate, "grounding_metadata", None)
            if gm:
                for chunk in getattr(gm, "grounding_chunks", []):
                    web = getattr(chunk, "web", None)
                    if web and getattr(web, "uri", None):
                        title = getattr(web, "title", web.uri) or web.uri
                        sources.append(f"{title} — {web.uri}")
    except Exception:
        pass
    return r.text, sources


# ─── Language detection ────────────────────────────────────────────────────────

def _detect_language(text: str) -> str:
    sample = text[:500].lower()
    if any(w in sample for w in [" ist ", " die ", " der ", " das ", " und ", " nicht ", " mit ", " für ", " von ", " auf "]):
        return "German"
    if any(w in sample for w in [" est ", " les ", " des ", " une ", " que ", " dans ", " pour ", " avec ", " sur "]):
        return "French"
    if any(w in sample for w in [" es ", " los ", " las ", " una ", " que ", " para ", " con ", " por ", " del "]):
        return "Spanish"
    if any(w in sample for w in [" é ", " os ", " as ", " uma ", " que ", " para ", " com ", " por ", " do ", " da "]):
        return "Portuguese"
    return "English"


_LANGUAGE_INSTRUCTION = "\n\nIMPORTANT: Respond in {lang}. The problem is written in {lang}, so all your output must be in {lang}."


# ─── Expert Persona Templates (v1.6) ──────────────────────────────────────────

_PERSONA_PRESETS: dict[str, tuple[str, str]] = {
    "cybersecurity": (
        "a skeptical security researcher with 15 years of cryptography and adversarial attack expertise — you prioritize threat models, failure modes, and worst-case scenarios",
        "a pragmatic cybersecurity industry analyst tracking real-world deployment patterns, compliance requirements, and enterprise adoption constraints",
    ),
    "finance": (
        "a rigorous quantitative analyst with expertise in financial modeling, risk assessment, and market microstructure — you demand numerical precision and challenge vague claims",
        "a seasoned investment professional with 20 years of market experience who focuses on valuation, capital allocation, and regulatory constraints",
    ),
    "medicine": (
        "an evidence-based clinical researcher specializing in systematic reviews and RCTs — you distinguish correlation from causation and demand effect sizes and confidence intervals",
        "a pragmatic healthcare practitioner focused on patient outcomes, clinical feasibility, and real-world implementation constraints within healthcare systems",
    ),
    "technology": (
        "a critical software architect with systems-thinking expertise — you focus on failure modes, scalability limits, technical debt, and second-order system effects",
        "a technology industry analyst tracking market adoption curves, competitive dynamics, and the gap between research capabilities and production deployments",
    ),
    "policy": (
        "a rigorous policy analyst examining second-order effects, stakeholder incentives, and historical precedents for similar interventions",
        "a pragmatic public administrator focused on implementation feasibility, political constraints, budget realities, and unintended consequences",
    ),
    "science": (
        "a skeptical research scientist who demands reproducibility, questions p-hacking, and distinguishes preliminary findings from established consensus",
        "a science communicator and historian of science tracking how scientific consensus forms, changes, and gets misrepresented in public discourse",
    ),
}


def _cosine_similarity(text_a: str, text_b: str) -> float:
    """TF-IDF cosine similarity between two texts (stdlib only, no extra deps).

    Returns a value in [0.0, 1.0]: 1.0 = identical content, 0.0 = no overlap.
    """
    from collections import Counter

    def _tokenize(t: str) -> list[str]:
        return re.findall(r"\b[a-z]{3,}\b", t.lower())

    tokens_a = _tokenize(text_a)
    tokens_b = _tokenize(text_b)
    if not tokens_a or not tokens_b:
        return 0.0

    vocab = set(tokens_a) | set(tokens_b)
    df = {t: sum(1 for doc in [tokens_a, tokens_b] if t in doc) for t in vocab}
    idf = {t: math.log(2 / df[t]) for t in vocab}

    def _tfidf(tokens: list[str]) -> dict[str, float]:
        tf = Counter(tokens)
        n = len(tokens)
        return {t: (tf.get(t, 0) / n) * idf[t] for t in vocab}

    vec_a = _tfidf(tokens_a)
    vec_b = _tfidf(tokens_b)

    dot = sum(vec_a[t] * vec_b[t] for t in vocab)
    mag_a = math.sqrt(sum(v ** 2 for v in vec_a.values()))
    mag_b = math.sqrt(sum(v ** 2 for v in vec_b.values()))
    if mag_a == 0 or mag_b == 0:
        return 0.0
    return round(dot / (mag_a * mag_b), 3)


def _build_persona_prefix(persona: str, role: str) -> str:
    """Build system prompt persona prefix for a given domain and role.

    role: 'thinking' (logical/analytical) or 'pro' (factual/contextual)
    Returns empty string if persona is empty.
    """
    if not persona.strip():
        return ""
    persona_lower = persona.strip().lower()
    preset = _PERSONA_PRESETS.get(persona_lower)
    if preset:
        desc = preset[0] if role == "thinking" else preset[1]
    else:
        # Free-form persona: generate generic expert descriptions
        if role == "thinking":
            desc = f"a rigorous {persona} researcher and critical analyst who applies deep domain expertise to identify logical gaps and challenge assumptions"
        else:
            desc = f"a pragmatic {persona} practitioner with real-world experience who grounds analysis in concrete evidence and implementation realities"
    return f"You approach this as {desc}.\n\nApply this expert lens throughout your analysis — let your domain background shape what evidence you weight, what risks you identify, and what nuances you highlight.\n\n"


# ─── Phase 0: Problem Decomposition ───────────────────────────────────────────

_DECOMPOSE_SYSTEM = """\
You are a problem analyst. Break the given problem into 3–5 focused sub-questions
that together cover the full scope of the problem. Each sub-question should address
a distinct aspect (technical, empirical, economic, ethical, temporal, etc.).

Respond ONLY with valid JSON (no markdown fences):
{{
  "sub_questions": [
    {{"question": "<specific sub-question>", "aspect": "<aspect label>"}},
    ...
  ],
  "reasoning": "<why this decomposition covers the problem>",
  "complexity": "simple|moderate|complex"
}}{lang_note}
"""


async def _claude_decompose_problem(problem: str, lang: str = "English") -> ProblemDecomposition:
    lang_note = _LANGUAGE_INSTRUCTION.format(lang=lang) if lang != "English" else ""
    system = _DECOMPOSE_SYSTEM.format(lang_note=lang_note)
    response = await _retry_async(
        _claude.messages.create,
        model=settings.claude_model,
        max_tokens=1024,
        system=system,
        messages=[{"role": "user", "content": f"Problem to decompose:\n\n{problem}"}],
    )
    data = _parse_json_response(response.content[0].text)
    return ProblemDecomposition(
        sub_questions=[
            SubQuestion(question=q.get("question", ""), aspect=q.get("aspect", "general"))
            for q in data.get("sub_questions", [])
        ],
        reasoning=data.get("reasoning", ""),
        complexity=data.get("complexity", "moderate"),
    )


def _format_sub_questions(decomposition: ProblemDecomposition) -> str:
    lines = ["\n\nAddress each of these sub-questions in your analysis:"]
    for i, sq in enumerate(decomposition.sub_questions, 1):
        lines.append(f"  {i}. [{sq.aspect.upper()}] {sq.question}")
    return "\n".join(lines)


# ─── Phase 1: Initial Thesis ──────────────────────────────────────────────────

_THINKING_SYSTEM = """\
You are a rigorous logical analyst. Reason step by step from first principles. Be concise.

Respond ONLY with valid JSON (no markdown fences):
{{
  "content": "<conclusion in 2-3 sentences>",
  "chain_of_thought": "<numbered steps, max 5 steps, each 1-2 sentences>",
  "confidence": <float 0.0-1.0>,
  "known_unknowns": ["<key uncertainty 1>", "<key uncertainty 2>"]
}}{lang_note}
"""

_PRO_SYSTEM = """\
You are a factual research expert. Provide accurate, evidence-based context. Be concise.

Respond ONLY with valid JSON (no markdown fences):
{{
  "content": "<key facts and data points, max 200 words>",
  "chain_of_thought": "<how you selected these facts, max 3 sentences>",
  "confidence": <float 0.0-1.0>,
  "known_unknowns": ["<important fact gap 1>", "<important fact gap 2>"]
}}{lang_note}
"""

_THINKING_SYSTEM_ADVERSARIAL = """\
You are a PRO-POSITION advocate. Your mandatory role: argue AS STRONGLY AS POSSIBLE
in FAVOR of the proposition using logical reasoning. Do NOT hedge or present counterarguments.

Respond ONLY with valid JSON (no markdown fences):
{{
  "content": "<strongest PRO argument in 2-3 sentences>",
  "chain_of_thought": "<numbered logical steps supporting PRO, max 5>",
  "confidence": <float 0.0-1.0>,
  "known_unknowns": ["<what could weaken the PRO case>"]
}}{lang_note}
"""

_PRO_SYSTEM_ADVERSARIAL = """\
You are a CONTRA-POSITION advocate. Your mandatory role: argue AS STRONGLY AS POSSIBLE
AGAINST the proposition using facts and evidence. Do NOT concede or be balanced.

Respond ONLY with valid JSON (no markdown fences):
{{
  "content": "<strongest CONTRA argument backed by facts, max 200 words>",
  "chain_of_thought": "<how you selected evidence against the proposition, max 3 sentences>",
  "confidence": <float 0.0-1.0>,
  "known_unknowns": ["<what could weaken the CONTRA case>"]
}}{lang_note}
"""

# ── v1.9: Toulmin format templates ────────────────────────────────────────────

_THINKING_SYSTEM_TOULMIN = """\
You are a rigorous logical analyst. Express your reasoning as a structured Toulmin argument.
Every field is mandatory — do not omit REBUTTAL.

Respond ONLY with valid JSON (no markdown fences):
{{
  "content": "CLAIM: <main assertion in 1 sentence>\\nGROUNDS: <logical evidence / reasoning chain>\\nWARRANT: <why these grounds support the claim>\\nQUALIFIER: <degree of certainty, e.g. 'almost certainly' / 'probably' / 'possibly'>\\nREBUTTAL: <explicit conditions under which the claim would NOT hold>",
  "chain_of_thought": "<how you arrived at this argument structure, max 3 sentences>",
  "confidence": <float 0.0-1.0>,
  "known_unknowns": ["<key uncertainty 1>", "<key uncertainty 2>"]
}}{lang_note}
"""

_PRO_SYSTEM_TOULMIN = """\
You are a factual research expert. Express your findings as a structured Toulmin argument.
Every field is mandatory — do not omit REBUTTAL.

Respond ONLY with valid JSON (no markdown fences):
{{
  "content": "CLAIM: <main factual assertion in 1 sentence>\\nGROUNDS: <specific data points, statistics, citations>\\nWARRANT: <why these facts support the claim>\\nQUALIFIER: <confidence in data quality and completeness>\\nREBUTTAL: <alternative interpretations, counter-evidence, or data gaps>",
  "chain_of_thought": "<how you selected these facts, max 3 sentences>",
  "confidence": <float 0.0-1.0>,
  "known_unknowns": ["<important fact gap 1>", "<important fact gap 2>"]
}}{lang_note}
"""

# ─── Phase 1: MoA Aggregation ─────────────────────────────────────────────────

_MOA_AGGREGATE_SYSTEM = """\
You receive N independent analyses of the same problem from different AI models.
Aggregate them into a single, superior analysis.

Rules:
1. Identify convergent claims (appear across multiple models — more reliable).
2. Identify divergent points (models disagree — flag as known_unknowns).
3. Synthesize a consolidated response incorporating the best reasoning from all models.
4. Confidence should be higher when models converge, lower when they diverge.

Respond ONLY with valid JSON (no markdown fences):
{{
  "content": "<synthesized analysis, best of all models>",
  "chain_of_thought": "<how you aggregated and what you prioritized>",
  "confidence": <float 0.0-1.0>,
  "known_unknowns": ["<points where models disagreed or were uncertain>"]
}}{lang_note}
"""


async def _moa_aggregate(
    problem: str,
    takes: list[InitialTake],
    lang: str = "English",
) -> dict:
    """Claude aggregates multiple parallel analyses into one consolidated take."""
    lang_note = _LANGUAGE_INSTRUCTION.format(lang=lang) if lang != "English" else ""
    system = _MOA_AGGREGATE_SYSTEM.format(lang_note=lang_note)

    analyses_text = "\n\n".join(
        f"--- Model {i+1}: {t.model_id} ---\n{t.content}\nReasoning: {t.chain_of_thought}\nConfidence: {t.confidence}"
        for i, t in enumerate(takes)
    )
    prompt = f"Problem: {problem}\n\nN={len(takes)} independent analyses:\n\n{analyses_text}\n\nAggregate these into one superior analysis."

    response = await _retry_async(
        _claude.messages.create,
        model=settings.claude_model,
        max_tokens=settings.max_tokens_phase1,
        system=system,
        messages=[{"role": "user", "content": prompt}],
    )
    return _parse_json_response(response.content[0].text)


def _coerce_str(value) -> str:
    if isinstance(value, list):
        return "\n".join(str(item) for item in value)
    return str(value) if value is not None else ""


async def _initial_thinking(
    problem: str,
    mock: bool = False,
    lang: str = "English",
    model: str | None = None,
    adversarial: bool = False,
    sub_questions_context: str = "",
    persona_prefix: str = "",
    debate_format: str = "prose",
) -> InitialTake:
    lang_note = _LANGUAGE_INSTRUCTION.format(lang=lang) if lang != "English" else ""
    if adversarial:
        template = _THINKING_SYSTEM_ADVERSARIAL
    elif debate_format == "toulmin":
        template = _THINKING_SYSTEM_TOULMIN
    else:
        template = _THINKING_SYSTEM
    system = persona_prefix + template.format(lang_note=lang_note)
    effective_model = model or settings.gemini_thinking_model
    role_label = "PRO Advocate (Logical)" if adversarial else "logical_analysis"
    prompt = f"Problem to analyze:\n\n{problem}{sub_questions_context}"

    if mock:
        response = await _retry_async(
            _claude.messages.create,
            model=settings.claude_model,
            max_tokens=settings.max_tokens_phase1,
            system=system,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.content[0].text
        effective_model = f"{settings.claude_model} [mock]"
    else:
        raw = await asyncio.to_thread(_gemini_thinking_call, prompt, system, settings.max_tokens_phase1, effective_model)

    data = _parse_json_response(raw)
    return InitialTake(
        model_id=effective_model,
        role=role_label,
        content=_coerce_str(data.get("content", raw)),
        chain_of_thought=_coerce_str(data.get("chain_of_thought", "")),
        confidence=float(data.get("confidence", 0.7)),
        known_unknowns=[str(x) for x in data.get("known_unknowns", [])],
    )


async def _initial_pro(
    problem: str,
    mock: bool = False,
    lang: str = "English",
    model: str | None = None,
    adversarial: bool = False,
    grounded: bool = False,
    sub_questions_context: str = "",
    persona_prefix: str = "",
    debate_format: str = "prose",
) -> InitialTake:
    lang_note = _LANGUAGE_INSTRUCTION.format(lang=lang) if lang != "English" else ""
    if adversarial:
        template = _PRO_SYSTEM_ADVERSARIAL
    elif debate_format == "toulmin":
        template = _PRO_SYSTEM_TOULMIN
    else:
        template = _PRO_SYSTEM
    system = persona_prefix + template.format(lang_note=lang_note)
    effective_model = model or settings.gemini_pro_model
    role_label = "CONTRA Advocate (Factual)" if adversarial else "factual_context"
    prompt = f"Problem requiring factual context:\n\n{problem}{sub_questions_context}"
    sources: list[str] = []

    if mock:
        response = await _retry_async(
            _claude.messages.create,
            model=settings.claude_model,
            max_tokens=settings.max_tokens_phase1,
            system=system,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.content[0].text
        data = _parse_json_response(raw)
        return InitialTake(
            model_id=f"{settings.claude_model} [mock]",
            role=role_label,
            content=_coerce_str(data.get("content", raw)),
            chain_of_thought=_coerce_str(data.get("chain_of_thought", "")),
            confidence=float(data.get("confidence", 0.7)),
            known_unknowns=[str(x) for x in data.get("known_unknowns", [])],
        )

    if grounded:
        raw, sources = await asyncio.to_thread(
            _gemini_pro_call_grounded, prompt, system, settings.max_tokens_phase1, effective_model
        )
        try:
            data = _parse_json_response(raw)
        except ValueError:
            data = {"content": raw, "chain_of_thought": "Grounded web search response.", "confidence": 0.75, "known_unknowns": []}
    else:
        raw = await asyncio.to_thread(_gemini_pro_call, prompt, system, settings.max_tokens_phase1, effective_model)
        data = _parse_json_response(raw)

    return InitialTake(
        model_id=effective_model,
        role=role_label,
        content=_coerce_str(data.get("content", raw)),
        chain_of_thought=_coerce_str(data.get("chain_of_thought", "")),
        confidence=float(data.get("confidence", 0.7)),
        known_unknowns=[str(x) for x in data.get("known_unknowns", [])],
        sources=sources,
    )


# ─── Phase 1.5: Claim-Level Fact-Check ────────────────────────────────────────

_FACTCHECK_SYSTEM = """\
You are a rigorous fact-checker. You receive two analyses and must:
1. Extract 6–10 specific, verifiable atomic claims from both analyses combined.
2. Assess each claim: "confirmed" (well-supported), "refuted" (contradicted by known facts),
   or "uncertain" (cannot be verified with confidence).
3. Provide brief evidence for your assessment.

Focus on factual claims, not opinions or predictions. Be honest about uncertainty.

Respond ONLY with valid JSON (no markdown fences):
{{
  "claims": [
    {{
      "claim": "<specific atomic claim>",
      "source_role": "<role of the agent who made it>",
      "status": "confirmed|refuted|uncertain",
      "evidence": "<1-2 sentences explaining your assessment>",
      "confidence": <float 0.0-1.0>
    }},
    ...
  ],
  "overall_reliability": <fraction of confirmed claims, float 0.0-1.0>,
  "summary": "<2-3 sentence overall assessment of factual quality>"
}}{lang_note}
"""


async def _claude_fact_check(
    problem: str,
    logical: InitialTake,
    factual: InitialTake,
    lang: str = "English",
) -> FactCheckResult:
    lang_note = _LANGUAGE_INSTRUCTION.format(lang=lang) if lang != "English" else ""
    system = _FACTCHECK_SYSTEM.format(lang_note=lang_note)

    # Include grounded sources if available
    sources_note = ""
    if factual.sources:
        sources_note = f"\n\nGrounded sources cited by Analysis B: {factual.sources[:5]}"

    prompt = f"""Problem: {problem}

--- Analysis A ({logical.role}, {logical.model_id}) ---
{logical.content}

--- Analysis B ({factual.role}, {factual.model_id}) ---
{factual.content}{sources_note}

Extract and verify the key factual claims from both analyses."""

    response = await _retry_async(
        _claude.messages.create,
        model=settings.claude_model,
        max_tokens=settings.max_tokens_critique,
        system=system,
        messages=[{"role": "user", "content": prompt}],
    )
    data = _parse_json_response(response.content[0].text)
    claims = [
        AtomicClaim(
            claim=c.get("claim", ""),
            source_role=c.get("source_role", "unknown"),
            status=c.get("status", "uncertain"),
            evidence=c.get("evidence", ""),
            confidence=float(c.get("confidence", 0.5)),
        )
        for c in data.get("claims", [])
    ]
    return FactCheckResult(
        claims=claims,
        overall_reliability=float(data.get("overall_reliability", 0.5)),
        summary=data.get("summary", ""),
    )


# ─── Phase 2a: Claude Adversarial Critique ────────────────────────────────────

_CRITIQUE_SYSTEM = """\
You are a ruthless adversarial critic. Expose every weakness, contradiction, and unfounded assumption.

Rules:
1. Find where analyses DISAGREE or CONTRADICT each other.
2. Identify unjustified assumptions.
3. Draft a synthesis that steelmans both positions while noting unresolved tensions.
4. Score each analysis on a 1–5 rubric.
5. Assign an agreement_score (0.0=total disagreement, 1.0=perfect convergence).

Rubric: logical_coherence, evidence_quality, completeness, reasoning_depth (each 1–5).

Respond ONLY with valid JSON (no markdown fences):
{{
  "contradictions": [{{"claim_a": "<from A>", "claim_b": "<from B>", "severity": "minor|major"}}, ...],
  "assumptions_challenged": ["<assumption 1>", ...],
  "synthesis_draft": "<synthesis reconciling both positions>",
  "rubric_logical": {{"logical_coherence": <1-5>, "evidence_quality": <1-5>, "completeness": <1-5>, "reasoning_depth": <1-5>}},
  "rubric_factual": {{"logical_coherence": <1-5>, "evidence_quality": <1-5>, "completeness": <1-5>, "reasoning_depth": <1-5>}},
  "agreement_score": <float 0.0-1.0>
}}{lang_note}
"""


async def _claude_critique(
    problem: str,
    logical: InitialTake,
    factual: InitialTake,
    lang: str = "English",
    prior_synthesis: str = "",
    fact_check: FactCheckResult | None = None,
) -> ClaudeSynthesis:
    lang_note = _LANGUAGE_INSTRUCTION.format(lang=lang) if lang != "English" else ""
    system = _CRITIQUE_SYSTEM.format(lang_note=lang_note)

    prior_context = f"\n\n--- PREVIOUS SYNTHESIS (improve upon this) ---\n{prior_synthesis}\n" if prior_synthesis else ""

    unknowns_a = f"\nKnown unknowns: {logical.known_unknowns}" if logical.known_unknowns else ""
    unknowns_b = f"\nKnown unknowns: {factual.known_unknowns}" if factual.known_unknowns else ""
    sources_b = f"\nGrounded sources: {factual.sources[:5]}" if factual.sources else ""
    moa_note_a = f"\n[MoA — aggregated from: {logical.aggregated_from}]" if logical.aggregated_from else ""
    moa_note_b = f"\n[MoA — aggregated from: {factual.aggregated_from}]" if factual.aggregated_from else ""

    fact_check_context = ""
    if fact_check:
        refuted = [c for c in fact_check.claims if c.status == "refuted"]
        if refuted:
            fact_check_context = f"\n\n--- FACT-CHECK FINDINGS (Phase 1.5) ---\n"
            fact_check_context += f"Overall reliability: {fact_check.overall_reliability:.0%}\n"
            fact_check_context += "Refuted claims:\n" + "\n".join(f"  ✗ [{c.source_role}] {c.claim} — {c.evidence}" for c in refuted)

    prompt = f"""Problem under debate:
<problem>
{problem}
</problem>

--- ANALYSIS A: {logical.role} ({logical.model_id}) ---
{logical.content}
Reasoning: {logical.chain_of_thought}
Confidence: {logical.confidence}{unknowns_a}{moa_note_a}

--- ANALYSIS B: {factual.role} ({factual.model_id}) ---
{factual.content}
Reasoning: {factual.chain_of_thought}
Confidence: {factual.confidence}{unknowns_b}{sources_b}{moa_note_b}{fact_check_context}{prior_context}
Find contradictions, challenge assumptions, create synthesis draft, assign agreement_score."""

    response = await _retry_async(
        _claude.messages.create,
        model=settings.claude_model,
        max_tokens=settings.max_tokens_critique,
        system=system,
        messages=[{"role": "user", "content": prompt}],
    )
    data = _parse_json_response(response.content[0].text)

    def _parse_rubric(raw: dict) -> RubricScore:
        return RubricScore(
            logical_coherence=int(raw.get("logical_coherence", 3)),
            evidence_quality=int(raw.get("evidence_quality", 3)),
            completeness=int(raw.get("completeness", 3)),
            reasoning_depth=int(raw.get("reasoning_depth", 3)),
        )

    return ClaudeSynthesis(
        contradictions=[
            Contradiction(claim_a=c.get("claim_a", ""), claim_b=c.get("claim_b", ""), severity=c.get("severity", "minor"))
            for c in data.get("contradictions", [])
        ],
        assumptions_challenged=data.get("assumptions_challenged", []),
        synthesis_draft=data.get("synthesis_draft", ""),
        rubric_logical=_parse_rubric(data.get("rubric_logical", {})),
        rubric_factual=_parse_rubric(data.get("rubric_factual", {})),
        agreement_score=float(data.get("agreement_score", 0.5)),
        # v1.7: objective content similarity between the two Phase 1 analyses
        semantic_similarity=_cosine_similarity(logical.content, factual.content),
    )


# ─── Phase 2b: Gemini Rebuttal (Multi-Turn) ───────────────────────────────────

_REBUTTAL_SYSTEM = """\
You are defending your original analysis against a critique. You must:
1. Concede points where the critique is genuinely correct.
2. Firmly defend points where your original analysis holds.
3. Assign rebuttal_score: 0.0 = fully refuted, 1.0 = fully maintained.

Respond ONLY with valid JSON (no markdown fences):
{{
  "rebuttal_content": "<your defense in 2-4 sentences>",
  "points_conceded": ["<point where critique was right>", ...],
  "points_maintained": ["<point you still hold despite critique>", ...],
  "rebuttal_score": <float 0.0-1.0>
}}{lang_note}
"""


async def _gemini_rebuttal(
    problem: str,
    original: InitialTake,
    synthesis: ClaudeSynthesis,
    mock: bool = False,
    lang: str = "English",
    model: str | None = None,
) -> GeminiRebuttal:
    lang_note = _LANGUAGE_INSTRUCTION.format(lang=lang) if lang != "English" else ""
    system = _REBUTTAL_SYSTEM.format(lang_note=lang_note)
    prompt = f"""Problem: {problem}

Your original analysis ({original.role}):
{original.content}

Adversarial critique:
Contradictions: {[(c.claim_a, c.claim_b, c.severity) for c in synthesis.contradictions]}
Assumptions challenged: {synthesis.assumptions_challenged}
Synthesis: {synthesis.synthesis_draft}

Rebut this critique. Concede where correct, defend where your analysis holds."""

    if mock:
        r = await _retry_async(
            _claude.messages.create,
            model=settings.claude_model,
            max_tokens=settings.max_tokens_critique,
            system=system,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = r.content[0].text
    else:
        raw = await asyncio.to_thread(_gemini_thinking_call, prompt, system, settings.max_tokens_critique, model)

    data = _parse_json_response(raw)
    return GeminiRebuttal(
        rebuttal_content=data.get("rebuttal_content", ""),
        points_conceded=data.get("points_conceded", []),
        points_maintained=data.get("points_maintained", []),
        rebuttal_score=float(data.get("rebuttal_score", 0.5)),
    )


# ─── Phase 2c: Gemini Verification ────────────────────────────────────────────

_VERIFY_SYSTEM = """\
You are a formal logic verifier. Check this synthesis draft for logical errors,
circular reasoning, and wishful thinking.

Respond ONLY with valid JSON (no markdown fences):
{{
  "logical_errors": ["<error 1>", ...],
  "wishful_thinking": ["<wishful claim 1>", ...],
  "verified": <true if logically sound, false if fundamentally flawed>,
  "verification_notes": "<overall assessment>"
}}{lang_note}
"""


async def _gemini_verify(
    problem: str,
    synthesis: ClaudeSynthesis,
    mock: bool = False,
    lang: str = "English",
    model: str | None = None,
) -> GeminiVerification:
    lang_note = _LANGUAGE_INSTRUCTION.format(lang=lang) if lang != "English" else ""
    system = _VERIFY_SYSTEM.format(lang_note=lang_note)
    prompt = f"""Problem: {problem}

Synthesis to verify:
{synthesis.synthesis_draft}

Agreement score: {synthesis.agreement_score}

Check for logical errors and wishful thinking."""

    if mock:
        r = await _retry_async(
            _claude.messages.create,
            model=settings.claude_model,
            max_tokens=settings.max_tokens_phase1,
            system=system,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = r.content[0].text
    else:
        raw = await asyncio.to_thread(_gemini_thinking_call, prompt, system, settings.max_tokens_phase1, model)

    data = _parse_json_response(raw)
    return GeminiVerification(
        logical_errors=data.get("logical_errors", []),
        wishful_thinking=data.get("wishful_thinking", []),
        verified=bool(data.get("verified", True)),
        verification_notes=data.get("verification_notes", ""),
    )


# ─── Phase 3: Final Consensus ─────────────────────────────────────────────────

_FINAL_SYSTEM = """\
You are a senior expert synthesizer and decision advisor. Write the single most robust, nuanced, accurate answer — and make it actionable.

Rules:
1. Incorporate insights from both analyses.
2. Explicitly acknowledge unresolved disagreements.
3. Weight claims by evidence quality, not confidence scores.
4. Be clear about what is known vs. uncertain.
5. Give a clear recommendation — what should the decision-maker do or conclude?
6. Identify 2–3 key uncertainties that, if resolved, would most change the answer.
7. Suggest 2–3 concrete next steps.

Respond ONLY with valid JSON (no markdown fences):
{{
  "content": "<definitive answer, well-structured>",
  "key_disagreements": ["<unresolved point 1>", ...],
  "consensus_score": <float 0.0-1.0, C = Σ(Confidence × Agreement) / n>,
  "confidence": <float 0.0-1.0>,
  "recommendation": "<single clear recommendation or verdict, 1–2 sentences>",
  "key_uncertainties": ["<what would need to be known to increase confidence>", ...],
  "next_steps": ["<concrete action 1>", "<concrete action 2>", ...],
  "divergence_explanation": "<ONLY populate when consensus_score < 0.4 — explain in 2–3 sentences WHY the analyses diverge: is it structural uncertainty, different value assumptions, factual gaps, or ambiguous framing? Otherwise set to null>"
}}{lang_note}
"""


async def _claude_final(
    problem: str,
    logical: InitialTake,
    factual: InitialTake,
    synthesis: ClaudeSynthesis,
    verification: GeminiVerification,
    rebuttal: GeminiRebuttal | None = None,
    fact_check: FactCheckResult | None = None,
    lang: str = "English",
) -> FinalAnswer:
    lang_note = _LANGUAGE_INSTRUCTION.format(lang=lang) if lang != "English" else ""
    system = _FINAL_SYSTEM.format(lang_note=lang_note)
    consensus_score = calculate_agreement_score(logical, factual, synthesis)

    fact_check_context = ""
    if fact_check:
        fact_check_context = f"\n\n--- Fact-Check (Phase 1.5) ---\nOverall reliability: {fact_check.overall_reliability:.0%}\n{fact_check.summary}"

    rebuttal_context = ""
    if rebuttal:
        rebuttal_context = f"\n\n--- Rebuttal ---\n{rebuttal.rebuttal_content}\nRebuttal score: {rebuttal.rebuttal_score}"

    prompt = f"""Problem: {problem}

Logical Analysis ({logical.model_id}, conf={logical.confidence}): {logical.content}
Factual Context ({factual.model_id}, conf={factual.confidence}): {factual.content}
{fact_check_context}
Contradictions: {[(c.severity, c.claim_a[:60], c.claim_b[:60]) for c in synthesis.contradictions]}
Assumptions challenged: {synthesis.assumptions_challenged}
Synthesis: {synthesis.synthesis_draft}
Agreement: {synthesis.agreement_score}
{rebuttal_context}
Verified: {verification.verified} | Errors: {verification.logical_errors}
Pre-calculated consensus: {consensus_score:.3f}

Write the final, definitive answer."""

    r = await _retry_async(
        _claude.messages.create,
        model=settings.claude_model,
        max_tokens=settings.max_tokens_final,
        system=system,
        messages=[{"role": "user", "content": prompt}],
    )
    data = _parse_json_response(r.content[0].text)
    raw_divergence = data.get("divergence_explanation")
    divergence_explanation = (raw_divergence or None) if isinstance(raw_divergence, str) else None
    return FinalAnswer(
        content=data.get("content", r.content[0].text),
        key_disagreements=data.get("key_disagreements", []),
        consensus_score=float(data.get("consensus_score", consensus_score)),
        confidence=float(data.get("confidence", 0.7)),
        recommendation=data.get("recommendation", ""),
        key_uncertainties=data.get("key_uncertainties", []),
        next_steps=data.get("next_steps", []),
        divergence_explanation=divergence_explanation,
    )


# ─── Phase 4: Skeptical Judge ─────────────────────────────────────────────────

_JUDGE_SYSTEM = """\
You are a completely independent skeptical judge. You did NOT participate in the debate.
Evaluate the full debate record as an outside observer.

Your mandate:
1. Identify cognitive biases (anchoring, confirmation bias, overconfidence, false balance, etc.).
2. Identify perspectives/stakeholders/angles ALL agents overlooked.
3. Assess the final answer's reliability independently.
4. reliability_score: 0.0=unreliable, 1.0=highly reliable.

Respond ONLY with valid JSON (no markdown fences):
{{
  "judgment": "<your independent verdict>",
  "bias_flags": ["<bias in agent X: description>", ...],
  "missed_perspectives": ["<important angle no agent addressed>", ...],
  "reliability_score": <float 0.0-1.0>,
  "reasoning": "<reasoning for reliability score>"
}}{lang_note}
"""


async def _claude_judge(
    problem: str,
    logical: InitialTake,
    factual: InitialTake,
    synthesis: ClaudeSynthesis,
    verification: GeminiVerification,
    final: FinalAnswer,
    rebuttal: GeminiRebuttal | None = None,
    fact_check: FactCheckResult | None = None,
    lang: str = "English",
) -> JudgeVerdict:
    lang_note = _LANGUAGE_INSTRUCTION.format(lang=lang) if lang != "English" else ""
    system = _JUDGE_SYSTEM.format(lang_note=lang_note)

    fc_section = f"\nFact-Check: {fact_check.overall_reliability:.0%} reliable, {fact_check.refuted_count} refuted claims. {fact_check.summary}" if fact_check else ""
    rb_section = f"\nRebuttal score: {rebuttal.rebuttal_score:.2f} | {rebuttal.rebuttal_content}" if rebuttal else ""

    prompt = f"""Problem: {problem}

=== DEBATE RECORD ===
Analysis A ({logical.role}, {logical.model_id}, conf={logical.confidence}):
{logical.content}
Known unknowns: {logical.known_unknowns}

Analysis B ({factual.role}, {factual.model_id}, conf={factual.confidence}):
{factual.content}
Known unknowns: {factual.known_unknowns}
Sources: {factual.sources[:3]}{fc_section}

Critique (agreement={synthesis.agreement_score}): {synthesis.synthesis_draft}
Contradictions: {len(synthesis.contradictions)} found{rb_section}
Verification: {'PASSED' if verification.verified else 'FAILED'} | {verification.verification_notes}

Final Answer (consensus={final.consensus_score:.2f}, conf={final.confidence:.2f}):
{final.content}
Unresolved: {final.key_disagreements}
=== END ===

As an independent judge, evaluate biases, blind spots, and missed perspectives."""

    r = await _retry_async(
        _claude.messages.create,
        model=settings.claude_model,
        max_tokens=settings.max_tokens_critique,
        system=system,
        messages=[{"role": "user", "content": prompt}],
    )
    data = _parse_json_response(r.content[0].text)
    return JudgeVerdict(
        judgment=data.get("judgment", ""),
        bias_flags=data.get("bias_flags", []),
        missed_perspectives=data.get("missed_perspectives", []),
        reliability_score=float(data.get("reliability_score", 0.7)),
        reasoning=data.get("reasoning", ""),
    )


# ─── Phase 1.6: Structured Argument Graph ─────────────────────────────────────

_ARGRAPH_SYSTEM = """\
You are a formal argument analyst. Extract the logical structure of two analyses as a
directed graph of premises, conclusions, evidence, and assumptions.

Rules:
1. Extract 3–4 nodes per analysis (total 6–8 nodes).
2. Node IDs: A1, A2, A3... for Analysis A; B1, B2, B3... for Analysis B.
3. node_type: "premise" (assumed starting point), "evidence" (cited fact/data),
              "conclusion" (derived claim), "assumption" (implicit belief).
4. edge_type: "supports" (A strengthens B), "derives" (A logically implies B),
              "contradicts" (A conflicts with B — use for cross-analysis conflicts).
5. Map internal chains within each analysis, then add "contradicts" edges BETWEEN analyses.

Respond ONLY with valid JSON (no markdown fences):
{{
  "nodes": [
    {{"id": "A1", "node_type": "premise|evidence|conclusion|assumption", "content": "<max 60 chars>", "source_role": "<role>"}},
    ...
  ],
  "edges": [
    {{"from_id": "A1", "to_id": "A2", "edge_type": "supports|derives|contradicts", "label": ""}},
    ...
  ],
  "summary": "<2 sentences: key structural finding about how the two argument chains relate>"
}}{lang_note}
"""


async def _claude_build_argument_graph(
    problem: str,
    logical: InitialTake,
    factual: InitialTake,
    lang: str = "English",
) -> ArgumentGraph:
    lang_note = _LANGUAGE_INSTRUCTION.format(lang=lang) if lang != "English" else ""
    system = _ARGRAPH_SYSTEM.format(lang_note=lang_note)
    prompt = f"""Problem: {problem}

--- Analysis A ({logical.role}, {logical.model_id}) ---
{logical.content}
Chain of thought: {logical.chain_of_thought}

--- Analysis B ({factual.role}, {factual.model_id}) ---
{factual.content}
Chain of thought: {factual.chain_of_thought}

Extract the formal argument graph."""

    r = await _retry_async(
        _claude.messages.create,
        model=settings.claude_model,
        max_tokens=2048,
        system=system,
        messages=[{"role": "user", "content": prompt}],
    )
    data = _parse_json_response(r.content[0].text)
    return ArgumentGraph(
        nodes=[ArgumentNode(**n) for n in data.get("nodes", [])],
        edges=[ArgumentEdge(**e) for e in data.get("edges", [])],
        summary=data.get("summary", ""),
    )


# ─── Phase 1 (Delphi): Iterative Position Refinement ─────────────────────────

_DELPHI_CONSENSUS_SYSTEM = """\
You are a facilitator. Summarize the GROUP CONSENSUS from multiple expert analyses WITHOUT
revealing individual positions. The summary must be neutral and anonymized (no "Model A said...").
Keep it to 3-4 sentences. This summary will be shown to all experts to help them refine their views.

Respond ONLY with valid JSON (no markdown fences):
{{
  "consensus_summary": "<anonymized group consensus, 3-4 sentences>",
  "key_disagreements": ["<point of disagreement 1>", "<point 2>"]
}}{lang_note}
"""

_DELPHI_REFINE_SYSTEM = """\
You are an expert analyst who previously gave an assessment of a problem.
You now see the group consensus from other experts.

Your task: REVISE or MAINTAIN your position.
- If the consensus reveals new evidence or logic you missed: revise with explanation.
- If you still disagree with the consensus: maintain your position with stronger justification.
- Do NOT simply agree with the group to avoid conflict. Intellectual independence is valued.

Respond ONLY with valid JSON (no markdown fences):
{{
  "content": "<your revised or maintained position, 2-3 sentences>",
  "chain_of_thought": "<what changed or why you maintain your view, max 3 steps>",
  "confidence": <float 0.0-1.0>,
  "known_unknowns": ["<uncertainty 1>"],
  "position_change": "maintained|refined|revised",
  "change_reason": "<brief explanation of what changed or why you held firm>"
}}{lang_note}
"""


async def _delphi_consensus(
    problem: str,
    takes: list[InitialTake],
    lang: str = "English",
) -> str:
    """Generate anonymized group consensus summary for Delphi feedback."""
    lang_note = _LANGUAGE_INSTRUCTION.format(lang=lang) if lang != "English" else ""
    system = _DELPHI_CONSENSUS_SYSTEM.format(lang_note=lang_note)
    analyses = "\n\n".join(f"Expert {i+1}: {t.content}" for i, t in enumerate(takes))
    prompt = f"Problem: {problem}\n\nExpert analyses:\n{analyses}\n\nGenerate anonymized group consensus."
    r = await _retry_async(
        _claude.messages.create,
        model=settings.claude_model,
        max_tokens=512,
        system=system,
        messages=[{"role": "user", "content": prompt}],
    )
    data = _parse_json_response(r.content[0].text)
    return data.get("consensus_summary", "")


async def _delphi_refine_thinking(
    problem: str,
    previous: InitialTake,
    consensus: str,
    mock: bool = False,
    lang: str = "English",
    model: str | None = None,
    adversarial: bool = False,
    sub_questions_context: str = "",
) -> InitialTake:
    """Delphi round: Gemini Thinking refines its logical position given group consensus."""
    lang_note = _LANGUAGE_INSTRUCTION.format(lang=lang) if lang != "English" else ""
    system = _DELPHI_REFINE_SYSTEM.format(lang_note=lang_note)
    prompt = f"""Problem: {problem}{sub_questions_context}

Your previous position:
{previous.content}
(confidence: {previous.confidence})

Group consensus from other experts:
{consensus}

Revise or maintain your position."""

    effective_model = model or settings.gemini_thinking_model
    if mock:
        r = await _retry_async(
            _claude.messages.create,
            model=settings.claude_model,
            max_tokens=settings.max_tokens_phase1,
            system=system,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = r.content[0].text
        effective_model = f"{settings.claude_model} [mock]"
    else:
        raw = await asyncio.to_thread(_gemini_thinking_call, prompt, system, settings.max_tokens_phase1, effective_model)

    data = _parse_json_response(raw)
    return InitialTake(
        model_id=effective_model,
        role=previous.role,
        content=_coerce_str(data.get("content", previous.content)),
        chain_of_thought=_coerce_str(data.get("chain_of_thought", "")),
        confidence=float(data.get("confidence", previous.confidence)),
        known_unknowns=[str(x) for x in data.get("known_unknowns", [])],
    )


async def _delphi_refine_pro(
    problem: str,
    previous: InitialTake,
    consensus: str,
    mock: bool = False,
    lang: str = "English",
    model: str | None = None,
    adversarial: bool = False,
    sub_questions_context: str = "",
) -> InitialTake:
    """Delphi round: Gemini Pro refines its factual position given group consensus."""
    lang_note = _LANGUAGE_INSTRUCTION.format(lang=lang) if lang != "English" else ""
    system = _DELPHI_REFINE_SYSTEM.format(lang_note=lang_note)
    prompt = f"""Problem: {problem}{sub_questions_context}

Your previous factual assessment:
{previous.content}
(confidence: {previous.confidence})

Group consensus from other experts:
{consensus}

Revise or maintain your factual assessment."""

    effective_model = model or settings.gemini_pro_model
    if mock:
        r = await _retry_async(
            _claude.messages.create,
            model=settings.claude_model,
            max_tokens=settings.max_tokens_phase1,
            system=system,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = r.content[0].text
        effective_model = f"{settings.claude_model} [mock]"
    else:
        raw = await asyncio.to_thread(_gemini_pro_call, prompt, system, settings.max_tokens_phase1, effective_model)

    data = _parse_json_response(raw)
    return InitialTake(
        model_id=effective_model,
        role=previous.role,
        content=_coerce_str(data.get("content", previous.content)),
        chain_of_thought=_coerce_str(data.get("chain_of_thought", "")),
        confidence=float(data.get("confidence", previous.confidence)),
        known_unknowns=[str(x) for x in data.get("known_unknowns", [])],
    )


# ─── Phase 1: Calibration Claim Extraction ────────────────────────────────────

_CALIBRATE_SYSTEM = """\
You are a forecasting analyst. Extract 3–6 measurable probabilistic claims from the
given analyses — claims that make explicit or implicit predictions that could be verified
in the future.

For each claim:
- Express as "X will happen" or "X is true"
- Assign a probability (0.0–1.0) based on what the analysis implies
- Give a 90% confidence interval [ci_lower, ci_upper]
- Estimate when it could be verified (time_horizon)

Focus on specific, falsifiable predictions. NOT vague statements.

Respond ONLY with valid JSON (no markdown fences):
{{
  "claims": [
    {{
      "claim": "<specific falsifiable prediction>",
      "probability": <float 0.0-1.0>,
      "ci_lower": <float 0.0-1.0>,
      "ci_upper": <float 0.0-1.0>,
      "model_id": "<which model implied this>",
      "source_role": "<which role>",
      "time_horizon": "<1 year|5 years|10 years|unknown>"
    }},
    ...
  ]
}}{lang_note}
"""


async def _claude_extract_calibration(
    debate_id: str,
    problem: str,
    logical: InitialTake,
    factual: InitialTake,
    fact_check: FactCheckResult | None = None,
    lang: str = "English",
) -> CalibrationRecord:
    lang_note = _LANGUAGE_INSTRUCTION.format(lang=lang) if lang != "English" else ""
    system = _CALIBRATE_SYSTEM.format(lang_note=lang_note)
    prompt = f"""Problem: {problem}

Analysis A ({logical.role}, {logical.model_id}):
{logical.content}

Analysis B ({factual.role}, {factual.model_id}):
{factual.content}

Extract measurable probabilistic claims from both analyses."""

    r = await _retry_async(
        _claude.messages.create,
        model=settings.claude_model,
        max_tokens=1024,
        system=system,
        messages=[{"role": "user", "content": prompt}],
    )
    data = _parse_json_response(r.content[0].text)
    claims = [ConfidenceClaim(**c) for c in data.get("claims", [])]

    # Cross-reference with fact-check if available
    alignment: float | None = None
    if fact_check and claims:
        confirmed_statuses = {c.status for c in fact_check.claims}
        # Simple heuristic: if most claims confirmed, high alignment
        if fact_check.claims:
            alignment = fact_check.confirmed_count / len(fact_check.claims)

    from datetime import datetime, timezone
    return CalibrationRecord(
        debate_id=debate_id,
        date=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        problem=problem,
        claims=claims,
        fact_check_alignment=alignment,
    )


def save_calibration_history(record: CalibrationRecord, output_dir: str = "output") -> Path:
    """Append calibration record to persistent JSONL history file."""
    path = Path(output_dir) / "calibration_history.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(record.model_dump_json() + "\n")
    return path


def load_calibration_history(output_dir: str = "output") -> list[CalibrationRecord]:
    """Load all past calibration records."""
    path = Path(output_dir) / "calibration_history.jsonl"
    if not path.exists():
        return []
    records = []
    for line in path.read_text(encoding="utf-8").strip().splitlines():
        try:
            records.append(CalibrationRecord.model_validate_json(line))
        except Exception:
            pass
    return records


def compute_calibration_stats(records: list[CalibrationRecord]) -> dict:
    """Summarize historical calibration: avg probability by model, claim counts."""
    if not records:
        return {}
    from collections import defaultdict
    model_claims: dict[str, list[float]] = defaultdict(list)
    for rec in records:
        for c in rec.claims:
            model_claims[c.model_id].append(c.probability)
    return {
        "total_debates": len(records),
        "total_claims": sum(len(r.claims) for r in records),
        "avg_probability_by_model": {m: sum(ps)/len(ps) for m, ps in model_claims.items()},
        "recent_debate": records[-1].date if records else None,
    }


# ─── Consensus Formula ────────────────────────────────────────────────────────

def calculate_agreement_score(
    logical: InitialTake,
    factual: InitialTake,
    synthesis: ClaudeSynthesis,
) -> float:
    """C = Σ(Confidence_Expert × Agreement_Score) / n"""
    scores = [
        logical.confidence * synthesis.agreement_score,
        factual.confidence * synthesis.agreement_score,
    ]
    return sum(scores) / len(scores)


# ─── DebateManager (public API) ───────────────────────────────────────────────

class DebateManager:
    """Orchestrates the multi-phase debate pipeline.

    Standard flags:
        mock_gemini, max_rounds, convergence_threshold, thinking_model, pro_model

    v1.2 extension flags:
        adversarial, grounded, multi_turn, judge

    v1.3 Tier-1 flags:
        moa, fact_check, decompose

    v1.3 Tier-2 flags:
        arg_graph      -- Structured argument graph after Phase 1 (Phase 1.6)
        delphi_rounds  -- Iterative Delphi refinement in Phase 1 (0 = disabled)
        calibrate      -- Extract & persist probabilistic claims for long-term calibration tracking
    """

    def __init__(
        self,
        mock_gemini: bool = False,
        max_rounds: int = 1,
        convergence_threshold: float = 0.8,
        thinking_model: str | None = None,
        pro_model: str | None = None,
        # v1.2
        adversarial: bool = False,
        grounded: bool = False,
        multi_turn: bool = False,
        judge: bool = False,
        # v1.3 Tier-1
        moa: bool = False,
        fact_check: bool = False,
        decompose: bool = False,
        # v1.3 Tier-2
        arg_graph: bool = False,
        delphi_rounds: int = 0,
        calibrate: bool = False,
        # v1.4
        context_text: str = "",
        # v1.6
        persona: str = "",
        # v1.9
        debate_format: str = "prose",
    ) -> None:
        self.mock_gemini = mock_gemini
        self.max_rounds = max(1, max_rounds)
        self.convergence_threshold = convergence_threshold
        self.thinking_model = thinking_model
        self.pro_model = pro_model
        self.adversarial = adversarial
        self.grounded = grounded
        self.multi_turn = multi_turn
        self.judge = judge
        self.moa = moa
        self.fact_check_enabled = fact_check
        self.decompose = decompose
        self.arg_graph = arg_graph
        self.delphi_rounds = max(0, delphi_rounds)
        self.calibrate = calibrate
        self.context_text = context_text.strip()
        self.persona = persona.strip()
        self.debate_format = debate_format

    async def decompose_problem(self, problem: str) -> ProblemDecomposition:
        """Phase 0: Break problem into sub-questions."""
        lang = _detect_language(problem)
        return await _claude_decompose_problem(problem, lang=lang)

    async def get_initial_takes(
        self,
        problem: str,
        decomposition: ProblemDecomposition | None = None,
    ) -> tuple[InitialTake, InitialTake]:
        """Phase 1: Run analyses in parallel. Supports MoA, adversarial, grounded, decompose."""
        problem = sanitize_input(problem)
        lang = _detect_language(problem)
        sub_q = _format_sub_questions(decomposition) if decomposition else ""
        if self.context_text:
            sub_q = f"\n\n--- Context provided by user ---\n{self.context_text}\n---" + sub_q

        # v1.6: Expert persona prefixes for Gemini system prompts
        persona_a = _build_persona_prefix(self.persona, "thinking")
        persona_b = _build_persona_prefix(self.persona, "pro")

        if self.moa and not self.mock_gemini:
            # MoA: run both models for each role, then aggregate
            thinking_models = [
                self.thinking_model or settings.gemini_thinking_model,
                self.pro_model or settings.gemini_pro_model,
            ]
            pro_models = [
                self.pro_model or settings.gemini_pro_model,
                self.thinking_model or settings.gemini_thinking_model,
            ]

            # Run all 4 model calls in parallel
            thinking_takes, pro_takes = await asyncio.gather(
                asyncio.gather(*[
                    _initial_thinking(problem, mock=False, lang=lang, model=m, adversarial=self.adversarial, sub_questions_context=sub_q, persona_prefix=persona_a, debate_format=self.debate_format)
                    for m in thinking_models
                ]),
                asyncio.gather(*[
                    _initial_pro(problem, mock=False, lang=lang, model=m, adversarial=self.adversarial, grounded=False, sub_questions_context=sub_q, persona_prefix=persona_b, debate_format=self.debate_format)
                    for m in pro_models
                ]),
            )

            # Aggregate with Claude in parallel
            logical_data, factual_data = await asyncio.gather(
                _moa_aggregate(problem, list(thinking_takes), lang=lang),
                _moa_aggregate(problem, list(pro_takes), lang=lang),
            )

            role_logical = "PRO Advocate (Logical)" if self.adversarial else "logical_analysis"
            role_factual = "CONTRA Advocate (Factual)" if self.adversarial else "factual_context"

            logical = InitialTake(
                model_id=f"MoA[{', '.join(thinking_models)}]",
                role=role_logical,
                content=_coerce_str(logical_data.get("content", "")),
                chain_of_thought=_coerce_str(logical_data.get("chain_of_thought", "")),
                confidence=float(logical_data.get("confidence", 0.7)),
                known_unknowns=[str(x) for x in logical_data.get("known_unknowns", [])],
                aggregated_from=thinking_models,
            )
            factual = InitialTake(
                model_id=f"MoA[{', '.join(pro_models)}]",
                role=role_factual,
                content=_coerce_str(factual_data.get("content", "")),
                chain_of_thought=_coerce_str(factual_data.get("chain_of_thought", "")),
                confidence=float(factual_data.get("confidence", 0.7)),
                known_unknowns=[str(x) for x in factual_data.get("known_unknowns", [])],
                aggregated_from=pro_models,
            )
        else:
            logical, factual = await asyncio.gather(
                _initial_thinking(problem, mock=self.mock_gemini, lang=lang, model=self.thinking_model, adversarial=self.adversarial, sub_questions_context=sub_q, persona_prefix=persona_a, debate_format=self.debate_format),
                _initial_pro(problem, mock=self.mock_gemini, lang=lang, model=self.pro_model, adversarial=self.adversarial, grounded=self.grounded and not self.mock_gemini, sub_questions_context=sub_q, persona_prefix=persona_b, debate_format=self.debate_format),
            )
        return logical, factual

    async def run_fact_check(
        self,
        problem: str,
        logical: InitialTake,
        factual: InitialTake,
    ) -> FactCheckResult:
        """Phase 1.5: Claim-level fact-checking of Phase 1 analyses."""
        lang = _detect_language(problem)
        return await _claude_fact_check(problem, logical, factual, lang=lang)

    async def run_critique_loop(
        self,
        problem: str,
        logical: InitialTake,
        factual: InitialTake,
        fact_check: FactCheckResult | None = None,
    ) -> tuple[ClaudeSynthesis, GeminiRebuttal | None, GeminiVerification]:
        """Phase 2: Claude critique (2a) → [rebuttal (2b)] → verification (2c)."""
        lang = _detect_language(problem)
        synthesis: ClaudeSynthesis | None = None
        rebuttal: GeminiRebuttal | None = None
        verification: GeminiVerification | None = None

        for round_n in range(self.max_rounds):
            prior = synthesis.synthesis_draft if synthesis else ""
            synthesis = await _claude_critique(
                problem, logical, factual,
                lang=lang, prior_synthesis=prior, fact_check=fact_check
            )
            if self.multi_turn:
                rebuttal = await _gemini_rebuttal(
                    problem, logical, synthesis,
                    mock=self.mock_gemini, lang=lang, model=self.thinking_model
                )
            verification = await _gemini_verify(
                problem, synthesis, mock=self.mock_gemini, lang=lang, model=self.thinking_model
            )
            # v1.6: Content-delta early exit — prevents hallucination amplification
            # from excessive rounds (research finding: >3 rounds risk diminishing returns)
            if synthesis.agreement_score >= self.convergence_threshold:
                break
            if round_n > 0 and prior:
                prior_words = set(prior.lower().split())
                new_words = set(synthesis.synthesis_draft.lower().split())
                if prior_words:
                    novel_fraction = len(new_words - prior_words) / max(len(new_words), 1)
                    if novel_fraction < 0.12:  # <12% new content = converged
                        break

        return synthesis, rebuttal, verification

    async def get_final_answer(
        self,
        problem: str,
        logical: InitialTake,
        factual: InitialTake,
        synthesis: ClaudeSynthesis,
        verification: GeminiVerification,
        rebuttal: GeminiRebuttal | None = None,
        fact_check: FactCheckResult | None = None,
    ) -> FinalAnswer:
        """Phase 3: Claude Opus writes the definitive final answer."""
        lang = _detect_language(problem)
        return await _claude_final(
            problem, logical, factual, synthesis, verification,
            rebuttal=rebuttal, fact_check=fact_check, lang=lang
        )

    async def get_judge_verdict(
        self,
        problem: str,
        logical: InitialTake,
        factual: InitialTake,
        synthesis: ClaudeSynthesis,
        verification: GeminiVerification,
        final: FinalAnswer,
        rebuttal: GeminiRebuttal | None = None,
        fact_check: FactCheckResult | None = None,
    ) -> JudgeVerdict:
        """Phase 4: Independent skeptical judge."""
        lang = _detect_language(problem)
        return await _claude_judge(
            problem, logical, factual, synthesis, verification, final,
            rebuttal=rebuttal, fact_check=fact_check, lang=lang
        )

    async def build_argument_graph(
        self,
        problem: str,
        logical: InitialTake,
        factual: InitialTake,
    ) -> ArgumentGraph:
        """Phase 1.6: Extract structured argument graph from Phase 1 analyses."""
        lang = _detect_language(problem)
        return await _claude_build_argument_graph(problem, logical, factual, lang=lang)

    async def run_delphi(
        self,
        problem: str,
        decomposition=None,
    ) -> tuple[InitialTake, InitialTake, DelphiProcess]:
        """Phase 1 (Delphi mode): Iterative position refinement across N rounds.

        Returns the final InitialTakes + the full DelphiProcess record.
        Note: Delphi replaces standard Phase 1 when delphi_rounds > 0.
        """
        lang = _detect_language(problem)
        sub_q = _format_sub_questions(decomposition) if decomposition else ""

        # Round 1: standard (blind) initial takes
        logical, factual = await asyncio.gather(
            _initial_thinking(problem, mock=self.mock_gemini, lang=lang, model=self.thinking_model, adversarial=self.adversarial, sub_questions_context=sub_q),
            _initial_pro(problem, mock=self.mock_gemini, lang=lang, model=self.pro_model, adversarial=self.adversarial, grounded=self.grounded and not self.mock_gemini, sub_questions_context=sub_q),
        )

        rounds: list[DelphiRound] = []
        converged = False
        convergence_round: int | None = None
        prev_conf_a = logical.confidence
        prev_conf_b = factual.confidence

        rounds.append(DelphiRound(
            round_n=1,
            position_a=logical.content[:200],
            position_b=factual.content[:200],
            confidence_a=logical.confidence,
            confidence_b=factual.confidence,
            consensus_summary="(Initial round — no prior consensus)",
            delta=0.0,
        ))

        for round_n in range(2, self.delphi_rounds + 1):
            # Generate anonymized consensus from previous round
            consensus = await _delphi_consensus(problem, [logical, factual], lang=lang)

            # Both agents refine in parallel
            logical, factual = await asyncio.gather(
                _delphi_refine_thinking(problem, logical, consensus, mock=self.mock_gemini, lang=lang, model=self.thinking_model, sub_questions_context=sub_q),
                _delphi_refine_pro(problem, factual, consensus, mock=self.mock_gemini, lang=lang, model=self.pro_model, sub_questions_context=sub_q),
            )

            delta = (abs(logical.confidence - prev_conf_a) + abs(factual.confidence - prev_conf_b)) / 2.0
            rounds.append(DelphiRound(
                round_n=round_n,
                position_a=logical.content[:200],
                position_b=factual.content[:200],
                confidence_a=logical.confidence,
                confidence_b=factual.confidence,
                consensus_summary=consensus,
                delta=delta,
            ))

            prev_conf_a = logical.confidence
            prev_conf_b = factual.confidence

            # Converge early if positions barely moved
            if delta < 0.05:
                converged = True
                convergence_round = round_n
                break

        return logical, factual, DelphiProcess(
            rounds=rounds,
            converged=converged,
            convergence_round=convergence_round,
        )

    async def extract_calibration(
        self,
        debate_id: str,
        problem: str,
        logical: InitialTake,
        factual: InitialTake,
        fact_check: FactCheckResult | None = None,
    ) -> CalibrationRecord:
        """Extract probabilistic claims from Phase 1 for long-term calibration tracking."""
        lang = _detect_language(problem)
        return await _claude_extract_calibration(debate_id, problem, logical, factual, fact_check=fact_check, lang=lang)

    def calculate_agreement(self, result: DebateResult) -> float:
        return calculate_agreement_score(result.logical_analysis, result.factual_context, result.critique)
