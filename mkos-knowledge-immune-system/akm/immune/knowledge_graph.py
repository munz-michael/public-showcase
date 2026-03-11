"""Knowledge Graph for transitive contradiction detection.

Builds an entity-relation graph over KB chunks and detects:
1. Direct contradictions (A contradicts B)
2. Transitive contradictions (A implies B, B contradicts C, so A conflicts with C)
3. Contradiction clusters (groups of mutually conflicting chunks)

Uses LLM for entity/relation extraction and contradiction assessment.
"""

from __future__ import annotations

import sqlite3
from collections import defaultdict
from dataclasses import dataclass, field

from akm.llm.client import ClaudeClient
from akm.search.engine import SearchEngine


@dataclass
class Entity:
    """A named entity extracted from a chunk."""
    name: str
    entity_type: str  # "technology", "concept", "organization", "metric"
    chunk_id: int


@dataclass
class Relation:
    """A claim/relation between entities from a specific chunk."""
    subject: str
    predicate: str  # "uses", "is", "has", "enables", "requires", "outperforms"
    object: str
    chunk_id: int
    confidence: float = 1.0


@dataclass
class Contradiction:
    """A detected contradiction between chunks."""
    chunk_id_a: int
    chunk_id_b: int
    relation_a: Relation
    relation_b: Relation
    contradiction_type: str  # "direct", "transitive"
    path: list[int] = field(default_factory=list)  # chunk IDs in transitive path
    confidence: float = 0.0
    description: str = ""


@dataclass
class KnowledgeGraphStats:
    n_entities: int
    n_relations: int
    n_chunks: int
    n_direct_contradictions: int
    n_transitive_contradictions: int
    contradiction_clusters: list[list[int]]


class KnowledgeGraph:
    """Entity-relation graph over KB chunks for contradiction detection."""

    EXTRACT_PROMPT = (
        "Extract factual claims from this knowledge base content as "
        "subject-predicate-object triples.\n\n"
        "Rules:\n"
        "- Extract 2-5 key claims per chunk\n"
        "- Subject and object should be named entities or concepts\n"
        "- Predicate should be a verb phrase\n"
        "- Include negations explicitly (e.g., 'does not support')\n\n"
        "Respond with JSON:\n"
        '{"entities": [{"name": "...", "type": "technology|concept|organization|metric"}], '
        '"relations": [{"subject": "...", "predicate": "...", "object": "...", '
        '"confidence": 0.0-1.0}]}'
    )

    CONTRADICTION_PROMPT = (
        "Given two claims from a knowledge base, determine if they contradict each other.\n\n"
        "Consider:\n"
        "- Direct opposition (X is Y vs X is not Y)\n"
        "- Incompatible properties (X uses A vs X uses B, when A and B are mutually exclusive)\n"
        "- Scope conflicts (X always does Y vs X sometimes does Y)\n\n"
        "Respond with JSON: {\"contradicts\": true/false, \"confidence\": 0.0-1.0, "
        "\"explanation\": \"...\"}"
    )

    # Canonical name mappings for entity normalization
    _ALIASES: dict[str, str] = {
        "postgres": "postgresql", "pg": "postgresql", "psql": "postgresql",
        "mongo": "mongodb", "mysql db": "mysql",
        "sqlite3": "sqlite", "cockroachdb": "cockroachdb",
        "k8s": "kubernetes", "kube": "kubernetes",
        "js": "javascript", "node": "nodejs", "node.js": "nodejs",
        "py": "python", "python3": "python", "python 3": "python",
        "ts": "typescript",
        "tf": "terraform",
        "es": "elasticsearch", "elastic": "elasticsearch",
        "redis cache": "redis", "redis db": "redis",
        "graphql api": "graphql", "gql": "graphql",
        "rest api": "rest", "restful": "rest", "restful api": "rest",
        "docker container": "docker", "containers": "docker",
        "sql query": "sql", "sql queries": "sql",
        "db": "database", "databases": "database", "rdbms": "relational database",
        "nosql db": "nosql", "nosql database": "nosql",
        "orm": "object-relational mapping",
        "api": "application programming interface",
    }

    def __init__(self, conn: sqlite3.Connection, llm: ClaudeClient) -> None:
        self.conn = conn
        self.llm = llm
        self.entities: dict[str, Entity] = {}
        self.relations: list[Relation] = []
        self._entity_to_chunks: dict[str, set[int]] = defaultdict(set)
        self._chunk_relations: dict[int, list[Relation]] = defaultdict(list)
        # Adjacency list: entity -> [(predicate, target_entity, chunk_id)]
        self._graph: dict[str, list[tuple[str, str, int]]] = defaultdict(list)

    def _normalize_entity(self, name: str) -> str:
        """Normalize entity name to canonical form."""
        name = name.lower().strip().rstrip("s.")  # lowercase, strip trailing s/period
        # Remove common noise prefixes
        for prefix in ("the ", "a ", "an "):
            if name.startswith(prefix):
                name = name[len(prefix):]
        return self._ALIASES.get(name, name)

    def extract_from_chunk(self, chunk_id: int, content: str) -> None:
        """Extract entities and relations from a single chunk."""
        try:
            result = self.llm.extract_json(self.EXTRACT_PROMPT, content[:2000])
        except (ValueError, Exception):
            return

        if not isinstance(result, dict):
            return

        # Extract entities
        for ent in result.get("entities", []):
            if isinstance(ent, dict) and "name" in ent:
                name = self._normalize_entity(ent["name"])
                if name and len(name) > 1:
                    self.entities[name] = Entity(
                        name=name,
                        entity_type=ent.get("type", "concept"),
                        chunk_id=chunk_id,
                    )
                    self._entity_to_chunks[name].add(chunk_id)

        # Extract relations
        for rel in result.get("relations", []):
            if not isinstance(rel, dict):
                continue
            subj = self._normalize_entity(rel.get("subject", ""))
            pred = rel.get("predicate", "").strip()
            obj = self._normalize_entity(rel.get("object", ""))
            conf = float(rel.get("confidence", 0.8))
            if subj and pred and obj:
                relation = Relation(subj, pred, obj, chunk_id, conf)
                self.relations.append(relation)
                self._chunk_relations[chunk_id].append(relation)
                self._graph[subj].append((pred, obj, chunk_id))
                self._entity_to_chunks[subj].add(chunk_id)
                self._entity_to_chunks[obj].add(chunk_id)

    def build_from_db(self, limit: int | None = None) -> None:
        """Build graph from all chunks in the database."""
        query = "SELECT id, content FROM chunks"
        params: list = []
        if limit:
            query += " LIMIT ?"
            params.append(limit)

        rows = self.conn.execute(query, params).fetchall()
        for row in rows:
            self.extract_from_chunk(row["id"], row["content"])

    def find_direct_contradictions(self) -> list[Contradiction]:
        """Find pairs of relations about the same subject that contradict."""
        contradictions: list[Contradiction] = []

        # Group relations by subject
        by_subject: dict[str, list[Relation]] = defaultdict(list)
        for rel in self.relations:
            by_subject[rel.subject].append(rel)

        # Check pairs within each subject group
        for subject, rels in by_subject.items():
            if len(rels) < 2:
                continue

            # Compare pairs from DIFFERENT chunks
            for i in range(len(rels)):
                for j in range(i + 1, len(rels)):
                    r_a, r_b = rels[i], rels[j]
                    if r_a.chunk_id == r_b.chunk_id:
                        continue

                    # Quick heuristic: similar predicates, different objects
                    if self._might_contradict(r_a, r_b):
                        # LLM verification
                        contradiction = self._verify_contradiction(r_a, r_b)
                        if contradiction:
                            contradictions.append(contradiction)

        return contradictions

    def find_transitive_contradictions(self, max_depth: int = 3) -> list[Contradiction]:
        """Find contradictions through relation chains.

        A implies B, B contradicts C → A transitively conflicts with C.
        """
        contradictions: list[Contradiction] = []
        direct = {(c.chunk_id_a, c.chunk_id_b) for c in self.find_direct_contradictions()}

        # For each entity, do BFS through the graph
        visited_pairs: set[tuple[int, int]] = set()

        for entity in self._graph:
            # BFS from this entity
            queue: list[tuple[str, list[int]]] = [(entity, [])]
            visited: set[str] = {entity}

            while queue:
                current, path_chunks = queue.pop(0)
                if len(path_chunks) >= max_depth:
                    continue

                for pred, target, chunk_id in self._graph.get(current, []):
                    if target in visited:
                        continue
                    visited.add(target)

                    new_path = path_chunks + [chunk_id]

                    # Check if target entity has claims in other chunks
                    for other_pred, other_target, other_chunk in self._graph.get(target, []):
                        if other_chunk in new_path:
                            continue

                        # Check if first and last chunk in path directly contradict
                        pair = (min(new_path[0], other_chunk), max(new_path[0], other_chunk))
                        if pair in visited_pairs:
                            continue
                        if pair in direct:
                            continue

                        # Check if the claim chain creates a contradiction
                        first_rel = self._chunk_relations[new_path[0]][0] if self._chunk_relations[new_path[0]] else None
                        last_rel = Relation(target, other_pred, other_target, other_chunk)

                        if first_rel and self._might_contradict(first_rel, last_rel):
                            c = self._verify_contradiction(
                                first_rel, last_rel,
                                contradiction_type="transitive",
                                path=new_path + [other_chunk],
                            )
                            if c:
                                contradictions.append(c)
                                visited_pairs.add(pair)

                    queue.append((target, new_path))

        return contradictions

    def find_contradiction_clusters(self) -> list[list[int]]:
        """Find groups of mutually contradicting chunks via connected components."""
        all_contradictions = self.find_direct_contradictions()

        # Build adjacency from contradictions
        adj: dict[int, set[int]] = defaultdict(set)
        for c in all_contradictions:
            adj[c.chunk_id_a].add(c.chunk_id_b)
            adj[c.chunk_id_b].add(c.chunk_id_a)

        # Find connected components
        visited: set[int] = set()
        clusters: list[list[int]] = []

        for node in adj:
            if node in visited:
                continue
            cluster: list[int] = []
            stack = [node]
            while stack:
                n = stack.pop()
                if n in visited:
                    continue
                visited.add(n)
                cluster.append(n)
                stack.extend(adj[n] - visited)
            if len(cluster) >= 2:
                clusters.append(sorted(cluster))

        return clusters

    def get_stats(self) -> KnowledgeGraphStats:
        """Get graph statistics."""
        direct = self.find_direct_contradictions()
        transitive = self.find_transitive_contradictions()
        clusters = self.find_contradiction_clusters()

        return KnowledgeGraphStats(
            n_entities=len(self.entities),
            n_relations=len(self.relations),
            n_chunks=len(set(r.chunk_id for r in self.relations)),
            n_direct_contradictions=len(direct),
            n_transitive_contradictions=len(transitive),
            contradiction_clusters=clusters,
        )

    def _might_contradict(self, a: Relation, b: Relation) -> bool:
        """Quick heuristic check if two relations might contradict."""
        # Same subject from different chunks: always worth checking
        if a.subject == b.subject and a.chunk_id != b.chunk_id:
            return True

        # Check for negation patterns even with different subjects
        negation_pairs = {
            ("uses", "does not use"), ("is", "is not"),
            ("supports", "does not support"), ("requires", "does not require"),
            ("enables", "prevents"), ("improves", "degrades"),
            ("corrupts", "creates"), ("should", "should never"),
        }
        pred_a = a.predicate.lower()
        pred_b = b.predicate.lower()
        for pos, neg in negation_pairs:
            if (pos in pred_a and neg in pred_b) or (neg in pred_a and pos in pred_b):
                return True

        return False

    def _verify_contradiction(
        self,
        a: Relation,
        b: Relation,
        contradiction_type: str = "direct",
        path: list[int] | None = None,
    ) -> Contradiction | None:
        """Use LLM to verify if two relations actually contradict."""
        try:
            result = self.llm.extract_json(
                self.CONTRADICTION_PROMPT,
                f"Claim A: {a.subject} {a.predicate} {a.object}\n"
                f"Claim B: {b.subject} {b.predicate} {b.object}",
            )
            if isinstance(result, dict) and result.get("contradicts"):
                return Contradiction(
                    chunk_id_a=a.chunk_id,
                    chunk_id_b=b.chunk_id,
                    relation_a=a,
                    relation_b=b,
                    contradiction_type=contradiction_type,
                    path=path or [a.chunk_id, b.chunk_id],
                    confidence=float(result.get("confidence", 0.5)),
                    description=result.get("explanation", ""),
                )
        except Exception:
            pass
        return None
