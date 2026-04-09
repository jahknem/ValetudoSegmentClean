#!/usr/bin/env python3
"""Live validation harness for Valetudo Segment Cleaner deployment checks."""

from __future__ import annotations

import argparse
import json
import socket
import sys
import time
from dataclasses import dataclass
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from typing import Any

import requests
from paho.mqtt import client as mqtt


@dataclass
class CheckResult:
    name: str
    ok: bool
    detail: str


def _load_helpers(repo_root: Path) -> Any:
    helpers_path = repo_root / "custom_components" / "valetudo_segment_cleaner" / "helpers.py"
    spec = spec_from_file_location("valetudo_helpers", helpers_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load helpers from {helpers_path}")
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _tcp_check(host: str, port: int, timeout: float = 3.0) -> CheckResult:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return CheckResult(f"tcp:{host}:{port}", True, "reachable")
    except OSError as err:
        return CheckResult(f"tcp:{host}:{port}", False, str(err))


def _http_check(base_url: str, timeout: float = 5.0) -> CheckResult:
    try:
        response = requests.get(f"{base_url}/api/", timeout=timeout)
        if response.status_code == 401:
            return CheckResult("ha_http_api", True, "401 Unauthorized expected without token")
        return CheckResult("ha_http_api", False, f"unexpected status {response.status_code}")
    except requests.RequestException as err:
        return CheckResult("ha_http_api", False, str(err))


def _mqtt_probe(
    host: str,
    port: int,
    username: str,
    password: str,
    topic: str,
    listen_seconds: int,
) -> tuple[CheckResult, dict[str, str]]:
    connected = {"ok": False, "detail": "not connected"}
    captured: dict[str, str] = {}

    def on_connect(client, userdata, flags, reason_code, properties=None):  # type: ignore[no-untyped-def]
        reason_text = str(reason_code)
        if reason_text.lower() == "success":
            connected["ok"] = True
            connected["detail"] = "connected"
            client.subscribe(topic, qos=0)
        else:
            connected["ok"] = False
            connected["detail"] = f"connect failed: {reason_text}"

    def on_message(client, userdata, msg):  # type: ignore[no-untyped-def]
        captured[msg.topic] = msg.payload.decode("utf-8", errors="replace")

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.username_pw_set(username, password)
    client.on_connect = on_connect
    client.on_message = on_message

    try:
        client.connect(host, port, keepalive=20)
    except OSError as err:
        return CheckResult("mqtt_auth", False, str(err)), captured

    client.loop_start()
    time.sleep(listen_seconds)
    client.loop_stop()
    client.disconnect()

    if not connected["ok"]:
        return CheckResult("mqtt_auth", False, connected["detail"]), captured

    detail = f"connected; captured {len(captured)} messages on {topic}"
    return CheckResult("mqtt_auth", True, detail), captured


def _analyze_valetudo(helpers: Any, payloads: dict[str, str]) -> tuple[CheckResult, dict[str, Any]]:
    segment_topics = [
        topic for topic in payloads if topic.startswith("valetudo/") and topic.endswith("/MapData/segments")
    ]
    capability_topics = [
        topic for topic in payloads if "/MapSegmentationCapability/clean" in topic
    ]

    robots: dict[str, dict[str, Any]] = {}
    for topic in segment_topics:
        parts = topic.split("/")
        if len(parts) < 4:
            continue
        robot_id = parts[1]
        payload = payloads[topic]
        segments = helpers.parse_segments_from_mqtt_payload(payload)
        name_map = helpers.to_name_id_map(segments)
        robots[robot_id] = {
            "segment_count": len(segments),
            "sample_segment_names": [seg.get("name") for seg in segments[:6]],
            "name_map_size": len(name_map),
        }

    if not robots:
        return (
            CheckResult(
                "valetudo_segments",
                False,
                "no segment payloads found under valetudo/+/MapData/segments",
            ),
            {"robots": robots, "capability_topics": sorted(capability_topics)},
        )

    detail = f"robots discovered: {', '.join(sorted(robots))}"
    return (
        CheckResult("valetudo_segments", True, detail),
        {"robots": robots, "capability_topics": sorted(capability_topics)},
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate live HA+MQTT+Valetudo connectivity and payloads")
    parser.add_argument("--ha-host", default="192.168.178.10")
    parser.add_argument("--ha-port", type=int, default=8123)
    parser.add_argument("--mqtt-host", default="192.168.178.10")
    parser.add_argument("--mqtt-port", type=int, default=1883)
    parser.add_argument("--mqtt-user", default="zigbee2mqtt")
    parser.add_argument("--mqtt-pass", default="wbV=.4zpPNL=3RZN:FTV")
    parser.add_argument("--mqtt-topic", default="valetudo/#")
    parser.add_argument("--listen-seconds", type=int, default=5)
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[1]
    helpers = _load_helpers(repo_root)

    results: list[CheckResult] = []
    results.append(_tcp_check(args.ha_host, args.ha_port))
    results.append(_tcp_check(args.mqtt_host, args.mqtt_port))
    results.append(_http_check(f"http://{args.ha_host}:{args.ha_port}"))

    mqtt_result, payloads = _mqtt_probe(
        args.mqtt_host,
        args.mqtt_port,
        args.mqtt_user,
        args.mqtt_pass,
        args.mqtt_topic,
        args.listen_seconds,
    )
    results.append(mqtt_result)

    valetudo_result, analysis = _analyze_valetudo(helpers, payloads)
    results.append(valetudo_result)

    print("=== Live Validation Results ===")
    for result in results:
        status = "OK" if result.ok else "FAIL"
        print(f"[{status}] {result.name}: {result.detail}")

    print("\n=== Discovery Analysis ===")
    print(json.dumps(analysis, indent=2, ensure_ascii=True))

    failed = [r for r in results if not r.ok]
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
