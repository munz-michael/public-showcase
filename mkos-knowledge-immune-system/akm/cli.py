"""CLI entry point for AKM."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from datetime import datetime, timezone

from akm.config import Config
from akm.utils.logger import console, log_error, log_info, log_phase, log_success, log_warning


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="akm",
        description="AI Knowledge Management - Cross-project knowledge search",
    )
    parser.add_argument("--version", action="version", version="%(prog)s 0.1.0")

    sub = parser.add_subparsers(dest="command")

    sub.add_parser("setup", help="Initialize database and index all projects")

    idx = sub.add_parser("index", help="Re-index new/changed files")
    idx.add_argument("--full", action="store_true", help="Full re-index (drop + rebuild)")
    idx.add_argument("--project", type=str, help="Index single project by slug")

    srch = sub.add_parser("search", help="Search knowledge base")
    srch.add_argument("query", nargs="+", help="Search query")
    srch.add_argument("--project", type=str, help="Filter by project slug")
    srch.add_argument("--limit", type=int, default=10)
    srch.add_argument("--format", choices=["rich", "json", "context"], default="rich")

    sub.add_parser("stats", help="Show index statistics")
    sub.add_parser("projects", help="List indexed projects")

    # --- Composting ---
    cmp = sub.add_parser("compost", help="Run knowledge composting pipeline")
    cmp.add_argument("--project", type=str, help="Filter by project slug")
    cmp.add_argument("--dry-run", action="store_true", help="Score only, don't decompose")
    cmp.add_argument("--threshold", type=float, default=0.7, help="Entropy threshold")
    sub.add_parser("compost-stats", help="Show composting statistics")

    # --- Fermentation ---
    fer = sub.add_parser("ferment", help="Ingest content into fermentation chamber")
    fer.add_argument("content", help="Content to ferment (or path to file)")
    fer.add_argument("--title", type=str, default="", help="Title for the content")
    fer.add_argument("--duration", type=float, default=24.0, help="Fermentation hours")
    sub.add_parser("ferment-status", help="Show fermentation chamber status")
    sub.add_parser("ferment-promote", help="Promote ready items from fermentation")

    # --- Immune System ---
    imm = sub.add_parser("immune-scan", help="Run immune system scan")
    imm.add_argument("--sample-size", type=int, default=10, help="Number of chunks to scan")
    sub.add_parser("immune-report", help="Show immune system health report")

    # --- Stigmergy ---
    sub.add_parser("stigmergy", help="Show pheromone signal landscape")

    # --- Quorum ---
    sub.add_parser("quorum-check", help="Check for quorum events (collective threats)")

    # --- Homeostasis ---
    sub.add_parser("homeostasis", help="Show system health and auto-tuning recommendations")
    homeo_apply = sub.add_parser("homeostasis-apply", help="Apply homeostatic parameter adjustments")

    # --- Dashboard ---
    sub.add_parser("dashboard", help="Start the AKM visualization dashboard")

    # --- Benchmarks ---
    bench = sub.add_parser("benchmark", help="Run benchmark suite")
    bench.add_argument("--component", choices=["composting", "fermentation", "immune", "all"],
                       default="all", help="Component to benchmark")
    bench.add_argument("--cache", action="store_true", help="Cache LLM responses for reproducibility")
    bench.add_argument("--clear-cache", action="store_true", help="Clear LLM response cache before run")
    bench.add_argument("--runs", type=int, default=1, help="Number of runs for statistics")
    bench.add_argument("--dataset", choices=["synthetic", "real_world"], default="synthetic",
                       help="Dataset type: synthetic (321 items) or real_world (225 Wikipedia-based)")
    bench.add_argument("--build-dataset", action="store_true",
                       help="Build/refresh real-world dataset from Wikipedia before benchmarking")
    bench.add_argument("--model", type=str, default=None,
                       help="LLM model override (e.g., gpt-4o, gpt-4o-mini, claude-haiku-4-5-20251001)")

    # --- KQAB Benchmark ---
    kqab = sub.add_parser("kqab", help="Run KQAB (Knowledge Quality Assurance Benchmark)")
    kqab.add_argument("--tasks", type=str, default="T1,T2,T3,T4",
                      help="Comma-separated task IDs to run (default: T1,T2,T3,T4)")
    kqab.add_argument("--cache", action="store_true", help="Cache LLM responses")
    kqab.add_argument("--model", type=str, default=None, help="LLM model override")
    kqab.add_argument("--variant", type=str, default="synth",
                      choices=["synth", "public", "combined"],
                      help="Dataset variant: synth (synthetic only), public (MNLI+FEVER), combined (both)")

    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    if not args.command:
        parse_args(["--help"])
        return

    config = Config.from_env()

    if args.command == "setup":
        _cmd_setup(config)
    elif args.command == "index":
        _cmd_index(config, full=args.full, project=args.project)
    elif args.command == "search":
        _cmd_search(config, " ".join(args.query), args.project, args.limit, args.format)
    elif args.command == "stats":
        _cmd_stats(config)
    elif args.command == "projects":
        _cmd_projects(config)
    elif args.command == "compost":
        _cmd_compost(config, args.project, args.dry_run, args.threshold)
    elif args.command == "compost-stats":
        _cmd_compost_stats(config)
    elif args.command == "ferment":
        _cmd_ferment(config, args.content, args.title, args.duration)
    elif args.command == "ferment-status":
        _cmd_ferment_status(config)
    elif args.command == "ferment-promote":
        _cmd_ferment_promote(config)
    elif args.command == "immune-scan":
        _cmd_immune_scan(config, args.sample_size)
    elif args.command == "immune-report":
        _cmd_immune_report(config)
    elif args.command == "stigmergy":
        _cmd_stigmergy(config)
    elif args.command == "quorum-check":
        _cmd_quorum_check(config)
    elif args.command == "homeostasis":
        _cmd_homeostasis(config)
    elif args.command == "homeostasis-apply":
        _cmd_homeostasis_apply(config)
    elif args.command == "dashboard":
        _cmd_dashboard()
    elif args.command == "benchmark":
        _cmd_benchmark(config, args.component, args.cache, args.clear_cache, args.runs,
                       args.dataset, args.build_dataset, args.model)
    elif args.command == "kqab":
        _cmd_kqab(config, args.tasks, args.cache, args.model, args.variant)


def _cmd_setup(config: Config) -> None:
    log_phase("SETUP", "Initialisiere AKM Knowledge Base")

    from akm.storage.database import Database
    db = Database(config.db_path)
    db.initialize()

    _cmd_index(config, full=True)


def _cmd_index(config: Config, full: bool = False, project: str | None = None) -> None:
    log_phase("INDEX", "Scanne Workspace...")

    from akm.ingestion.chunker import SectionChunker
    from akm.ingestion.parsers import JSONParser, MarkdownParser
    from akm.ingestion.scanner import WorkspaceScanner
    from akm.storage.database import Database
    from akm.storage.stores import ChunkStore, DocumentStore, ProjectStore

    db = Database(config.db_path)
    db.initialize()
    scanner = WorkspaceScanner(config)
    chunker = SectionChunker(max_tokens=config.max_chunk_tokens)

    # Load projects from Cockpit
    cockpit_projects = scanner.load_projects()

    with db.connect() as conn:
        proj_store = ProjectStore(conn)
        doc_store = DocumentStore(conn)
        chunk_store = ChunkStore(conn)

        # Register projects from Cockpit
        project_ids: dict[str, int] = {}
        for p in cockpit_projects:
            slug = p.get("id", "")
            if not slug:
                continue
            pid = proj_store.upsert(
                slug=slug,
                name=p.get("name", slug),
                path=os.path.join(config.workspace_root, p.get("path", "")),
                project_type=p.get("type", ""),
                description=p.get("description", ""),
                tags=p.get("tags", []),
            )
            project_ids[slug] = pid

        # Scan files
        files = scanner.scan_all()
        if project:
            files = [f for f in files if f.project_slug == project]

        log_info(f"{len(files)} Dateien gefunden")

        # Ensure all project slugs have IDs
        for f in files:
            if f.project_slug not in project_ids:
                pid = proj_store.upsert(
                    slug=f.project_slug,
                    name=f.project_slug,
                    path=str(f.path).rsplit("/", 1)[0],
                )
                project_ids[f.project_slug] = pid

        # Index files
        new_count = 0
        skip_count = 0
        chunk_count = 0
        t0 = time.time()

        for f in files:
            pid = project_ids[f.project_slug]

            # Content hash for change detection
            try:
                with open(f.path, "rb") as fh:
                    content_hash = hashlib.sha256(fh.read()).hexdigest()
            except OSError:
                continue

            line_count = 0
            try:
                with open(f.path, encoding="utf-8", errors="replace") as fh:
                    line_count = sum(1 for _ in fh)
            except OSError:
                pass

            mtime = datetime.fromtimestamp(f.mtime, tz=timezone.utc).isoformat()

            # Parse
            try:
                if f.file_type == "markdown":
                    doc = MarkdownParser.parse(f.path)
                else:
                    doc = JSONParser.parse(f.path)
            except Exception:
                continue

            # Upsert document (returns existing ID if hash unchanged)
            doc_id = doc_store.upsert(
                project_id=pid,
                file_path=f.path,
                file_type=f.file_type,
                title=doc.title,
                file_size=f.size,
                line_count=line_count,
                content_hash=content_hash,
                modified_at=mtime,
            )

            # Check if chunks already exist for this doc (unchanged)
            existing_chunks = conn.execute(
                "SELECT COUNT(*) as c FROM chunks WHERE document_id = ?", (doc_id,)
            ).fetchone()["c"]
            if existing_chunks > 0 and not full:
                skip_count += 1
                continue

            # Chunk and store
            file_name = os.path.basename(f.path)
            chunks = chunker.chunk(doc, f.project_slug, file_name)
            if chunks:
                n = chunk_store.insert_batch(doc_id, chunks)
                chunk_count += n

            new_count += 1

        elapsed = time.time() - t0
        log_success(f"Indexiert: {new_count} neu, {skip_count} unveraendert, {chunk_count} Chunks ({elapsed:.1f}s)")


def _cmd_search(config: Config, query: str, project: str | None,
                limit: int, fmt: str) -> None:
    from akm.search.engine import SearchEngine
    from akm.storage.database import Database

    db = Database(config.db_path)
    with db.connect() as conn:
        engine = SearchEngine(conn)
        results = engine.search(query, limit=limit, project=project)

    if not results:
        log_warning(f"Keine Ergebnisse fuer: {query}")
        return

    if fmt == "json":
        out = [
            {
                "score": r.score,
                "project": r.project_slug,
                "project_name": r.project_name,
                "file": r.file_path,
                "heading": r.heading,
                "snippet": r.snippet(500),
            }
            for r in results
        ]
        print(json.dumps(out, ensure_ascii=False, indent=2))

    elif fmt == "context":
        for r in results:
            print(f"--- [{r.project_name}] {r.document_title} ---")
            print(f"## {r.heading}")
            print(r.snippet(800))
            print(f"Source: {r.file_path}")
            print()

    else:
        # Rich table
        from rich.table import Table
        table = Table(title=f"Suche: {query}", show_lines=True)
        table.add_column("#", style="dim", width=3)
        table.add_column("Projekt", style="cyan", width=20)
        table.add_column("Heading", style="bold", width=30)
        table.add_column("Snippet", width=60)

        for i, r in enumerate(results, 1):
            table.add_row(
                str(i),
                r.project_slug,
                r.heading[:30],
                r.snippet(200),
            )

        console.print(table)


def _cmd_stats(config: Config) -> None:
    from akm.search.engine import SearchEngine
    from akm.storage.database import Database

    db = Database(config.db_path)
    if not os.path.exists(config.db_path):
        log_error("Database nicht gefunden. Zuerst 'akm setup' ausfuehren.")
        return

    with db.connect() as conn:
        engine = SearchEngine(conn)
        s = engine.stats()

    db_size = os.path.getsize(config.db_path) / (1024 * 1024)

    log_phase("STATS", "AKM Knowledge Base")
    log_info(f"Projekte:   {s['projects']}")
    log_info(f"Dokumente:  {s['documents']}")
    log_info(f"Chunks:     {s['chunks']}")
    log_info(f"Tokens:     {s['total_tokens']:,}")
    log_info(f"DB-Groesse: {db_size:.1f} MB")


def _cmd_projects(config: Config) -> None:
    from akm.storage.database import Database
    from akm.storage.stores import ProjectStore

    db = Database(config.db_path)
    if not os.path.exists(config.db_path):
        log_error("Database nicht gefunden. Zuerst 'akm setup' ausfuehren.")
        return

    with db.connect() as conn:
        projects = ProjectStore(conn).get_all()

    from rich.table import Table
    table = Table(title="Indexierte Projekte")
    table.add_column("Slug", style="cyan")
    table.add_column("Name", style="bold")
    table.add_column("Typ", style="dim")
    table.add_column("Docs", justify="right")
    table.add_column("Tokens", justify="right")

    for p in projects:
        table.add_row(
            p["slug"],
            p["name"],
            p["project_type"],
            str(p["doc_count"]),
            f"{p['token_count']:,}",
        )

    console.print(table)


# ── Dashboard Command ────────────────────────────────────────────────────


def _cmd_dashboard() -> None:
    import subprocess
    import sys

    log_phase("DASHBOARD", "Starte AKM Dashboard...")

    app_path = os.path.join(os.path.dirname(__file__), "dashboard", "app.py")
    subprocess.run([sys.executable, "-m", "streamlit", "run", app_path,
                    "--server.headless", "true"])


# ── Composting Commands ──────────────────────────────────────────────────


def _cmd_compost(config: Config, project: str | None, dry_run: bool, threshold: float) -> None:
    from akm.composting.composter import KnowledgeComposter
    from akm.llm.client import ClaudeClient
    from akm.storage.database import Database

    log_phase("COMPOST", "Knowledge Composting Pipeline")

    db = Database(config.db_path)
    with db.connect() as conn:
        llm = ClaudeClient(model=config.llm_model, api_key=config.anthropic_api_key)
        composter = KnowledgeComposter(conn, llm, entropy_threshold=threshold)
        result = composter.run(project_slug=project, dry_run=dry_run)

    log_info(f"Chunks bewertet:    {result.chunks_scored}")
    log_info(f"Chunks kompostiert: {result.chunks_composted}")
    log_info(f"Naehrstoffe:        {result.nutrients_extracted}")
    if result.cost_usd > 0:
        log_info(f"LLM-Kosten:        ${result.cost_usd:.4f}")
    if dry_run:
        log_warning("Dry-Run: Keine Aenderungen vorgenommen")
    else:
        log_success("Composting abgeschlossen")


def _cmd_compost_stats(config: Config) -> None:
    from akm.composting.nutrient_store import NutrientStore
    from akm.storage.database import Database

    db = Database(config.db_path)
    with db.connect() as conn:
        store = NutrientStore(conn)
        stats = store.get_stats()

    log_phase("COMPOST-STATS", "Naehrstoff-Bibliothek")
    log_info(f"Gesamt: {stats['total']} Naehrstoffe")
    for ntype, data in stats.get("by_type", {}).items():
        log_info(f"  {ntype}: {data['count']} (avg confidence: {data['avg_confidence']:.3f})")
    if stats.get("top_used"):
        log_info("Top genutzt:")
        for item in stats["top_used"]:
            log_info(f"  [{item['nutrient_type']}] {item['title']} ({item['usage_count']}x)")


# ── Fermentation Commands ────────────────────────────────────────────────


def _cmd_ferment(config: Config, content: str, title: str, duration: float) -> None:
    from akm.fermentation.fermenter import Fermenter
    from akm.llm.client import ClaudeClient
    from akm.storage.database import Database

    # If content looks like a file path, read it
    if os.path.isfile(content):
        with open(content, encoding="utf-8") as f:
            content = f.read()
        if not title:
            title = os.path.basename(content)

    log_phase("FERMENT", f"Ingest: {title or content[:50]}")

    db = Database(config.db_path)
    with db.connect() as conn:
        llm = ClaudeClient(model=config.llm_model, api_key=config.anthropic_api_key)
        fermenter = Fermenter(conn, llm, duration_hours=duration)
        result = fermenter.ingest_and_ferment(content, title=title)

    log_info(f"Fermentation ID:   {result.fermentation_id}")
    log_info(f"Cross-Referenzen:  {result.cross_refs_found}")
    log_info(f"Widersprueche:     {result.contradictions_found}")
    log_info(f"Konfidenz:         {result.final_confidence:.2f}")
    log_success(f"Status: {result.status}")


def _cmd_ferment_status(config: Config) -> None:
    from akm.fermentation.chamber import FermentationChamber
    from akm.storage.database import Database

    db = Database(config.db_path)
    with db.connect() as conn:
        chamber = FermentationChamber(conn)
        items = chamber.get_fermenting()
        ready = chamber.get_ready()

    log_phase("FERMENT-STATUS", "Fermentationskammer")
    log_info(f"In Fermentation: {len(items)}")
    log_info(f"Bereit:          {len(ready)}")

    if items:
        from rich.table import Table
        table = Table(title="Fermentierende Items")
        table.add_column("ID", style="dim", width=4)
        table.add_column("Titel", style="bold", width=30)
        table.add_column("Konfidenz", justify="right", width=10)
        table.add_column("Status", width=12)

        for item in items:
            table.add_row(
                str(item.id), item.title[:30],
                f"{item.confidence_score:.2f}", item.status,
            )
        console.print(table)


def _cmd_ferment_promote(config: Config) -> None:
    from akm.fermentation.fermenter import Fermenter
    from akm.llm.client import ClaudeClient
    from akm.storage.database import Database

    log_phase("FERMENT-PROMOTE", "Verarbeite reife Items")

    db = Database(config.db_path)
    with db.connect() as conn:
        llm = ClaudeClient(model=config.llm_model, api_key=config.anthropic_api_key)
        fermenter = Fermenter(conn, llm)
        results = fermenter.process_ready()

    if not results:
        log_info("Keine Items bereit zur Promotion")
        return

    for r in results:
        status_msg = f"ID {r.fermentation_id}: {r.status}"
        if r.status == "promoted":
            log_success(status_msg)
        elif r.status == "rejected":
            log_error(status_msg)
        else:
            log_info(status_msg)


# ── Immune System Commands ───────────────────────────────────────────────


def _cmd_immune_scan(config: Config, sample_size: int) -> None:
    from akm.immune.system import KnowledgeImmuneSystem
    from akm.llm.client import ClaudeClient
    from akm.storage.database import Database

    log_phase("IMMUNE-SCAN", f"Scanne {sample_size} Chunks")

    db = Database(config.db_path)
    with db.connect() as conn:
        llm = ClaudeClient(model=config.llm_model, api_key=config.anthropic_api_key)
        immune = KnowledgeImmuneSystem(conn, llm)

        # Get random sample of chunk IDs
        rows = conn.execute(
            "SELECT id FROM chunks ORDER BY RANDOM() LIMIT ?", (sample_size,)
        ).fetchall()
        chunk_ids = [r["id"] for r in rows]

        results = immune.scan_batch(chunk_ids)

    healthy = sum(1 for r in results if r.is_healthy)
    threats_total = sum(len(r.threats_found) for r in results)

    log_info(f"Gescannt:  {len(results)} Chunks")
    log_info(f"Gesund:    {healthy}/{len(results)}")
    log_info(f"Threats:   {threats_total}")

    if threats_total > 0:
        from rich.table import Table
        table = Table(title="Gefundene Threats")
        table.add_column("Chunk", style="dim", width=6)
        table.add_column("Typ", style="bold", width=15)
        table.add_column("Konfidenz", justify="right", width=10)
        table.add_column("Beschreibung", width=50)

        for r in results:
            for t in r.threats_found:
                table.add_row(
                    str(t.target_id), t.threat_type.value,
                    f"{t.confidence:.2f}", t.description[:50],
                )
        console.print(table)


def _cmd_immune_report(config: Config) -> None:
    from akm.immune.system import KnowledgeImmuneSystem
    from akm.llm.client import ClaudeClient
    from akm.storage.database import Database

    db = Database(config.db_path)
    with db.connect() as conn:
        llm = ClaudeClient(model=config.llm_model, api_key=config.anthropic_api_key)
        immune = KnowledgeImmuneSystem(conn, llm)
        report = immune.get_health_report()

    log_phase("IMMUNE-REPORT", "Knowledge Health Report")
    log_info(f"Chunks total:        {report['total_chunks']}")
    log_info(f"Immune Patterns:     {report['immune_memory']['total_patterns']}")
    if report["immune_memory"].get("by_type"):
        for ptype, data in report["immune_memory"]["by_type"].items():
            log_info(f"  {ptype}: {data['count']} patterns (fitness: {data['avg_fitness']:.3f})")


# ── Stigmergy Command ───────────────────────────────────────────────────


def _cmd_stigmergy(config: Config) -> None:
    from akm.stigmergy.signals import StigmergyNetwork
    from akm.storage.database import Database

    db = Database(config.db_path)
    with db.connect() as conn:
        network = StigmergyNetwork(conn)
        evaporated = network.evaporate()
        stats = network.get_stats()

    log_phase("STIGMERGY", "Pheromone Signal Landscape")
    log_info(f"Active signals: {stats['active_signals']}")
    if evaporated:
        log_info(f"Evaporated:     {evaporated}")
    for stype, data in stats.get("by_type", {}).items():
        log_info(f"  {stype}: {data['count']} signals (avg intensity: {data['avg_intensity']:.3f})")
    if stats["active_domains"]:
        log_info(f"Active domains: {', '.join(stats['active_domains'])}")


# ── Quorum Command ──────────────────────────────────────────────────────


def _cmd_quorum_check(config: Config) -> None:
    from akm.quorum.sensing import QuorumSensor
    from akm.storage.database import Database

    db = Database(config.db_path)
    with db.connect() as conn:
        sensor = QuorumSensor(conn)
        events = sensor.check_quorum()

    log_phase("QUORUM", "Collective Threat Detection")

    if not events:
        log_info("No quorum events detected -- all domains below threshold")
        return

    for event in events:
        log_warning(
            f"QUORUM REACHED: {event.domain} / {event.threat_type} "
            f"({event.chunk_count} chunks, avg confidence {event.avg_confidence:.2f})"
        )
        log_info(f"  Recommended action: {event.action.value}")


# ── Homeostasis Commands ────────────────────────────────────────────────


def _cmd_homeostasis(config: Config) -> None:
    from akm.homeostasis.regulator import HomeostasisRegulator
    from akm.storage.database import Database

    db = Database(config.db_path)
    with db.connect() as conn:
        regulator = HomeostasisRegulator(conn)
        report = regulator.get_health_report()

    log_phase("HOMEOSTASIS", f"System Health: {report['status'].upper()}")

    vitals = report["vitals"]
    log_info(f"Total chunks:       {vitals['total_chunks']}")
    log_info(f"Threat rate:        {vitals['threat_rate']:.4f}")
    log_info(f"False positive rate: {vitals['false_positive_rate']:.4f}")
    log_info(f"Avg entropy:        {vitals['avg_entropy']:.4f}")
    log_info(f"Composting rate:    {vitals['composting_throughput']:.4f}")
    log_info(f"Ferment rejection:  {vitals['fermentation_rejection_rate']:.4f}")
    log_info(f"Nutrient reuse:     {vitals['nutrient_reuse_rate']:.4f}")

    if report["adjustments"]:
        log_warning(f"\n  {len(report['adjustments'])} parameter adjustments recommended:")
        for adj in report["adjustments"]:
            log_info(f"    {adj['parameter']}: {adj['current']:.3f} -> {adj['recommended']:.3f}")
            log_info(f"      Reason: {adj['reason']}")
    else:
        log_success("All parameters within healthy ranges")


def _cmd_homeostasis_apply(config: Config) -> None:
    from akm.homeostasis.regulator import HomeostasisRegulator
    from akm.storage.database import Database

    db = Database(config.db_path)
    with db.connect() as conn:
        regulator = HomeostasisRegulator(conn)
        results = regulator.apply_adjustments()
        regulator.record_vitals()

    log_phase("HOMEOSTASIS-APPLY", "Applying parameter adjustments")

    if not results:
        log_info("No adjustments needed -- system is in homeostasis")
        return

    for r in results:
        log_success(f"{r['parameter']}: {r['old']:.3f} -> {r['new']:.3f}")
        log_info(f"  {r['reason']}")


# ── Benchmark Command ────────────────────────────────────────────────────


def _cmd_benchmark(config: Config, component: str, use_cache: bool = False,
                   clear_cache: bool = False, n_runs: int = 1,
                   dataset_type: str = "synthetic", build_dataset: bool = False,
                   model_override: str | None = None) -> None:
    from akm.benchmarks.runner import BenchmarkRunner
    from akm.llm.client import ClaudeClient
    from akm.storage.database import Database

    if clear_cache:
        from akm.llm.cache import CachedClaudeClient
        dummy_llm = ClaudeClient(model=config.llm_model, api_key=config.anthropic_api_key)
        cached = CachedClaudeClient(dummy_llm)
        cleared = cached.clear_cache()
        log_info(f"Cache geleert: {cleared} Eintraege")

    if build_dataset:
        from akm.benchmarks.real_world_dataset import build_real_world_dataset, RealWorldDatasetConfig, save_dataset, dataset_stats
        log_info("Building real-world dataset from Wikipedia...")
        rw_config = RealWorldDatasetConfig(wiki_cache_path=os.path.join(os.path.dirname(config.db_path), "wiki_cache.json"))
        items = build_real_world_dataset(config=rw_config)
        ds_path = os.path.join(os.path.dirname(config.db_path), "real_world_dataset.json")
        save_dataset(items, ds_path)
        stats = dataset_stats(items)
        log_success(f"Dataset built: {stats['total_items']} items ({stats['by_label']})")
        dataset_type = "real_world"

    log_phase("BENCHMARK", f"Running {component} benchmarks ({n_runs} run(s), cache={'on' if use_cache else 'off'}, dataset={dataset_type})")

    db = Database(config.db_path)
    with db.connect() as conn:
        model_name = model_override or config.llm_model
        if model_name.startswith("gpt-"):
            from akm.llm.openai_client import OpenAIClient
            llm = OpenAIClient(model=model_name, api_key=config.openai_api_key)
            log_info(f"Using OpenAI model: {model_name}")
        else:
            llm = ClaudeClient(model=model_name, api_key=config.anthropic_api_key)
            log_info(f"Using Anthropic model: {model_name}")
        runner = BenchmarkRunner(conn, llm, use_cache=use_cache, dataset_type=dataset_type)

        if n_runs > 1:
            report = runner.run_multiple(component=component, n_runs=n_runs)
        else:
            report = runner.run(component=component)

    # Print summary
    log_success(f"Benchmark abgeschlossen: {report['total_benchmarks']} Tests")
    log_info(f"Dauer:      {report['total_duration_seconds']:.1f}s")
    log_info(f"LLM-Kosten: ${report['total_cost_usd']:.4f}")

    if use_cache and hasattr(runner.llm, 'cache_hits'):
        log_info(f"Cache:      {runner.llm.cache_hits} hits / {runner.llm.cache_misses} misses")

    for name, result in report.get("results", {}).items():
        log_info(f"\n  {name}:")
        for metric, value in result.get("metrics", {}).items():
            if isinstance(value, float):
                log_info(f"    {metric}: {value:.4f}")
            else:
                log_info(f"    {metric}: {value}")

    # Save report
    report_path = os.path.join(os.path.dirname(config.db_path), "benchmark_report.json")
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    log_success(f"Report: {report_path}")


def _cmd_kqab(config: Config, tasks_str: str, use_cache: bool = False,
              model_override: str | None = None, variant: str = "synth") -> None:
    from akm.benchmarks.kqab_runner import KQABRunner, MKOSSystem, LLMFewShotSystem
    from akm.llm.client import ClaudeClient
    from akm.storage.database import Database

    task_ids = [t.strip() for t in tasks_str.split(",")]
    log_phase("KQAB", f"Knowledge Quality Assurance Benchmark ({', '.join(task_ids)}, variant={variant})")

    db = Database(config.db_path)
    with db.connect() as conn:
        model_name = model_override or config.llm_model
        if model_name.startswith("gpt-"):
            from akm.llm.openai_client import OpenAIClient
            llm = OpenAIClient(model=model_name, api_key=config.openai_api_key)
            log_info(f"Using OpenAI model: {model_name}")
        else:
            llm = ClaudeClient(model=model_name, api_key=config.anthropic_api_key)
            log_info(f"Using Anthropic model: {model_name}")

        runner = KQABRunner(conn, llm, use_cache=use_cache)
        report = runner.run(tasks=task_ids, variant=variant)

    # Print results
    for task_id, task_result in report.get("results", {}).items():
        log_phase(task_id, task_result["task_name"])
        log_info(f"  Items: {task_result['n_items']}, Labels: {task_result['labels']}")
        for sys_name, sys_result in task_result.get("systems", {}).items():
            f1 = sys_result.get("macro_f1", 0)
            ci = sys_result.get("bootstrap_ci", {}).get("overall", {}).get("f1", {})
            ci_str = ""
            if ci:
                ci_str = f" [{ci.get('ci_95', [0,0])[0]:.3f}, {ci.get('ci_95', [0,0])[1]:.3f}]"
            log_success(f"  {sys_name}: Macro-F1={f1:.4f}{ci_str}")

            # Per-class breakdown
            for cls, metrics in sys_result.get("per_class", {}).items():
                cls_f1 = metrics.get("f1", 0) if isinstance(metrics, dict) else 0
                log_info(f"    {cls}: F1={cls_f1:.3f}")

    log_success(f"KQAB complete: {report['total_duration_seconds']:.1f}s, ${report['total_cost_usd']:.4f}")

    # Save report
    suffix = f"_{variant}" if variant != "synth" else ""
    report_path = os.path.join(os.path.dirname(config.db_path), f"kqab_report{suffix}.json")
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    log_success(f"Report: {report_path}")
