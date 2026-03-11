"""End-to-end benchmark tests with mock LLM."""

from __future__ import annotations

from tests.conftest import MockClaudeClient


def test_benchmark_immune_heuristic_vs_none(seeded_db):
    """Heuristic baseline should outperform no-immune baseline."""
    from akm.benchmarks.baselines import NoImmuneBaseline, SimpleHeuristicBaseline
    from akm.benchmarks.datasets import immune_dataset, seed_benchmark_db
    from akm.benchmarks.metrics import detection_f1

    dataset = immune_dataset()
    chunk_ids = seed_benchmark_db(seeded_db, dataset)
    ground_truth = [item.labels[0] for item in dataset]

    # No-immune: predicts everything healthy
    no_immune = NoImmuneBaseline()
    no_result = no_immune.scan(seeded_db, chunk_ids)
    no_f1 = detection_f1(no_result["predictions"], ground_truth)

    # Heuristic: keyword-based
    heuristic = SimpleHeuristicBaseline()
    h_result = heuristic.scan(seeded_db, chunk_ids)
    h_f1 = detection_f1(h_result["predictions"], ground_truth)

    # No-immune should have 0 detection
    assert no_f1.f1 == 0.0
    healthy_count = sum(1 for item in dataset if item.labels[0] == "healthy")
    assert no_f1.true_negatives == healthy_count

    # Heuristic should detect at least some threats
    assert h_f1.f1 > 0.0
    assert h_result["threats_detected"] > 0

    print(f"\n  No-Immune F1:  {no_f1.f1:.4f}")
    print(f"  Heuristic F1:  {h_f1.f1:.4f}")
    print(f"  Heuristic detected: {h_result['threats_detected']} threats")


def test_benchmark_immune_full_ais(seeded_db):
    """Full AIS benchmark with mock LLM."""
    from akm.benchmarks.datasets import immune_dataset, seed_benchmark_db
    from akm.benchmarks.metrics import detection_f1, per_class_f1
    from akm.immune.system import KnowledgeImmuneSystem

    dataset = immune_dataset()
    chunk_ids = seed_benchmark_db(seeded_db, dataset)
    ground_truth = [item.labels[0] for item in dataset]

    # Mock LLM: new 2-phase architecture
    # Phase 1 (innate): {"label": "...", "confidence": ...}
    # Phase 2 (adaptive): detector response (only for threats)
    responses = []
    for item in dataset:
        label = item.labels[0]
        if label == "hallucination":
            # Phase 1: innate classification
            responses.append({"label": "hallucination", "confidence": 0.8, "reason": "Fabricated claim"})
            # Phase 2: deep analysis by HallucinationDetector
            responses.append([{"description": "Unsourced claim", "evidence": "fabricated", "confidence": 0.8}])
        elif label == "staleness":
            responses.append({"label": "staleness", "confidence": 0.8, "reason": "Outdated reference"})
            responses.append([{"description": "Outdated reference", "evidence": "old version", "confidence": 0.8}])
        elif label == "bias":
            # Phase 1: innate says bias
            responses.append({"label": "bias", "confidence": 0.7, "reason": "Single perspective"})
            # Phase 2: dual-detector runs BOTH bias and contradiction detectors
            responses.append([{"description": "Single perspective", "evidence": "absolutist", "confidence": 0.7}])
            responses.append([])  # contradiction detector finds nothing
        elif label == "contradiction":
            # Phase 1: innate says contradiction
            responses.append({"label": "contradiction", "confidence": 0.6, "reason": "Contradicts facts"})
            # Phase 2: dual-detector runs BOTH bias and contradiction detectors
            responses.append([])  # bias detector finds nothing
            responses.append([{"description": "Contradicts established fact", "evidence": "wrong claim", "confidence": 0.6}])
        else:
            # healthy -- only innate call needed
            responses.append({"label": "healthy", "confidence": 0.9, "reason": "Accurate content"})

    llm = MockClaudeClient(responses=responses)
    immune = KnowledgeImmuneSystem(seeded_db, llm)

    predictions = []
    for cid in chunk_ids:
        result = immune.scan_chunk(cid)
        if result.threats_found:
            top = max(result.threats_found, key=lambda t: t.confidence)
            predictions.append(top.threat_type.value)
        else:
            predictions.append("healthy")

    ais_f1 = detection_f1(predictions, ground_truth)
    per_class = per_class_f1(predictions, ground_truth)

    print(f"\n  AIS Overall F1:     {ais_f1.f1:.4f}")
    print(f"  AIS Precision:      {ais_f1.precision:.4f}")
    print(f"  AIS Recall:         {ais_f1.recall:.4f}")
    for cls, metrics in per_class.items():
        print(f"  {cls:>15}: F1={metrics['f1']:.4f} P={metrics['precision']:.4f} R={metrics['recall']:.4f}")

    # AIS with perfect mock should detect hallucinations, staleness, bias
    assert ais_f1.precision > 0.5
    assert ais_f1.recall > 0.3


def test_benchmark_composting_pipeline(db):
    """Composting benchmark with mock LLM."""
    from akm.benchmarks.datasets import composting_dataset, seed_benchmark_db
    from akm.benchmarks.metrics import knowledge_density
    from akm.composting.composter import KnowledgeComposter

    dataset = composting_dataset()
    chunk_ids = seed_benchmark_db(db, dataset)

    # Mock: entropy scoring (100 chunks) + decomposition (50 outdated chunks * nutrients)
    responses = []
    # First: entropy scoring for all 100 chunks
    for i, item in enumerate(dataset):
        if "outdated" in item.labels:
            responses.append({"entropy": 0.9, "reason": "outdated"})
        else:
            responses.append({"entropy": 0.2, "reason": "current"})

    # Then: decomposition for each outdated chunk (50 chunks)
    for item in dataset:
        if "outdated" in item.labels:
            responses.append([
                {"type": "principle", "title": f"Lesson from {item.title}",
                 "content": "Extracted principle", "confidence": 0.8},
                {"type": "error_pattern", "title": f"Anti-pattern in {item.title}",
                 "content": "What went wrong", "confidence": 0.7},
            ])

    llm = MockClaudeClient(responses=responses)
    composter = KnowledgeComposter(db, llm, entropy_threshold=0.5)
    result = composter.run(dry_run=False, batch_size=200)

    assert result.chunks_scored == 100
    assert result.chunks_composted == 50  # all outdated chunks
    assert result.nutrients_extracted == 100  # 2 nutrients per outdated chunk

    density = knowledge_density(
        total_chunks=100,
        unique_nutrients=result.nutrients_extracted,
        nutrient_reuse_count=0,
    )

    print(f"\n  Chunks scored:      {result.chunks_scored}")
    print(f"  Chunks composted:   {result.chunks_composted}")
    print(f"  Nutrients extracted: {result.nutrients_extracted}")
    print(f"  Knowledge density:  {density['knowledge_density']:.4f}")


def test_benchmark_fermentation_pipeline(seeded_db):
    """Fermentation benchmark with mock LLM."""
    from akm.benchmarks.datasets import fermentation_dataset, seed_benchmark_db
    from akm.benchmarks.metrics import consistency_score
    from akm.fermentation.fermenter import Fermenter

    base_items, new_items = fermentation_dataset()
    seed_benchmark_db(seeded_db, base_items)

    # FTS can match multiple base chunks per new item, each consuming an LLM call.
    # Provide a generous pool of generic "extends" responses (safe default).
    generic_response = {"relationship": "extends", "similarity": 0.5, "explanation": "related"}
    responses = [generic_response] * 1000

    llm = MockClaudeClient(responses=responses)
    fermenter = Fermenter(seeded_db, llm, duration_hours=0)

    total_contradictions = 0
    total_cross_refs = 0
    for item in new_items:
        result = fermenter.ingest_and_ferment(item.content, title=item.title)
        total_contradictions += result.contradictions_found
        total_cross_refs += result.cross_refs_found

    print(f"\n  New items processed:    {len(new_items)}")
    print(f"  Cross-refs found:      {total_cross_refs}")
    # Pipeline ran successfully -- cross-refs were found
    assert total_cross_refs > 0


def test_benchmark_metrics_computation():
    """Verify metric computations are correct."""
    from akm.benchmarks.metrics import (
        ClassificationMetrics,
        detection_f1,
        knowledge_density,
        per_class_f1,
    )

    # Perfect detection
    preds = ["hallucination", "healthy", "bias", "healthy"]
    truth = ["hallucination", "healthy", "bias", "healthy"]
    m = detection_f1(preds, truth)
    assert m.f1 == 1.0
    assert m.precision == 1.0
    assert m.recall == 1.0

    # No detection
    preds = ["healthy", "healthy", "healthy", "healthy"]
    truth = ["hallucination", "healthy", "bias", "healthy"]
    m = detection_f1(preds, truth)
    assert m.recall == 0.0
    assert m.true_negatives == 2

    # Knowledge density
    kd = knowledge_density(100, 50, 20)
    assert kd["knowledge_density"] == 0.5
    assert kd["nutrient_reuse_rate"] == 0.4

    # Retrieval quality
    from akm.benchmarks.metrics import retrieval_quality
    rq = retrieval_quality(hits=15, total_pairs=20, mrr_sum=12.5)
    assert rq["retrieval_recall_at_5"] == 0.75
    assert rq["mean_reciprocal_rank"] == 0.625
    assert rq["pairs_found"] == 15

    # Groundedness
    from akm.benchmarks.metrics import groundedness_score
    gs = groundedness_score(evidence_grounded=8, total_threats=10, avg_word_overlap=0.65)
    assert gs["citation_accuracy"] == 0.8
    assert gs["avg_word_overlap"] == 0.65

    # Latency percentiles
    from akm.benchmarks.metrics import latency_percentiles
    durations = [0.1, 0.2, 0.15, 0.3, 0.05, 0.12, 0.08, 0.25, 0.18, 0.22]
    lp = latency_percentiles(durations)
    assert lp["n"] == 10
    assert lp["mean_ms"] > 0
    assert lp["p50_ms"] > 0
    assert lp["p95_ms"] >= lp["p50_ms"]

    # Edge case: empty latencies
    lp_empty = latency_percentiles([])
    assert lp_empty["n"] == 0


def test_bootstrap_ci():
    """Bootstrap CI should produce valid confidence intervals."""
    from akm.benchmarks.statistics import bootstrap_classification_ci

    # Perfect classifier
    preds = ["hallucination"] * 20 + ["healthy"] * 30
    truth = ["hallucination"] * 20 + ["healthy"] * 30
    result = bootstrap_classification_ci(preds, truth, n_bootstrap=500, seed=42)

    assert result.overall_f1.observed == 1.0
    assert result.overall_f1.ci_95_lower == 1.0  # perfect = no variance
    assert result.overall_f1.ci_95_upper == 1.0
    assert result.n_samples == 50
    assert result.n_bootstrap == 500

    # Imperfect classifier with some errors
    preds2 = (
        ["hallucination"] * 18 + ["healthy"] * 2  # 2 FN
        + ["healthy"] * 27 + ["hallucination"] * 3  # 3 FP
    )
    truth2 = ["hallucination"] * 20 + ["healthy"] * 30
    result2 = bootstrap_classification_ci(preds2, truth2, n_bootstrap=1000, seed=42)

    # F1 should be between 0 and 1
    assert 0.5 < result2.overall_f1.observed < 1.0
    # CI should bracket the observed value
    assert result2.overall_f1.ci_95_lower <= result2.overall_f1.observed
    assert result2.overall_f1.ci_95_upper >= result2.overall_f1.observed
    # CI should have nonzero width
    assert result2.overall_f1.ci_95_upper > result2.overall_f1.ci_95_lower

    # Per-class should include both classes
    assert "hallucination" in result2.per_class_f1
    assert "healthy" in result2.per_class_f1

    # to_dict() should work
    d = result2.to_dict()
    assert "overall" in d
    assert "per_class" in d
    assert d["overall"]["f1"]["ci_95"][0] <= d["overall"]["f1"]["observed"]


def test_bootstrap_ci_multiclass():
    """Bootstrap CI should work with multiple threat classes."""
    from akm.benchmarks.statistics import bootstrap_classification_ci

    preds = (
        ["hallucination"] * 10 + ["staleness"] * 8 + ["bias"] * 5
        + ["healthy"] * 2  # 2 misses
        + ["healthy"] * 25
    )
    truth = (
        ["hallucination"] * 10 + ["staleness"] * 10  # 2 FN staleness
        + ["bias"] * 5
        + ["healthy"] * 25
    )
    result = bootstrap_classification_ci(preds, truth, n_bootstrap=500, seed=42)

    # All classes should have CIs
    for cls in ["hallucination", "staleness", "bias", "healthy"]:
        assert cls in result.per_class_f1
        ci = result.per_class_f1[cls]
        assert ci.ci_95_lower <= ci.observed
        assert ci.ci_95_upper >= ci.observed


# ── KQAB Tests ────────────────────────────────────────────────────────────


def test_kqab_suite_builds():
    """KQAB suite should build with all 4 tasks."""
    from akm.benchmarks.kqab import build_kqab_suite, kqab_summary

    suite = build_kqab_suite()

    assert "T1" in suite
    assert "T2" in suite
    assert "T3" in suite
    assert "T4" in suite

    # T1: Threat Detection (reuses immune_dataset)
    assert suite["T1"].size > 100
    assert "healthy" in suite["T1"].labels
    assert "hallucination" in suite["T1"].labels

    # T2: Contradiction Discovery
    assert suite["T2"].size >= 35  # 15 contradicts + 10 consistent + 10 unrelated
    t2_labels = [item.labels[0] for item in suite["T2"].items]
    assert "contradicts" in t2_labels
    assert "consistent" in t2_labels
    assert "unrelated" in t2_labels

    # T3: Temporal Decay (expanded to 200)
    assert suite["T3"].size >= 200
    t3_labels = [item.labels[0] for item in suite["T3"].items]
    assert "current" in t3_labels
    assert "outdated" in t3_labels
    assert "deprecated" in t3_labels

    # T4: Evidence Grounding
    assert suite["T4"].size >= 24  # 8 supported + 8 unsupported + 8 partial
    t4_labels = [item.labels[0] for item in suite["T4"].items]
    assert "supported" in t4_labels
    assert "unsupported" in t4_labels
    assert "partial" in t4_labels

    # Summary
    summary = kqab_summary(suite)
    assert summary["total_items"] > 500  # 321 + 35 + 200 + 28 = 584


def test_kqab_t2_dataset_quality():
    """T2 contradiction pairs should have distinct chunk_a and chunk_b."""
    from akm.benchmarks.kqab import t2_contradiction_dataset

    pairs = t2_contradiction_dataset()
    assert len(pairs) >= 35

    for pair in pairs:
        assert pair.chunk_a != pair.chunk_b
        assert pair.label in {"contradicts", "consistent", "unrelated"}
        assert len(pair.chunk_a) > 20
        assert len(pair.chunk_b) > 20


def test_kqab_t3_dataset_quality():
    """T3 temporal decay items should have correct labels and domain coverage."""
    from akm.benchmarks.kqab import t3_temporal_decay_dataset

    items = t3_temporal_decay_dataset()
    assert len(items) >= 200  # Expanded dataset

    label_counts = {}
    domain_counts = {"se": 0, "general": 0}
    for item in items:
        label = item.labels[0]
        assert label in {"current", "outdated", "deprecated"}
        label_counts[label] = label_counts.get(label, 0) + 1
        domain = item.metadata.get("domain", "unknown")
        if domain in domain_counts:
            domain_counts[domain] += 1

    assert label_counts["current"] >= 80
    assert label_counts["outdated"] >= 80
    assert label_counts["deprecated"] >= 40
    # Both domains should be represented
    assert domain_counts["se"] > 50
    assert domain_counts["general"] > 30


def test_kqab_t4_dataset_quality():
    """T4 evidence grounding items should have claim and context."""
    from akm.benchmarks.kqab import t4_evidence_grounding_dataset

    items = t4_evidence_grounding_dataset()
    assert len(items) >= 24

    for item in items:
        assert item.label in {"supported", "unsupported", "partial"}
        assert len(item.claim) > 10
        assert len(item.context) >= 1
        assert all(len(c) > 10 for c in item.context)


def test_kqab_result_metrics():
    """KQABResult should compute correct macro-F1."""
    from akm.benchmarks.kqab import KQABResult

    result = KQABResult(
        task_id="T2",
        system_name="test",
        predictions=["contradicts"] * 10 + ["consistent"] * 10 + ["unrelated"] * 10,
        ground_truth=["contradicts"] * 10 + ["consistent"] * 10 + ["unrelated"] * 10,
    )
    assert result.macro_f1 == 1.0

    # Imperfect
    result2 = KQABResult(
        task_id="T2",
        system_name="test",
        predictions=["contradicts"] * 15 + ["consistent"] * 5 + ["unrelated"] * 10,
        ground_truth=["contradicts"] * 10 + ["consistent"] * 10 + ["unrelated"] * 10,
    )
    assert 0.3 < result2.macro_f1 < 1.0


def test_ablation_configs():
    """Ablation configs should cover all standard variants."""
    from akm.benchmarks.ablation import default_ablation_configs, ALL_DETECTORS

    configs = default_ablation_configs()
    names = {c.name for c in configs}

    # Must have full and innate-only
    assert "full_ais" in names
    assert "innate_only" in names

    # Must have leave-one-out for each detector
    for det in ALL_DETECTORS:
        assert f"without_{det}" in names

    # Must have single-detector for each
    for det in ALL_DETECTORS:
        assert f"only_{det}" in names

    # Total: 2 + 4 + 4 = 10 configs
    assert len(configs) == 10
