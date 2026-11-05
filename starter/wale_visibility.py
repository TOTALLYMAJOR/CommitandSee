#!/usr/bin/env python3
"""Read-only GitHub product visibility. Python 3.11+, standard library only.

Snapshots are observations, never release approvals. Supplied receipt matching
checks bindings and dates; it does not authenticate the evidence's producer.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

UTC = timezone.utc
SHA = re.compile(r"^[0-9a-fA-F]{40}$")
IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")
REPOSITORY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9-]{0,38}/[A-Za-z0-9_.-]{1,100}$")


def utcnow() -> datetime:
    return datetime.now(UTC)


def timestamp(value: datetime | None = None) -> str:
    return (value or utcnow()).astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def parse_time(value: Any) -> datetime:
    if not isinstance(value, str):
        raise ValueError("Timestamp must be an ISO 8601 string with a timezone")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("Timestamp needs a timezone")
    return parsed.astimezone(UTC)


def _strings(value: Any, name: str, nonempty: bool = False) -> list[str]:
    if not isinstance(value, list) or (nonempty and not value):
        raise ValueError(f"{name} must be a {'nonempty ' if nonempty else ''}list")
    if any(not isinstance(v, str) or not v.strip() for v in value) or len(value) != len(set(value)):
        raise ValueError(f"{name} must contain unique nonempty strings")
    return value


def _id(value: Any, name: str) -> str:
    if not isinstance(value, str) or not IDENTIFIER.fullmatch(value):
        raise ValueError(f"{name} is not a valid identifier")
    return value


def valid_ref(value: Any) -> bool:
    return (isinstance(value, str) and bool(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/-]{0,254}", value))
            and ".." not in value and "//" not in value and not value.endswith(("/", ".", ".lock")))


def validate_manifest(manifest: Any) -> dict[str, Any]:
    if not isinstance(manifest, dict) or type(manifest.get("schema_version")) is not int or manifest["schema_version"] != 1:
        raise ValueError("Manifest schema_version must be 1")
    product = manifest.get("product")
    if not isinstance(product, dict):
        raise ValueError("Manifest product must be an object")
    _id(product.get("id"), "Product id")
    if not isinstance(product.get("name"), str) or not product["name"].strip():
        raise ValueError("Product name is required")
    if not isinstance(product.get("membership_status"), str) or product["membership_status"] not in {"proposed", "confirmed"}:
        raise ValueError("Product membership_status must be proposed or confirmed")
    age = manifest.get("max_age_hours", 24)
    if isinstance(age, bool) or not isinstance(age, (int, float)) or not math.isfinite(age) or age <= 0:
        raise ValueError("max_age_hours must be a finite positive number")
    components = manifest.get("components")
    if not isinstance(components, list) or not 1 <= len(components) <= 100:
        raise ValueError("Manifest needs 1 to 100 components")
    ids: set[str] = set()
    repositories: set[str] = set()
    for component in components:
        if not isinstance(component, dict):
            raise ValueError("Each component must be an object")
        cid = _id(component.get("id"), "Component id")
        if cid in ids:
            raise ValueError("Duplicate component id")
        ids.add(cid)
        repo = component.get("repository")
        if not isinstance(repo, str) or not REPOSITORY.fullmatch(repo) or repo.split("/")[1] in {".", ".."}:
            raise ValueError("Repository must be an owner/name slug, never a URL or credential")
        if repo.casefold() in repositories:
            raise ValueError("Version 1 supports one component per repository; duplicate repository slug")
        repositories.add(repo.casefold())
        if "ref" in component and not valid_ref(component["ref"]):
            raise ValueError("Component ref contains unsupported or invalid characters")
        if type(component.get("required")) is not bool:
            raise ValueError("Each component needs a boolean required flag")
        if not isinstance(component.get("role"), str) or not component["role"].strip():
            raise ValueError("Each component needs a role")
        _strings(component.get("required_workflows", []), "required_workflows")
        event = component.get("workflow_event", "push")
        if not isinstance(event, str) or not re.fullmatch(r"[a-z][a-z0-9_]{0,63}", event):
            raise ValueError("workflow_event must be a nonempty GitHub event token, such as push")
    edges = manifest.get("dependencies", [])
    if not isinstance(edges, list):
        raise ValueError("dependencies must be a list")
    for edge in edges:
        if (not isinstance(edge, dict) or not isinstance(edge.get("consumer"), str)
                or not isinstance(edge.get("provider"), str) or edge["consumer"] not in ids or edge["provider"] not in ids):
            raise ValueError("Dependency refers to an unknown component")
        if edge["consumer"] == edge["provider"]:
            raise ValueError("Self dependencies are not supported")
        if any(not isinstance(edge.get(k), str) or not edge[k].strip() for k in ("kind", "status")):
            raise ValueError("Dependency kind and status must be nonempty strings")
    capabilities = manifest.get("capabilities", [])
    if not isinstance(capabilities, list):
        raise ValueError("capabilities must be a list")
    capability_ids: set[str] = set()
    for capability in capabilities:
        if not isinstance(capability, dict):
            raise ValueError("Each capability must be an object")
        cid = _id(capability.get("id"), "Capability id")
        if cid in capability_ids:
            raise ValueError("Duplicate capability id")
        capability_ids.add(cid)
        if not isinstance(capability.get("name"), str) or not capability["name"].strip():
            raise ValueError("Capability name is required")
        members = _strings(capability.get("components"), "Capability components", True)
        if not set(members) <= ids:
            raise ValueError("Capability refers to an unknown component")
        _strings(capability.get("acceptance_criteria"), "Capability acceptance criteria", True)
    return manifest


def manifest_digest(manifest: dict[str, Any]) -> str:
    validate_manifest(manifest)
    return hashlib.sha256(json.dumps(manifest, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                                    allow_nan=False).encode("utf-8")).hexdigest()


def acceptance_scope(manifest: dict[str, Any]) -> set[str]:
    return ({c["id"] for c in manifest["components"] if c["required"]}
            | {cid for cap in manifest.get("capabilities", []) for cid in cap["components"]})


class SourceError(Exception):
    def __init__(self, state: str, message: str):
        self.state, self.message = state, message
        super().__init__(message)


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class GitHubClient:
    """GET only, fixed origin, TLS verified, no redirects, no credential logging."""
    def __init__(self, token: str = "", timeout: float = 20):
        self.token, self.timeout = token, timeout
        self.opener = build_opener(NoRedirect())

    def get(self, path: str) -> tuple[Any, dict[str, str]]:
        if not path.startswith("/repos/") or any(x in path for x in ("://", "\\", "\r", "\n", "#")):
            raise SourceError("invalid_request", "Only fixed-origin repository API paths are supported")
        headers = {"Accept": "application/vnd.github+json", "User-Agent": "wale-product-visibility/1",
                   "X-GitHub-Api-Version": "2026-03-10"}
        if self.token:
            headers["Authorization"] = "Bearer " + self.token
        try:
            with self.opener.open(Request("https://api.github.com" + path, headers=headers, method="GET"),
                                  timeout=self.timeout) as response:
                body = response.read(10_000_001)
                if len(body) > 10_000_000:
                    raise SourceError("response_too_large", "API response exceeds the 10 MB limit")
                return json.loads(body), {k.lower(): v for k, v in response.headers.items()}
        except HTTPError as error:
            remaining = error.headers.get("X-RateLimit-Remaining") if error.headers else None
            limited = error.code == 429 or (error.code == 403 and (remaining == "0" or error.headers.get("Retry-After")))
            state = ("rate_limited" if limited else {401: "unauthorized", 403: "forbidden",
                     404: "missing_or_inaccessible"}.get(error.code, "http_error"))
            raise SourceError(state, f"GitHub returned HTTP {error.code}; response body omitted") from None
        except (URLError, TimeoutError, OSError):
            raise SourceError("network_error", "GitHub request failed; network error details omitted") from None
        except (ValueError, UnicodeError):
            raise SourceError("invalid_response", "GitHub response is not valid JSON") from None


def _failure(error: Exception, observed_at: str) -> dict[str, Any]:
    return {"state": error.state if isinstance(error, SourceError) else "invalid_response", "complete": False,
            "truncated": False, "observed_at": observed_at,
            "error": error.message if isinstance(error, SourceError) else "Unexpected or malformed source response"}


def _pages(client: Any, path: str, params: dict[str, Any], key: str | None, max_pages: int,
           observed_at: str | None = None) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    for page in range(1, max_pages + 1):
        at = observed_at or timestamp()
        try:
            payload, headers = client.get(path + "?" + urlencode({**params, "per_page": 100, "page": page}))
            batch = payload.get(key) if key and isinstance(payload, dict) else payload
            if not isinstance(batch, list) or any(not isinstance(x, dict) for x in batch):
                raise ValueError("Malformed collection")
            items.extend(batch)
            links = {k.lower(): v for k, v in headers.items()}.get("link", "")
            total = payload.get("total_count") if isinstance(payload, dict) else None
            if key and len(items) >= 1000 and type(total) is int and total > 1000:
                return {"state": "partial", "complete": False, "truncated": True, "observed_at": at,
                        "error": "Filtered Actions query exceeds GitHub's 1000-result cap", "pages": page, "items": items}
            more = bool(re.search(r'rel=["\']next["\']', links))
            more = more or (type(total) is int and total > len(items)) or (len(batch) == 100 and type(total) is not int)
            if not more:
                return {"state": "ok", "complete": True, "truncated": False, "observed_at": at,
                        "pages": page, "items": items}
        except (SourceError, ValueError, TypeError, KeyError) as error:
            result = _failure(error, at)
            result.update(items=items, pages=page - 1)
            if items:
                result["state"] = "partial"
            return result
    return {"state": "partial", "complete": False, "truncated": True, "observed_at": at,
            "error": "Page cap reached; results are incomplete", "pages": max_pages, "items": items}


def collect_snapshot(manifest: dict[str, Any], client: Any = None, max_pages: int = 3,
                     observed_at: str | None = None) -> dict[str, Any]:
    digest = manifest_digest(manifest)
    if type(max_pages) is not int or not 1 <= max_pages <= 100:
        raise ValueError("max_pages must be between 1 and 100")
    if observed_at is not None:
        parse_time(observed_at)
    client = client or GitHubClient(os.getenv("GH_TOKEN") or os.getenv("GITHUB_TOKEN") or "")
    snapshot: dict[str, Any] = {"schema_version": 1, "mode": "live", "collector": "GitHub REST GET",
        "product_id": manifest["product"]["id"], "manifest_sha256": digest,
        "observed_at": observed_at or timestamp(), "components": []}
    for component in manifest["components"]:
        base = "/repos/" + component["repository"]
        record: dict[str, Any] = {"id": component["id"], "repository": component["repository"],
                                 "repository_id": None, "ref": component.get("ref"), "sha": None, "sources": {}}
        sources = record["sources"]
        for source, path in (("repository", base), ("commit", "")):
            at = observed_at or timestamp()
            try:
                if source == "commit":
                    if not valid_ref(record["ref"]):
                        raise SourceError("not_collected", "Ref could not be resolved")
                    path = base + "/commits/" + quote(record["ref"], safe="")
                payload, _ = client.get(path)
                if not isinstance(payload, dict):
                    raise ValueError("Malformed object")
                if source == "repository":
                    if payload.get("full_name", component["repository"]).lower() != component["repository"].lower():
                        raise SourceError("identity_mismatch", "Returned repository differs from the manifest")
                    if type(payload.get("id")) is not int or payload["id"] <= 0:
                        raise ValueError("Repository id missing")
                    record["repository_id"] = payload["id"]
                    record["ref"] = component.get("ref") or payload.get("default_branch")
                    record["default_branch"] = payload.get("default_branch")
                else:
                    if not isinstance(payload.get("sha"), str) or not SHA.fullmatch(payload["sha"]):
                        raise ValueError("Commit SHA missing")
                    record["sha"] = payload["sha"].lower()
                sources[source] = {"state": "ok", "complete": True, "observed_at": at}
            except (SourceError, ValueError, TypeError, AttributeError) as error:
                sources[source] = _failure(error, at)
        sources["pull_requests"] = _pages(client, base + "/pulls", {"state": "open"}, None, max_pages, observed_at)
        if record["sha"]:
            sources["workflows"] = _pages(client, base + "/actions/runs", {"head_sha": record["sha"]},
                                          "workflow_runs", max_pages, observed_at)
        else:
            sources["workflows"] = {**_failure(SourceError("not_collected", "Commit SHA is unknown"),
                                                observed_at or timestamp()), "items": []}
        # Persist an allowlist of public API fields, never response headers or authorization.
        item_keys = ("number", "title", "html_url", "draft", "updated_at")
        sources["pull_requests"]["items"] = [{k: item[k] for k in item_keys if k in item}
                                             for item in sources["pull_requests"]["items"]]
        workflow_keys = ("id", "workflow_id", "name", "path", "event", "head_sha", "status", "conclusion",
                         "run_attempt", "run_number", "created_at", "updated_at", "run_started_at", "html_url")
        sources["workflows"]["items"] = [{k: run[k] for k in workflow_keys if k in run}
                                          for run in sources["workflows"]["items"]]
        snapshot["components"].append(record)
    snapshot["collection_finished_at"] = observed_at or timestamp()
    return snapshot


def freshness(observed_at: Any, max_age_hours: float, now: datetime | None = None) -> str:
    try:
        age = (now or utcnow()) - parse_time(observed_at)
        return "FUTURE" if age.total_seconds() < 0 else "STALE" if age > timedelta(hours=max_age_hours) else "FRESH"
    except (ValueError, TypeError, OverflowError):
        return "UNKNOWN"


def _result(status: str, detail: str, **kwargs: Any) -> dict[str, Any]:
    return {"status": status, "detail": detail, **kwargs}


def evaluate_ci(component: dict[str, Any], record: dict[str, Any], max_age_hours: float = 24,
                now: datetime | None = None) -> dict[str, Any]:
    selected = component.get("required_workflows", [])
    event = component.get("workflow_event", "push")
    source = record.get("sources", {}).get("workflows", {})
    if not selected:
        return _result("UNKNOWN", "No workflows selected in the manifest")
    if source.get("complete") is not True or source.get("state") != "ok":
        return _result("UNKNOWN", "Workflow collection is unavailable or incomplete")
    if freshness(source.get("observed_at"), max_age_hours, now) != "FRESH":
        return _result("UNKNOWN", "Workflow observation is stale, future-dated, or undated")
    sha = record.get("sha")
    if not isinstance(sha, str) or not SHA.fullmatch(sha):
        return _result("UNKNOWN", "Component commit SHA is unknown")
    runs = source.get("items", [])
    if not isinstance(runs, list) or any(not isinstance(r, dict) or r.get("head_sha") != sha for r in runs):
        return _result("UNKNOWN", "Workflow data is malformed or includes a different commit")
    latest: list[dict[str, Any]] = []
    for name in selected:
        named = [r for r in runs if r.get("name") == name]
        if any(not isinstance(r.get("event"), str) or not r["event"] for r in named):
            return _result("UNKNOWN", "Selected workflow is missing its triggering event: " + name)
        matches = [r for r in named if r["event"] == event]
        if not matches:
            return _result("UNKNOWN", "Selected workflow missing for event " + event + ": " + name)
        if any(type(r.get("workflow_id")) is not int for r in matches) or len({r["workflow_id"] for r in matches}) != 1:
            return _result("UNKNOWN", "Workflow name is ambiguous or has no identity: " + name)
        try:
            # A rerun's newest attempt supersedes older attempts of that run.
            by_run: dict[int, dict[str, Any]] = {}
            for run in matches:
                if (type(run.get("id")) is not int or run["id"] <= 0
                        or type(run.get("run_attempt", 1)) is not int or run.get("run_attempt", 1) <= 0):
                    raise ValueError("Invalid run identity")
                for date in (run.get("created_at"), run.get("run_started_at") or run.get("created_at"),
                             run.get("updated_at") or run.get("created_at")):
                    if parse_time(date) > (now or utcnow()):
                        raise ValueError("Future-dated workflow execution")
                prior = by_run.get(run["id"])
                if prior is None or (run.get("run_attempt", 1), parse_time(run.get("updated_at") or run.get("created_at"))) > (
                        prior.get("run_attempt", 1), parse_time(prior.get("updated_at") or prior.get("created_at"))):
                    by_run[run["id"]] = run
            latest.append(max(by_run.values(), key=lambda r: (parse_time(r.get("run_started_at") or r.get("created_at")),
                                                                r["id"], r.get("run_attempt", 1))))
        except (ValueError, TypeError):
            return _result("UNKNOWN", "Workflow execution identity or date is missing, invalid, or future-dated")
    failed = [r["name"] for r in latest if r.get("status") == "completed" and r.get("conclusion") != "success"]
    if failed:
        return _result("NOT PASSING", "Latest selected run did not succeed: " + ", ".join(failed), runs=latest)
    if any(r.get("status") != "completed" for r in latest):
        return _result("PENDING", "A selected workflow has not completed", runs=latest)
    return _result("PASSING OBSERVED", "Selected Actions workflows succeeded at this SHA; this is not product acceptance", runs=latest)


def validate_snapshot(manifest: dict[str, Any], snapshot: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(snapshot, dict) or type(snapshot.get("schema_version")) is not int or snapshot["schema_version"] != 1:
        raise ValueError("Unsupported snapshot schema")
    if snapshot.get("manifest_sha256") != manifest_digest(manifest) or snapshot.get("product_id") != manifest["product"]["id"]:
        raise ValueError("Snapshot does not match this manifest; recollect instead of relabeling")
    if not isinstance(snapshot.get("mode"), str) or snapshot["mode"] not in {"live", "demo"}:
        raise ValueError("Snapshot mode must be live or demo")
    records = snapshot.get("components")
    if not isinstance(records, list) or any(not isinstance(r, dict) for r in records):
        raise ValueError("Snapshot components must be objects")
    ids = [r.get("id") for r in records]
    if any(not isinstance(cid, str) for cid in ids) or len(ids) != len(set(ids)):
        raise ValueError("Snapshot component IDs must be unique strings")
    mapped = {r["id"]: r for r in records}
    if set(mapped) != {c["id"] for c in manifest["components"]}:
        raise ValueError("Snapshot component membership differs from manifest")
    for component in manifest["components"]:
        record = mapped[component["id"]]
        if record.get("repository") != component["repository"]:
            raise ValueError("Snapshot repository identity differs from manifest")
        if not isinstance(record.get("sources"), dict):
            raise ValueError("Snapshot sources are missing")
        if record.get("sha") is not None and (not isinstance(record["sha"], str) or not SHA.fullmatch(record["sha"])):
            raise ValueError("Snapshot SHA must be a full commit SHA or null")
        if record.get("repository_id") is not None and (type(record["repository_id"]) is not int or record["repository_id"] <= 0):
            raise ValueError("Snapshot repository ID must be a positive integer or null")
        for name in ("repository", "commit", "pull_requests", "workflows"):
            source = record["sources"].get(name)
            if not isinstance(source, dict) or type(source.get("complete")) is not bool or not isinstance(source.get("state"), str):
                raise ValueError("Snapshot needs typed states for all four source collections")
            if name in {"pull_requests", "workflows"} and (not isinstance(source.get("items"), list)
                    or any(not isinstance(item, dict) for item in source["items"])):
                raise ValueError("Snapshot collection items must be objects")
    return mapped


def safe_url(value: Any) -> str | None:
    if not isinstance(value, str) or any(ord(c) < 33 for c in value):
        return None
    try:
        parsed = urlsplit(value)
        return value if parsed.scheme in {"https", "http"} and parsed.hostname and not parsed.username and not parsed.password else None
    except ValueError:
        return None


def evaluate_receipt(manifest: dict[str, Any], snapshot: dict[str, Any], receipt: Any = None,
                     now: datetime | None = None) -> dict[str, Any]:
    records = validate_snapshot(manifest, snapshot)
    scope = sorted(acceptance_scope(manifest))
    if receipt is None:
        return _result("UNKNOWN", "No integration acceptance receipt was supplied", scope=scope)
    if not isinstance(receipt, dict):
        return _result("INVALID", "Receipt must be an object", scope=scope)
    now = now or utcnow()
    try:
        if type(receipt.get("schema_version")) is not int or receipt["schema_version"] != 1 or receipt.get("product_id") != manifest["product"]["id"]:
            return _result("MISMATCH", "Receipt schema or product identity differs", scope=scope)
        if receipt.get("manifest_sha256") != manifest_digest(manifest):
            return _result("MISMATCH", "Receipt does not bind this manifest and its acceptance criteria", scope=scope)
        if not scope or not manifest.get("capabilities"):
            return _result("UNKNOWN", "No product acceptance capabilities are defined", scope=scope)
        vector = {cid: records[cid].get("sha") for cid in scope}
        if any(not isinstance(sha, str) or not SHA.fullmatch(sha) for sha in vector.values()):
            return _result("UNKNOWN", "A component in the acceptance scope has no commit SHA", scope=scope)
        supplied_vector = receipt.get("component_shas")
        if not isinstance(supplied_vector, dict) or supplied_vector != vector:
            return _result("MISMATCH", "Receipt component set or commit SHAs differ from the acceptance scope", scope=scope)
        if "component_repository_ids" in receipt:
            expected_ids = {cid: records[cid].get("repository_id") for cid in scope}
            supplied_ids = receipt["component_repository_ids"]
            if (not isinstance(supplied_ids, dict) or any(type(rid) is not int for rid in supplied_ids.values())
                    or any(type(rid) is not int or rid <= 0 for rid in expected_ids.values()) or supplied_ids != expected_ids):
                return _result("MISMATCH", "Receipt repository IDs differ or are unknown", scope=scope)
        for cid in scope:
            for name in ("repository", "commit"):
                source = records[cid]["sources"].get(name, {})
                if (source.get("state") != "ok" or source.get("complete") is not True
                        or freshness(source.get("observed_at"), manifest.get("max_age_hours", 24), now) != "FRESH"):
                    return _result("UNKNOWN", "Identity or commit observation is incomplete or stale: " + cid, scope=scope)
        checked, expires = parse_time(receipt.get("checked_at")), parse_time(receipt.get("expires_at"))
        if checked > now or expires <= checked:
            return _result("INVALID", "Receipt time interval is invalid or future-dated", scope=scope)
        if expires <= now or now - checked > timedelta(hours=manifest.get("max_age_hours", 24)):
            return _result("STALE", "Receipt has expired or exceeds the configured evidence age", scope=scope)
        caps = _strings(receipt.get("capabilities"), "Receipt capabilities", True)
        if set(caps) != {c["id"] for c in manifest["capabilities"]}:
            return _result("MISMATCH", "Receipt capability coverage differs from the manifest", scope=scope)
        if receipt.get("environment") != "integration" or not safe_url(receipt.get("evidence_url")):
            return _result("INVALID", "Receipt needs an integration environment and a safe HTTP(S) evidence URL", scope=scope)
        if receipt.get("result") == "fail":
            return _result("FAILED SUPPLIED RECEIPT", "Supplied integration result is fail", scope=scope)
        if receipt.get("result") != "pass":
            return _result("INVALID", "Receipt result must be pass or fail", scope=scope)
        identity_note = "Repository IDs are bound. " if "component_repository_ids" in receipt else "Repository IDs are not bound. "
        return _result("MATCHED SUPPLIED RECEIPT", identity_note + "Scope, criteria, versions and dates match; producer and evidence content are not authenticated", scope=scope)
    except (ValueError, TypeError, OverflowError):
        return _result("INVALID", "Malformed receipt fields or dates", scope=scope)


def _e(value: Any) -> str:
    return html.escape(str(value), quote=True)


def _link(label: Any, url: Any) -> str:
    return f'<a href="{_e(url)}" rel="noreferrer">{_e(label)}</a>' if safe_url(url) else _e(label)


def _badge(status: str) -> str:
    style = "good" if status in {"PASSING OBSERVED", "MATCHED SUPPLIED RECEIPT", "FRESH"} else "bad" if status in {"NOT PASSING", "FAILED SUPPLIED RECEIPT", "MISMATCH", "INVALID"} else "neutral"
    return f'<span class="badge {style}">{_e(status)}</span>'


def render_report(manifest: dict[str, Any], snapshot: dict[str, Any], receipt: Any = None,
                  now: datetime | None = None) -> str:
    records = validate_snapshot(manifest, snapshot)
    now = now or utcnow()
    age = manifest.get("max_age_hours", 24)
    acceptance = evaluate_receipt(manifest, snapshot, receipt, now)
    rows, details, vectors = [], [], []
    pr_total, complete_prs = 0, True
    for component in manifest["components"]:
        cid, repo = component["id"], component["repository"]
        record = records[cid]
        ci = evaluate_ci(component, record, age, now)
        sources = record["sources"]
        prs = sources.get("pull_requests", {})
        pr_items = prs.get("items", [])
        if not isinstance(pr_items, list):
            raise ValueError("Snapshot pull request items must be a list")
        pr_total += len(pr_items)
        complete_prs = (complete_prs and prs.get("state") == "ok" and prs.get("complete") is True
                        and freshness(prs.get("observed_at"), age, now) == "FRESH")
        errors = [f'{name}: {source.get("state", "unknown")} — {source.get("error", "incomplete")}'
                  for name, source in sources.items() if isinstance(source, dict) and (source.get("complete") is not True or source.get("state") != "ok")]
        source_states = [f'{name}: {source.get("state", "unknown")} / {freshness(source.get("observed_at"), age, now)}'
                         for name, source in sources.items() if isinstance(source, dict)]
        sha = record.get("sha") or "UNKNOWN"
        selected = ", ".join(component.get("required_workflows", [])) or "None selected"
        rows.append(f'<tr><td><strong>{_e(cid)}</strong><br>{_link(repo, "https://github.com/" + repo)}<small>{_e(component["role"])}</small></td>'
                    f'<td>{_e("Required" if component["required"] else "Optional")}<br><small>Receipt scope: {"yes" if cid in acceptance["scope"] else "no"}</small></td>'
                    f'<td>{_e(record.get("ref") or "UNKNOWN")}<br><code>{_e(sha[:12])}</code></td>'
                    f'<td>{_badge(ci["status"])}<small>{_e(ci["detail"])}<br>Selected: {_e(selected)}<br>Event: {_e(component.get("workflow_event", "push"))}</small></td>'
                    f'<td>{len(pr_items) if prs.get("complete") is True and prs.get("state") == "ok" else str(len(pr_items)) + " observed; total unknown"}<small>{_e("; ".join(source_states))}</small></td></tr>')
        vectors.append(f'<tr><td>{_e(cid)}</td><td>{_e(record.get("repository_id") or "UNKNOWN")}</td><td><code>{_e(sha)}</code></td></tr>')
        pr_html = "".join(f'<li>{_link("#" + str(pr.get("number", "?")) + " " + str(pr.get("title", "Untitled")), pr.get("html_url"))}</li>' for pr in pr_items if isinstance(pr, dict))
        run_html = "".join(f'<li>{_link(run.get("name", "Unnamed"), run.get("html_url"))}: {_e(run.get("status"))} / {_e(run.get("conclusion"))}; '
                           f'event {_e(run.get("event", "unknown"))}; attempt {_e(run.get("run_attempt", "?"))}; execution {_e(run.get("run_started_at") or run.get("created_at") or "undated")}</li>' for run in ci.get("runs", []))
        details.append(f'<details><summary>{_e(cid)} · source details and links</summary><p>{_e("; ".join(errors)) or "All requested sources returned complete results."}</p>'
                       f'<h4>Open pull requests</h4><ul>{pr_html or "<li>No PRs observed; consult collection status above.</li>"}</ul>'
                       f'<h4>Latest selected workflow executions</h4><ul>{run_html or "<li>No complete selected-workflow assessment available.</li>"}</ul></details>')
    edge_rows = "".join(f'<tr><td>{_e(e["consumer"])}</td><td>{_e(e["provider"])}</td><td>{_e(e["kind"])}</td><td>{_e(e["status"])}</td></tr>' for e in manifest.get("dependencies", []))
    cap_rows = "".join(f'<tr><td><strong>{_e(c["name"])}</strong><small>{_e(c["id"])}</small></td><td>{_e(", ".join(c["components"]))}</td>'
                       f'<td><ul>{"".join("<li>" + _e(a) + "</li>" for a in c["acceptance_criteria"])}</ul></td></tr>' for c in manifest.get("capabilities", []))
    receipt_details = "No receipt supplied. Integration acceptance, deployment, and human acceptance remain unknown."
    if isinstance(receipt, dict):
        receipt_details = (f'Evidence: {_link(receipt.get("evidence_url", "missing"), receipt.get("evidence_url"))}<br>'
                           f'Checked: {_e(receipt.get("checked_at", "missing"))}; expires: {_e(receipt.get("expires_at", "missing"))}<br>'
                           f'Environment: {_e(receipt.get("environment", "missing"))}; supplied result: {_e(receipt.get("result", "missing"))}')
    mode = "DEMO · SYNTHETIC DATA" if snapshot["mode"] == "demo" else "COLLECTED GITHUB OBSERVATIONS"
    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'">
<title>{_e(manifest['product']['name'])} · Product visibility</title><style>
:root{{color-scheme:dark;font-family:system-ui,sans-serif;background:#0b1220;color:#e8eff9}}body{{margin:0}}main{{max-width:1280px;margin:auto;padding:32px 24px 64px}}
h1{{font-size:clamp(2rem,4vw,3.4rem);margin:12px 0}}h2{{margin-top:34px}}p,li{{line-height:1.6}}.kicker{{letter-spacing:.12em;color:#68ddc5;font-size:.8rem;font-weight:700}}
.muted,small{{color:#a9bbd0}}small{{display:block;margin-top:8px;line-height:1.5}}a{{color:#78dccc}}code{{font-size:.85em;overflow-wrap:anywhere}}.cards{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:16px;margin:26px 0}}
.card,details,.receipt{{background:#121f31;border:1px solid #2a3c53;border-radius:12px;padding:20px}}.number{{font-size:1.6rem;font-weight:700;display:block;margin-top:10px}}
.table{{overflow-x:auto}}table{{width:100%;border-collapse:collapse}}th,td{{text-align:left;border-bottom:1px solid #2a3c53;padding:14px 12px;vertical-align:top}}th{{color:#a9bbd0;font-size:.8rem}}
.badge{{display:inline-block;border-radius:5px;padding:5px 8px;font-size:.75rem;font-weight:700}}.good{{background:#123e38;color:#8ce9d2}}.bad{{background:#51272e;color:#ffc3c7}}.neutral{{background:#353443;color:#e6dcbd}}
details{{margin:12px 0}}summary{{cursor:pointer;font-weight:600}}.receipt{{border-left:4px solid #68ddc5}}footer{{margin-top:30px;border-top:1px solid #2a3c53;padding-top:20px}}ul{{padding-left:20px;margin-top:6px}}
@media(max-width:700px){{main{{padding:22px 14px}}.cards{{grid-template-columns:1fr}}td,th{{padding:10px 8px}}}}@media print{{:root{{color-scheme:light;background:white;color:black}}.card,details,.receipt{{background:white}}small,.muted,th{{color:#334}}a{{color:#067}}details{{display:block}}}}
</style></head><body><main>
<div class="kicker">{mode}</div><h1>{_e(manifest['product']['name'])}</h1>
<p class="muted">Product visibility across repositories · composition {_e(manifest['product']['membership_status'])}<br>
Collection began {_e(snapshot.get('observed_at'))}; ended {_e(snapshot.get('collection_finished_at', snapshot.get('observed_at')))}.<br>
Report evaluated {timestamp(now)} · {_e(snapshot.get('collector', 'unspecified collector'))}. Static export; observations do not update when you reopen this file.</p>
<div class="cards"><div class="card">Component repositories<span class="number">{len(records)}</span><small>{len(acceptance['scope'])} in the receipt acceptance scope</small></div>
<div class="card">Open pull requests<span class="number">{pr_total if complete_prs else str(pr_total) + ' observed'}</span><small>{'Complete fresh collection' if complete_prs else 'Total unknown: some sources are unavailable, incomplete or stale'}</small></div>
<div class="card">Integration receipt<span class="number">{_badge(acceptance['status'])}</span><small>No product health percentage is inferred.</small></div></div>
<h2>Component observations</h2><p>Selected workflow names are this manifest’s observation policy. They are not a discovery of GitHub branch protection or required status checks.</p>
<div class="table"><table><thead><tr><th>Component / repository</th><th>Membership</th><th>Observed ref / SHA</th><th>Selected workflow observations</th><th>PRs / source coverage</th></tr></thead><tbody>{''.join(rows)}</tbody></table></div>
<h2>Product capabilities</h2><div class="table"><table><thead><tr><th>Capability</th><th>Components</th><th>Declared acceptance criteria</th></tr></thead><tbody>{cap_rows or '<tr><td colspan="3">None declared</td></tr>'}</tbody></table></div>
<h2>Declared relationships</h2><p class="muted">These are manifest declarations, not automatically discovered runtime dependencies.</p><div class="table"><table><thead><tr><th>Consumer</th><th>Provider</th><th>Relationship</th><th>Evidence status</th></tr></thead><tbody>{edge_rows or '<tr><td colspan="4">None declared</td></tr>'}</tbody></table></div>
<h2>Integration evidence</h2><div class="receipt">{_badge(acceptance['status'])}<p>{_e(acceptance['detail'])}</p><p>Receipt scope: {_e(', '.join(acceptance['scope']) or 'none')}.</p><p>{receipt_details}</p>
<small>A supplied receipt is not an authenticated attestation. This tool does not fetch its evidence URL, rerun tests, approve a release, establish production deployment, or infer human acceptance. Matching demo receipts remain synthetic.</small></div>
<h2>Observed version vector</h2><p class="muted">A timestamped set of repository commits, collected sequentially. It is not a product release or an atomic cross-repository snapshot.</p><div class="table"><table><thead><tr><th>Component</th><th>GitHub repository ID</th><th>Full commit SHA</th></tr></thead><tbody>{''.join(vectors)}</tbody></table></div>
<p class="muted">Manifest SHA-256: <code>{_e(snapshot['manifest_sha256'])}</code></p>
<h2>Evidence links</h2>{''.join(details)}
<footer><strong>Coverage limits</strong><p class="muted">GitHub repository metadata, selected refs, open PRs and Actions workflow runs are collected. Local-only commits and worktrees, issues, package/runtime dependencies, external CI, branch protection, artifact digests, production deployments, and human acceptance are not collected. Exact-SHA CI observations do not establish cross-repository compatibility. Source freshness is measured at collection time; test execution dates are shown separately. Provenance and snapshot contents are not cryptographically authenticated.</p></footer>
</main></body></html>'''


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON object key")
        result[key] = value
    return result


def read_json(path: str | Path) -> Any:
    target = Path(path)
    if target.stat().st_size > 25_000_000:
        raise ValueError("Input JSON exceeds the 25 MB limit")
    return json.loads(target.read_text(encoding="utf-8"), object_pairs_hook=_unique_object,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError("Non-finite JSON number")))


def write_file(path: str | Path, content: str) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=target.parent, delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(content)
        os.replace(temporary, target)
    finally:
        if temporary and temporary.exists():
            temporary.unlink()


def write_json(path: str | Path, value: Any) -> None:
    write_file(path, json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n")


def demo(output_dir: str | Path) -> None:
    now = utcnow().replace(microsecond=0)
    manifest = {"schema_version": 1, "product": {"id": "demo-product", "name": "Demo Product", "membership_status": "proposed"},
        "components": [{"id": cid, "repository": "example/" + cid, "ref": "main", "role": role, "required": True,
                        "required_workflows": ["CI"], "workflow_event": "push"} for cid, role in (("web", "Interface"), ("api", "Service"))],
        "dependencies": [{"consumer": "web", "provider": "api", "kind": "HTTP API", "status": "synthetic declaration"}],
        "capabilities": [{"id": "journey", "name": "Demo customer journey", "components": ["web", "api"],
                          "acceptance_criteria": ["A synthetic end-to-end example completes"]}], "max_age_hours": 24}
    class DemoClient:
        def get(self, path):
            cid = "web" if "/web" in path else "api"
            sha = ("a" if cid == "web" else "b") * 40
            if "/commits/" in path:
                return {"sha": sha}, {}
            if "/pulls?" in path:
                return [], {}
            if "/actions/runs?" in path:
                return {"total_count": 1, "workflow_runs": [{"id": 1, "workflow_id": 10, "name": "CI", "event": "push", "head_sha": sha,
                    "status": "completed", "conclusion": "success", "run_attempt": 1, "created_at": timestamp(now - timedelta(hours=1)),
                    "html_url": "https://example.invalid/synthetic-ci"}]}, {}
            return {"id": 100 if cid == "web" else 200, "full_name": "example/" + cid, "default_branch": "main"}, {}
    snapshot = collect_snapshot(manifest, DemoClient(), observed_at=timestamp(now))
    snapshot.update(mode="demo", collector="Synthetic demo fixture; no GitHub calls")
    receipt = {"schema_version": 1, "product_id": "demo-product", "manifest_sha256": manifest_digest(manifest),
        "component_shas": {r["id"]: r["sha"] for r in snapshot["components"]},
        "component_repository_ids": {r["id"]: r["repository_id"] for r in snapshot["components"]},
        "checked_at": timestamp(now - timedelta(minutes=5)), "expires_at": timestamp(now + timedelta(hours=1)),
        "result": "pass", "evidence_url": "https://example.invalid/synthetic-receipt", "environment": "integration", "capabilities": ["journey"]}
    out = Path(output_dir)
    for name, value in (("product.json", manifest), ("snapshot.json", snapshot), ("receipt.json", receipt)):
        write_json(out / name, value)
    write_file(out / "report.html", render_report(manifest, snapshot, receipt, now))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    collect = sub.add_parser("collect", help="Read GitHub and save a timestamped snapshot")
    collect.add_argument("--manifest", required=True)
    collect.add_argument("--output", required=True)
    collect.add_argument("--max-pages", type=int, default=3)
    collect.add_argument("--use-gh-auth", action="store_true", help="Read an existing github.com gh login; does not log in")
    report = sub.add_parser("report", help="Render a saved snapshot as static HTML")
    report.add_argument("--manifest", required=True)
    report.add_argument("--snapshot", required=True)
    report.add_argument("--output", required=True)
    report.add_argument("--receipt")
    sample = sub.add_parser("demo", help="Generate visibly synthetic offline examples")
    sample.add_argument("--output-dir", default="demo")
    args = parser.parse_args(argv)
    try:
        if args.command == "demo":
            demo(args.output_dir)
            print("Synthetic demo written. Open " + str(Path(args.output_dir) / "report.html"))
        elif args.command == "collect":
            token = os.getenv("GH_TOKEN") or os.getenv("GITHUB_TOKEN") or ""
            if args.use_gh_auth and not token:
                try:
                    result = subprocess.run(["gh", "auth", "token", "--hostname", "github.com"], capture_output=True,
                                            text=True, timeout=10, check=False)
                    if result.returncode != 0 or not result.stdout.strip():
                        raise ValueError("Existing gh authentication is unavailable")
                    token = result.stdout.strip()
                except (OSError, subprocess.SubprocessError):
                    raise ValueError("Existing gh authentication is unavailable") from None
            snapshot = collect_snapshot(read_json(args.manifest), GitHubClient(token), args.max_pages)
            write_json(args.output, snapshot)
            incomplete = sum(s.get("complete") is not True for c in snapshot["components"] for s in c["sources"].values())
            print(f"Snapshot written; {incomplete} source collections incomplete. Inspect source states before using it.")
            return 2 if incomplete else 0
        else:
            manifest, snapshot = read_json(args.manifest), read_json(args.snapshot)
            receipt = read_json(args.receipt) if args.receipt else None
            write_file(args.output, render_report(manifest, snapshot, receipt))
            print("Static report written. Open " + args.output)
        return 0
    except (ValueError, OSError) as error:
        # Paths, credentials and response bodies are deliberately absent from errors.
        print("Error: " + (str(error) if isinstance(error, ValueError) else "Local file operation failed"), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
