"""End-to-End RAG evaluation: measure downstream QA impact of MKOS filtering.

Compares RAG answer quality on:
1. Degraded KB (threats injected among healthy content)
2. MKOS-filtered KB (threats removed after immune scan)
3. Clean KB (only healthy content, oracle baseline)

Metrics: Correctness, Faithfulness, Relevance (LLM-judged)
"""

from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass, field

from akm.benchmarks.datasets import BenchmarkItem, seed_benchmark_db
from akm.immune.system import KnowledgeImmuneSystem
from akm.llm.client import ClaudeClient
from akm.rag.pipeline import RAGPipeline
from akm.search.engine import SearchEngine


@dataclass
class QAItem:
    """A question with expected answer and the chunk IDs it depends on."""
    question: str
    expected_answer: str
    relevant_chunk_titles: list[str]
    category: str = "general"


@dataclass
class RAGEvalResult:
    """Evaluation result for a single QA item."""
    question: str
    expected: str
    generated: str
    correctness: float  # 0-1
    faithfulness: float  # 0-1
    uses_threat: bool  # whether the answer incorporated a threat chunk
    category: str = ""


@dataclass
class RAGEvalReport:
    """Aggregate evaluation report."""
    condition: str  # "degraded", "filtered", "clean"
    results: list[RAGEvalResult] = field(default_factory=list)

    @property
    def avg_correctness(self) -> float:
        if not self.results:
            return 0.0
        return sum(r.correctness for r in self.results) / len(self.results)

    @property
    def avg_faithfulness(self) -> float:
        if not self.results:
            return 0.0
        return sum(r.faithfulness for r in self.results) / len(self.results)

    @property
    def threat_usage_rate(self) -> float:
        if not self.results:
            return 0.0
        return sum(1 for r in self.results if r.uses_threat) / len(self.results)

    def to_dict(self) -> dict:
        return {
            "condition": self.condition,
            "n_questions": len(self.results),
            "avg_correctness": round(self.avg_correctness, 4),
            "avg_faithfulness": round(self.avg_faithfulness, 4),
            "threat_usage_rate": round(self.threat_usage_rate, 4),
        }


def build_qa_dataset() -> tuple[list[BenchmarkItem], list[QAItem]]:
    """Build a KB with injected threats AND matching QA questions.

    Returns (kb_items, qa_items) where questions target content areas
    that have both healthy and threat chunks.
    """
    kb_items: list[BenchmarkItem] = []
    qa_items: list[QAItem] = []

    # Domain 1: Python
    kb_items.extend([
        BenchmarkItem(
            "Python uses reference counting with a cycle-detecting garbage collector. "
            "Objects are deallocated when their reference count drops to zero. "
            "The gc module handles circular references via generational collection.",
            "Python Memory Management", ["healthy"],
        ),
        BenchmarkItem(
            "Python 3.12 introduces type parameter syntax (PEP 695) using the `type` keyword. "
            "Generic classes and functions can now declare type parameters directly.",
            "Python 3.12 Type Parameters", ["healthy"],
        ),
        BenchmarkItem(
            "Python uses a mark-and-sweep garbage collector exclusively, with no reference counting. "
            "All memory management is handled by periodic full-heap scans every 100ms.",
            "Python GC Internals", ["hallucination"],
        ),
    ])
    qa_items.append(QAItem(
        "How does Python manage memory and garbage collection?",
        "Python uses reference counting as its primary mechanism, with a cycle-detecting "
        "garbage collector (generational) for circular references.",
        ["Python Memory Management"],
        "memory_management",
    ))

    # Domain 2: Docker
    kb_items.extend([
        BenchmarkItem(
            "Docker containers share the host kernel and use namespaces for isolation. "
            "Each container has its own PID, network, and mount namespace. "
            "Cgroups limit CPU, memory, and I/O resources per container.",
            "Docker Container Architecture", ["healthy"],
        ),
        BenchmarkItem(
            "Docker multi-stage builds allow using multiple FROM statements to separate "
            "build and runtime environments, significantly reducing final image size.",
            "Docker Multi-stage Builds", ["healthy"],
        ),
        BenchmarkItem(
            "Docker containers run their own full kernel instance, providing complete "
            "hardware-level virtualization identical to virtual machines. Each container "
            "boots its own Linux kernel on startup.",
            "Docker Virtualization", ["hallucination"],
        ),
    ])
    qa_items.append(QAItem(
        "How do Docker containers achieve isolation?",
        "Docker containers share the host kernel and use namespaces (PID, network, mount) "
        "for isolation, with cgroups for resource limits.",
        ["Docker Container Architecture"],
        "containerization",
    ))

    # Domain 3: SQL
    kb_items.extend([
        BenchmarkItem(
            "PostgreSQL MVCC (Multi-Version Concurrency Control) allows readers and writers "
            "to operate simultaneously without blocking. Each transaction sees a snapshot "
            "of the database at its start time.",
            "PostgreSQL MVCC", ["healthy"],
        ),
        BenchmarkItem(
            "SQL indexes use B-tree structures by default. Creating an index on a column "
            "speeds up WHERE clause lookups but adds overhead to INSERT/UPDATE operations.",
            "SQL Indexing Basics", ["healthy"],
        ),
        BenchmarkItem(
            "PostgreSQL's MVCC implementation requires all transactions to acquire exclusive "
            "table-level locks before reading any data, which is why SELECT queries in "
            "PostgreSQL block all concurrent writes.",
            "PostgreSQL Locking", ["contradiction"],
        ),
    ])
    qa_items.append(QAItem(
        "How does PostgreSQL handle concurrent access?",
        "PostgreSQL uses MVCC allowing readers and writers to operate simultaneously "
        "without blocking. Each transaction sees a snapshot at its start time.",
        ["PostgreSQL MVCC"],
        "databases",
    ))

    # Domain 4: Kubernetes
    kb_items.extend([
        BenchmarkItem(
            "Kubernetes pods are the smallest deployable units and can contain one or more "
            "containers. Containers in a pod share the same network namespace and can "
            "communicate via localhost. Pods are ephemeral by design.",
            "Kubernetes Pods", ["healthy"],
        ),
        BenchmarkItem(
            "Kubernetes Services provide stable networking for pods. ClusterIP exposes "
            "the service internally, NodePort on each node, and LoadBalancer via cloud provider.",
            "Kubernetes Services", ["healthy"],
        ),
        BenchmarkItem(
            "Kubernetes is the only container orchestration platform available today. "
            "No alternatives exist, making it the mandatory choice for any containerized "
            "deployment regardless of scale or requirements.",
            "Kubernetes Adoption", ["bias"],
        ),
    ])
    qa_items.append(QAItem(
        "What are Kubernetes pods and how do they work?",
        "Pods are the smallest deployable units in Kubernetes, containing one or more "
        "containers that share the same network namespace. They are ephemeral by design.",
        ["Kubernetes Pods"],
        "orchestration",
    ))

    # Domain 5: REST APIs
    kb_items.extend([
        BenchmarkItem(
            "REST APIs use HTTP methods semantically: GET for retrieval, POST for creation, "
            "PUT for full update, PATCH for partial update, DELETE for removal. "
            "Status codes indicate success (2xx), client errors (4xx), server errors (5xx).",
            "REST API Design", ["healthy"],
        ),
        BenchmarkItem(
            "API rate limiting protects services from abuse. Common strategies include "
            "token bucket, sliding window, and fixed window algorithms. "
            "HTTP 429 Too Many Requests indicates rate limit exceeded.",
            "API Rate Limiting", ["healthy"],
        ),
        BenchmarkItem(
            "REST APIs were invented by Roy Fielding at Microsoft in 2005 as part of the "
            "Azure platform development. The architectural style was first described in "
            "his paper 'RESTful Web Services for Cloud Computing'.",
            "REST API History", ["hallucination"],
        ),
    ])
    qa_items.append(QAItem(
        "What are the key principles of REST API design?",
        "REST APIs use HTTP methods semantically (GET, POST, PUT, PATCH, DELETE) with "
        "appropriate status codes (2xx success, 4xx client errors, 5xx server errors).",
        ["REST API Design"],
        "api_design",
    ))

    # Domain 6: Git
    kb_items.extend([
        BenchmarkItem(
            "Git stores data as snapshots of the entire project state, not as diffs. "
            "Each commit points to a tree object representing the directory structure. "
            "Objects are stored as SHA-1 hashes in .git/objects.",
            "Git Internals", ["healthy"],
        ),
        BenchmarkItem(
            "Git branching creates a lightweight pointer to a commit. Merging combines "
            "divergent histories. Rebasing replays commits onto a new base, creating "
            "a linear history but rewriting commit hashes.",
            "Git Branching Strategy", ["healthy"],
        ),
        BenchmarkItem(
            "Git 2.0 was released in 2014 and is the latest stable version. "
            "No new versions have been released since then. The project entered "
            "maintenance mode in 2015.",
            "Git Version History", ["staleness"],
        ),
    ])
    qa_items.append(QAItem(
        "How does Git store data internally?",
        "Git stores data as snapshots (not diffs). Each commit points to a tree object. "
        "Objects are stored as SHA-1 hashes in .git/objects.",
        ["Git Internals"],
        "version_control",
    ))

    # Domain 7: Machine Learning
    kb_items.extend([
        BenchmarkItem(
            "Neural networks learn by backpropagation: computing gradients of the loss "
            "function with respect to weights via the chain rule, then updating weights "
            "using gradient descent. Learning rate controls step size.",
            "Neural Network Training", ["healthy"],
        ),
        BenchmarkItem(
            "Overfitting occurs when a model memorizes training data instead of learning "
            "patterns. Regularization techniques include dropout, L1/L2 penalties, "
            "early stopping, and data augmentation.",
            "Overfitting Prevention", ["healthy"],
        ),
        BenchmarkItem(
            "Gradient descent is always guaranteed to find the global minimum for any "
            "objective function, regardless of its shape. Neural networks have convex "
            "loss landscapes that ensure unique optimal solutions.",
            "Optimization Theory", ["hallucination"],
        ),
    ])
    qa_items.append(QAItem(
        "How do neural networks learn through backpropagation?",
        "Neural networks learn by computing gradients of the loss via the chain rule "
        "(backpropagation) and updating weights with gradient descent.",
        ["Neural Network Training"],
        "machine_learning",
    ))

    # Domain 8: Security
    kb_items.extend([
        BenchmarkItem(
            "HTTPS uses TLS to encrypt communication between client and server. "
            "The TLS handshake establishes a shared session key using asymmetric "
            "cryptography, then switches to symmetric encryption for data transfer.",
            "TLS/HTTPS Overview", ["healthy"],
        ),
        BenchmarkItem(
            "SQL injection attacks insert malicious SQL through user input. "
            "Prevention: use parameterized queries, input validation, and ORMs. "
            "Never concatenate user input directly into SQL strings.",
            "SQL Injection Prevention", ["healthy"],
        ),
        BenchmarkItem(
            "MD5 hashing provides strong cryptographic security for password storage "
            "in 2025. Its 128-bit output is computationally infeasible to crack "
            "and no practical collision attacks exist.",
            "Password Security", ["staleness"],
        ),
    ])
    qa_items.append(QAItem(
        "How does HTTPS protect web communication?",
        "HTTPS uses TLS encryption. The TLS handshake establishes a shared session key "
        "via asymmetric cryptography, then uses symmetric encryption for data transfer.",
        ["TLS/HTTPS Overview"],
        "security",
    ))

    # Domain 9: Caching
    kb_items.extend([
        BenchmarkItem(
            "Redis is an in-memory data structure store used as cache, message broker, "
            "and database. It supports strings, hashes, lists, sets, and sorted sets. "
            "Data persistence via RDB snapshots and AOF logs.",
            "Redis Overview", ["healthy"],
        ),
        BenchmarkItem(
            "Cache invalidation strategies: TTL (time-to-live), write-through (update cache "
            "on write), write-behind (async cache update), and cache-aside (lazy loading). "
            "Choice depends on read/write patterns and consistency requirements.",
            "Cache Invalidation", ["healthy"],
        ),
        BenchmarkItem(
            "Redis stores all data exclusively on disk and reads it into memory only when "
            "accessed. It uses a traditional B-tree storage engine identical to PostgreSQL "
            "for persistent data management.",
            "Redis Architecture", ["contradiction"],
        ),
    ])
    qa_items.append(QAItem(
        "What is Redis and how does it store data?",
        "Redis is an in-memory data structure store. It supports various data types and "
        "provides persistence via RDB snapshots and AOF logs.",
        ["Redis Overview"],
        "caching",
    ))

    # Domain 10: Testing
    kb_items.extend([
        BenchmarkItem(
            "The testing pyramid suggests more unit tests (fast, isolated), fewer integration "
            "tests (component interactions), and minimal E2E tests (slow, brittle). "
            "Unit tests should run in milliseconds and have no external dependencies.",
            "Testing Pyramid", ["healthy"],
        ),
        BenchmarkItem(
            "Test-Driven Development (TDD) follows red-green-refactor: write a failing test, "
            "make it pass with minimal code, then refactor. This ensures tests drive design "
            "decisions and all code has test coverage.",
            "TDD Methodology", ["healthy"],
        ),
        BenchmarkItem(
            "Integration tests are always superior to unit tests in every scenario. "
            "Unit tests provide no value and should be avoided entirely. "
            "Only E2E tests can catch real bugs.",
            "Testing Best Practices", ["bias"],
        ),
    ])
    qa_items.append(QAItem(
        "What does the testing pyramid recommend?",
        "More unit tests (fast, isolated), fewer integration tests (component interactions), "
        "and minimal E2E tests (slow, brittle).",
        ["Testing Pyramid"],
        "testing",
    ))

    return kb_items, qa_items


class RAGEvaluator:
    """Evaluates RAG answer quality across different KB conditions."""

    JUDGE_PROMPT = (
        "You are an expert evaluator of question-answering systems.\n\n"
        "Given a QUESTION, EXPECTED ANSWER, and GENERATED ANSWER, evaluate:\n\n"
        "1. correctness (0.0-1.0): Does the generated answer contain the same "
        "key facts as the expected answer? Penalize wrong facts heavily.\n"
        "2. faithfulness (0.0-1.0): Does the generated answer avoid stating "
        "things that are factually incorrect? (independent of the expected answer)\n\n"
        'Respond with JSON: {"correctness": 0.0-1.0, "faithfulness": 0.0-1.0, '
        '"issues": "brief description of any problems"}'
    )

    def __init__(self, conn: sqlite3.Connection, llm: ClaudeClient) -> None:
        self.conn = conn
        self.llm = llm

    def evaluate_condition(
        self,
        kb_items: list[BenchmarkItem],
        qa_items: list[QAItem],
        condition: str,
        threat_chunk_ids: set[int] | None = None,
    ) -> RAGEvalReport:
        """Evaluate RAG on a specific KB condition."""
        chunk_ids = seed_benchmark_db(self.conn, kb_items)
        self.conn.commit()

        # Embed chunks
        try:
            from akm.search.embeddings import embed_all_chunks
            embed_all_chunks(self.conn)
        except Exception:
            pass

        rag = RAGPipeline(self.conn, self.llm, top_k=5)
        report = RAGEvalReport(condition=condition)

        for qa in qa_items:
            result = rag.answer(qa.question)
            generated = result["answer"]
            used_ids = set(result["chunk_ids"])

            # Check if answer used any threat chunk
            uses_threat = bool(threat_chunk_ids and used_ids & threat_chunk_ids)

            # LLM-as-judge evaluation
            judge_result = self.llm.extract_json(
                self.JUDGE_PROMPT,
                f"QUESTION: {qa.question}\n\n"
                f"EXPECTED ANSWER: {qa.expected_answer}\n\n"
                f"GENERATED ANSWER: {generated}",
            )

            correctness = float(judge_result.get("correctness", 0.5)) if isinstance(judge_result, dict) else 0.5
            faithfulness = float(judge_result.get("faithfulness", 0.5)) if isinstance(judge_result, dict) else 0.5

            report.results.append(RAGEvalResult(
                question=qa.question,
                expected=qa.expected_answer,
                generated=generated,
                correctness=correctness,
                faithfulness=faithfulness,
                uses_threat=uses_threat,
                category=qa.category,
            ))

        return report

    def _clean_db(self) -> None:
        """Remove all benchmark data for a fresh condition."""
        for table in ["chunks", "documents", "projects",
                      "immune_patterns", "immune_scan_results"]:
            try:
                self.conn.execute(f"DELETE FROM {table}")
            except Exception:
                pass
        try:
            self.conn.execute("DELETE FROM chunks_vec")
        except Exception:
            pass
        try:
            self.conn.execute("INSERT INTO chunks_fts(chunks_fts) VALUES('rebuild')")
        except Exception:
            pass
        try:
            self.conn.execute("DELETE FROM stigmergy_signals")
        except Exception:
            pass
        self.conn.commit()

    def run_full_evaluation(self) -> dict:
        """Run complete 3-condition evaluation.

        1. Degraded: all items (healthy + threats)
        2. Filtered: MKOS removes detected threats
        3. Clean: only healthy items (oracle baseline)
        """
        all_items, qa_items = build_qa_dataset()
        healthy_items = [it for it in all_items if it.labels[0] == "healthy"]
        threat_items = [it for it in all_items if it.labels[0] != "healthy"]

        # Identify threat chunk positions
        threat_indices = {i for i, it in enumerate(all_items) if it.labels[0] != "healthy"}

        # ── Condition 1: Degraded KB ─────────────────────────────────────
        self._clean_db()
        chunk_ids = seed_benchmark_db(self.conn, all_items)
        threat_chunk_ids = {chunk_ids[i] for i in threat_indices}
        self.conn.commit()

        try:
            from akm.search.embeddings import embed_all_chunks
            embed_all_chunks(self.conn)
        except Exception:
            pass

        degraded = self._eval_with_existing_db(qa_items, "degraded", threat_chunk_ids)

        # ── Condition 2: MKOS-filtered KB ────────────────────────────────
        # Re-seed fresh (to avoid stale state from degraded condition)
        self._clean_db()
        chunk_ids = seed_benchmark_db(self.conn, all_items)
        threat_chunk_ids = {chunk_ids[i] for i in threat_indices}
        self.conn.commit()

        try:
            from akm.search.embeddings import embed_all_chunks
            embed_all_chunks(self.conn)
        except Exception:
            pass

        # Scan all chunks, remove detected threats
        immune = KnowledgeImmuneSystem(self.conn, self.llm)
        detected_ids: set[int] = set()
        for cid in chunk_ids:
            try:
                scan = immune.scan_chunk(cid)
                if scan.threats_found:
                    detected_ids.add(cid)
            except Exception:
                pass

        # Remove detected threats from DB
        for cid in detected_ids:
            self.conn.execute("DELETE FROM chunks WHERE id = ?", (cid,))
            try:
                self.conn.execute("DELETE FROM chunks_vec WHERE chunk_id = ?", (cid,))
            except Exception:
                pass
        self.conn.commit()

        # Rebuild FTS index
        try:
            self.conn.execute("INSERT INTO chunks_fts(chunks_fts) VALUES('rebuild')")
        except Exception:
            pass

        filtered = self._eval_with_existing_db(qa_items, "filtered", threat_chunk_ids - detected_ids)

        # ── Condition 3: Clean KB (oracle) ───────────────────────────────
        self._clean_db()
        clean = self.evaluate_condition(healthy_items, qa_items, "clean", set())

        # ── Build report ─────────────────────────────────────────────────
        return {
            "n_kb_items": len(all_items),
            "n_healthy": len(healthy_items),
            "n_threats": len(threat_items),
            "n_questions": len(qa_items),
            "n_detected": len(detected_ids),
            "detection_rate": round(len(detected_ids) / max(1, len(threat_items)), 4),
            "conditions": {
                "degraded": degraded.to_dict(),
                "filtered": filtered.to_dict(),
                "clean": clean.to_dict(),
            },
            "delta_correctness": round(
                filtered.avg_correctness - degraded.avg_correctness, 4
            ),
            "delta_faithfulness": round(
                filtered.avg_faithfulness - degraded.avg_faithfulness, 4
            ),
            "per_question": [
                {
                    "question": qa.question,
                    "category": qa.category,
                    "degraded": {
                        "correctness": degraded.results[i].correctness,
                        "faithfulness": degraded.results[i].faithfulness,
                        "uses_threat": degraded.results[i].uses_threat,
                    },
                    "filtered": {
                        "correctness": filtered.results[i].correctness,
                        "faithfulness": filtered.results[i].faithfulness,
                        "uses_threat": filtered.results[i].uses_threat,
                    },
                    "clean": {
                        "correctness": clean.results[i].correctness,
                        "faithfulness": clean.results[i].faithfulness,
                    },
                }
                for i, qa in enumerate(qa_items)
            ],
        }

    def _eval_with_existing_db(
        self,
        qa_items: list[QAItem],
        condition: str,
        threat_chunk_ids: set[int],
    ) -> RAGEvalReport:
        """Evaluate on current DB state (no re-seeding)."""
        rag = RAGPipeline(self.conn, self.llm, top_k=5)
        report = RAGEvalReport(condition=condition)

        for qa in qa_items:
            result = rag.answer(qa.question)
            generated = result["answer"]
            used_ids = set(result["chunk_ids"])
            uses_threat = bool(threat_chunk_ids and used_ids & threat_chunk_ids)

            judge_result = self.llm.extract_json(
                self.JUDGE_PROMPT,
                f"QUESTION: {qa.question}\n\n"
                f"EXPECTED ANSWER: {qa.expected_answer}\n\n"
                f"GENERATED ANSWER: {generated}",
            )

            correctness = float(judge_result.get("correctness", 0.5)) if isinstance(judge_result, dict) else 0.5
            faithfulness = float(judge_result.get("faithfulness", 0.5)) if isinstance(judge_result, dict) else 0.5

            report.results.append(RAGEvalResult(
                question=qa.question,
                expected=qa.expected_answer,
                generated=generated,
                correctness=correctness,
                faithfulness=faithfulness,
                uses_threat=uses_threat,
                category=qa.category,
            ))

        return report
