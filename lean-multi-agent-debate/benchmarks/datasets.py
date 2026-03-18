"""
Benchmark dataset: 15 test problems across 3 categories.

Categories:
  - factual:      Problems with an objectively correct answer.
  - controversial: Multi-perspective problems without a single ground truth.
  - technical:    Domain-specific reasoning questions.

Format:
  {
    "id": str,
    "problem": str,
    "category": "factual" | "controversial" | "technical",
    "expected_min_consensus": float,   # Lower bound for consensus score (0.0–1.0)
    "expected_max_latency_s": int,     # Soft latency ceiling (informational only)
    "tags": list[str],
  }
"""

BENCHMARK_PROBLEMS: list[dict] = [
    # ── Factual (5 problems) ──────────────────────────────────────────────────
    {
        "id": "f01",
        "problem": "Is RSA-2048 mathematically broken today (2026)?",
        "category": "factual",
        "expected_min_consensus": 0.75,
        "expected_max_latency_s": 60,
        "tags": ["cryptography", "quantum", "security"],
    },
    {
        "id": "f02",
        "problem": "Has the global mean surface temperature increased since 1880?",
        "category": "factual",
        "expected_min_consensus": 0.85,
        "expected_max_latency_s": 60,
        "tags": ["climate", "science"],
    },
    {
        "id": "f03",
        "problem": "Is Python's GIL (Global Interpreter Lock) removed in CPython 3.13?",
        "category": "factual",
        "expected_min_consensus": 0.70,
        "expected_max_latency_s": 60,
        "tags": ["python", "concurrency", "technical"],
    },
    {
        "id": "f04",
        "problem": "Does transformer self-attention scale quadratically with sequence length?",
        "category": "factual",
        "expected_min_consensus": 0.80,
        "expected_max_latency_s": 60,
        "tags": ["ml", "transformers", "complexity"],
    },
    {
        "id": "f05",
        "problem": "Is Bitcoin's total supply capped at 21 million coins?",
        "category": "factual",
        "expected_min_consensus": 0.90,
        "expected_max_latency_s": 60,
        "tags": ["crypto", "bitcoin"],
    },

    # ── Controversial (5 problems) ────────────────────────────────────────────
    {
        "id": "c01",
        "problem": "Should advanced AI systems be open-sourced?",
        "category": "controversial",
        "expected_min_consensus": 0.40,
        "expected_max_latency_s": 90,
        "tags": ["ai", "policy", "open-source"],
    },
    {
        "id": "c02",
        "problem": "Is universal basic income a viable economic policy for the 21st century?",
        "category": "controversial",
        "expected_min_consensus": 0.35,
        "expected_max_latency_s": 90,
        "tags": ["economics", "policy", "ubi"],
    },
    {
        "id": "c03",
        "problem": "Does social media do more harm than good to society?",
        "category": "controversial",
        "expected_min_consensus": 0.40,
        "expected_max_latency_s": 90,
        "tags": ["social", "media", "psychology"],
    },
    {
        "id": "c04",
        "problem": "Should gene editing in human embryos be permitted for disease prevention?",
        "category": "controversial",
        "expected_min_consensus": 0.35,
        "expected_max_latency_s": 90,
        "tags": ["bioethics", "genetics", "crispr"],
    },
    {
        "id": "c05",
        "problem": "Is nuclear energy essential for reaching net-zero carbon emissions by 2050?",
        "category": "controversial",
        "expected_min_consensus": 0.45,
        "expected_max_latency_s": 90,
        "tags": ["energy", "climate", "nuclear"],
    },

    # ── Technical (5 problems) ────────────────────────────────────────────────
    {
        "id": "t01",
        "problem": "Is RAG (Retrieval-Augmented Generation) superior to fine-tuning for domain-specific LLM applications?",
        "category": "technical",
        "expected_min_consensus": 0.55,
        "expected_max_latency_s": 90,
        "tags": ["llm", "rag", "fine-tuning"],
    },
    {
        "id": "t02",
        "problem": "Should microservices be the default architecture for new web applications in 2026?",
        "category": "technical",
        "expected_min_consensus": 0.50,
        "expected_max_latency_s": 90,
        "tags": ["architecture", "microservices", "software"],
    },
    {
        "id": "t03",
        "problem": "Is Rust a better choice than C++ for new systems programming projects?",
        "category": "technical",
        "expected_min_consensus": 0.55,
        "expected_max_latency_s": 90,
        "tags": ["rust", "cpp", "systems"],
    },
    {
        "id": "t04",
        "problem": "Will large language models achieve AGI-level reasoning within 5 years (by 2031)?",
        "category": "technical",
        "expected_min_consensus": 0.35,
        "expected_max_latency_s": 90,
        "tags": ["agi", "llm", "prediction"],
    },
    {
        "id": "t05",
        "problem": "Is vector search with approximate nearest neighbors sufficient for production RAG systems, or do hybrid approaches (BM25 + dense) always outperform?",
        "category": "technical",
        "expected_min_consensus": 0.50,
        "expected_max_latency_s": 90,
        "tags": ["rag", "vector-search", "retrieval"],
    },
]


def get_problems_by_category(category: str) -> list[dict]:
    return [p for p in BENCHMARK_PROBLEMS if p["category"] == category]


def get_problem_by_id(problem_id: str) -> dict | None:
    return next((p for p in BENCHMARK_PROBLEMS if p["id"] == problem_id), None)
