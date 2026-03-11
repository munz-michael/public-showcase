"""Tests for the Quorum Sensing module."""

from __future__ import annotations

from akm.quorum.sensing import QuorumAction, QuorumSensor


def _seed_threats(db, domain_heading: str, threat_type: str, count: int):
    """Insert fake immune scan results for testing quorum."""
    # Need chunks with headings for domain extraction
    doc_id = db.execute(
        "SELECT id FROM documents LIMIT 1"
    ).fetchone()
    if not doc_id:
        db.execute(
            "INSERT INTO projects (slug, name, path) VALUES ('qtest', 'Q Test', '/tmp')"
        )
        db.execute(
            "INSERT INTO documents (project_id, file_path, file_type, title) "
            "VALUES (1, '/tmp/q.md', 'markdown', 'Q Doc')"
        )
        db.commit()

    chunk_ids = []
    for i in range(count):
        cursor = db.execute(
            "INSERT INTO chunks (document_id, chunk_index, heading, content, token_count) "
            "VALUES (1, ?, ?, ?, 10)",
            (100 + i, f"{domain_heading}/section{i}", f"Content about {domain_heading} item {i}"),
        )
        chunk_ids.append(cursor.lastrowid)

    for cid in chunk_ids:
        db.execute(
            "INSERT INTO immune_scan_results "
            "(chunk_id, threat_type, threat_description, confidence) "
            "VALUES (?, ?, ?, ?)",
            (cid, threat_type, f"Test {threat_type}", 0.7),
        )
    db.commit()
    return chunk_ids


def test_no_quorum_below_threshold(seeded_db):
    """No quorum events when threats are below threshold."""
    sensor = QuorumSensor(seeded_db)
    # Insert only 2 threats (default threshold for hallucination is 3)
    _seed_threats(seeded_db, "python", "hallucination", 2)
    events = sensor.check_quorum()
    assert len(events) == 0


def test_quorum_reached(seeded_db):
    """Quorum is reached when enough threats accumulate in a domain."""
    sensor = QuorumSensor(seeded_db)
    _seed_threats(seeded_db, "docker", "hallucination", 4)

    events = sensor.check_quorum()
    assert len(events) == 1
    assert events[0].domain == "docker"
    assert events[0].threat_type == "hallucination"
    assert events[0].chunk_count == 4
    assert events[0].action == QuorumAction.DOMAIN_QUARANTINE


def test_staleness_quorum_triggers_cascade_compost(seeded_db):
    """Staleness quorum should recommend cascade composting."""
    sensor = QuorumSensor(seeded_db)
    _seed_threats(seeded_db, "react", "staleness", 6)

    events = sensor.check_quorum()
    assert len(events) == 1
    assert events[0].action == QuorumAction.CASCADE_COMPOST


def test_execute_quarantine_action(seeded_db):
    """Executing quarantine should update scan results."""
    sensor = QuorumSensor(seeded_db)
    chunk_ids = _seed_threats(seeded_db, "kubernetes", "hallucination", 4)

    events = sensor.check_quorum()
    result = sensor.execute_action(events[0])

    assert result["action"] == "domain_quarantine"
    assert result["chunks_affected"] == 4

    # Verify scan results updated
    quarantined = seeded_db.execute(
        "SELECT COUNT(*) as c FROM immune_scan_results "
        "WHERE response_action = 'quarantine'"
    ).fetchone()["c"]
    assert quarantined == 4


def test_execute_cascade_compost_sets_entropy(seeded_db):
    """Cascade compost action should set high entropy on affected chunks."""
    sensor = QuorumSensor(seeded_db)
    _seed_threats(seeded_db, "legacy", "staleness", 6)

    events = sensor.check_quorum()
    sensor.execute_action(events[0])

    # Check entropy was set
    high_entropy = seeded_db.execute(
        "SELECT COUNT(*) as c FROM chunk_entropy WHERE entropy_score >= 0.9"
    ).fetchone()["c"]
    assert high_entropy == 6


def test_quorum_stats(seeded_db):
    """Stats should track quorum events."""
    sensor = QuorumSensor(seeded_db)
    _seed_threats(seeded_db, "api", "contradiction", 4)

    events = sensor.check_quorum()
    for event in events:
        sensor.execute_action(event)

    stats = sensor.get_stats()
    assert stats["total_events"] >= 1
    assert stats["active_events"] >= 1


def test_resolve_quorum(seeded_db):
    """Resolving a quorum should mark it as resolved."""
    sensor = QuorumSensor(seeded_db)
    _seed_threats(seeded_db, "db", "hallucination", 3)

    events = sensor.check_quorum()
    sensor.execute_action(events[0])

    active = sensor.get_active_quorums()
    assert len(active) >= 1

    sensor.resolve_quorum(active[0]["id"])

    active_after = sensor.get_active_quorums()
    resolved_ids = {a["id"] for a in active} - {a["id"] for a in active_after}
    assert len(resolved_ids) >= 1
