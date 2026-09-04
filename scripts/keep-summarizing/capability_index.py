#!/usr/bin/env python3
"""Versioned semantic capability records with deterministic validation."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
from types import MappingProxyType
from typing import Any, Mapping, Sequence


NODE_KINDS = frozenset({"domain", "capability", "constraint_capability"})
LIFECYCLES = frozenset({"candidate", "grounded", "accepted", "superseded"})
FRESHNESS = frozenset({"current", "stale"})
RELATION_TYPES = frozenset(
    {"contains", "requires", "constrains", "produces", "consumes", "transitions", "validates", "conflicts_with", "related_to"}
)
EVIDENCE_KINDS = frozenset({"accepted_spec", "knowledge", "public_contract", "integration_test", "history", "source"})
IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")
NODE_FIELDS = frozenset(
    {
        "node_id", "kind", "title", "summary", "actor", "outcome", "preconditions",
        "effects", "failures", "policies", "aliases", "lifecycle", "freshness",
        "parent_id", "evidence_ids",
    }
)
RELATION_FIELDS = frozenset({"relation_id", "from_id", "to_id", "type", "evidence_ids"})
EVIDENCE_FIELDS = frozenset({"evidence_id", "kind", "locator", "identity", "authority", "observed_at"})
INDEX_FIELDS = frozenset({"schema_version", "index_id", "nodes", "relations", "evidence", "generated_at", "source_digest"})


class CapabilityIndexError(ValueError):
    """Raised when semantic capability data violates API-008."""


def _record(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise CapabilityIndexError(f"{label} must be an object")
    return dict(value)


def _closed(record: Mapping[str, Any], fields: frozenset[str], label: str) -> None:
    missing = fields - record.keys()
    unknown = record.keys() - fields
    if missing:
        raise CapabilityIndexError(f"{label} missing fields: {', '.join(sorted(missing))}")
    if unknown:
        raise CapabilityIndexError(f"{label} has unknown fields: {', '.join(sorted(unknown))}")


def _identifier(value: object, label: str) -> str:
    if not isinstance(value, str) or not IDENTIFIER.fullmatch(value):
        raise CapabilityIndexError(f"{label} must be a stable identifier")
    return value


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CapabilityIndexError(f"{label} must be a nonempty string")
    return value


def _strings(value: object, label: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise CapabilityIndexError(f"{label} must be a list")
    result = tuple(_text(item, f"{label} item") for item in value)
    if len(result) != len(set(result)):
        raise CapabilityIndexError(f"{label} contains duplicates")
    return result


@dataclass(frozen=True)
class FeatureUnit:
    node_id: str
    kind: str
    title: str
    summary: str
    actor: str
    outcome: str
    preconditions: tuple[str, ...]
    effects: tuple[str, ...]
    failures: tuple[str, ...]
    policies: tuple[str, ...]
    aliases: tuple[str, ...]
    lifecycle: str
    freshness: str
    parent_id: str | None
    evidence_ids: tuple[str, ...]

    @classmethod
    def from_dict(cls, value: object) -> "FeatureUnit":
        record = _record(value, "node")
        _closed(record, NODE_FIELDS, "node")
        kind = _text(record["kind"], "node.kind")
        lifecycle = _text(record["lifecycle"], "node.lifecycle")
        freshness = _text(record["freshness"], "node.freshness")
        if kind not in NODE_KINDS:
            raise CapabilityIndexError(f"invalid node kind: {kind}")
        if lifecycle not in LIFECYCLES:
            raise CapabilityIndexError(f"invalid node lifecycle: {lifecycle}")
        if freshness not in FRESHNESS:
            raise CapabilityIndexError(f"invalid node freshness: {freshness}")
        parent = record["parent_id"]
        if parent is not None:
            parent = _identifier(parent, "node.parent_id")
        return cls(
            node_id=_identifier(record["node_id"], "node.node_id"),
            kind=kind,
            title=_text(record["title"], "node.title"),
            summary=_text(record["summary"], "node.summary"),
            actor=_text(record["actor"], "node.actor"),
            outcome=_text(record["outcome"], "node.outcome"),
            preconditions=_strings(record["preconditions"], "node.preconditions"),
            effects=_strings(record["effects"], "node.effects"),
            failures=_strings(record["failures"], "node.failures"),
            policies=_strings(record["policies"], "node.policies"),
            aliases=_strings(record["aliases"], "node.aliases"),
            lifecycle=lifecycle,
            freshness=freshness,
            parent_id=parent,
            evidence_ids=_strings(record["evidence_ids"], "node.evidence_ids"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id, "kind": self.kind, "title": self.title,
            "summary": self.summary, "actor": self.actor, "outcome": self.outcome,
            "preconditions": list(self.preconditions), "effects": list(self.effects),
            "failures": list(self.failures), "policies": list(self.policies),
            "aliases": list(self.aliases), "lifecycle": self.lifecycle,
            "freshness": self.freshness, "parent_id": self.parent_id,
            "evidence_ids": list(self.evidence_ids),
        }


@dataclass(frozen=True)
class FeatureRelation:
    relation_id: str
    from_id: str
    to_id: str
    type: str
    evidence_ids: tuple[str, ...]

    @classmethod
    def from_dict(cls, value: object) -> "FeatureRelation":
        record = _record(value, "relation")
        _closed(record, RELATION_FIELDS, "relation")
        relation_type = _text(record["type"], "relation.type")
        if relation_type not in RELATION_TYPES:
            raise CapabilityIndexError(f"invalid relation type: {relation_type}")
        return cls(
            relation_id=_identifier(record["relation_id"], "relation.relation_id"),
            from_id=_identifier(record["from_id"], "relation.from_id"),
            to_id=_identifier(record["to_id"], "relation.to_id"),
            type=relation_type,
            evidence_ids=_strings(record["evidence_ids"], "relation.evidence_ids"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "relation_id": self.relation_id, "from_id": self.from_id,
            "to_id": self.to_id, "type": self.type,
            "evidence_ids": list(self.evidence_ids),
        }


@dataclass(frozen=True)
class EvidenceRecord:
    evidence_id: str
    kind: str
    locator: str
    identity: str
    authority: object
    observed_at: str

    @classmethod
    def from_dict(cls, value: object) -> "EvidenceRecord":
        record = _record(value, "evidence")
        _closed(record, EVIDENCE_FIELDS, "evidence")
        kind = _text(record["kind"], "evidence.kind")
        if kind not in EVIDENCE_KINDS:
            raise CapabilityIndexError(f"invalid evidence kind: {kind}")
        authority = record["authority"]
        if not isinstance(authority, (bool, str)) or isinstance(authority, str) and not authority.strip():
            raise CapabilityIndexError("evidence.authority must be a boolean or nonempty string")
        return cls(
            evidence_id=_identifier(record["evidence_id"], "evidence.evidence_id"), kind=kind,
            locator=_text(record["locator"], "evidence.locator"),
            identity=_text(record["identity"], "evidence.identity"), authority=authority,
            observed_at=_text(record["observed_at"], "evidence.observed_at"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "evidence_id": self.evidence_id, "kind": self.kind, "locator": self.locator,
            "identity": self.identity, "authority": self.authority,
            "observed_at": self.observed_at,
        }


@dataclass(frozen=True)
class CapabilityIndex:
    schema_version: str
    index_id: str
    nodes: tuple[FeatureUnit, ...]
    relations: tuple[FeatureRelation, ...]
    evidence: tuple[EvidenceRecord, ...]
    generated_at: str
    source_digest: str
    extensions: Mapping[str, Any]

    @classmethod
    def from_dict(cls, value: object) -> "CapabilityIndex":
        record = _record(value, "capability index")
        missing = INDEX_FIELDS - record.keys()
        if missing:
            raise CapabilityIndexError(f"capability index missing fields: {', '.join(sorted(missing))}")
        for field in ("nodes", "relations", "evidence"):
            if not isinstance(record[field], list):
                raise CapabilityIndexError(f"capability index.{field} must be a list")
        nodes = tuple(FeatureUnit.from_dict(item) for item in record["nodes"])
        relations = tuple(FeatureRelation.from_dict(item) for item in record["relations"])
        evidence = tuple(EvidenceRecord.from_dict(item) for item in record["evidence"])
        index = cls(
            schema_version=_text(record["schema_version"], "capability index.schema_version"),
            index_id=_identifier(record["index_id"], "capability index.index_id"),
            nodes=nodes, relations=relations, evidence=evidence,
            generated_at=_text(record["generated_at"], "capability index.generated_at"),
            source_digest=_text(record["source_digest"], "capability index.source_digest"),
            extensions=MappingProxyType({key: record[key] for key in record.keys() - INDEX_FIELDS}),
        )
        index._validate_graph()
        return index

    def _validate_graph(self) -> None:
        node_ids = [node.node_id for node in self.nodes]
        relation_ids = [relation.relation_id for relation in self.relations]
        evidence_ids = [item.evidence_id for item in self.evidence]
        if len(node_ids) != len(set(node_ids)):
            raise CapabilityIndexError("duplicate node_id")
        if len(relation_ids) != len(set(relation_ids)):
            raise CapabilityIndexError("duplicate relation_id")
        if len(evidence_ids) != len(set(evidence_ids)):
            raise CapabilityIndexError("duplicate evidence_id")
        known_nodes, known_evidence = set(node_ids), set(evidence_ids)
        contains: dict[str, list[str]] = {node_id: [] for node_id in node_ids}
        parent_edges: dict[str, list[str]] = {node_id: [] for node_id in node_ids}
        for relation in self.relations:
            if relation.from_id not in known_nodes:
                raise CapabilityIndexError(f"relation has unknown from_id: {relation.from_id}")
            if relation.to_id not in known_nodes:
                raise CapabilityIndexError(f"relation has unknown to_id: {relation.to_id}")
            if not set(relation.evidence_ids) <= known_evidence:
                raise CapabilityIndexError("relation references unknown evidence_id")
            if relation.type == "contains":
                contains[relation.from_id].append(relation.to_id)
                parent_edges[relation.to_id].append(relation.from_id)
        for node in self.nodes:
            if not set(node.evidence_ids) <= known_evidence:
                raise CapabilityIndexError("node references unknown evidence_id")
            if node.parent_id is None:
                if node.kind != "domain":
                    raise CapabilityIndexError(f"node {node.node_id} must have exactly one parent")
                if parent_edges[node.node_id]:
                    raise CapabilityIndexError(f"domain root {node.node_id} has a canonical parent relation")
            elif parent_edges[node.node_id] != [node.parent_id]:
                raise CapabilityIndexError(f"node {node.node_id} canonical parent relation does not match parent_id")
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(node_id: str) -> None:
            if node_id in visiting:
                raise CapabilityIndexError("contains cycle")
            if node_id in visited:
                return
            visiting.add(node_id)
            for child in contains[node_id]:
                visit(child)
            visiting.remove(node_id)
            visited.add(node_id)

        for node_id in sorted(known_nodes):
            visit(node_id)

    def node(self, node_id: str) -> FeatureUnit:
        for node in self.nodes:
            if node.node_id == node_id:
                return node
        raise KeyError(node_id)

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "schema_version": self.schema_version, "index_id": self.index_id,
            "nodes": [node.to_dict() for node in self.nodes],
            "relations": [relation.to_dict() for relation in self.relations],
            "evidence": [item.to_dict() for item in self.evidence],
            "generated_at": self.generated_at, "source_digest": self.source_digest,
        }
        payload.update(dict(self.extensions))
        return payload

    @classmethod
    def load(cls, path: Path) -> "CapabilityIndex":
        try:
            return cls.from_dict(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError) as exc:
            raise CapabilityIndexError(f"cannot load capability index: {exc}") from exc

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")


@dataclass(frozen=True)
class RankedCandidate:
    node_id: str
    score: float
    semantic_score: float
    relation_relevance: float
    authority_support: float
    risk_relevance: float
    trusted: bool


def _tokens(value: str) -> set[str]:
    return {token.casefold() for token in re.findall(r"[A-Za-z0-9_]+", value) if len(token) > 1}


def _authority_supported(index: CapabilityIndex, node: FeatureUnit) -> bool:
    authoritative = {
        item.evidence_id
        for item in index.evidence
        if item.authority is True
        or isinstance(item.authority, str)
        and item.authority.casefold() in {"authoritative", "accepted", "current", "confirmed"}
    }
    return bool(set(node.evidence_ids) & authoritative)


def _semantic_score(node: FeatureUnit, query_tokens: set[str]) -> float:
    weighted_fields: Sequence[tuple[Sequence[str], float]] = (
        ((node.title,), 3.0),
        ((node.summary,), 2.0),
        (node.aliases, 4.0),
        ((node.actor, node.outcome), 1.0),
        (node.preconditions + node.effects + node.failures + node.policies, 1.5),
    )
    return sum(
        len(query_tokens & _tokens(" ".join(values))) * weight
        for values, weight in weighted_fields
    )


def rank_candidates(
    index: CapabilityIndex,
    query_text: str,
    *,
    domain_hints: Sequence[str] = (),
) -> tuple[RankedCandidate, ...]:
    """Rank searchable nodes deterministically; trust is reported, never inferred from score."""
    query_tokens = _tokens(_text(query_text, "query_text"))
    hints = set(domain_hints)
    unknown_hints = hints - {node.node_id for node in index.nodes}
    if unknown_hints:
        raise CapabilityIndexError(f"unknown domain hints: {', '.join(sorted(unknown_hints))}")
    connected: dict[str, set[str]] = {node.node_id: set() for node in index.nodes}
    for relation in index.relations:
        connected[relation.from_id].add(relation.to_id)
        connected[relation.to_id].add(relation.from_id)
    risk_tokens = {
        "permission", "ownership", "destructive", "data", "external", "state",
        "transition", "compatibility", "conflict", "failure", "write", "delete",
    }
    ranked: list[RankedCandidate] = []
    for node in index.nodes:
        if node.lifecycle == "superseded":
            continue
        semantic = _semantic_score(node, query_tokens)
        if semantic <= 0:
            continue
        relation = 1.0 if hints and (node.parent_id in hints or connected[node.node_id] & hints) else 0.0
        authority = 1.0 if _authority_supported(index, node) else 0.0
        risk = float(len(query_tokens & risk_tokens & _tokens(" ".join(node.effects + node.failures + node.policies))))
        trusted = node.lifecycle in {"grounded", "accepted"} and node.freshness == "current" and bool(authority)
        generic_penalty = 0.5 if _tokens(node.title) <= {"capability", "domain", "constraint"} else 0.0
        score = semantic + relation + authority + risk - generic_penalty
        ranked.append(
            RankedCandidate(
                node_id=node.node_id, score=score, semantic_score=semantic,
                relation_relevance=relation, authority_support=authority,
                risk_relevance=risk, trusted=trusted,
            )
        )
    return tuple(sorted(ranked, key=lambda item: (-item.score, item.node_id)))


def retrieve_by_intent(
    index: CapabilityIndex,
    query_text: str,
    *,
    domain_hints: Sequence[str] = (),
    trusted_only: bool = True,
    limit: int | None = None,
) -> tuple[RankedCandidate, ...]:
    """Retrieve ranked candidates, excluding advisory candidates from trusted context by default."""
    if limit is not None and (not isinstance(limit, int) or isinstance(limit, bool) or limit < 1):
        raise CapabilityIndexError("limit must be a positive integer")
    candidates = rank_candidates(index, query_text, domain_hints=domain_hints)
    if trusted_only:
        candidates = tuple(item for item in candidates if item.trusted)
    return candidates[:limit]


@dataclass(frozen=True)
class TraversalEntry:
    node_id: str
    depth: int


@dataclass(frozen=True)
class TraversalResult:
    depth: str
    inclusions: tuple[TraversalEntry, ...]
    frontier: tuple[str, ...]
    stopping_reason: str


TRAVERSAL_DEPTHS = MappingProxyType({"light": 1, "standard": 2, "deep": 4})


def traverse_capabilities(
    index: CapabilityIndex,
    start_ids: Sequence[str],
    *,
    depth: str = "standard",
    max_nodes: int = 32,
    relation_types: Sequence[str] | None = None,
) -> TraversalResult:
    """Traverse outgoing typed relations with explicit deterministic budgets."""
    if depth not in TRAVERSAL_DEPTHS:
        raise CapabilityIndexError("depth must be light, standard, or deep")
    if not isinstance(max_nodes, int) or isinstance(max_nodes, bool) or max_nodes < 1:
        raise CapabilityIndexError("max_nodes must be a positive integer")
    known = {node.node_id for node in index.nodes}
    starts = tuple(sorted(set(start_ids)))
    unknown = set(starts) - known
    if unknown:
        raise CapabilityIndexError(f"unknown start node: {', '.join(sorted(unknown))}")
    if not starts:
        raise CapabilityIndexError("at least one start node is required")
    allowed_types = set(relation_types) if relation_types is not None else set(RELATION_TYPES)
    invalid_types = allowed_types - RELATION_TYPES
    if invalid_types:
        raise CapabilityIndexError(f"unknown relation types: {', '.join(sorted(invalid_types))}")
    outgoing: dict[str, set[str]] = {node_id: set() for node_id in known}
    for relation in index.relations:
        if relation.type in allowed_types:
            outgoing[relation.from_id].add(relation.to_id)

    depth_limit = TRAVERSAL_DEPTHS[depth]
    queue: list[tuple[str, int]] = [(node_id, 0) for node_id in starts]
    queued = set(starts)
    visited: set[str] = set()
    inclusions: list[TraversalEntry] = []
    frontier: set[str] = set()
    depth_stopped = False
    while queue:
        node_id, current_depth = queue.pop(0)
        queued.discard(node_id)
        if node_id in visited:
            continue
        if len(inclusions) >= max_nodes:
            frontier.add(node_id)
            frontier.update(item[0] for item in queue if item[0] not in visited)
            break
        visited.add(node_id)
        inclusions.append(TraversalEntry(node_id=node_id, depth=current_depth))
        neighbors = sorted(outgoing[node_id] - visited)
        if current_depth >= depth_limit:
            if neighbors:
                depth_stopped = True
                frontier.update(neighbors)
            continue
        for neighbor in neighbors:
            if neighbor not in queued:
                queue.append((neighbor, current_depth + 1))
                queued.add(neighbor)
        queue.sort(key=lambda item: (item[1], item[0]))

    if frontier and len(inclusions) >= max_nodes:
        reason = "node_budget"
    elif depth_stopped:
        reason = "depth_budget"
    else:
        reason = "frontier_exhausted"
    return TraversalResult(
        depth=depth,
        inclusions=tuple(inclusions),
        frontier=tuple(sorted(frontier - visited)),
        stopping_reason=reason,
    )
