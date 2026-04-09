from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

HELPERS_PATH = (
    Path(__file__).resolve().parents[1]
    / "custom_components"
    / "valetudo_segment_cleaner"
    / "helpers.py"
)

SPEC = spec_from_file_location("valetudo_segment_cleaner_helpers", HELPERS_PATH)
assert SPEC and SPEC.loader
HELPERS = module_from_spec(SPEC)
SPEC.loader.exec_module(HELPERS)

parse_segments_payload = HELPERS.parse_segments_payload
resolve_segment_ids = HELPERS.resolve_segment_ids
to_name_id_map = HELPERS.to_name_id_map
extract_robot_id_from_topic = HELPERS.extract_robot_id_from_topic
parse_segments_from_mqtt_payload = HELPERS.parse_segments_from_mqtt_payload


def test_parse_segments_payload_from_plain_list() -> None:
    payload = [{"id": 16, "name": "Kitchen"}, {"id": 18, "name": "Hall"}]
    segments = parse_segments_payload(payload)
    assert segments == payload


def test_parse_segments_payload_from_nested_segment_id_to_name() -> None:
    payload = {"metaData": {"segmentIdToName": {"16": "Kitchen", "18": "Hall"}}}
    segments = parse_segments_payload(payload)
    assert {item["id"] for item in segments} == {16, 18}


def test_to_name_id_map_case_insensitive() -> None:
    mapping = to_name_id_map([{"id": 16, "name": "Kitchen"}, {"id": 18, "name": "Hall"}])
    assert mapping["kitchen"] == 16
    assert mapping["hall"] == 18


def test_resolve_segment_ids_deduplicates_and_tracks_unknown() -> None:
    ids, unresolved = resolve_segment_ids(
        ["Kitchen", "kitchen", "Hall", "Unknown"],
        {"kitchen": 16, "hall": 18},
    )
    assert ids == [16, 18]
    assert unresolved == ["Unknown"]


def test_extract_robot_id_from_topic() -> None:
    robot_id = extract_robot_id_from_topic(
        "valetudo/roborock/MapData/map-data-hass",
        "valetudo",
    )
    assert robot_id == "roborock"


def test_parse_segments_from_mqtt_payload() -> None:
    payload = '{"segments": [{"id": 1, "name": "Kitchen"}, {"id": 2, "name": "Hall"}]}'
    segments = parse_segments_from_mqtt_payload(payload)
    assert segments == [{"id": 1, "name": "Kitchen"}, {"id": 2, "name": "Hall"}]


def test_parse_segments_from_mqtt_payload_bare_mapping() -> None:
    payload = '{"16":"Office","17":"Kueche","18":"Klo"}'
    segments = parse_segments_from_mqtt_payload(payload)
    assert segments == [
        {"id": 16, "name": "Office"},
        {"id": 17, "name": "Kueche"},
        {"id": 18, "name": "Klo"},
    ]
