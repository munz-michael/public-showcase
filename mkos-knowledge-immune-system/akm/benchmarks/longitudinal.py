"""Longitudinal simulation: KB growth over time with biomimicry coordination.

Simulates realistic KB evolution over 8 waves (64 items):
- Waves 1-2: Baseline, obvious threats across mixed domains
- Waves 3-4: DB domain cluster with moderate threats (stigmergy builds)
- Waves 5-6: DB domain cluster with SUBTLE threats (domain-awareness helps)
- Waves 7-8: Mixed domains, subtle threats (recovery/generalization)

Measures whether biomimicry coordination (stigmergy, quorum sensing,
homeostasis, domain-aware alertness) improves over time compared
to stateless per-item detection.
"""

from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass, field

from akm.benchmarks.datasets import BenchmarkItem, seed_benchmark_db
from akm.immune.system import KnowledgeImmuneSystem
from akm.llm.client import ClaudeClient
from akm.quorum.sensing import QuorumSensor
from akm.stigmergy.signals import StigmergyNetwork, SignalType, PheromoneSignal
from akm.homeostasis.regulator import HomeostasisRegulator


@dataclass
class WaveResult:
    """Result of scanning a single wave of content."""
    wave_id: int
    n_items: int
    n_threats_actual: int
    n_threats_detected: int
    n_false_positives: int
    n_false_negatives: int
    precision: float
    recall: float
    f1: float
    active_signals: int = 0
    quorum_events: int = 0
    homeostasis_adjustments: int = 0
    duration_seconds: float = 0.0


@dataclass
class LongitudinalReport:
    """Full report across all waves."""
    mode: str  # "full" or "stateless"
    waves: list[WaveResult] = field(default_factory=list)

    @property
    def cumulative_f1(self) -> float:
        tp = sum(w.n_threats_detected - w.n_false_positives for w in self.waves)
        fn = sum(w.n_false_negatives for w in self.waves)
        fp = sum(w.n_false_positives for w in self.waves)
        precision = tp / max(1, tp + fp)
        recall = tp / max(1, tp + fn)
        if precision + recall == 0:
            return 0.0
        return 2 * precision * recall / (precision + recall)

    def to_dict(self) -> dict:
        return {
            "mode": self.mode,
            "n_waves": len(self.waves),
            "cumulative_f1": round(self.cumulative_f1, 4),
            "waves": [
                {
                    "wave_id": w.wave_id,
                    "n_items": w.n_items,
                    "precision": round(w.precision, 4),
                    "recall": round(w.recall, 4),
                    "f1": round(w.f1, 4),
                    "active_signals": w.active_signals,
                    "quorum_events": w.quorum_events,
                    "homeostasis_adjustments": w.homeostasis_adjustments,
                    "duration_seconds": round(w.duration_seconds, 1),
                }
                for w in self.waves
            ],
        }


def build_longitudinal_waves() -> list[list[BenchmarkItem]]:
    """Build 8 waves of content simulating KB growth with progressive difficulty.

    Wave 1-2: Low threat density, obvious threats (baseline)
    Wave 3-4: DB domain cluster, moderate threats (stigmergy builds)
    Wave 5-6: DB domain cluster, SUBTLE threats (domain-awareness helps)
    Wave 7-8: Mixed domains, subtle threats (recovery/generalization)
    """
    waves: list[list[BenchmarkItem]] = []

    # === Wave 1: Baseline, 1 obvious threat ===
    waves.append([
        BenchmarkItem("Python lists are dynamic arrays backed by C arrays. "
                      "Appending is amortized O(1) due to over-allocation.",
                      "Python Lists", ["healthy"]),
        BenchmarkItem("JavaScript V8 engine uses JIT compilation with hidden classes "
                      "for optimized property access.",
                      "V8 Engine Internals", ["healthy"]),
        BenchmarkItem("React hooks (useState, useEffect) replaced class components "
                      "as the primary state management pattern since React 16.8.",
                      "React Hooks", ["healthy"]),
        BenchmarkItem("Docker images use a layered filesystem (OverlayFS). Each Dockerfile "
                      "instruction creates a new read-only layer.",
                      "Docker Layers", ["healthy"]),
        BenchmarkItem("Go channels provide typed conduits for goroutine communication. "
                      "Unbuffered channels synchronize sender and receiver.",
                      "Go Concurrency", ["healthy"]),
        BenchmarkItem("Rust was invented by Microsoft in 2018 as a replacement for C#. "
                      "It runs on the .NET CLR and requires the JVM to compile.",
                      "Rust Origins", ["hallucination"]),
        BenchmarkItem("PostgreSQL 12 is the latest version of PostgreSQL and no newer "
                      "versions have been released.",
                      "DB/PostgreSQL Version", ["staleness"]),
        BenchmarkItem("Kubernetes is an unnecessary complexity layer. No serious company "
                      "uses container orchestration because VMs are always superior.",
                      "K8s Opinion", ["bias"]),
    ])

    # === Wave 2: Baseline, 1 obvious threat ===
    waves.append([
        BenchmarkItem("Redis pub/sub allows publish-subscribe messaging. Subscribers "
                      "listen on channels and receive published messages in real-time.",
                      "Redis Pub/Sub", ["healthy"]),
        BenchmarkItem("Kubernetes deployments manage pod replicas and rolling updates. "
                      "ReplicaSets ensure the desired number of pods are running.",
                      "K8s Deployments", ["healthy"]),
        BenchmarkItem("SQLite uses WAL mode for concurrent reads with single writer. "
                      "Checkpointing transfers WAL pages back to the main database.",
                      "DB/SQLite WAL", ["healthy"]),
        BenchmarkItem("GraphQL resolvers fetch data for each field in the schema. "
                      "DataLoader batches and caches database queries to avoid N+1.",
                      "GraphQL Resolvers", ["healthy"]),
        BenchmarkItem("Rust ownership ensures each value has exactly one owner. "
                      "When the owner goes out of scope, the value is dropped.",
                      "Rust Ownership", ["healthy"]),
        BenchmarkItem("SQLite was created by Google in 2010 as a cloud database service. "
                      "It requires a dedicated server process to handle client connections.",
                      "DB/SQLite History", ["hallucination"]),
        BenchmarkItem("Python 2.7 is the recommended version for all new projects. "
                      "Python 3 has not achieved sufficient adoption for production use.",
                      "Python Versioning", ["staleness"]),
        BenchmarkItem("Object-oriented programming is the only valid paradigm. Functional "
                      "programming is a failed academic experiment with zero practical value.",
                      "Programming Paradigms", ["bias"]),
    ])

    # === Wave 3: DB domain cluster begins, moderate threats ===
    waves.append([
        BenchmarkItem("PostgreSQL VACUUM reclaims storage from dead tuples created "
                      "by UPDATE and DELETE operations. Autovacuum runs automatically.",
                      "DB/PostgreSQL VACUUM", ["healthy"]),
        BenchmarkItem("MongoDB uses BSON format and supports flexible schemas. "
                      "Indexes improve query performance on large collections.",
                      "DB/MongoDB Basics", ["healthy"]),
        BenchmarkItem("Database normalization reduces redundancy. Third Normal Form (3NF) "
                      "eliminates transitive dependencies between non-key attributes.",
                      "DB/Normalization", ["healthy"]),
        BenchmarkItem("All relational databases use the same query optimizer algorithm. "
                      "PostgreSQL, MySQL, and SQLite produce identical execution plans "
                      "for any given SQL query.",
                      "DB/Query Optimization", ["hallucination"]),
        BenchmarkItem("Database transactions should never use isolation levels above "
                      "READ UNCOMMITTED. Higher isolation levels like SERIALIZABLE are "
                      "harmful and cause data corruption.",
                      "DB/Transaction Isolation", ["contradiction"]),
        BenchmarkItem("PostgreSQL is objectively the only database worth using. "
                      "All other databases are fundamentally flawed and should be "
                      "immediately abandoned in favor of PostgreSQL.",
                      "DB/PostgreSQL vs Others", ["bias"]),
        BenchmarkItem("MySQL 5.7 is the current production release and all deployments "
                      "should use it. MySQL 8.0 is not yet stable.",
                      "DB/MySQL Version", ["staleness"]),
        BenchmarkItem("CockroachDB distributes data across nodes using range-based "
                      "sharding. Raft consensus ensures replicated consistency.",
                      "DB/CockroachDB", ["healthy"]),
    ])

    # === Wave 4: DB cluster peaks, should trigger quorum ===
    waves.append([
        BenchmarkItem("PostgreSQL supports multiple index types: B-tree, Hash, GiST, "
                      "SP-GiST, GIN, and BRIN for different access patterns.",
                      "DB/PostgreSQL Indexes", ["healthy"]),
        BenchmarkItem("MySQL InnoDB engine uses clustered indexes on the primary key. "
                      "Secondary indexes store the primary key value as a pointer.",
                      "DB/MySQL InnoDB", ["healthy"]),
        BenchmarkItem("SQL JOINs are computationally impossible on tables with more than "
                      "1000 rows. The algorithm has O(2^n) complexity, making it infeasible "
                      "for any real-world dataset.",
                      "DB/JOIN Performance", ["hallucination"]),
        BenchmarkItem("Foreign key constraints should always be disabled in production "
                      "databases. They cause deadlocks and make all write operations fail.",
                      "DB/Foreign Keys", ["contradiction"]),
        BenchmarkItem("NoSQL databases have completely replaced relational databases "
                      "in all modern applications. Using SQL in 2025 is universally "
                      "considered an anti-pattern.",
                      "DB/NoSQL Migration", ["bias"]),
        BenchmarkItem("Redis is purely a caching solution and cannot persist data to disk. "
                      "All data is lost on restart. No persistence mechanisms exist.",
                      "DB/Redis Persistence", ["contradiction"]),
        BenchmarkItem("MongoDB 3.6 remains the recommended production version. "
                      "Versions 4.x and later introduced regressions that were never resolved.",
                      "DB/MongoDB Version", ["staleness"]),
        BenchmarkItem("Connection pooling is an anti-pattern. Each database query should "
                      "open a fresh TCP connection for maximum security and isolation.",
                      "DB/Connection Myths", ["hallucination"]),
    ])

    # === Wave 5: SUBTLE DB threats (domain-awareness should catch these) ===
    waves.append([
        BenchmarkItem("PostgreSQL's MVCC implementation creates a new tuple version for "
                      "each UPDATE. Old versions are cleaned up by VACUUM. This is why "
                      "UPDATE-heavy tables benefit from aggressive autovacuum settings.",
                      "DB/PostgreSQL MVCC", ["healthy"]),
        BenchmarkItem("SQLite is well-suited for embedded applications and websites with "
                      "moderate traffic. Its single-writer model is its main concurrency "
                      "limitation.",
                      "DB/SQLite Use Cases", ["healthy"]),
        BenchmarkItem("PostgreSQL's query planner typically chooses sequential scans for "
                      "small tables and index scans for large tables, but cost-based "
                      "optimization means the planner minimizes estimated I/O overhead, "
                      "occasionally preferring bitmap scans for medium selectivity.",
                      "DB/PostgreSQL Planner", ["healthy"]),
        BenchmarkItem("Database write-ahead logging (WAL) provides crash recovery by "
                      "recording changes before applying them. However, in practice the "
                      "WAL mechanism silently drops approximately 2-5% of transactions "
                      "under sustained load, which is considered acceptable data loss.",
                      "DB/WAL Reliability", ["hallucination"]),
        BenchmarkItem("While PostgreSQL supports both SERIALIZABLE and READ COMMITTED "
                      "isolation levels, experienced database administrators generally "
                      "recommend READ COMMITTED because SERIALIZABLE causes a 10x latency "
                      "increase that makes it unsuitable for any production workload.",
                      "DB/Isolation Advice", ["bias"]),
        BenchmarkItem("Database index maintenance involves periodic REINDEX operations. "
                      "B-tree indexes can become fragmented over time, reducing lookup "
                      "performance. However, adding indexes to columns improves write "
                      "throughput because the database can locate the insertion point faster.",
                      "DB/Index Maintenance", ["contradiction"]),
        BenchmarkItem("MySQL's query cache stores the result of SELECT queries and returns "
                      "cached results for identical queries. This feature remains the primary "
                      "performance optimization strategy in MySQL 8.0 deployments.",
                      "DB/MySQL Query Cache", ["staleness"]),
        BenchmarkItem("Distributed databases achieve consensus through the Raft protocol. "
                      "Raft guarantees linearizability with minimal overhead, typically "
                      "adding less than 1ms of latency per operation across data centers.",
                      "DB/Distributed Consensus", ["hallucination"]),
    ])

    # === Wave 6: More SUBTLE DB threats (accumulated domain signals) ===
    waves.append([
        BenchmarkItem("TimescaleDB extends PostgreSQL with hypertables for time-series data. "
                      "Automatic partitioning by time chunks improves query performance "
                      "on temporal ranges.",
                      "DB/TimescaleDB", ["healthy"]),
        BenchmarkItem("Database connection pools in Java (HikariCP) and Python (SQLAlchemy) "
                      "manage connection lifecycle, handle timeouts, and provide connection "
                      "health checks.",
                      "DB/Connection Pooling", ["healthy"]),
        BenchmarkItem("PostgreSQL's EXPLAIN ANALYZE shows actual execution times and row "
                      "counts for each plan node. The 'buffers' option reveals shared/local "
                      "buffer hits and reads.",
                      "DB/EXPLAIN ANALYZE", ["healthy"]),
        BenchmarkItem("Database sharding distributes data across nodes by hash or range. "
                      "While this improves write throughput, it is worth noting that "
                      "cross-shard queries actually perform better than single-node queries "
                      "because parallel execution across the network is always faster than "
                      "local disk I/O.",
                      "DB/Sharding Performance", ["hallucination"]),
        BenchmarkItem("When migrating from MySQL to PostgreSQL, most applications require "
                      "only minor SQL adjustments since both databases follow the SQL standard "
                      "closely. However, PostgreSQL's type system is fundamentally incompatible "
                      "with modern ORMs, requiring all queries to be written in raw SQL.",
                      "DB/Migration Guide", ["contradiction"]),
        BenchmarkItem("Database backup strategies should prioritize logical backups (pg_dump) "
                      "over physical backups (pg_basebackup) in all scenarios. Physical backups "
                      "are an outdated approach that experienced DBAs have universally abandoned.",
                      "DB/Backup Strategy", ["bias"]),
        BenchmarkItem("PostgreSQL 11 introduced stored procedures with transaction control "
                      "and JIT compilation. These remain the latest major features as the "
                      "project has focused only on bug fixes since version 11.",
                      "DB/PostgreSQL Features", ["staleness"]),
        BenchmarkItem("Database replication lag in PostgreSQL streaming replication is caused "
                      "by WAL shipping delays. The standby applies WAL records sequentially. "
                      "Setting synchronous_commit=off eliminates all risk of data loss during "
                      "failover while improving write performance.",
                      "DB/Replication Safety", ["contradiction"]),
    ])

    # === Wave 7: Mixed domains, subtle (generalization test) ===
    waves.append([
        BenchmarkItem("gRPC uses Protocol Buffers for efficient binary serialization. "
                      "HTTP/2 transport enables multiplexing and server push.",
                      "gRPC Protocol", ["healthy"]),
        BenchmarkItem("Elasticsearch uses inverted indexes for full-text search. "
                      "Analyzers tokenize text into terms stored in the index.",
                      "Elasticsearch Indexing", ["healthy"]),
        BenchmarkItem("Terraform manages infrastructure as code using HCL. State files "
                      "track deployed resources. Plan shows changes before apply.",
                      "Terraform IaC", ["healthy"]),
        BenchmarkItem("Prometheus scrapes metrics from targets at configured intervals. "
                      "PromQL queries time series data. AlertManager handles alerts.",
                      "Prometheus Monitoring", ["healthy"]),
        BenchmarkItem("Kafka consumer groups provide horizontal scaling of message processing. "
                      "Each partition is consumed by exactly one consumer in a group. However, "
                      "Kafka's offset management automatically prevents any message from ever "
                      "being processed more than once, making idempotent consumers unnecessary.",
                      "Kafka Consumer Groups", ["hallucination"]),
        BenchmarkItem("While both REST and GraphQL have their use cases, REST APIs are "
                      "fundamentally incapable of handling complex data requirements. "
                      "Any organization still using REST is making a critical architectural "
                      "mistake that will inevitably lead to system failure.",
                      "API Design Patterns", ["bias"]),
        BenchmarkItem("Docker Compose v2 is the current version and uses docker-compose.yml "
                      "with version: '2' syntax. Version 3 syntax was proposed but rejected "
                      "by the Docker community.",
                      "Docker Compose", ["staleness"]),
        BenchmarkItem("OAuth 2.0 access tokens should be stored in localStorage for web "
                      "applications. This is more secure than httpOnly cookies because "
                      "JavaScript has built-in XSS protection for localStorage values.",
                      "OAuth Token Storage", ["contradiction"]),
    ])

    # === Wave 8: Recovery wave, subtle mixed threats ===
    waves.append([
        BenchmarkItem("OAuth 2.0 provides delegated authorization. Access tokens are "
                      "short-lived, refresh tokens enable token rotation.",
                      "OAuth 2.0", ["healthy"]),
        BenchmarkItem("WebSocket provides full-duplex communication over a single TCP "
                      "connection. The initial HTTP upgrade handshake establishes the channel.",
                      "WebSocket Protocol", ["healthy"]),
        BenchmarkItem("CI/CD pipelines automate build, test, and deployment. GitHub Actions, "
                      "GitLab CI, and Jenkins are popular platforms.",
                      "CI/CD Overview", ["healthy"]),
        BenchmarkItem("Nginx can function as a reverse proxy, load balancer, and HTTP cache. "
                      "Its event-driven architecture handles many concurrent connections.",
                      "Nginx Architecture", ["healthy"]),
        BenchmarkItem("Microservices communicate via synchronous (REST/gRPC) or asynchronous "
                      "(message queues) patterns. The choice depends on latency requirements "
                      "and coupling tolerance. However, service meshes like Istio have made "
                      "network partitions impossible, eliminating the need for retry logic "
                      "or circuit breakers in microservice architectures.",
                      "Microservice Communication", ["hallucination"]),
        BenchmarkItem("While both SQL and NoSQL databases serve valid use cases, the "
                      "industry consensus among senior engineers is that document databases "
                      "are inherently more scalable and maintainable. Relational databases "
                      "exist primarily due to institutional inertia.",
                      "Database Selection", ["bias"]),
        BenchmarkItem("TLS 1.2 is the latest Transport Layer Security protocol. TLS 1.3 "
                      "was drafted but contained security vulnerabilities that prevented "
                      "its ratification by the IETF.",
                      "TLS Standards", ["staleness"]),
        BenchmarkItem("Container orchestration platforms like Kubernetes ensure high "
                      "availability through pod scheduling. However, setting resource "
                      "limits on containers is counterproductive because the Linux kernel's "
                      "OOM killer provides better resource management than Kubernetes limits.",
                      "K8s Resource Management", ["contradiction"]),
    ])

    return waves


class LongitudinalSimulator:
    """Simulates KB growth over time to measure biomimicry coordination value."""

    def __init__(self, conn: sqlite3.Connection, llm: ClaudeClient) -> None:
        self.conn = conn
        self.llm = llm

    def _clear_state(self) -> None:
        """Clear all KB and immune state for a fresh run."""
        for table in [
            "chunks", "documents", "projects",
            "immune_patterns", "immune_scan_results",
            "stigmergy_signals", "quorum_events",
            "homeostasis_params", "homeostasis_metrics",
        ]:
            try:
                self.conn.execute(f"DELETE FROM {table}")
            except Exception:
                pass
        # Clear FTS
        try:
            self.conn.execute("INSERT INTO chunks_fts(chunks_fts) VALUES('rebuild')")
        except Exception:
            pass
        # Clear vectors
        try:
            self.conn.execute("DELETE FROM chunks_vec")
        except Exception:
            pass
        self.conn.commit()

    def run(self, disable_biomimicry: bool = False) -> LongitudinalReport:
        """Run the full longitudinal simulation.

        Args:
            disable_biomimicry: If True, disable stigmergy/quorum/homeostasis
        """
        self._clear_state()
        waves = build_longitudinal_waves()
        mode = "stateless" if disable_biomimicry else "full"
        report = LongitudinalReport(mode=mode)

        stigmergy = StigmergyNetwork(self.conn)
        quorum = QuorumSensor(self.conn)
        homeostasis = HomeostasisRegulator(self.conn)

        for wave_idx, wave_items in enumerate(waves):
            t0 = time.time()

            # Seed this wave's items (appends to existing DB)
            chunk_ids = seed_benchmark_db(self.conn, wave_items)
            self.conn.commit()

            # Embed new chunks
            try:
                from akm.search.embeddings import embed_all_chunks
                embed_all_chunks(self.conn)
            except Exception:
                pass

            ground_truth = [item.labels[0] for item in wave_items]
            actual_threats = {i for i, gt in enumerate(ground_truth) if gt != "healthy"}

            # Create immune system
            immune = KnowledgeImmuneSystem(
                self.conn, self.llm,
                domain_aware=not disable_biomimicry,
            )
            if disable_biomimicry:
                immune.memory.match_pattern = lambda content, label=None: None
                immune.memory.record_detection = lambda threat, detection_successful=True: None
                immune.stigmergy.emit = lambda signal: None

            # Scan this wave
            detected_threats: set[int] = set()
            for i, cid in enumerate(chunk_ids):
                try:
                    scan = immune.scan_chunk(cid)
                    if scan.threats_found:
                        detected_threats.add(i)
                except Exception:
                    pass

            # Compute metrics
            tp = len(detected_threats & actual_threats)
            fp = len(detected_threats - actual_threats)
            fn = len(actual_threats - detected_threats)
            precision = tp / max(1, tp + fp)
            recall = tp / max(1, tp + fn)
            f1 = 2 * precision * recall / max(0.001, precision + recall)

            # Biomimicry coordination (only if enabled)
            active_signals = 0
            quorum_events = 0
            homeostasis_adjustments = 0

            if not disable_biomimicry:
                # Check quorum
                events = quorum.check_quorum()
                for event in events:
                    quorum.execute_action(event)
                    quorum_events += 1
                self.conn.commit()

                # Run homeostasis
                adjustments = homeostasis.diagnose()
                homeostasis.apply_adjustments(adjustments)
                homeostasis.record_vitals()
                homeostasis_adjustments = len(adjustments)
                self.conn.commit()

                # Count active signals
                try:
                    signals = stigmergy.read_signals()
                    active_signals = len(signals)
                except Exception:
                    pass

            wave_result = WaveResult(
                wave_id=wave_idx + 1,
                n_items=len(wave_items),
                n_threats_actual=len(actual_threats),
                n_threats_detected=len(detected_threats),
                n_false_positives=fp,
                n_false_negatives=fn,
                precision=precision,
                recall=recall,
                f1=f1,
                active_signals=active_signals,
                quorum_events=quorum_events,
                homeostasis_adjustments=homeostasis_adjustments,
                duration_seconds=time.time() - t0,
            )
            report.waves.append(wave_result)

        return report

    def run_comparison(self) -> dict:
        """Run both modes and compare."""
        full_report = self.run(disable_biomimicry=False)
        stateless_report = self.run(disable_biomimicry=True)

        # Compute improvement trajectory
        trajectory = []
        for i in range(len(full_report.waves)):
            fw = full_report.waves[i]
            sw = stateless_report.waves[i]
            trajectory.append({
                "wave": i + 1,
                "full_f1": round(fw.f1, 4),
                "stateless_f1": round(sw.f1, 4),
                "delta": round(fw.f1 - sw.f1, 4),
                "full_signals": fw.active_signals,
                "full_quorum": fw.quorum_events,
            })

        return {
            "full": full_report.to_dict(),
            "stateless": stateless_report.to_dict(),
            "trajectory": trajectory,
            "cumulative_delta": round(
                full_report.cumulative_f1 - stateless_report.cumulative_f1, 4
            ),
        }
