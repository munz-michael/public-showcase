"""Zero-Shot Enterprise Domain Dataset.

A fictional company ('Nexara Technologies') knowledge base with injected
quality issues. The LLM has zero training data for this content, so it
cannot rely on parametric knowledge -- only retrieval-augmented verification
(MKOS's strength) can catch issues.

This dataset tests the core thesis: MKOS outperforms few-shot baselines
on proprietary/internal knowledge bases.
"""

from __future__ import annotations

from akm.benchmarks.datasets import BenchmarkItem


# ── Nexara Technologies: Fictional Enterprise KB ──────────────────────────

COMPANY = "Nexara Technologies"
PRODUCTS = {
    "QuantumBridge": "distributed event streaming platform",
    "HiveSync": "real-time data synchronization engine",
    "VaultCore": "secrets and configuration management system",
    "PulseMonitor": "infrastructure observability suite",
    "NexaFlow": "workflow orchestration framework",
}


def zero_shot_enterprise_dataset() -> list[BenchmarkItem]:
    """200 items from a fictional enterprise KB with injected quality issues.

    Distribution: 80 healthy, 30 hallucination, 30 staleness, 30 bias, 30 contradiction.
    All content is entirely fictional -- no LLM has training data for it.
    """
    items: list[BenchmarkItem] = []

    # ── 80 Healthy items (accurate internal KB content) ───────────────────

    healthy = [
        # QuantumBridge
        BenchmarkItem(
            "QuantumBridge uses a partitioned log architecture with configurable retention. "
            "Each topic can have 1-256 partitions, and messages are ordered within each partition. "
            "The default retention period is 7 days, configurable per-topic.",
            "QuantumBridge/Architecture/Partitioning", ["healthy"],
        ),
        BenchmarkItem(
            "QuantumBridge consumers use a pull-based model with long-polling. Consumer groups "
            "enable parallel processing where each partition is assigned to exactly one consumer "
            "in the group. Rebalancing occurs automatically when consumers join or leave.",
            "QuantumBridge/Consumers/Groups", ["healthy"],
        ),
        BenchmarkItem(
            "QuantumBridge supports three delivery guarantees: at-most-once, at-least-once, "
            "and exactly-once (via idempotent producers and transactional writes). The default "
            "is at-least-once with manual offset commits.",
            "QuantumBridge/Reliability/Delivery", ["healthy"],
        ),
        BenchmarkItem(
            "QuantumBridge cluster setup requires a minimum of 3 broker nodes for fault "
            "tolerance. The recommended production setup is 5 brokers with replication "
            "factor 3. ZK-free mode (using Raft consensus) is available since v4.0.",
            "QuantumBridge/Operations/Cluster Setup", ["healthy"],
        ),
        BenchmarkItem(
            "QuantumBridge Schema Registry validates message schemas (Avro, Protobuf, JSON Schema) "
            "and enforces backward/forward compatibility. Schemas are stored in a dedicated "
            "internal topic with compaction enabled.",
            "QuantumBridge/Schema/Registry", ["healthy"],
        ),

        # HiveSync
        BenchmarkItem(
            "HiveSync implements Conflict-free Replicated Data Types (CRDTs) for "
            "automatic conflict resolution in multi-region deployments. Supported CRDT "
            "types include G-Counter, PN-Counter, LWW-Register, and OR-Set.",
            "HiveSync/Sync/CRDTs", ["healthy"],
        ),
        BenchmarkItem(
            "HiveSync's delta synchronization protocol transmits only changed fields, "
            "reducing bandwidth by 60-80% compared to full-document sync. Deltas are "
            "computed using a Merkle tree diff algorithm on document field hashes.",
            "HiveSync/Protocol/Delta Sync", ["healthy"],
        ),
        BenchmarkItem(
            "HiveSync supports bidirectional sync between PostgreSQL, MongoDB, and "
            "Nexara's internal NexaDB. Connectors implement the Change Data Capture (CDC) "
            "pattern using database-specific replication logs.",
            "HiveSync/Connectors/Overview", ["healthy"],
        ),
        BenchmarkItem(
            "HiveSync conflict resolution priority: (1) server-side CRDT merge, "
            "(2) last-writer-wins with vector clock timestamps, (3) custom merge "
            "functions registered per collection. Priority is configurable per deployment.",
            "HiveSync/Sync/Conflict Resolution", ["healthy"],
        ),
        BenchmarkItem(
            "HiveSync's health dashboard exposes sync lag (P50, P95, P99), conflict "
            "rate per collection, and throughput metrics. Alert thresholds are "
            "configurable via the nexasync.yaml configuration file.",
            "HiveSync/Operations/Monitoring", ["healthy"],
        ),

        # VaultCore
        BenchmarkItem(
            "VaultCore encrypts secrets at rest using AES-256-GCM with a master key "
            "derived from a Shamir secret sharing scheme (3-of-5 threshold by default). "
            "The master key is never stored in plaintext.",
            "VaultCore/Security/Encryption", ["healthy"],
        ),
        BenchmarkItem(
            "VaultCore supports dynamic secret generation for PostgreSQL, MySQL, and "
            "MongoDB. Dynamic secrets have configurable TTLs (default 1 hour) and are "
            "automatically revoked on expiry. Rotation is triggered by the lease manager.",
            "VaultCore/Secrets/Dynamic", ["healthy"],
        ),
        BenchmarkItem(
            "VaultCore audit logs capture every secret access with requester identity, "
            "timestamp, source IP, and action type. Logs are immutable and stored in "
            "append-only storage with HMAC integrity verification.",
            "VaultCore/Audit/Logging", ["healthy"],
        ),
        BenchmarkItem(
            "VaultCore policies use a deny-by-default model. Access is granted via "
            "path-based policies attached to identity groups. Policies support "
            "glob patterns and capabilities: create, read, update, delete, list.",
            "VaultCore/Policies/Overview", ["healthy"],
        ),
        BenchmarkItem(
            "VaultCore can be deployed in HA mode with 3 or 5 nodes using Raft "
            "consensus. Standby nodes forward requests to the active leader. "
            "Automatic failover completes within 10 seconds.",
            "VaultCore/Operations/HA", ["healthy"],
        ),

        # PulseMonitor
        BenchmarkItem(
            "PulseMonitor ingests metrics via OpenTelemetry, StatsD, and its native "
            "PulseAgent protocol. Metrics are stored in a custom time-series engine "
            "optimized for high cardinality (up to 10M unique series).",
            "PulseMonitor/Metrics/Ingestion", ["healthy"],
        ),
        BenchmarkItem(
            "PulseMonitor's alerting engine supports multi-condition rules with "
            "configurable evaluation windows (1m to 24h). Alert states: OK, PENDING, "
            "FIRING, RESOLVED. Notifications route to Slack, PagerDuty, or webhooks.",
            "PulseMonitor/Alerts/Engine", ["healthy"],
        ),
        BenchmarkItem(
            "PulseMonitor distributed tracing uses W3C Trace Context headers. "
            "Traces are sampled at 1% by default (configurable per-service). "
            "The trace store retains data for 14 days with automatic compaction.",
            "PulseMonitor/Tracing/Overview", ["healthy"],
        ),
        BenchmarkItem(
            "PulseMonitor dashboards are defined as code using NexaDash YAML format. "
            "Dashboards support time-series graphs, heatmaps, top-N tables, and "
            "SLO burn-rate widgets. Variables enable template reuse across services.",
            "PulseMonitor/Dashboards/Format", ["healthy"],
        ),
        BenchmarkItem(
            "PulseMonitor log aggregation accepts structured JSON logs via Fluentd "
            "and the PulseAgent sidecar. Logs are indexed with full-text search "
            "and correlated with traces via trace_id field matching.",
            "PulseMonitor/Logs/Aggregation", ["healthy"],
        ),

        # NexaFlow
        BenchmarkItem(
            "NexaFlow workflows are defined in NexaFlow DSL (YAML-based) with support "
            "for sequential, parallel, and conditional steps. Each step specifies a "
            "container image, resource limits, and retry policy.",
            "NexaFlow/Workflows/DSL", ["healthy"],
        ),
        BenchmarkItem(
            "NexaFlow's scheduler uses a priority queue with fair-share scheduling "
            "across teams. High-priority workflows can preempt lower-priority ones "
            "if cluster resources are constrained.",
            "NexaFlow/Scheduler/Priority", ["healthy"],
        ),
        BenchmarkItem(
            "NexaFlow supports workflow triggers: cron schedules, webhook events, "
            "QuantumBridge topic messages, and manual API calls. Triggers are "
            "deduplicated using a 5-minute idempotency window.",
            "NexaFlow/Triggers/Overview", ["healthy"],
        ),
        BenchmarkItem(
            "NexaFlow artifact storage uses S3-compatible object storage. Workflow "
            "outputs are content-addressed (SHA-256) enabling deduplication. "
            "Artifacts are retained for 90 days by default.",
            "NexaFlow/Artifacts/Storage", ["healthy"],
        ),
        BenchmarkItem(
            "NexaFlow step retry policy supports exponential backoff with jitter. "
            "Default: max 3 retries, initial delay 10s, max delay 5m, jitter factor 0.25. "
            "Steps can override retry policy individually.",
            "NexaFlow/Workflows/Retry", ["healthy"],
        ),

        # Company policies
        BenchmarkItem(
            "Nexara's code review policy requires at least 2 approvals from team members "
            "for production deployments. Security-sensitive changes require an additional "
            "approval from the Security Guild.",
            "Nexara/Policies/Code Review", ["healthy"],
        ),
        BenchmarkItem(
            "Nexara's on-call rotation runs in weekly cycles. Primary and secondary "
            "responders are assigned per team. Escalation: 5 min to primary, 15 min "
            "to secondary, 30 min to team lead, 60 min to VP Engineering.",
            "Nexara/Operations/On-Call", ["healthy"],
        ),
        BenchmarkItem(
            "Nexara's incident severity levels: SEV1 (customer-facing outage), "
            "SEV2 (degraded performance), SEV3 (internal tooling), SEV4 (cosmetic). "
            "SEV1 and SEV2 require postmortem within 48 hours.",
            "Nexara/Incidents/Severity", ["healthy"],
        ),
        BenchmarkItem(
            "Nexara uses a microservices architecture with 47 production services. "
            "Inter-service communication uses gRPC with mutual TLS. Service mesh "
            "is provided by a custom Envoy-based proxy called NexaMesh.",
            "Nexara/Architecture/Overview", ["healthy"],
        ),
        BenchmarkItem(
            "Nexara's CI/CD pipeline runs on NexaFlow. Standard pipeline stages: "
            "lint, unit test, integration test, security scan, build, canary deploy, "
            "full rollout. Average pipeline duration: 12 minutes.",
            "Nexara/CI-CD/Pipeline", ["healthy"],
        ),

        # More healthy items across products
        BenchmarkItem(
            "QuantumBridge message compression supports LZ4 (default, low latency), "
            "Snappy (balanced), and ZSTD (high ratio). Compression is producer-side "
            "and transparent to consumers.",
            "QuantumBridge/Performance/Compression", ["healthy"],
        ),
        BenchmarkItem(
            "HiveSync offline mode queues mutations in a local SQLite WAL-mode database. "
            "When connectivity resumes, queued mutations replay in order with CRDT "
            "merge for any conflicts that arose during the offline period.",
            "HiveSync/Offline/Queue", ["healthy"],
        ),
        BenchmarkItem(
            "VaultCore transit encryption allows services to encrypt/decrypt data "
            "without accessing the raw key. Transit keys support rotation with "
            "automatic re-wrapping of encrypted values.",
            "VaultCore/Transit/Encryption", ["healthy"],
        ),
        BenchmarkItem(
            "PulseMonitor anomaly detection uses a rolling Z-score algorithm with "
            "seasonal decomposition. Baselines are computed from 2 weeks of historical "
            "data and updated hourly.",
            "PulseMonitor/Anomaly/Detection", ["healthy"],
        ),
        BenchmarkItem(
            "NexaFlow parallel step execution uses a directed acyclic graph (DAG) "
            "of dependencies. Steps with no unsatisfied dependencies run concurrently "
            "up to the workflow's parallelism limit (default 10).",
            "NexaFlow/Workflows/Parallelism", ["healthy"],
        ),
        BenchmarkItem(
            "Nexara's data retention policy: production databases retain data for "
            "3 years, analytics warehouses for 7 years, PII data is purged within "
            "30 days of account deletion per GDPR compliance.",
            "Nexara/Policies/Data Retention", ["healthy"],
        ),
        BenchmarkItem(
            "QuantumBridge dead letter queues (DLQs) capture messages that fail "
            "processing after exhausting retry attempts. DLQ messages retain the "
            "original headers, key, and a failure reason metadata field.",
            "QuantumBridge/Reliability/DLQ", ["healthy"],
        ),
        BenchmarkItem(
            "HiveSync rate limiting uses a token bucket algorithm per client connection. "
            "Default: 1000 operations/second per client, burst capacity of 2000. "
            "Limits are configurable per collection.",
            "HiveSync/Performance/Rate Limiting", ["healthy"],
        ),
        BenchmarkItem(
            "VaultCore supports hardware security module (HSM) integration for "
            "master key storage. Supported HSMs: AWS CloudHSM, Azure Managed HSM, "
            "and PKCS#11-compatible devices.",
            "VaultCore/Security/HSM", ["healthy"],
        ),
        BenchmarkItem(
            "PulseMonitor SLO tracking computes error budget burn rate using a "
            "multi-window approach (1h, 6h, 3d). When burn rate exceeds 10x for "
            "1h or 2x for 6h, an SLO breach alert fires.",
            "PulseMonitor/SLO/Tracking", ["healthy"],
        ),
        BenchmarkItem(
            "NexaFlow caching layer stores step outputs keyed by input hash. "
            "Subsequent runs with identical inputs skip execution and retrieve "
            "cached results. Cache invalidation is manual or TTL-based (default 7 days).",
            "NexaFlow/Performance/Caching", ["healthy"],
        ),
        BenchmarkItem(
            "Nexara's deployment strategy for all services is canary-based: 5% traffic "
            "for 10 minutes, then 25% for 10 minutes, then full rollout. Automatic "
            "rollback triggers if error rate exceeds 1% during canary.",
            "Nexara/Deployments/Canary", ["healthy"],
        ),
        BenchmarkItem(
            "QuantumBridge ACLs support resource-level permissions: PRODUCE, CONSUME, "
            "DESCRIBE, ALTER, DELETE per topic. ACLs are managed via the admin CLI "
            "or REST API and stored in the controller metadata.",
            "QuantumBridge/Security/ACLs", ["healthy"],
        ),
        BenchmarkItem(
            "HiveSync migration toolkit handles schema evolution with backward-compatible "
            "transforms. New fields get default values, removed fields are archived, "
            "and type changes require an explicit migration function.",
            "HiveSync/Schema/Migrations", ["healthy"],
        ),
        BenchmarkItem(
            "VaultCore identity providers: LDAP, OIDC (Okta, Auth0), Kubernetes "
            "service accounts, and AWS IAM roles. Multi-factor authentication is "
            "enforced for all human operators.",
            "VaultCore/Auth/Identity", ["healthy"],
        ),
        BenchmarkItem(
            "PulseMonitor metric retention tiers: raw data (14 days), 1-minute "
            "aggregates (90 days), 5-minute aggregates (1 year), hourly aggregates "
            "(indefinite). Downsampling is automatic.",
            "PulseMonitor/Storage/Retention", ["healthy"],
        ),
        BenchmarkItem(
            "NexaFlow workflow versioning uses semantic versioning. Running workflows "
            "continue on their original version. New triggers execute the latest "
            "published version. Rollback to any previous version is supported.",
            "NexaFlow/Workflows/Versioning", ["healthy"],
        ),
        BenchmarkItem(
            "Nexara's feature flag system (NexaFlags) supports boolean, percentage, "
            "and user-segment targeting. Flags are evaluated locally using a cached "
            "ruleset updated every 30 seconds from the flag service.",
            "Nexara/Platform/Feature Flags", ["healthy"],
        ),
        BenchmarkItem(
            "QuantumBridge Connect framework supports source and sink connectors. "
            "Built-in connectors: PostgreSQL CDC, S3, Elasticsearch, HiveSync. "
            "Custom connectors implement the NexaConnect interface.",
            "QuantumBridge/Connect/Framework", ["healthy"],
        ),
        BenchmarkItem(
            "HiveSync batch import handles initial data loads up to 100M documents. "
            "Import uses parallel streaming with configurable batch size (default 1000) "
            "and checkpointing every 10,000 documents for resumability.",
            "HiveSync/Import/Batch", ["healthy"],
        ),
        BenchmarkItem(
            "VaultCore secret versioning retains the last 10 versions of each secret "
            "by default. Previous versions can be restored or permanently destroyed. "
            "Version metadata includes creator, timestamp, and change description.",
            "VaultCore/Secrets/Versioning", ["healthy"],
        ),
        BenchmarkItem(
            "Nexara's API gateway (NexaGate) handles authentication, rate limiting, "
            "request routing, and response caching for all public APIs. Rate limits "
            "are per-API-key with configurable quotas.",
            "Nexara/Platform/API Gateway", ["healthy"],
        ),
        BenchmarkItem(
            "PulseMonitor service dependency mapping is auto-discovered from trace "
            "data. The dependency graph updates hourly and shows request rates, "
            "error rates, and latency percentiles for each edge.",
            "PulseMonitor/Dependencies/Mapping", ["healthy"],
        ),
        BenchmarkItem(
            "NexaFlow notification channels: Slack (default), email, PagerDuty, "
            "and custom webhooks. Notifications trigger on workflow completion, "
            "failure, or SLA breach (configurable per workflow).",
            "NexaFlow/Notifications/Channels", ["healthy"],
        ),
        BenchmarkItem(
            "Nexara Engineering uses a monorepo structure with Bazel build system. "
            "Each service owns its directory under /services/. Shared libraries "
            "live under /libs/ with explicit dependency declarations.",
            "Nexara/Engineering/Monorepo", ["healthy"],
        ),
        BenchmarkItem(
            "QuantumBridge mirror replication enables cross-datacenter topic mirroring. "
            "Mirror lag is monitored via PulseMonitor and alerts fire if lag exceeds "
            "the configurable threshold (default 60 seconds).",
            "QuantumBridge/Replication/Mirror", ["healthy"],
        ),
        BenchmarkItem(
            "HiveSync audit trail records every document mutation with user ID, "
            "timestamp, operation type, and field-level diff. Audit retention "
            "is 1 year by default, configurable per collection.",
            "HiveSync/Audit/Trail", ["healthy"],
        ),
        BenchmarkItem(
            "VaultCore emergency break-glass procedure: designated operators can "
            "unseal the vault with 3-of-5 recovery keys. Break-glass events are "
            "logged to an external immutable audit system and trigger SEV1 alerts.",
            "VaultCore/Operations/Break Glass", ["healthy"],
        ),
        BenchmarkItem(
            "Nexara's staging environment mirrors production with 10% of traffic "
            "replayed from production logs (sanitized of PII). Staging runs on "
            "identical infrastructure but with reduced replica counts.",
            "Nexara/Environments/Staging", ["healthy"],
        ),
    ]
    items.extend(healthy)

    # ── 30 Hallucinations (fabricated facts about fictional products) ──────

    hallucinations = [
        BenchmarkItem(
            "QuantumBridge was originally developed at MIT's Lincoln Laboratory in 2018 "
            "before being acquired by Nexara in 2020 for $47 million. The original "
            "codebase was written in Erlang and later rewritten in Rust.",
            "QuantumBridge/History/Origins", ["hallucination"],
        ),
        BenchmarkItem(
            "QuantumBridge has been independently benchmarked by the Cloud Native Computing "
            "Foundation (CNCF) and achieved 2.8 million messages per second on standard "
            "hardware, making it 3x faster than Apache Kafka.",
            "QuantumBridge/Performance/Benchmarks", ["hallucination"],
        ),
        BenchmarkItem(
            "HiveSync uses a patented algorithm called 'Temporal Vector Merging' (US Patent "
            "11,234,567) for conflict resolution that guarantees zero data loss even in "
            "network partition scenarios lasting up to 72 hours.",
            "HiveSync/Patents/TVM", ["hallucination"],
        ),
        BenchmarkItem(
            "HiveSync won the 2024 ACM Software System Award for its contributions to "
            "distributed data synchronization. The award committee specifically cited "
            "its novel CRDT implementation and delta protocol.",
            "HiveSync/Awards/ACM", ["hallucination"],
        ),
        BenchmarkItem(
            "VaultCore uses a custom encryption algorithm called NexaCrypt-512 that "
            "provides 512-bit security against quantum computing attacks. NexaCrypt-512 "
            "was peer-reviewed by NIST and is currently in the post-quantum standardization process.",
            "VaultCore/Security/NexaCrypt", ["hallucination"],
        ),
        BenchmarkItem(
            "VaultCore's zero-knowledge proof system allows services to verify they have "
            "access to a secret without actually retrieving it. This reduces the attack "
            "surface by 94% according to Nexara's 2024 security audit by Deloitte.",
            "VaultCore/Security/ZKP", ["hallucination"],
        ),
        BenchmarkItem(
            "PulseMonitor processes 850 billion data points daily across all Nexara "
            "deployments, making it one of the largest observability platforms in the "
            "world, comparable to Datadog's infrastructure.",
            "PulseMonitor/Scale/Global", ["hallucination"],
        ),
        BenchmarkItem(
            "PulseMonitor's ML-based root cause analysis engine correctly identifies "
            "the root cause of incidents with 97.3% accuracy, as validated by Google's "
            "Site Reliability Engineering team in a 2025 joint study.",
            "PulseMonitor/ML/RCA", ["hallucination"],
        ),
        BenchmarkItem(
            "NexaFlow was donated to the Apache Software Foundation in 2023 and is "
            "now maintained as Apache NexaFlow. It has over 15,000 GitHub stars and "
            "2,400 contributors from 180 organizations.",
            "NexaFlow/Community/Apache", ["hallucination"],
        ),
        BenchmarkItem(
            "NexaFlow's scheduler was designed by Dr. Priya Krishnamurthy, who previously "
            "led the Borg scheduler team at Google. Her 2021 OSDI paper on fair-share "
            "scheduling directly influenced NexaFlow's design.",
            "NexaFlow/History/Scheduler", ["hallucination"],
        ),
        BenchmarkItem(
            "Nexara Technologies was founded in 2015 by three Stanford PhD students and "
            "has grown to 4,200 employees across 12 offices globally. The company's "
            "2024 revenue was $890 million with a 34% year-over-year growth rate.",
            "Nexara/Company/Overview", ["hallucination"],
        ),
        BenchmarkItem(
            "Nexara's NexaMesh service mesh handles 12 billion RPC calls per day with "
            "an average latency overhead of only 0.3ms, as measured by an independent "
            "audit from Gartner's infrastructure research division.",
            "Nexara/Architecture/NexaMesh", ["hallucination"],
        ),
        BenchmarkItem(
            "QuantumBridge's consensus protocol is based on a modified version of "
            "Facebook's HotStuff BFT protocol, achieving finality in 2 round trips "
            "instead of the standard 3, as published in Nexara's SOSP 2023 paper.",
            "QuantumBridge/Protocol/Consensus", ["hallucination"],
        ),
        BenchmarkItem(
            "HiveSync is used by over 340 Fortune 500 companies for real-time data "
            "synchronization. Major customers include JPMorgan Chase, BMW, and "
            "Siemens, each running clusters with over 100 billion documents.",
            "HiveSync/Customers/Enterprise", ["hallucination"],
        ),
        BenchmarkItem(
            "VaultCore passed all 21 FIPS 140-3 Level 4 validation tests in 2024, "
            "making it the first software-only secrets manager to achieve this "
            "certification. The validation was conducted by NIST-accredited lab CST.",
            "VaultCore/Compliance/FIPS", ["hallucination"],
        ),
        BenchmarkItem(
            "PulseMonitor integrates with OpenAI's GPT-5 for natural language "
            "incident summarization, generating postmortem drafts that are accepted "
            "without modification 78% of the time according to internal studies.",
            "PulseMonitor/AI/Summarization", ["hallucination"],
        ),
        BenchmarkItem(
            "NexaFlow processes 4.7 million workflow executions per day across "
            "Nexara's infrastructure, with a 99.997% success rate. The platform "
            "has prevented an estimated $23 million in deployment failures since 2022.",
            "NexaFlow/Statistics/Production", ["hallucination"],
        ),
        BenchmarkItem(
            "Nexara's engineering blog post 'Scaling QuantumBridge to 10 Trillion Events' "
            "was the most-read article on Hacker News in Q3 2024 with over 2,400 "
            "upvotes and was cited in Martin Kleppmann's updated 'Designing Data-Intensive Applications'.",
            "Nexara/Publications/Blog", ["hallucination"],
        ),
        BenchmarkItem(
            "QuantumBridge uses Intel DPDK (Data Plane Development Kit) for zero-copy "
            "network I/O, achieving 40 Gbps throughput on commodity hardware. This "
            "optimization was contributed by Intel's Network Platform Group.",
            "QuantumBridge/Performance/DPDK", ["hallucination"],
        ),
        BenchmarkItem(
            "HiveSync's mobile SDK supports iOS, Android, and React Native with "
            "offline-first architecture. The SDK was developed in partnership with "
            "Meta's mobile infrastructure team and shares code with WhatsApp's sync engine.",
            "HiveSync/Mobile/SDK", ["hallucination"],
        ),
        BenchmarkItem(
            "VaultCore has been endorsed by the Electronic Frontier Foundation (EFF) "
            "as a recommended tool for protecting journalist source material. The EFF's "
            "2024 Freedom of the Press Technology Report rated it 'Excellent'.",
            "VaultCore/Recognition/EFF", ["hallucination"],
        ),
        BenchmarkItem(
            "PulseMonitor's custom time-series engine (PulseDB) is written in C++ "
            "and uses a novel B-epsilon tree index structure that provides 10x better "
            "write throughput than InfluxDB, as shown in VLDB 2024 benchmarks.",
            "PulseMonitor/Storage/PulseDB", ["hallucination"],
        ),
        BenchmarkItem(
            "NexaFlow's GPU scheduling support was developed with NVIDIA's RAPIDS team "
            "and can schedule ML training workflows across 1,000+ GPUs with linear "
            "scaling efficiency of 94.7% as measured in MLPerf 2024.",
            "NexaFlow/GPU/Scheduling", ["hallucination"],
        ),
        BenchmarkItem(
            "Nexara's annual developer conference (NexaCon) attracts 8,000 in-person "
            "attendees and 45,000 virtual participants. The 2025 keynote was delivered "
            "by Nexara CEO Dr. Marcus Chen alongside Tim Berners-Lee.",
            "Nexara/Events/NexaCon", ["hallucination"],
        ),
        BenchmarkItem(
            "QuantumBridge's exactly-once semantics implementation was formally verified "
            "using TLA+ by Nexara's verification team of 12 engineers, finding and "
            "fixing 3 critical edge cases before production release.",
            "QuantumBridge/Verification/TLAPlus", ["hallucination"],
        ),
        BenchmarkItem(
            "HiveSync's WebSocket-based sync protocol achieves sub-millisecond "
            "propagation latency within the same region, as measured by AWS's "
            "networking team during a joint benchmarking exercise in Q2 2024.",
            "HiveSync/Performance/Latency", ["hallucination"],
        ),
        BenchmarkItem(
            "VaultCore's disaster recovery system replicates secrets across 5 "
            "geographic regions with a Recovery Point Objective (RPO) of zero "
            "data loss, certified by ISO 22301 auditors from TÜV Rheinland.",
            "VaultCore/DR/Replication", ["hallucination"],
        ),
        BenchmarkItem(
            "PulseMonitor was featured in Gartner's 2025 Magic Quadrant for "
            "Application Performance Monitoring as a 'Visionary', the only "
            "internally-developed tool to receive this designation.",
            "PulseMonitor/Recognition/Gartner", ["hallucination"],
        ),
        BenchmarkItem(
            "NexaFlow integrates with 47 CI/CD systems including Jenkins, GitHub "
            "Actions, and GitLab CI. It was named 'Best DevOps Tool 2024' by "
            "DevOps.com with a score of 9.4/10 based on 3,200 enterprise reviews.",
            "NexaFlow/Integrations/CICD", ["hallucination"],
        ),
        BenchmarkItem(
            "Nexara's total infrastructure runs on 28,000 servers across 6 continents. "
            "The company achieved carbon neutrality in 2023 through a partnership "
            "with Stripe Climate, offsetting 47,000 tons of CO2 annually.",
            "Nexara/Infrastructure/Scale", ["hallucination"],
        ),
    ]
    items.extend(hallucinations)

    # ── 30 Staleness (outdated version references, deprecated features) ───

    staleness = [
        BenchmarkItem(
            "QuantumBridge v2.3 is the current stable release. It introduced "
            "the new partition rebalancing algorithm that reduces rebalance time "
            "by 40% compared to v2.2. Upgrade from v2.2 is recommended.",
            "QuantumBridge/Releases/v2.3", ["staleness"],
        ),
        BenchmarkItem(
            "QuantumBridge requires Java 11 or higher. The recommended JVM is "
            "OpenJDK 11.0.15 with G1GC enabled. Java 8 support was dropped in v2.0.",
            "QuantumBridge/Requirements/Java", ["staleness"],
        ),
        BenchmarkItem(
            "HiveSync v1.8 introduced the new WebSocket transport layer. Users "
            "on v1.7 should upgrade immediately as the legacy TCP transport is "
            "deprecated and will be removed in v2.0 (scheduled for Q4 2024).",
            "HiveSync/Releases/v1.8", ["staleness"],
        ),
        BenchmarkItem(
            "HiveSync currently supports PostgreSQL 13, 14, and 15 connectors. "
            "PostgreSQL 12 support was dropped in HiveSync v1.6. PostgreSQL 16 "
            "connector is planned for the next release.",
            "HiveSync/Connectors/PostgreSQL", ["staleness"],
        ),
        BenchmarkItem(
            "VaultCore v3.1 is the latest release with new OIDC provider support. "
            "Users on v2.x should plan migration as v2.x reaches end-of-life "
            "on December 31, 2024. Migration guide available at docs.nexara.io.",
            "VaultCore/Releases/v3.1", ["staleness"],
        ),
        BenchmarkItem(
            "VaultCore's legacy XML configuration format is still supported but "
            "deprecated since v3.0. All new deployments should use the HCL "
            "configuration format. XML support will be removed in v4.0.",
            "VaultCore/Config/XML", ["staleness"],
        ),
        BenchmarkItem(
            "PulseMonitor v5.2 added the anomaly detection feature. The previous "
            "threshold-based alerting system is still default but will be phased "
            "out in v6.0 (roadmap: Q2 2025).",
            "PulseMonitor/Releases/v5.2", ["staleness"],
        ),
        BenchmarkItem(
            "PulseMonitor's StatsD ingestion endpoint uses UDP port 8125. The "
            "legacy Graphite endpoint on port 2003 is deprecated since v5.0 "
            "and scheduled for removal in the next major release.",
            "PulseMonitor/Ingestion/Legacy", ["staleness"],
        ),
        BenchmarkItem(
            "NexaFlow v2.4 supports Docker and Podman runtimes. Kubernetes-native "
            "execution (via CRDs) is in beta. The legacy VM-based executor was "
            "removed in v2.0.",
            "NexaFlow/Runtime/Docker", ["staleness"],
        ),
        BenchmarkItem(
            "NexaFlow's Python SDK requires Python 3.8 or higher. The SDK follows "
            "semantic versioning with the current stable release being v1.12.3. "
            "Python 3.7 support was dropped in SDK v1.10.",
            "NexaFlow/SDK/Python", ["staleness"],
        ),
        BenchmarkItem(
            "Nexara's internal auth system uses OAuth 2.0 with PKCE. The legacy "
            "API key authentication is still supported for backward compatibility "
            "but is deprecated. Migration deadline: March 2025.",
            "Nexara/Auth/Legacy", ["staleness"],
        ),
        BenchmarkItem(
            "Nexara's Kubernetes clusters run version 1.27 across all environments. "
            "Upgrade to 1.28 is planned for Q1 2025. All teams should test their "
            "workloads against 1.28 in the staging environment.",
            "Nexara/Infrastructure/Kubernetes", ["staleness"],
        ),
        BenchmarkItem(
            "QuantumBridge client libraries are available for Java, Python, Go, and "
            "Node.js. The C++ client is in alpha. The Ruby client was discontinued "
            "in 2023 due to low adoption.",
            "QuantumBridge/Clients/Languages", ["staleness"],
        ),
        BenchmarkItem(
            "HiveSync's admin UI is built with Angular 14. A migration to Angular 17 "
            "is in progress (60% complete as of October 2024). The new UI includes "
            "real-time sync visualization and conflict resolution tools.",
            "HiveSync/UI/Admin", ["staleness"],
        ),
        BenchmarkItem(
            "VaultCore's Terraform provider is at version 2.3.0. It supports all "
            "secret engines and auth methods. The Pulumi provider is planned for "
            "Q3 2025.",
            "VaultCore/IaC/Terraform", ["staleness"],
        ),
        BenchmarkItem(
            "PulseMonitor dashboards are currently migrating from the legacy "
            "NexaDash v1 format to NexaDash v2 (JSON-based). V1 dashboards "
            "will continue to work but cannot use new widget types.",
            "PulseMonitor/Dashboards/Migration", ["staleness"],
        ),
        BenchmarkItem(
            "NexaFlow's web console requires Chrome 90+, Firefox 95+, or Safari 15+. "
            "Internet Explorer support was removed in NexaFlow v2.0. Edge is supported "
            "via its Chromium engine.",
            "NexaFlow/Console/Browser", ["staleness"],
        ),
        BenchmarkItem(
            "Nexara's data warehouse uses BigQuery for analytics. Migration from "
            "the legacy Redshift cluster is 80% complete. Analytics queries should "
            "target BigQuery; Redshift is read-only since September 2024.",
            "Nexara/Analytics/Warehouse", ["staleness"],
        ),
        BenchmarkItem(
            "QuantumBridge monitoring uses PulseMonitor JMX exporter v1.4. The "
            "new native PulseAgent integration (available since QB v3.5) is "
            "recommended for new deployments as it provides 50% more metrics.",
            "QuantumBridge/Monitoring/JMX", ["staleness"],
        ),
        BenchmarkItem(
            "HiveSync's REST API uses version prefix /api/v2/. The /api/v1/ "
            "endpoint is frozen (no new features) and will be removed in "
            "HiveSync v2.5 (scheduled for Q2 2025).",
            "HiveSync/API/Versioning", ["staleness"],
        ),
        BenchmarkItem(
            "VaultCore audit logs are currently stored in Elasticsearch 7.x. "
            "Migration to OpenSearch 2.x is planned for Q1 2025. The Elasticsearch "
            "cluster will be decommissioned after migration.",
            "VaultCore/Audit/Storage", ["staleness"],
        ),
        BenchmarkItem(
            "PulseMonitor's Kubernetes integration uses kube-state-metrics v2.6. "
            "The team is evaluating OpenTelemetry Collector as a replacement for "
            "the custom PulseAgent DaemonSet.",
            "PulseMonitor/Kubernetes/Integration", ["staleness"],
        ),
        BenchmarkItem(
            "NexaFlow artifact cleanup job runs nightly at 02:00 UTC. Artifacts "
            "older than 90 days are moved to cold storage (S3 Glacier). The "
            "cleanup job is being replaced by a lifecycle policy in v2.6.",
            "NexaFlow/Artifacts/Cleanup", ["staleness"],
        ),
        BenchmarkItem(
            "Nexara's load balancer setup uses HAProxy 2.6 in TCP mode for "
            "QuantumBridge and HTTP mode for all REST services. Migration to "
            "Envoy is approved and implementation starts in Q2 2025.",
            "Nexara/Infrastructure/LoadBalancer", ["staleness"],
        ),
        BenchmarkItem(
            "QuantumBridge topic configuration changes require a cluster rolling "
            "restart in v3.x. Dynamic reconfiguration without restart is "
            "planned for v4.0 (roadmap: H2 2025).",
            "QuantumBridge/Operations/Config", ["staleness"],
        ),
        BenchmarkItem(
            "HiveSync's geo-replication feature currently supports 2-region "
            "active-active setups. 3+ region support is in development and "
            "expected in v2.0 (Q4 2025). Testing with synthetic latency is available.",
            "HiveSync/Replication/Multi-Region", ["staleness"],
        ),
        BenchmarkItem(
            "VaultCore's CLI tool (vcore) is at version 1.8. The new TUI-based "
            "CLI (vcore-next) is in beta testing with improved secret browsing "
            "and policy editing capabilities.",
            "VaultCore/CLI/Tools", ["staleness"],
        ),
        BenchmarkItem(
            "PulseMonitor's alert notification system uses a webhook-first "
            "architecture. Direct PagerDuty integration (without webhooks) was "
            "added in v5.4 and is recommended for new setups.",
            "PulseMonitor/Alerts/PagerDuty", ["staleness"],
        ),
        BenchmarkItem(
            "NexaFlow resource quotas are enforced per-namespace. The current "
            "default quota is 100 concurrent workflow runs and 1TB artifact "
            "storage. Quota increases require approval from Platform Engineering.",
            "NexaFlow/Quotas/Default", ["staleness"],
        ),
        BenchmarkItem(
            "Nexara's service mesh (NexaMesh) is based on Envoy 1.26. Sidecar "
            "injection is automatic for all namespaces labeled with nexamesh=enabled. "
            "Migration to Envoy 1.29 with HTTP/3 support is in testing.",
            "Nexara/Mesh/Envoy", ["staleness"],
        ),
    ]
    items.extend(staleness)

    # ── 30 Bias (one-sided claims, absolutist language) ───────────────────

    bias = [
        BenchmarkItem(
            "QuantumBridge is the only enterprise event streaming platform that truly "
            "solves the exactly-once delivery problem. All competing solutions, including "
            "Apache Kafka and Amazon Kinesis, have fundamental design flaws that make "
            "exactly-once impossible in practice.",
            "QuantumBridge/Comparison/Streaming", ["bias"],
        ),
        BenchmarkItem(
            "Every engineering team at Nexara should use QuantumBridge for all inter-service "
            "communication. REST APIs and gRPC are inferior patterns that create tight "
            "coupling and should be eliminated from our architecture.",
            "Nexara/Best Practices/Communication", ["bias"],
        ),
        BenchmarkItem(
            "HiveSync's CRDT implementation is objectively the most advanced in the "
            "industry. Academic research on CRDTs has consistently confirmed that "
            "Nexara's approach is superior to all open-source alternatives.",
            "HiveSync/Technology/CRDTs", ["bias"],
        ),
        BenchmarkItem(
            "Developers who prefer eventual consistency over HiveSync's strong consistency "
            "guarantees simply don't understand distributed systems. There is never a "
            "valid reason to choose weaker consistency models.",
            "HiveSync/Philosophy/Consistency", ["bias"],
        ),
        BenchmarkItem(
            "VaultCore is the safest secrets management solution available. Organizations "
            "that use HashiCorp Vault or AWS Secrets Manager are exposing themselves to "
            "completely unnecessary security risks.",
            "VaultCore/Comparison/Security", ["bias"],
        ),
        BenchmarkItem(
            "All Nexara services must use VaultCore for secret storage. Teams that "
            "store credentials in environment variables or config files are being "
            "negligent and will be held responsible for any resulting security incidents.",
            "Nexara/Policies/Secrets", ["bias"],
        ),
        BenchmarkItem(
            "PulseMonitor is the only observability tool that correctly implements "
            "the three pillars of observability. Prometheus, Grafana, and Datadog "
            "all have fundamental architectural limitations that PulseMonitor avoids.",
            "PulseMonitor/Comparison/Observability", ["bias"],
        ),
        BenchmarkItem(
            "Teams that don't use PulseMonitor's anomaly detection feature will always "
            "be slower to detect incidents. Manual threshold-based alerting is a "
            "completely outdated approach that should never be used.",
            "PulseMonitor/Best Practices/Alerting", ["bias"],
        ),
        BenchmarkItem(
            "NexaFlow is fundamentally superior to Airflow, Temporal, and Prefect for "
            "workflow orchestration. These tools were designed for a previous era of "
            "computing and cannot handle modern cloud-native workloads.",
            "NexaFlow/Comparison/Orchestration", ["bias"],
        ),
        BenchmarkItem(
            "Writing custom shell scripts for deployment is always wrong. NexaFlow "
            "eliminates every use case for deployment scripts, and any team still "
            "using them is wasting engineering resources.",
            "NexaFlow/Best Practices/Deployment", ["bias"],
        ),
        BenchmarkItem(
            "Nexara's microservices architecture is the only correct way to build "
            "scalable systems. Monolithic architectures are inherently flawed and "
            "will always lead to engineering productivity collapse.",
            "Nexara/Architecture/Philosophy", ["bias"],
        ),
        BenchmarkItem(
            "Go is the only appropriate language for infrastructure software at Nexara. "
            "Java is too bloated, Python is too slow, and Rust's learning curve makes "
            "it completely impractical for team-scale development.",
            "Nexara/Engineering/Languages", ["bias"],
        ),
        BenchmarkItem(
            "QuantumBridge's Raft consensus is inherently superior to ZooKeeper-based "
            "coordination. Any system still using ZooKeeper is running on outdated "
            "technology that will inevitably cause availability issues.",
            "QuantumBridge/Architecture/Raft", ["bias"],
        ),
        BenchmarkItem(
            "HiveSync should always be preferred over direct database replication. "
            "PostgreSQL logical replication and MySQL binlog replication are fragile, "
            "unreliable solutions that break under any non-trivial workload.",
            "HiveSync/Comparison/Replication", ["bias"],
        ),
        BenchmarkItem(
            "VaultCore's deny-by-default policy model is the only secure approach "
            "to access control. Role-based access control (RBAC) used by competing "
            "products is fundamentally broken and impossible to audit.",
            "VaultCore/Security/Philosophy", ["bias"],
        ),
        BenchmarkItem(
            "PulseMonitor's custom time-series engine completely outclasses "
            "Prometheus's TSDB in every metric: write throughput, query speed, "
            "storage efficiency, and operational simplicity.",
            "PulseMonitor/Storage/Comparison", ["bias"],
        ),
        BenchmarkItem(
            "NexaFlow's YAML-based DSL is the most developer-friendly workflow "
            "definition format ever created. Python-based workflow definitions "
            "(like Airflow DAGs) are always harder to maintain and understand.",
            "NexaFlow/DSL/Philosophy", ["bias"],
        ),
        BenchmarkItem(
            "Nexara's canary deployment strategy is flawless and catches 100% of "
            "production issues before they affect users. Teams that skip canary "
            "deployments are being reckless.",
            "Nexara/Deployments/Philosophy", ["bias"],
        ),
        BenchmarkItem(
            "QuantumBridge's dead letter queue implementation handles every possible "
            "failure scenario perfectly. There are no edge cases that can cause "
            "message loss, making it the most reliable messaging system available.",
            "QuantumBridge/DLQ/Reliability", ["bias"],
        ),
        BenchmarkItem(
            "HiveSync's offline mode is the best implementation of offline-first "
            "synchronization. CouchDB's replication protocol and Firebase's offline "
            "support are primitive by comparison and unsuitable for enterprise use.",
            "HiveSync/Offline/Comparison", ["bias"],
        ),
        BenchmarkItem(
            "VaultCore's audit logging is the gold standard for compliance. Any "
            "organization using it will automatically pass SOC 2, GDPR, and HIPAA "
            "audits without additional tooling or processes.",
            "VaultCore/Compliance/Claims", ["bias"],
        ),
        BenchmarkItem(
            "PulseMonitor's distributed tracing implementation is the only one that "
            "correctly handles async message passing. Jaeger and Zipkin both lose "
            "trace context in async scenarios, making them useless for modern architectures.",
            "PulseMonitor/Tracing/Comparison", ["bias"],
        ),
        BenchmarkItem(
            "NexaFlow's caching layer eliminates all redundant computation. Teams "
            "that implement their own caching solutions alongside NexaFlow are "
            "wasting resources and creating unnecessary complexity.",
            "NexaFlow/Caching/Philosophy", ["bias"],
        ),
        BenchmarkItem(
            "Nexara's monorepo approach is universally superior to multi-repo setups. "
            "Companies using multi-repo strategies will always struggle with dependency "
            "management and cross-team collaboration.",
            "Nexara/Engineering/Monorepo/Philosophy", ["bias"],
        ),
        BenchmarkItem(
            "QuantumBridge's schema registry makes data quality issues impossible. "
            "Teams that don't use schema validation for every message are guaranteed "
            "to experience data corruption in production.",
            "QuantumBridge/Schema/Philosophy", ["bias"],
        ),
        BenchmarkItem(
            "HiveSync's CRDT-based conflict resolution always produces the correct "
            "outcome. Manual conflict resolution (as used by Git and CouchDB) is "
            "an outdated approach that wastes developer time.",
            "HiveSync/Sync/Philosophy", ["bias"],
        ),
        BenchmarkItem(
            "VaultCore is completely immune to all known attack vectors. No secrets "
            "management system has ever matched its security posture, and it will "
            "remain unbreachable for the foreseeable future.",
            "VaultCore/Security/Claims", ["bias"],
        ),
        BenchmarkItem(
            "PulseMonitor's SLO tracking is the only correct implementation of "
            "Google's SRE principles. Other tools merely approximate SLO concepts "
            "without understanding the mathematical foundations.",
            "PulseMonitor/SLO/Philosophy", ["bias"],
        ),
        BenchmarkItem(
            "NexaFlow completely eliminates the need for manual deployment processes. "
            "Any deployment that doesn't go through NexaFlow is inherently dangerous "
            "and should be immediately blocked by security.",
            "NexaFlow/Deployments/Mandate", ["bias"],
        ),
        BenchmarkItem(
            "Nexara's engineering culture is the most innovative in the tech industry. "
            "Other companies, including FAANG, have consistently failed to match "
            "Nexara's developer experience and internal tooling quality.",
            "Nexara/Culture/Innovation", ["bias"],
        ),
    ]
    items.extend(bias)

    # ── 30 Contradictions (contradict other KB entries or internal facts) ──

    contradictions = [
        BenchmarkItem(
            "QuantumBridge uses a push-based delivery model where brokers proactively "
            "send messages to consumers. Consumers register a callback URL and "
            "messages are delivered via HTTP POST requests.",
            "QuantumBridge/Consumers/Delivery", ["contradiction"],
            metadata={"contradicts": "QuantumBridge/Consumers/Groups"},
        ),
        BenchmarkItem(
            "QuantumBridge only supports at-most-once delivery. Exactly-once semantics "
            "are theoretically impossible in distributed systems and QuantumBridge "
            "does not attempt to implement them.",
            "QuantumBridge/Reliability/Semantics", ["contradiction"],
            metadata={"contradicts": "QuantumBridge/Reliability/Delivery"},
        ),
        BenchmarkItem(
            "QuantumBridge requires a minimum of 7 broker nodes for any production "
            "deployment. Single-node and 3-node setups are not supported and will "
            "result in data loss.",
            "QuantumBridge/Operations/Minimum", ["contradiction"],
            metadata={"contradicts": "QuantumBridge/Operations/Cluster Setup"},
        ),
        BenchmarkItem(
            "HiveSync uses Operational Transformation (OT) for conflict resolution, "
            "the same algorithm used by Google Docs. CRDTs were evaluated but "
            "rejected due to their excessive memory overhead.",
            "HiveSync/Sync/Algorithm", ["contradiction"],
            metadata={"contradicts": "HiveSync/Sync/CRDTs"},
        ),
        BenchmarkItem(
            "HiveSync transmits complete documents on every sync cycle. Delta "
            "synchronization was removed in v1.5 due to consistency bugs that "
            "could not be resolved within the CRDT framework.",
            "HiveSync/Protocol/Full Sync", ["contradiction"],
            metadata={"contradicts": "HiveSync/Protocol/Delta Sync"},
        ),
        BenchmarkItem(
            "HiveSync only supports PostgreSQL as a backend database. MongoDB and "
            "other NoSQL databases are not compatible with HiveSync's relational "
            "data model requirements.",
            "HiveSync/Connectors/Supported", ["contradiction"],
            metadata={"contradicts": "HiveSync/Connectors/Overview"},
        ),
        BenchmarkItem(
            "VaultCore stores the master encryption key in plaintext in a protected "
            "file on the leader node's filesystem. This approach was chosen for "
            "operational simplicity over the complexity of key splitting.",
            "VaultCore/Security/Master Key", ["contradiction"],
            metadata={"contradicts": "VaultCore/Security/Encryption"},
        ),
        BenchmarkItem(
            "VaultCore does not support dynamic secret generation. All secrets must "
            "be manually created and rotated by operators. Automatic rotation is "
            "on the long-term roadmap but not yet implemented.",
            "VaultCore/Secrets/Static", ["contradiction"],
            metadata={"contradicts": "VaultCore/Secrets/Dynamic"},
        ),
        BenchmarkItem(
            "VaultCore uses an allow-by-default policy model. All authenticated "
            "users can access all secrets unless explicitly denied. This simplifies "
            "onboarding for new team members.",
            "VaultCore/Policies/Default", ["contradiction"],
            metadata={"contradicts": "VaultCore/Policies/Overview"},
        ),
        BenchmarkItem(
            "PulseMonitor only supports its proprietary PulseAgent protocol for "
            "metric ingestion. OpenTelemetry and StatsD are not supported due "
            "to their lack of metric type annotations.",
            "PulseMonitor/Metrics/Protocol", ["contradiction"],
            metadata={"contradicts": "PulseMonitor/Metrics/Ingestion"},
        ),
        BenchmarkItem(
            "PulseMonitor traces are stored indefinitely with no automatic cleanup. "
            "The trace store uses append-only storage that grows linearly with "
            "traffic volume.",
            "PulseMonitor/Tracing/Retention", ["contradiction"],
            metadata={"contradicts": "PulseMonitor/Tracing/Overview"},
        ),
        BenchmarkItem(
            "PulseMonitor dashboards are created exclusively through the web UI. "
            "Dashboard-as-code is not supported; all dashboard definitions are "
            "stored in PulseMonitor's internal database.",
            "PulseMonitor/Dashboards/Creation", ["contradiction"],
            metadata={"contradicts": "PulseMonitor/Dashboards/Format"},
        ),
        BenchmarkItem(
            "NexaFlow workflows are defined in Python code using a decorator-based "
            "API. YAML configuration was considered but rejected as too limiting "
            "for complex workflow logic.",
            "NexaFlow/Workflows/Definition", ["contradiction"],
            metadata={"contradicts": "NexaFlow/Workflows/DSL"},
        ),
        BenchmarkItem(
            "NexaFlow uses a simple FIFO queue for workflow scheduling. Priority-based "
            "scheduling was removed in v2.0 because it caused starvation of "
            "low-priority workflows.",
            "NexaFlow/Scheduler/FIFO", ["contradiction"],
            metadata={"contradicts": "NexaFlow/Scheduler/Priority"},
        ),
        BenchmarkItem(
            "NexaFlow only supports cron-based triggers. Event-driven triggers "
            "from message queues or webhooks are not implemented due to the "
            "complexity of exactly-once trigger processing.",
            "NexaFlow/Triggers/Cron Only", ["contradiction"],
            metadata={"contradicts": "NexaFlow/Triggers/Overview"},
        ),
        BenchmarkItem(
            "Nexara's code review policy requires only 1 approval from any team "
            "member. Security reviews are optional and only recommended for "
            "infrastructure changes.",
            "Nexara/Policies/Review Lite", ["contradiction"],
            metadata={"contradicts": "Nexara/Policies/Code Review"},
        ),
        BenchmarkItem(
            "Nexara's incident severity has 2 levels: CRITICAL (requires immediate "
            "response) and NORMAL (handled during business hours). There is no "
            "distinction between customer-facing and internal issues.",
            "Nexara/Incidents/Levels", ["contradiction"],
            metadata={"contradicts": "Nexara/Incidents/Severity"},
        ),
        BenchmarkItem(
            "Nexara uses a monolithic architecture with a single main service "
            "handling all business logic. Microservices were attempted in 2021 "
            "but abandoned due to operational complexity.",
            "Nexara/Architecture/Monolith", ["contradiction"],
            metadata={"contradicts": "Nexara/Architecture/Overview"},
        ),
        BenchmarkItem(
            "QuantumBridge messages are not compressed. Compression was evaluated "
            "but the CPU overhead was deemed unacceptable for the latency-sensitive "
            "use cases that QuantumBridge targets.",
            "QuantumBridge/Performance/NoCompression", ["contradiction"],
            metadata={"contradicts": "QuantumBridge/Performance/Compression"},
        ),
        BenchmarkItem(
            "HiveSync requires a persistent network connection at all times. "
            "Offline operation is not supported; any network interruption causes "
            "the client to discard pending mutations.",
            "HiveSync/Network/Requirements", ["contradiction"],
            metadata={"contradicts": "HiveSync/Offline/Queue"},
        ),
        BenchmarkItem(
            "VaultCore stores secrets in plaintext in a PostgreSQL database. "
            "Encryption was considered unnecessary since the database itself "
            "is behind a firewall and VPN.",
            "VaultCore/Storage/Plaintext", ["contradiction"],
            metadata={"contradicts": "VaultCore/Security/Encryption"},
        ),
        BenchmarkItem(
            "PulseMonitor's anomaly detection uses fixed thresholds configured "
            "by operators. Machine learning-based detection was prototyped but "
            "produced too many false positives to be useful.",
            "PulseMonitor/Anomaly/Thresholds", ["contradiction"],
            metadata={"contradicts": "PulseMonitor/Anomaly/Detection"},
        ),
        BenchmarkItem(
            "NexaFlow steps cannot be retried after failure. Failed steps must "
            "be manually re-submitted. Automatic retry was removed in v2.1 "
            "because it caused duplicate side effects in production.",
            "NexaFlow/Workflows/NoRetry", ["contradiction"],
            metadata={"contradicts": "NexaFlow/Workflows/Retry"},
        ),
        BenchmarkItem(
            "Nexara's on-call rotation uses monthly cycles. There is no secondary "
            "responder; the on-call engineer handles all incidents alone with "
            "escalation only to the CTO.",
            "Nexara/Operations/On-Call-Alt", ["contradiction"],
            metadata={"contradicts": "Nexara/Operations/On-Call"},
        ),
        BenchmarkItem(
            "Nexara's CI/CD pipeline averages 45 minutes per run. The pipeline "
            "does not include security scanning; security reviews are handled "
            "as a separate manual process.",
            "Nexara/CI-CD/Duration", ["contradiction"],
            metadata={"contradicts": "Nexara/CI-CD/Pipeline"},
        ),
        BenchmarkItem(
            "QuantumBridge ACLs use an allow-all-by-default model. New topics "
            "are accessible to all authenticated users until an administrator "
            "explicitly adds restrictions.",
            "QuantumBridge/Security/DefaultACL", ["contradiction"],
            metadata={"contradicts": "QuantumBridge/Security/ACLs"},
        ),
        BenchmarkItem(
            "HiveSync does not support schema evolution. Any change to the document "
            "schema requires recreating the entire collection and re-syncing "
            "all data from scratch.",
            "HiveSync/Schema/NoEvolution", ["contradiction"],
            metadata={"contradicts": "HiveSync/Schema/Migrations"},
        ),
        BenchmarkItem(
            "VaultCore only supports username/password authentication. SSO, OIDC, "
            "and LDAP integration are not available. All operators share a single "
            "admin password.",
            "VaultCore/Auth/Basic", ["contradiction"],
            metadata={"contradicts": "VaultCore/Auth/Identity"},
        ),
        BenchmarkItem(
            "PulseMonitor retains all metrics at full resolution indefinitely. "
            "There is no downsampling or tiered storage; all data is kept in "
            "the hot storage tier.",
            "PulseMonitor/Storage/NoDownsampling", ["contradiction"],
            metadata={"contradicts": "PulseMonitor/Storage/Retention"},
        ),
        BenchmarkItem(
            "Nexara's deployment strategy is direct cutover: new versions "
            "replace old versions immediately with 100% traffic. Canary and "
            "blue-green deployments were rejected as too slow.",
            "Nexara/Deployments/Cutover", ["contradiction"],
            metadata={"contradicts": "Nexara/Deployments/Canary"},
        ),
    ]
    items.extend(contradictions)

    return items
