"""Public CVE titles from NVD. No exploit code and no exploit database."""

from __future__ import annotations

import json
from dataclasses import dataclass
from urllib.parse import urlencode

import httpx

from agentx.memory import looks_like_secret

_NVD = "https://services.nvd.nist.gov/rest/json/cves/2.0"
_LIMIT = 3


@dataclass(frozen=True)
class CveNotice:
    cve_id: str
    severity: str
    summary: str


def lookup_cves(keyword: str, *, getter=None) -> list[CveNotice]:
    text = " ".join(keyword.split())
    if not text or len(text) > 60 or looks_like_secret(text):
        return []
    query = urlencode({"keywordSearch": text, "resultsPerPage": _LIMIT})
    fetch = getter or _get
    payload = fetch(f"{_NVD}?{query}")
    return _notices(payload)[:_LIMIT]


def _get(url: str):
    try:
        response = httpx.get(url, timeout=15, trust_env=True)
    except httpx.HTTPError:
        return None
    if response.status_code != 200:
        return None
    try:
        return response.json()
    except json.JSONDecodeError:
        return None


def _notices(payload) -> list[CveNotice]:
    if not isinstance(payload, dict):
        return []
    rows = payload.get("vulnerabilities")
    if not isinstance(rows, list):
        return []
    notices: list[CveNotice] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        cve = row.get("cve")
        if not isinstance(cve, dict):
            continue
        cve_id = str(cve.get("id") or "").strip()
        if not cve_id.startswith("CVE-"):
            continue
        notices.append(
            CveNotice(cve_id, _severity(cve), _summary(cve))
        )
    return notices


def _severity(cve: dict) -> str:
    metrics = cve.get("metrics")
    if not isinstance(metrics, dict):
        return "UNKNOWN"
    for key in ("cvssMetricV31", "cvssMetricV30", "cvssMetricV2"):
        rows = metrics.get(key)
        if not isinstance(rows, list) or not rows:
            continue
        first = rows[0]
        if not isinstance(first, dict):
            continue
        data = first.get("cvssData")
        if isinstance(data, dict):
            severity = str(data.get("baseSeverity") or "").strip()
            if severity:
                return severity.upper()
    return "UNKNOWN"


def _summary(cve: dict) -> str:
    rows = cve.get("descriptions")
    if not isinstance(rows, list):
        return ""
    for row in rows:
        if not isinstance(row, dict):
            continue
        if str(row.get("lang") or "").casefold() == "en":
            return " ".join(str(row.get("value") or "").split())[:180]
    return ""
