"""Read KB prices in the frequent encrypted publication; no Sheet writes or waiting loops."""
from datetime import datetime, timedelta, timezone
import json
from math import isfinite
from pathlib import Path

KST = timezone(timedelta(hours=9))
ROOT = Path(__file__).resolve().parent.parent


def expected_date(now):
    now = now.astimezone(KST)
    friday = now.date() - timedelta(days=(now.weekday()-4) % 7)
    if now.weekday() == 4 and now.hour < 8:
        friday -= timedelta(days=7)
    return friday.isoformat()


def refresh_due(previous, fetched, now):
    now = now.astimezone(KST)
    target = expected_date(now)
    pending = bool((previous or {}).get("errors")) or any(str(a.get("asof") or "") < target for a in (previous or {}).get("assets", []))
    ttl = 5 if now.weekday() == 4 and now.hour >= 8 and pending else 60
    # Crossing 08:00 must invalidate a successful 07:59 collection immediately.
    try:
        prior = datetime.fromisoformat(fetched).astimezone(KST)
    except (ValueError, TypeError):
        return True
    boundary = now.replace(hour=8, minute=0, second=0, microsecond=0)
    return (now.weekday() == 4 and now >= boundary > prior) or (now-prior).total_seconds() >= ttl*60


def collect(properties, known, now, lookup):
    target = expected_date(now)
    assets, errors, updated = [], [], []
    for prop in properties:
        name = prop["name"]
        old = known.get(name)
        try:
            price, asof = lookup(prop["complex_id"], prop["area_id"], prop.get("price_field", "매매일반거래가"), window_s=0)
            value = float(price) * 10000
            day = datetime.fromisoformat(asof).date()
            if not isfinite(value) or value <= 0 or day > now.astimezone(KST).date():
                raise ValueError("Invalid KB quote")
            if old and (asof < str(old.get("asof") or "") or not .5 <= value / old["value_krw"] <= 2):
                raise ValueError("Regressive KB quote")
            assets.append({"name": name, "owner": prop.get("owner", ""), "category": "부동산",
                           "quantity": 1, "price": value, "currency": "KRW", "value_krw": round(value),
                           "asof": asof, "note": "KB시세 직접 조회"})
            updated.append(name)
        except Exception as error:
            errors.append({"name": name, "reason": type(error).__name__})
            print(f"WARN: KB 직접 조회 예외 ({type(error).__name__}): {str(error)[:160]}")
            if old:
                assets.append(dict(old))
    pending = [a["name"] for a in assets if str(a.get("asof") or "") < target]
    return {"assets": assets, "errors": errors, "pending": pending, "updated": updated, "expected_date": target,
            "fetched_at": now.isoformat()}


def fetch_real_estate(previous=None):
    import yaml
    import crypto_util
    import kb_api
    pw = crypto_util.get_passphrase()
    portfolio = yaml.safe_load(crypto_util.decrypt_bytes((ROOT/"config/portfolio.enc").read_text(), pw))
    snap = json.loads(crypto_util.decrypt_bytes((ROOT/"docs/data/latest.enc").read_text(), pw))
    known = {a["name"]: a for a in snap.get("assets", []) if a.get("category") == "부동산" and a.get("value_krw", 0) > 0}
    for asset in (previous or {}).get("assets", []):
        old = known.get(asset["name"])
        if asset.get("value_krw", 0) > 0 and (not old or str(asset.get("asof") or "") >= str(old.get("asof") or "")):
            known[asset["name"]] = asset
    result = collect(portfolio.get("real_estate") or [], known, datetime.now(KST), kb_api.latest_price)
    print(f"OK: KB 직접 조회 성공 {len(result['updated'])}건 · 이번 주 대기 {len(result['pending'])}건 · 조회 실패 {len(result['errors'])}건")
    return result
