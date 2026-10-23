"""Distinguish valid empty results from unavailable reads. Never renew success time on failure."""
from __future__ import annotations


def read_block(key, reader, args, previous, fetched, statuses, now, reuse):
    if reuse and key in previous and previous[key] is not None:
        statuses[key] = {"state": "cached", "attempted_at": now.isoformat()}
        return previous[key], False
    try:
        value = reader(*args)
    except Exception as error:
        statuses[key] = {"state": "error", "attempted_at": now.isoformat(), "reason": type(error).__name__}
        return previous.get(key), False
    if value is None or value == {}:
        statuses[key] = {"state": "error", "attempted_at": now.isoformat(), "reason": "unavailable"}
        return previous.get(key), False
    fetched[key] = now.isoformat()
    statuses[key] = {"state": "ok", "attempted_at": now.isoformat()}
    return value, True
