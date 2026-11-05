"""Offline acceptance tests; no network, credentials, or package installation."""
import copy
from datetime import datetime, timedelta, timezone
from io import BytesIO, StringIO
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError

import wale_visibility as w

NOW = datetime(2026, 11, 4, 22, 0, tzinfo=timezone.utc)
AT = w.timestamp(NOW - timedelta(minutes=1))
A, B = "a" * 40, "b" * 40


def manifest():
    return {"schema_version": 1, "product": {"id": "product", "name": "Product", "membership_status": "proposed"},
            "components": [{"id": "core", "repository": "example/core", "ref": "main", "role": "Core service",
                            "required": True, "required_workflows": ["CI"]}],
            "dependencies": [], "capabilities": [{"id": "journey", "name": "Journey", "components": ["core"],
                                                    "acceptance_criteria": ["Customer completes the journey"]}],
            "max_age_hours": 24}


def run(**overrides):
    return {"id": 10, "workflow_id": 20, "name": "CI", "event": "push", "head_sha": A, "status": "completed",
            "conclusion": "success", "run_attempt": 1, "created_at": w.timestamp(NOW - timedelta(hours=2)),
            "html_url": "https://github.com/example/core/actions/runs/10", **overrides}


class FakeClient:
    def __init__(self, runs=None, fail_pr=False):
        self.runs = [run()] if runs is None else runs
        self.fail_pr = fail_pr
        self.calls = []

    def get(self, path):
        self.calls.append(path)
        if "/commits/" in path:
            return {"sha": A}, {}
        if "/pulls?" in path:
            if self.fail_pr:
                raise w.SourceError("forbidden", "GitHub returned HTTP 403; response body omitted")
            return [], {}
        if "/actions/runs?" in path:
            return {"workflow_runs": copy.deepcopy(self.runs), "total_count": len(self.runs)}, {}
        return {"id": 123, "full_name": "example/core", "default_branch": "main"}, {}


def snapshot(m=None, **kwargs):
    return w.collect_snapshot(m or manifest(), FakeClient(**kwargs), observed_at=AT)


def receipt(m, s):
    scope = w.acceptance_scope(m)
    return {"schema_version": 1, "product_id": "product", "manifest_sha256": w.manifest_digest(m),
            "component_shas": {r["id"]: r["sha"] for r in s["components"] if r["id"] in scope},
            "component_repository_ids": {r["id"]: r["repository_id"] for r in s["components"] if r["id"] in scope},
            "checked_at": w.timestamp(NOW - timedelta(minutes=5)), "expires_at": w.timestamp(NOW + timedelta(hours=1)),
            "result": "pass", "evidence_url": "https://example.com/evidence/1", "environment": "integration",
            "capabilities": ["journey"]}


class ManifestTests(unittest.TestCase):
    def test_duplicate_component_id_rejected(self):
        m = manifest()
        m["components"].append(copy.deepcopy(m["components"][0]))
        with self.assertRaises(ValueError):
            w.validate_manifest(m)

    def test_urls_credentials_and_path_traversal_rejected(self):
        for repo in ("https://token@github.com/owner/repo", "owner/../repo", "owner/..", "owner/repo?token=secret"):
            with self.subTest(repo=repo):
                m = manifest()
                m["components"][0]["repository"] = repo
                with self.assertRaises(ValueError):
                    w.validate_manifest(m)

    def test_dangling_edges_capabilities_and_invalid_types(self):
        for change in (lambda m: m.update(dependencies=[{"consumer": "missing", "provider": "core"}]),
                       lambda m: m["capabilities"][0].update(components=["missing"]),
                       lambda m: m["components"][0].update(required="true"),
                       lambda m: m.update(max_age_hours=float("nan")),
                       lambda m: m["components"][0].update(ref="main..old")):
            m = manifest()
            change(m)
            with self.assertRaises(ValueError):
                w.validate_manifest(m)

    def test_manifest_digest_binds_criteria(self):
        m = manifest()
        before = w.manifest_digest(m)
        m["capabilities"][0]["acceptance_criteria"][0] = "Different criterion"
        self.assertNotEqual(before, w.manifest_digest(m))

    def test_duplicate_repository_slug_rejected_case_insensitively(self):
        m = manifest()
        m["components"].append({**m["components"][0], "id": "second", "repository": "EXAMPLE/CORE"})
        with self.assertRaises(ValueError):
            w.validate_manifest(m)

    def test_enum_types_and_workflow_event_validation_are_clean_errors(self):
        for change in (lambda m: m["product"].update(membership_status=[]),
                       lambda m: m["components"][0].update(workflow_event=""),
                       lambda m: m["components"][0].update(workflow_event=["push"])):
            m = manifest()
            change(m)
            with self.assertRaises(ValueError):
                w.validate_manifest(m)


class CollectionTests(unittest.TestCase):
    def test_collect_resolves_sha_and_uses_sha_filter(self):
        client = FakeClient()
        s = w.collect_snapshot(manifest(), client, observed_at=AT)
        self.assertEqual(s["components"][0]["sha"], A)
        self.assertIn("/repos/example/core/actions/runs?head_sha=" + A + "&per_page=100&page=1", client.calls)
        self.assertEqual(s["components"][0]["repository_id"], 123)

    def test_source_failure_remains_unknown_and_report_not_zero_total(self):
        m, s = manifest(), snapshot(fail_pr=True)
        source = s["components"][0]["sources"]["pull_requests"]
        self.assertFalse(source["complete"])
        self.assertEqual(source["state"], "forbidden")
        report = w.render_report(m, s, now=NOW)
        self.assertIn("0 observed; total unknown", report)
        self.assertIn("Total unknown:", report)

    def test_pagination_follows_bounded_pages_and_flags_cap(self):
        class Pages:
            def get(self, path):
                return [{"number": i} for i in range(100)], {"Link": '<https://api.github.com/next>; rel="next"'}
        result = w._pages(Pages(), "/repos/a/b/pulls", {"state": "open"}, None, 2, AT)
        self.assertEqual(len(result["items"]), 200)
        self.assertFalse(result["complete"])
        self.assertTrue(result["truncated"])
        self.assertEqual(result["pages"], 2)

    def test_missing_link_full_page_checks_next_page(self):
        class Pages:
            def get(self, path):
                return ([{"number": i} for i in range(100)] if path.endswith("page=1") else []), {}
        result = w._pages(Pages(), "/repos/a/b/pulls", {}, None, 2, AT)
        self.assertTrue(result["complete"])
        self.assertEqual(result["pages"], 2)

    def test_actions_1000_limit_stays_incomplete(self):
        class Pages:
            def get(self, path):
                return {"total_count": 1001, "workflow_runs": [{"id": i} for i in range(100)]}, {}
        result = w._pages(Pages(), "/repos/a/b/actions/runs", {}, "workflow_runs", 20, AT)
        self.assertFalse(result["complete"])
        self.assertEqual(result["pages"], 10)
        self.assertIn("1000", result["error"])

    def test_partial_pages_preserve_observations_on_failure(self):
        class Pages:
            def get(self, path):
                if path.endswith("page=2"):
                    raise w.SourceError("rate_limited", "GitHub returned HTTP 429; response body omitted")
                return [{"number": 1}], {"link": '<https://api.github.com/next>; rel="next"'}
        result = w._pages(Pages(), "/repos/a/b/pulls", {}, None, 3, AT)
        self.assertEqual(result["state"], "partial")
        self.assertEqual(result["items"], [{"number": 1}])
        self.assertFalse(result["complete"])

    def test_network_and_http_errors_redact_tokens_and_bodies(self):
        secret = "a-secret-do-not-print"
        client = w.GitHubClient(secret)
        for error in (HTTPError("https://api.github.com/" + secret, 403, secret, {}, BytesIO(secret.encode())),
                      URLError(secret)):
            with patch.object(client.opener, "open", side_effect=error):
                with self.assertRaises(w.SourceError) as caught:
                    client.get("/repos/a/b")
                self.assertNotIn(secret, str(caught.exception))

    def test_fixed_origin_and_no_redirect(self):
        client = w.GitHubClient("secret")
        with self.assertRaises(w.SourceError):
            client.get("https://evil.example/repos/a/b")
        self.assertIsNone(w.NoRedirect().redirect_request(None, None, 302, "", {}, "https://evil.example"))


class CITests(unittest.TestCase):
    def assess(self, runs=None, mutate=None):
        m = manifest()
        s = snapshot(runs=runs)
        if mutate:
            mutate(m, s["components"][0])
        return w.evaluate_ci(m["components"][0], s["components"][0], now=NOW)

    def test_zero_workflows_unknown(self):
        self.assertEqual(self.assess([])["status"], "UNKNOWN")

    def test_unselected_workflows_unknown(self):
        result = self.assess(mutate=lambda m, r: m["components"][0].update(required_workflows=[]))
        self.assertEqual(result["status"], "UNKNOWN")

    def test_named_workflow_passes_only_at_exact_sha(self):
        self.assertEqual(self.assess()["status"], "PASSING OBSERVED")
        self.assertEqual(self.assess([run(head_sha=B)])["status"], "UNKNOWN")

    def test_latest_attempt_failure_overrides_prior_success(self):
        self.assertEqual(self.assess([run(), run(run_attempt=2, conclusion="failure")])["status"], "NOT PASSING")

    def test_newer_run_pending_overrides_old_success(self):
        newer = run(id=11, created_at=w.timestamp(NOW - timedelta(minutes=10)), status="in_progress", conclusion=None)
        self.assertEqual(self.assess([run(), newer])["status"], "PENDING")

    def test_unrelated_success_cannot_hide_selected_failure(self):
        runs = [run(conclusion="failure"), run(id=11, workflow_id=21, name="Dependency graph", created_at=AT)]
        self.assertEqual(self.assess(runs)["status"], "NOT PASSING")

    def test_neutral_skipped_cancelled_are_not_passing(self):
        for conclusion in ("neutral", "skipped", "cancelled", None):
            with self.subTest(conclusion=conclusion):
                self.assertEqual(self.assess([run(conclusion=conclusion)])["status"], "NOT PASSING")

    def test_missing_selected_workflow_and_ambiguous_name_unknown(self):
        self.assertEqual(self.assess(mutate=lambda m, r: m["components"][0].update(required_workflows=["CI", "Missing"]))["status"], "UNKNOWN")
        self.assertEqual(self.assess([run(), run(id=11, workflow_id=21)])["status"], "UNKNOWN")

    def test_partial_and_stale_observations_never_green(self):
        for changes in ({"complete": False, "truncated": True}, {"observed_at": w.timestamp(NOW - timedelta(days=2))}):
            result = self.assess(mutate=lambda m, r: r["sources"]["workflows"].update(changes))
            self.assertEqual(result["status"], "UNKNOWN")

    def test_old_execution_with_fresh_sha_observation_is_allowed(self):
        self.assertEqual(self.assess([run(created_at="2020-01-01T00:00:00Z")])["status"], "PASSING OBSERVED")

    def test_wrong_event_success_does_not_hide_push_failure(self):
        runs = [run(conclusion="failure"), run(id=11, event="workflow_dispatch", created_at=AT)]
        self.assertEqual(self.assess(runs)["status"], "NOT PASSING")
        self.assertEqual(self.assess([run(event="workflow_dispatch")])["status"], "UNKNOWN")
        self.assertEqual(self.assess([run(event=None)])["status"], "UNKNOWN")

    def test_future_execution_time_prevents_passing(self):
        self.assertEqual(self.assess([run(run_started_at=w.timestamp(NOW + timedelta(hours=1)))])["status"], "UNKNOWN")


class ReceiptTests(unittest.TestCase):
    def setUp(self):
        self.m = manifest()
        self.s = snapshot(self.m)
        self.r = receipt(self.m, self.s)

    def status(self):
        return w.evaluate_receipt(self.m, self.s, self.r, NOW)["status"]

    def test_matching_receipt_is_explicitly_unverified(self):
        result = w.evaluate_receipt(self.m, self.s, self.r, NOW)
        self.assertEqual(result["status"], "MATCHED SUPPLIED RECEIPT")
        self.assertIn("not authenticated", result["detail"])

    def test_missing_receipt_unknown(self):
        self.assertEqual(w.evaluate_receipt(self.m, self.s, now=NOW)["status"], "UNKNOWN")

    def test_manifest_or_sha_mismatch(self):
        self.r["manifest_sha256"] = "x" * 64
        self.assertEqual(self.status(), "MISMATCH")
        self.r = receipt(self.m, self.s)
        self.r["component_shas"]["core"] = B
        self.assertEqual(self.status(), "MISMATCH")

    def test_exact_component_set_required(self):
        for vector in ({}, {"core": A, "extra": B}):
            self.r["component_shas"] = vector
            self.assertEqual(self.status(), "MISMATCH")

    def test_expired_future_invalid_and_old_receipts(self):
        for changes, expected in (({"expires_at": w.timestamp(NOW)}, "STALE"),
                                  ({"checked_at": w.timestamp(NOW + timedelta(minutes=1))}, "INVALID"),
                                  ({"expires_at": "not a date"}, "INVALID"),
                                  ({"checked_at": w.timestamp(NOW - timedelta(days=2))}, "STALE")):
            self.r = receipt(self.m, self.s)
            self.r.update(changes)
            self.assertEqual(self.status(), expected)

    def test_missing_capability_and_unsafe_url_fail(self):
        self.r["capabilities"] = ["other"]
        self.assertEqual(self.status(), "MISMATCH")
        self.r = receipt(self.m, self.s)
        self.r["evidence_url"] = "javascript:alert(1)"
        self.assertEqual(self.status(), "INVALID")

    def test_wrong_repo_id_and_failed_receipt_fail(self):
        self.r["component_repository_ids"]["core"] = 321
        self.assertEqual(self.status(), "MISMATCH")
        self.r = receipt(self.m, self.s)
        self.r["result"] = "fail"
        self.assertEqual(self.status(), "FAILED SUPPLIED RECEIPT")

    def test_required_component_unknown_blocks_receipt(self):
        self.s["components"][0]["sha"] = None
        self.assertEqual(self.status(), "UNKNOWN")

    def test_contradictory_source_state_cannot_match(self):
        for name in ("repository", "commit"):
            self.s = snapshot(self.m)
            self.s["components"][0]["sources"][name]["state"] = "forbidden"
            self.assertEqual(self.status(), "UNKNOWN")

    def test_unused_optional_component_does_not_block_core_receipt(self):
        optional = {**self.m["components"][0], "id": "optional", "repository": "example/optional", "required": False}
        self.m["components"].append(optional)
        extra = copy.deepcopy(self.s["components"][0])
        extra.update(id="optional", repository="example/optional", repository_id=None, sha=None)
        for source in extra["sources"].values():
            source.update(complete=False, state="forbidden")
        self.s["components"].append(extra)
        self.s["manifest_sha256"] = w.manifest_digest(self.m)
        self.r = receipt(self.m, self.s)
        self.assertEqual(self.status(), "MATCHED SUPPLIED RECEIPT")
        self.assertEqual(w.acceptance_scope(self.m), {"core"})
        self.m["capabilities"][0]["components"].append("optional")
        self.s["manifest_sha256"] = w.manifest_digest(self.m)
        self.r = receipt(self.m, self.s)
        self.assertEqual(self.status(), "UNKNOWN")


class ReportAndCLITests(unittest.TestCase):
    def test_snapshot_cannot_be_relabelled_after_manifest_edit(self):
        m, s = manifest(), snapshot()
        m["product"]["name"] = "Another product"
        with self.assertRaises(ValueError):
            w.render_report(m, s, now=NOW)

    def test_html_text_is_escaped_and_dangerous_links_removed(self):
        m = manifest()
        m["product"]["name"] = '<script>alert("x")</script>'
        s = snapshot(m)
        s["components"][0]["sources"]["pull_requests"]["items"] = [
            {"number": 1, "title": '<img src=x onerror="alert(1)">', "html_url": "javascript:alert(1)"}]
        report = w.render_report(m, s, now=NOW)
        self.assertNotIn("<script>", report)
        self.assertNotIn("<img src=x", report)
        self.assertNotIn('href="javascript:', report)
        self.assertIn("&lt;script&gt;", report)
        self.assertIn("Content-Security-Policy", report)

    def test_snapshot_rejects_malformed_sources(self):
        m, s = manifest(), snapshot()
        s["components"][0]["sources"]["workflows"] = "oops"
        with self.assertRaises(ValueError):
            w.render_report(m, s, now=NOW)

    def test_snapshot_enum_type_and_contradictory_pr_state(self):
        m, s = manifest(), snapshot()
        s["mode"] = []
        with self.assertRaises(ValueError):
            w.render_report(m, s, now=NOW)
        s = snapshot()
        s["components"][0]["sources"]["pull_requests"]["state"] = "forbidden"
        report = w.render_report(m, s, now=NOW)
        self.assertIn("Total unknown:", report)
        self.assertNotIn("Complete fresh collection", report)

    def test_demo_generates_real_files_and_explicit_synthetic_banner(self):
        with tempfile.TemporaryDirectory() as directory, patch("sys.stdout", new_callable=StringIO):
            self.assertEqual(w.main(["demo", "--output-dir", directory]), 0)
            out = Path(directory)
            self.assertEqual(w.read_json(out / "snapshot.json")["mode"], "demo")
            report = (out / "report.html").read_text()
            self.assertIn("DEMO · SYNTHETIC DATA", report)
            self.assertIn("MATCHED SUPPLIED RECEIPT", report)
            self.assertTrue((out / "receipt.json").is_file())

    def test_json_duplicate_keys_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.json"
            path.write_text('{"key":1,"key":2}')
            with self.assertRaises(ValueError):
                w.read_json(path)

    def test_collect_partial_exits_two_but_retains_snapshot(self):
        with tempfile.TemporaryDirectory() as directory, patch("sys.stdout", new_callable=StringIO):
            path = Path(directory)
            w.write_json(path / "product.json", manifest())
            with patch.object(w, "GitHubClient", return_value=FakeClient(fail_pr=True)):
                code = w.main(["collect", "--manifest", str(path / "product.json"), "--output", str(path / "snapshot.json")])
            self.assertEqual(code, 2)
            self.assertTrue((path / "snapshot.json").is_file())


if __name__ == "__main__":
    unittest.main()
