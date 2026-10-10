"""Laptop live view: the snapshot arrives first, then events, plus keep-alives."""

from __future__ import annotations

import json

import httpx

from .conftest import next_event, photo_meta, upload_through_hooks


def test_snapshot_then_live_events(live_server, settings, image_bytes):
    with httpx.Client(base_url=live_server) as http:
        created = http.post("/api/sessions").json()
        session_id, owner = created["session_id"], created["owner_token"]
        before = upload_through_hooks(
            http, settings, photo_meta(created, "before.jpg"), image_bytes, tus_id="before"
        )

        with http.stream(
            "GET",
            f"/api/sessions/{session_id}/events",
            headers={"Authorization": f"Bearer {owner}"},
        ) as response:
            assert response.status_code == 200
            assert response.headers["content-type"].startswith("text/event-stream")
            lines = response.iter_lines()

            name, data = next_event(lines)
            assert name == "snapshot"
            snapshot = json.loads(data)
            assert [asset["id"] for asset in snapshot["assets"]] == [before]

            # Something published while the stream is open must arrive next, in order.
            during = upload_through_hooks(
                http, settings, photo_meta(created, "during.jpg"), image_bytes, tus_id="during"
            )
            received = []
            while len(received) < 3:
                name, data = next_event(lines)
                assert name != "snapshot", "only one snapshot per connection"
                event = json.loads(data)
                if event.get("id") == during:
                    received.append((name, event["status"]))
            assert received == [
                ("asset.created", "uploading"),
                ("asset.stored", "stored"),
                ("asset.ready", "ready"),
            ]


def test_events_reach_a_second_subscriber(live_server, settings, image_bytes):
    with httpx.Client(base_url=live_server) as http:
        created = http.post("/api/sessions").json()
        session_id, owner = created["session_id"], created["owner_token"]
        url = f"/api/sessions/{session_id}/events"

        with http.stream("GET", url, headers={"Authorization": f"Bearer {owner}"}) as response:
            lines = response.iter_lines()
            assert next_event(lines)[0] == "snapshot"
            asset_id = upload_through_hooks(
                http, settings, photo_meta(created), image_bytes, tus_id="second"
            )
            name, data = next_event(lines)
            assert name == "asset.created"
            assert json.loads(data)["id"] == asset_id


def test_events_require_the_owner_token(live_server):
    with httpx.Client(base_url=live_server) as http:
        created = http.post("/api/sessions").json()
        assert http.get(f"/api/sessions/{created['session_id']}/events").status_code == 401
        # EventSource cannot set headers, so ?token= is accepted here
        assert http.get(
            f"/api/sessions/{created['session_id']}/events?token={created['pair_token']}"
        ).status_code == 401


def test_keep_alive_comment_keeps_idle_connections_open(live_server, monkeypatch):
    monkeypatch.setattr("backend.api.KEEPALIVE_SECONDS", 0.2)
    with httpx.Client(base_url=live_server) as http:
        created = http.post("/api/sessions").json()
        url = f"/api/sessions/{created['session_id']}/events"
        with http.stream("GET", url, headers={"Authorization": f"Bearer {created['owner_token']}"}) as response:
            lines = response.iter_lines()
            assert next_event(lines)[0] == "snapshot"
            # nothing is published, so the only thing coming is the keep-alive comment
            comment = next(line for line in lines if line.startswith(":"))
            assert comment == ": keep-alive"