from __future__ import annotations


def channel_from_topic(topic: str) -> str | None:
    parts = topic.split(".")
    if len(parts) >= 3 and parts[0] == "channel" and parts[1] in {
        "broadcast",
        "dead_letter",
        "connection",
    }:
        return parts[2]
    return None


def runtime_from_topic(topic: str) -> str | None:
    marker = ".runtime."
    if marker not in topic:
        return None
    return topic.split(marker, 1)[1].split(".", 1)[0] or None


def connection_from_topic(topic: str) -> str | None:
    marker = ".connection."
    if marker not in topic:
        return None
    tail = topic.split(marker, 1)[1]
    return tail.split(".", 1)[0] or None
