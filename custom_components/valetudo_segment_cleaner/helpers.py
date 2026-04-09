"""Helpers for parsing and resolving Valetudo segments."""

from __future__ import annotations

from collections.abc import Iterable
import json
from typing import Any


def _normalize_name(name: str) -> str:
    return name.strip().casefold()


def _extract_segments_from_iterable(values: Iterable[Any]) -> list[dict[str, int | str]]:
    segments: list[dict[str, int | str]] = []

    for value in values:
        if isinstance(value, dict):
            seg_id = value.get("id")
            seg_name = value.get("name")

            if isinstance(seg_id, int) and isinstance(seg_name, str):
                segments.append({"id": seg_id, "name": seg_name})
                continue

            nested_segments = parse_segments_payload(value)
            if nested_segments:
                segments.extend(nested_segments)

        elif isinstance(value, list):
            nested_segments = _extract_segments_from_iterable(value)
            if nested_segments:
                segments.extend(nested_segments)

    return segments


def parse_segments_payload(payload: Any) -> list[dict[str, int | str]]:
    """Attempt to parse segment list from varying Valetudo payload shapes."""
    if isinstance(payload, dict):
        if payload:
            maybe_mapping: list[dict[str, int | str]] = []
            all_pairs = True
            for seg_id, seg_name in payload.items():
                try:
                    parsed_id = int(seg_id)
                except (TypeError, ValueError):
                    all_pairs = False
                    break
                if not isinstance(seg_name, str):
                    all_pairs = False
                    break
                maybe_mapping.append({"id": parsed_id, "name": seg_name})
            if all_pairs and maybe_mapping:
                return maybe_mapping

        known_keys = ("segments", "segment", "data", "payload", "result", "map")

        for key in known_keys:
            if key in payload:
                segments = parse_segments_payload(payload[key])
                if segments:
                    return segments

        if "segmentIdToName" in payload and isinstance(payload["segmentIdToName"], dict):
            items = payload["segmentIdToName"].items()
            pairs = []
            for seg_id, seg_name in items:
                try:
                    parsed_id = int(seg_id)
                except (TypeError, ValueError):
                    continue
                if isinstance(seg_name, str):
                    pairs.append({"id": parsed_id, "name": seg_name})
            if pairs:
                return pairs

        recursive = _extract_segments_from_iterable(payload.values())
        if recursive:
            return recursive

    if isinstance(payload, list):
        parsed = _extract_segments_from_iterable(payload)
        if parsed:
            return parsed

    return []


def to_name_id_map(segments: list[dict[str, int | str]]) -> dict[str, int]:
    """Convert segment list to a case-insensitive name->id mapping."""
    mapping: dict[str, int] = {}
    for segment in segments:
        seg_name = segment.get("name")
        seg_id = segment.get("id")
        if isinstance(seg_name, str) and isinstance(seg_id, int):
            mapping[_normalize_name(seg_name)] = seg_id
    return mapping


def resolve_segment_ids(
    requested_names: list[str],
    name_to_id_map: dict[str, int],
) -> tuple[list[int], list[str]]:
    """Resolve names to ids, returning (resolved_ids, unresolved_names)."""
    resolved: list[int] = []
    unresolved: list[str] = []

    for name in requested_names:
        key = _normalize_name(name)
        if key in name_to_id_map:
            resolved.append(name_to_id_map[key])
        else:
            unresolved.append(name)

    # Remove duplicates while preserving order.
    deduped: list[int] = []
    seen: set[int] = set()
    for seg_id in resolved:
        if seg_id in seen:
            continue
        seen.add(seg_id)
        deduped.append(seg_id)

    return deduped, unresolved


def extract_robot_id_from_topic(topic: str, topic_prefix: str) -> str | None:
    """Extract robot ID from topics like valetudo/<robot_id>/MapData/map-data-hass."""
    normalized_prefix = topic_prefix.strip("/")
    parts = topic.strip("/").split("/")

    if len(parts) < 2:
        return None

    if parts[0] != normalized_prefix:
        return None

    return parts[1]


def parse_json_payload(payload: str) -> Any:
    """Parse JSON payload and return raw object, or None on decode failure."""
    try:
        return json.loads(payload)
    except json.JSONDecodeError:
        return None


def parse_segments_from_mqtt_payload(payload: str) -> list[dict[str, int | str]]:
    """Parse segment objects from MQTT JSON payload text."""
    parsed = parse_json_payload(payload)
    if parsed is None:
        return []
    return parse_segments_payload(parsed)
