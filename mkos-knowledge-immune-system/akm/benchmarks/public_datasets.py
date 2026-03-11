"""Public dataset adapters for KQAB benchmark.

Loads established NLP datasets and adapts them to KQAB format:
- MNLI (MultiNLI) -> T2 Contradiction Discovery
- FEVER (copenlu/fever_gold_evidence) -> T4 Evidence Grounding

This gives KQAB peer-reviewed ground truth labels for credibility.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from akm.benchmarks.datasets import BenchmarkItem
from akm.benchmarks.kqab import ChunkPair, GroundingItem


# Label mappings
MNLI_LABEL_MAP = {0: "consistent", 1: "unrelated", 2: "contradicts"}
FEVER_LABEL_MAP = {"SUPPORTS": "supported", "REFUTES": "unsupported", "NOT ENOUGH INFO": "partial"}


def load_mnli_for_t2(
    n_per_class: int = 67,
    seed: int = 42,
    min_premise_len: int = 40,
    max_premise_len: int = 500,
) -> list[ChunkPair]:
    """Load MNLI validation set and adapt to T2 contradiction discovery format.

    Samples balanced classes: contradicts, consistent, unrelated.
    Filters for premise/hypothesis pairs that resemble KB chunks
    (reasonable length, no trivial examples).

    Args:
        n_per_class: Number of items per class (total = 3 * n_per_class).
        seed: Random seed for reproducible sampling.
        min_premise_len: Minimum premise character length.
        max_premise_len: Maximum premise character length.

    Returns:
        List of ChunkPair items with MNLI-derived ground truth.
    """
    from datasets import load_dataset

    ds = load_dataset("nyu-mll/multi_nli", split="validation_matched")

    rng = random.Random(seed)
    pairs_by_label: dict[str, list[ChunkPair]] = {
        "contradicts": [],
        "consistent": [],
        "unrelated": [],
    }

    # Shuffle indices for random sampling
    indices = list(range(len(ds)))
    rng.shuffle(indices)

    for idx in indices:
        item = ds[idx]
        label_id = item["label"]
        if label_id not in MNLI_LABEL_MAP:
            continue

        our_label = MNLI_LABEL_MAP[label_id]
        premise = item["premise"].strip()
        hypothesis = item["hypothesis"].strip()

        # Filter for KB-chunk-like content
        if len(premise) < min_premise_len or len(premise) > max_premise_len:
            continue
        if len(hypothesis) < 10:
            continue

        if len(pairs_by_label[our_label]) >= n_per_class:
            continue

        pairs_by_label[our_label].append(
            ChunkPair(
                chunk_a=premise,
                chunk_b=hypothesis,
                label=our_label,
                metadata={
                    "source": "mnli",
                    "genre": item.get("genre", ""),
                    "pair_id": item.get("pairID", ""),
                },
            )
        )

        # Check if we have enough
        if all(len(v) >= n_per_class for v in pairs_by_label.values()):
            break

    # Combine and shuffle
    all_pairs = []
    for pairs in pairs_by_label.values():
        all_pairs.extend(pairs)
    rng.shuffle(all_pairs)

    return all_pairs


def load_fever_for_t4(
    n_per_class: int = 67,
    seed: int = 42,
    min_evidence_len: int = 30,
) -> list[GroundingItem]:
    """Load FEVER validation set and adapt to T4 evidence grounding format.

    Maps FEVER labels to KQAB:
    - SUPPORTS -> supported (claim fully backed by evidence)
    - REFUTES -> unsupported (evidence contradicts claim)
    - NOT ENOUGH INFO -> partial (evidence doesn't fully confirm or deny)

    Args:
        n_per_class: Number of items per class.
        seed: Random seed for reproducible sampling.
        min_evidence_len: Minimum evidence text length.

    Returns:
        List of GroundingItem with FEVER-derived ground truth.
    """
    from datasets import load_dataset

    ds = load_dataset("copenlu/fever_gold_evidence", split="validation")

    rng = random.Random(seed)
    items_by_label: dict[str, list[GroundingItem]] = {
        "supported": [],
        "unsupported": [],
        "partial": [],
    }

    indices = list(range(len(ds)))
    rng.shuffle(indices)

    for idx in indices:
        item = ds[idx]
        fever_label = item["label"]
        if fever_label not in FEVER_LABEL_MAP:
            continue

        our_label = FEVER_LABEL_MAP[fever_label]

        if len(items_by_label[our_label]) >= n_per_class:
            continue

        claim = item["claim"].strip()
        if len(claim) < 10:
            continue

        # Extract evidence text
        evidence_texts = []
        for ev in item.get("evidence", []):
            if isinstance(ev, list) and len(ev) >= 3:
                ev_text = ev[2] if isinstance(ev[2], str) else str(ev[2])
                if ev_text and len(ev_text) >= min_evidence_len:
                    # Clean up Wikipedia-style formatting
                    ev_text = ev_text.replace("-LRB-", "(").replace("-RRB-", ")")
                    ev_text = ev_text.replace("-LSB-", "[").replace("-RSB-", "]")
                    evidence_texts.append(ev_text)

        # For NOT ENOUGH INFO, evidence may be weak/irrelevant — that's the point
        if our_label in ("supported", "unsupported") and not evidence_texts:
            continue

        # Use claim as-is if no evidence (for partial/NEI cases)
        if not evidence_texts:
            evidence_texts = ["No direct evidence found in the knowledge base."]

        items_by_label[our_label].append(
            GroundingItem(
                claim=claim,
                context=evidence_texts,
                label=our_label,
                metadata={
                    "source": "fever",
                    "original_label": fever_label,
                    "fever_id": item.get("original_id", ""),
                    "verifiable": item.get("verifiable", ""),
                },
            )
        )

        if all(len(v) >= n_per_class for v in items_by_label.values()):
            break

    all_items = []
    for items in items_by_label.values():
        all_items.extend(items)
    rng.shuffle(all_items)

    return all_items


def mnli_to_benchmark_items(pairs: list[ChunkPair]) -> list[BenchmarkItem]:
    """Convert MNLI ChunkPairs to BenchmarkItems for the KQAB runner."""
    return [
        BenchmarkItem(
            content=f"CHUNK A: {p.chunk_a}\n\nCHUNK B: {p.chunk_b}",
            title=f"mnli_{i}",
            labels=[p.label],
            metadata={**p.metadata, "chunk_a": p.chunk_a, "chunk_b": p.chunk_b},
        )
        for i, p in enumerate(pairs)
    ]


def fever_to_benchmark_items(items: list[GroundingItem]) -> list[BenchmarkItem]:
    """Convert FEVER GroundingItems to BenchmarkItems for the KQAB runner."""
    return [
        BenchmarkItem(
            content=f"CLAIM: {g.claim}\n\nCONTEXT:\n" + "\n---\n".join(g.context),
            title=f"fever_{i}",
            labels=[g.label],
            metadata={**g.metadata, "claim": g.claim, "context": g.context},
        )
        for i, g in enumerate(items)
    ]
