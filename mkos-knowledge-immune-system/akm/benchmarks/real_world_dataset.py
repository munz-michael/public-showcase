"""Real-world dataset pipeline for MKOS benchmarks.

Sources content from Wikipedia and introduces controlled perturbations
to create labeled threat examples with documented provenance.

Strategy:
- Healthy: Real Wikipedia paragraphs (unmodified)
- Hallucination: Real text with fabricated claims injected
- Staleness: Real text with outdated version/date references
- Bias: Real text rewritten to express strong one-sided preference
- Contradiction: Real text with factually inverted claims

Each item includes provenance metadata (source URL, modification type,
original vs modified text) for reproducibility and auditing.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from urllib.request import urlopen, Request
from urllib.parse import quote

from akm.benchmarks.datasets import BenchmarkItem


# ── Wikipedia API ──────────────────────────────────────────────────────────


WIKI_API = "https://en.wikipedia.org/api/rest_v1/page/summary/"

# Technical topics for software engineering KB context
WIKI_TOPICS = [
    # Programming languages
    "Python_(programming_language)", "Rust_(programming_language)",
    "TypeScript", "Go_(programming_language)", "Java_(programming_language)",
    "C%2B%2B", "Kotlin_(programming_language)", "Swift_(programming_language)",
    # Databases
    "PostgreSQL", "SQLite", "MongoDB", "Redis", "Apache_Cassandra",
    # Web technologies
    "React_(software)", "Node.js", "GraphQL", "WebAssembly", "HTTP/2",
    # DevOps / Infrastructure
    "Docker_(software)", "Kubernetes", "Terraform_(software)",
    "Git", "CI/CD", "Microservices",
    # CS concepts
    "B-tree", "Hash_table", "CAP_theorem", "MapReduce",
    "Raft_(algorithm)", "Bloom_filter", "Merkle_tree",
    # ML/AI
    "Transformer_(deep_learning_architecture)", "Attention_(machine_learning)",
    "Gradient_descent", "Neural_network_(machine_learning)",
    "Reinforcement_learning", "Convolutional_neural_network",
    # Software engineering
    "Test-driven_development", "Continuous_integration",
    "Design_pattern_(computer_science)", "SOLID",
    "Agile_software_development", "Technical_debt",
]


@dataclass
class WikiArticle:
    """A fetched Wikipedia article summary."""
    title: str
    extract: str
    url: str
    topic_slug: str
    fetch_timestamp: str


def fetch_wiki_summaries(
    topics: list[str] | None = None,
    delay: float = 0.5,
    cache_path: str | None = None,
) -> list[WikiArticle]:
    """Fetch Wikipedia article summaries via REST API.

    Args:
        topics: List of Wikipedia article slugs. Defaults to WIKI_TOPICS.
        delay: Seconds between requests (be polite).
        cache_path: If set, cache results to/from this JSON file.
    """
    topics = topics or WIKI_TOPICS

    # Check cache
    if cache_path:
        p = Path(cache_path)
        if p.exists():
            data = json.loads(p.read_text())
            return [WikiArticle(**a) for a in data]

    articles = []
    for slug in topics:
        try:
            url = f"{WIKI_API}{slug}"
            req = Request(url, headers={"User-Agent": "MKOS-Benchmark/1.0"})
            with urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode())

            extract = data.get("extract", "")
            if len(extract) < 50:
                continue

            articles.append(WikiArticle(
                title=data.get("title", slug),
                extract=extract,
                url=data.get("content_urls", {}).get("desktop", {}).get("page", url),
                topic_slug=slug,
                fetch_timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            ))

            if delay > 0:
                time.sleep(delay)

        except Exception:
            continue

    # Save cache
    if cache_path and articles:
        p = Path(cache_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(
            [a.__dict__ for a in articles],
            ensure_ascii=False, indent=2,
        ))

    return articles


# ── Perturbation Functions ─────────────────────────────────────────────────


def _make_hallucination(article: WikiArticle, idx: int) -> BenchmarkItem:
    """Inject a fabricated claim into real text."""
    fabrications = [
        "According to a 2024 study by MIT researchers, {title} has been shown to reduce development costs by 73% compared to all alternatives.",
        "The original creator of {title} announced in January 2025 that the project will be completely rewritten from scratch using a novel paradigm.",
        "{title} was officially deprecated by its maintainers in late 2024 due to fundamental security vulnerabilities that cannot be patched.",
        "A peer-reviewed analysis in Nature Computing demonstrated that {title} consistently outperforms all competing solutions by a factor of 10x.",
        "The European Union mandated the use of {title} in all government systems starting March 2025 under the Digital Infrastructure Act.",
        "Internal benchmarks leaked from Google showed {title} processes 1 billion requests per second on commodity hardware.",
        "{title} was awarded the ACM Software System Award in 2024 for revolutionizing the field of distributed computing.",
        "A critical zero-day vulnerability (CVE-2025-0001) was discovered in {title} that affects all versions since inception.",
    ]

    fab = fabrications[idx % len(fabrications)].format(title=article.title)
    # Insert fabrication after first sentence
    sentences = article.extract.split(". ")
    if len(sentences) > 1:
        modified = sentences[0] + ". " + fab + " " + ". ".join(sentences[1:])
    else:
        modified = article.extract + " " + fab

    return BenchmarkItem(
        content=modified,
        title=f"{article.title} (modified)",
        labels=["hallucination"],
        metadata={
            "source": "wikipedia",
            "source_url": article.url,
            "perturbation": "hallucination",
            "original_text": article.extract,
            "injected_claim": fab,
            "provenance_hash": hashlib.sha256(article.extract.encode()).hexdigest()[:16],
        },
    )


def _make_staleness(article: WikiArticle, idx: int) -> BenchmarkItem:
    """Rewrite text with outdated version references."""
    stale_rewrites = [
        ("is ", "was, as of 2018, "),
        ("uses ", "used, in its 2016 version, "),
        ("supports ", "supported, before the 2019 deprecation, "),
        ("allows ", "allowed, in versions prior to the 2017 rewrite, "),
        ("provides ", "provided, as documented in the 2015 specification, "),
        ("enables ", "enabled, according to the 2014 release notes, "),
    ]

    old_phrase, new_phrase = stale_rewrites[idx % len(stale_rewrites)]
    # Apply to first occurrence only
    modified = article.extract.replace(old_phrase, new_phrase, 1)

    # Add explicit outdated framing
    suffix = f" Note: This information reflects the state of {article.title} as of 2016 and may not apply to current versions."
    modified += suffix

    return BenchmarkItem(
        content=modified,
        title=f"{article.title} (outdated)",
        labels=["staleness"],
        metadata={
            "source": "wikipedia",
            "source_url": article.url,
            "perturbation": "staleness",
            "original_text": article.extract,
            "stale_pattern": f"'{old_phrase}' -> '{new_phrase}'",
            "provenance_hash": hashlib.sha256(article.extract.encode()).hexdigest()[:16],
        },
    )


def _make_bias(article: WikiArticle, idx: int) -> BenchmarkItem:
    """Rewrite text with strong one-sided preference."""
    bias_templates = [
        "{title} is by far the best solution in its category. Any developer who chooses a competing technology is making a serious mistake that will cost their team months of productivity.",
        "In my extensive experience, {title} is the only viable option for professional development. Alternatives are simply not worth considering for any serious project.",
        "Every competent engineer should be using {title}. The technology has no real drawbacks, and critics are typically unfamiliar with its true capabilities.",
        "{title} has completely replaced all competing solutions in the industry. Teams that haven't adopted it yet are falling behind and will struggle to recruit talent.",
        "After evaluating dozens of options, {title} stands alone as the superior choice. Its design philosophy is flawless, and competing approaches are fundamentally misguided.",
    ]

    biased = bias_templates[idx % len(bias_templates)].format(title=article.title)
    # Prepend real context, append biased opinion
    first_sentence = article.extract.split(". ")[0] + "."
    modified = f"{first_sentence} {biased}"

    return BenchmarkItem(
        content=modified,
        title=f"{article.title} (opinion)",
        labels=["bias"],
        metadata={
            "source": "wikipedia",
            "source_url": article.url,
            "perturbation": "bias",
            "original_text": article.extract,
            "bias_template": bias_templates[idx % len(bias_templates)],
            "provenance_hash": hashlib.sha256(article.extract.encode()).hexdigest()[:16],
        },
    )


def _make_contradiction(article: WikiArticle, idx: int) -> BenchmarkItem:
    """Invert key factual claims in the text."""
    inversions = [
        ("is a", "is not a"),
        ("allows", "prevents"),
        ("enables", "prevents"),
        ("supports", "does not support"),
        ("provides", "lacks"),
        ("uses", "avoids using"),
        ("designed to", "not designed to"),
        ("can be", "cannot be"),
        ("improves", "degrades"),
        ("reduces", "increases"),
    ]

    modified = article.extract
    applied = False
    for orig, inverted in inversions:
        if orig in modified.lower():
            # Case-insensitive replace of first occurrence
            pattern = re.compile(re.escape(orig), re.IGNORECASE)
            modified = pattern.sub(inverted, modified, count=1)
            applied = True
            break

    if not applied:
        # Fallback: negate the first sentence
        sentences = modified.split(". ")
        if sentences:
            sentences[0] = "Contrary to popular belief, it is false that " + sentences[0].lower()
            modified = ". ".join(sentences)

    return BenchmarkItem(
        content=modified,
        title=f"{article.title} (inverted)",
        labels=["contradiction"],
        metadata={
            "source": "wikipedia",
            "source_url": article.url,
            "perturbation": "contradiction",
            "original_text": article.extract,
            "provenance_hash": hashlib.sha256(article.extract.encode()).hexdigest()[:16],
        },
    )


def _make_healthy(article: WikiArticle) -> BenchmarkItem:
    """Use unmodified real text as healthy example."""
    return BenchmarkItem(
        content=article.extract,
        title=article.title,
        labels=["healthy"],
        metadata={
            "source": "wikipedia",
            "source_url": article.url,
            "perturbation": "none",
            "provenance_hash": hashlib.sha256(article.extract.encode()).hexdigest()[:16],
        },
    )


# ── Dataset Builder ────────────────────────────────────────────────────────


@dataclass
class RealWorldDatasetConfig:
    """Configuration for real-world dataset generation."""
    n_healthy: int = 80
    n_hallucination: int = 40
    n_staleness: int = 30
    n_bias: int = 25
    n_contradiction: int = 25
    wiki_cache_path: str = os.path.expanduser("~/.akm/wiki_cache.json")

    @property
    def total(self) -> int:
        return self.n_healthy + self.n_hallucination + self.n_staleness + self.n_bias + self.n_contradiction


def build_real_world_dataset(
    config: RealWorldDatasetConfig | None = None,
    articles: list[WikiArticle] | None = None,
) -> list[BenchmarkItem]:
    """Build a real-world dataset from Wikipedia content.

    Uses round-robin assignment: each article gets one perturbation type,
    cycling through the categories until quotas are filled.

    Args:
        config: Dataset size configuration.
        articles: Pre-fetched articles (for testing). If None, fetches from Wikipedia.

    Returns:
        List of BenchmarkItems with provenance metadata.
    """
    config = config or RealWorldDatasetConfig()

    if articles is None:
        articles = fetch_wiki_summaries(cache_path=config.wiki_cache_path)

    if len(articles) < 10:
        raise ValueError(f"Need at least 10 articles, got {len(articles)}")

    items: list[BenchmarkItem] = []
    counters = {
        "healthy": 0,
        "hallucination": 0,
        "staleness": 0,
        "bias": 0,
        "contradiction": 0,
    }
    limits = {
        "healthy": config.n_healthy,
        "hallucination": config.n_hallucination,
        "staleness": config.n_staleness,
        "bias": config.n_bias,
        "contradiction": config.n_contradiction,
    }
    # Order: healthy first (unmodified), then threats
    category_order = ["healthy", "hallucination", "staleness", "bias", "contradiction"]

    # Round-robin: cycle through articles, assign categories
    art_idx = 0
    for category in category_order:
        while counters[category] < limits[category]:
            article = articles[art_idx % len(articles)]
            art_idx += 1

            if category == "healthy":
                items.append(_make_healthy(article))
            elif category == "hallucination":
                items.append(_make_hallucination(article, counters[category]))
            elif category == "staleness":
                items.append(_make_staleness(article, counters[category]))
            elif category == "bias":
                items.append(_make_bias(article, counters[category]))
            elif category == "contradiction":
                items.append(_make_contradiction(article, counters[category]))

            counters[category] += 1

    # Add contradiction counterparts (healthy versions of contradiction sources)
    n_counterparts = min(config.n_contradiction, 25)
    contra_items = [i for i in items if i.labels[0] == "contradiction"]
    for pair_idx, item in enumerate(contra_items[:n_counterparts]):
        original = item.metadata.get("original_text", "")
        if original:
            items.append(BenchmarkItem(
                content=original,
                title=item.metadata.get("source_url", "").split("/")[-1].replace("_", " "),
                labels=["healthy"],
                metadata={
                    "source": "wikipedia",
                    "source_url": item.metadata.get("source_url", ""),
                    "perturbation": "none",
                    "is_counterpart": True,
                    "pair_id": pair_idx,
                },
            ))
            # Tag the contradiction with pair_id too
            item.metadata["pair_id"] = pair_idx

    return items


def save_dataset(items: list[BenchmarkItem], path: str) -> None:
    """Save dataset to JSON for reproducibility."""
    data = []
    for item in items:
        data.append({
            "content": item.content,
            "title": item.title,
            "labels": item.labels,
            "metadata": item.metadata,
        })

    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2))


def load_dataset(path: str) -> list[BenchmarkItem]:
    """Load dataset from JSON."""
    data = json.loads(Path(path).read_text())
    return [
        BenchmarkItem(
            content=d["content"],
            title=d["title"],
            labels=d["labels"],
            metadata=d.get("metadata", {}),
        )
        for d in data
    ]


def dataset_stats(items: list[BenchmarkItem]) -> dict:
    """Summary statistics for a dataset."""
    by_label: dict[str, int] = {}
    by_source: dict[str, int] = {}
    total_chars = 0

    for item in items:
        label = item.labels[0] if item.labels else "unknown"
        by_label[label] = by_label.get(label, 0) + 1
        source = item.metadata.get("source", "unknown")
        by_source[source] = by_source.get(source, 0) + 1
        total_chars += len(item.content)

    return {
        "total_items": len(items),
        "by_label": by_label,
        "by_source": by_source,
        "avg_chars": total_chars // len(items) if items else 0,
        "has_provenance": sum(1 for i in items if i.metadata.get("provenance_hash")),
        "has_counterparts": sum(1 for i in items if i.metadata.get("is_counterpart")),
    }
