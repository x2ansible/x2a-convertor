"""Tests for the report module that posts artifacts to the x2a API."""

import hashlib
import hmac
import json

import pytest
import responses
from requests.exceptions import HTTPError

from src.report.report import ArtifactType, ReportClient, report_artifacts

COLLECT_URL = "https://server.example/projects/abc-123/collectArtifacts?phase=init"

PLAN_URL = "https://storage.example/artifacts/migration-plan.md"
SOURCES_URL = "https://storage.example/artifacts/roles/nginx.tar.gz"
MODULE_PLAN_URL = "https://storage.example/artifacts/migration-plan-nginx.md"

CALLBACK_TOKEN = "a1b2c3d4e5f67890abcdef1234567890abcdef1234567890abcdef1234567890"


class TestArtifactType:
    """Tests for ArtifactType enum."""

    def test_valid_values(self):
        assert ArtifactType.MIGRATION_PLAN.value == "migration_plan"
        assert ArtifactType.MODULE_MIGRATION_PLAN.value == "module_migration_plan"
        assert ArtifactType.MIGRATED_SOURCES.value == "migrated_sources"
        assert ArtifactType.PROJECT_METADATA.value == "project_metadata"
        assert ArtifactType.ANSIBLE_PROJECT.value == "ansible_project"

    def test_enum_count(self):
        assert len(ArtifactType) == 5


class TestReportClientParseArtifact:
    """Tests for artifact parsing and validation."""

    def test_valid_artifact_pair(self):
        client = ReportClient(
            url=COLLECT_URL,
            job_id="job-1",
            artifact_pairs=[f"migration_plan:{PLAN_URL}"],
            callback_token=CALLBACK_TOKEN,
        )
        artifacts = client._build_artifacts()

        assert len(artifacts) == 1
        assert artifacts[0]["type"] == "migration_plan"
        assert artifacts[0]["value"] == PLAN_URL
        assert "id" in artifacts[0]

    def test_multiple_artifacts(self):
        client = ReportClient(
            url=COLLECT_URL,
            job_id="job-1",
            artifact_pairs=[
                f"migration_plan:{PLAN_URL}",
                f"migrated_sources:{SOURCES_URL}",
            ],
            callback_token=CALLBACK_TOKEN,
        )
        artifacts = client._build_artifacts()

        assert len(artifacts) == 2
        types = {a["type"] for a in artifacts}
        assert types == {"migration_plan", "migrated_sources"}
        values = {a["value"] for a in artifacts}
        assert values == {PLAN_URL, SOURCES_URL}

    def test_invalid_artifact_type_raises(self):
        client = ReportClient(
            url=COLLECT_URL,
            job_id="job-1",
            artifact_pairs=[f"invalid_type:{PLAN_URL}"],
            callback_token=CALLBACK_TOKEN,
        )

        with pytest.raises(ValueError, match="Invalid artifact type 'invalid_type'"):
            client._build_artifacts()

    def test_missing_separator_raises(self):
        client = ReportClient(
            url=COLLECT_URL,
            job_id="job-1",
            artifact_pairs=["no_separator_here"],
            callback_token=CALLBACK_TOKEN,
        )

        with pytest.raises(ValueError, match="Expected 'type:url'"):
            client._build_artifacts()

    def test_artifact_ids_are_unique(self):
        client = ReportClient(
            url=COLLECT_URL,
            job_id="job-1",
            artifact_pairs=[
                f"migration_plan:{PLAN_URL}",
                f"migration_plan:{PLAN_URL}",
            ],
            callback_token=CALLBACK_TOKEN,
        )
        artifacts = client._build_artifacts()

        ids = [a["id"] for a in artifacts]
        assert len(ids) == len(set(ids))

    def test_all_valid_artifact_types(self):
        for artifact_type in ArtifactType:
            client = ReportClient(
                url=COLLECT_URL,
                job_id="job-1",
                artifact_pairs=[f"{artifact_type.value}:{PLAN_URL}"],
                callback_token=CALLBACK_TOKEN,
            )
            artifacts = client._build_artifacts()
            assert artifacts[0]["type"] == artifact_type.value

    def test_url_with_query_params_preserved(self):
        artifact_url = "https://storage.example/file.md?token=abc&v=2"
        client = ReportClient(
            url=COLLECT_URL,
            job_id="job-1",
            artifact_pairs=[f"migration_plan:{artifact_url}"],
            callback_token=CALLBACK_TOKEN,
        )
        artifacts = client._build_artifacts()

        assert artifacts[0]["value"] == artifact_url


class TestReportClientPayload:
    """Tests for payload building logic."""

    def test_success_status_when_no_error(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)

        client = ReportClient(
            url=COLLECT_URL,
            job_id="job-1",
            artifact_pairs=[f"migration_plan:{PLAN_URL}"],
            callback_token=CALLBACK_TOKEN,
        )
        payload = client._build_payload()

        assert payload["status"] == "success"
        assert "errorDetails" not in payload

    def test_error_status_when_error_message(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)

        client = ReportClient(
            url=COLLECT_URL,
            job_id="job-1",
            artifact_pairs=[f"migration_plan:{PLAN_URL}"],
            callback_token=CALLBACK_TOKEN,
            error_message="something went wrong",
        )
        payload = client._build_payload()

        assert payload["status"] == "error"
        assert payload["errorDetails"] == "something went wrong"

    def test_job_id_in_payload(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)

        client = ReportClient(
            url=COLLECT_URL,
            job_id="my-job-uuid",
            artifact_pairs=[f"migration_plan:{PLAN_URL}"],
            callback_token=CALLBACK_TOKEN,
        )
        payload = client._build_payload()

        assert payload["jobId"] == "my-job-uuid"

    def test_commit_id_included_in_payload(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)

        client = ReportClient(
            url=COLLECT_URL,
            job_id="job-1",
            artifact_pairs=[f"migration_plan:{PLAN_URL}"],
            callback_token=CALLBACK_TOKEN,
            commit_id="abc123def456",
        )
        payload = client._build_payload()

        assert payload["commitId"] == "abc123def456"

    def test_commit_id_omitted_when_none(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)

        client = ReportClient(
            url=COLLECT_URL,
            job_id="job-1",
            artifact_pairs=[f"migration_plan:{PLAN_URL}"],
            callback_token=CALLBACK_TOKEN,
        )
        payload = client._build_payload()

        assert "commitId" not in payload

    def test_no_telemetry_when_file_missing(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)

        client = ReportClient(
            url=COLLECT_URL,
            job_id="job-1",
            artifact_pairs=[f"migration_plan:{PLAN_URL}"],
            callback_token=CALLBACK_TOKEN,
        )
        payload = client._build_payload()

        assert "telemetry" not in payload


class TestReportClientSignature:
    """Tests for HMAC-SHA256 signature generation."""

    def test_signature_generation(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)

        client = ReportClient(
            url=COLLECT_URL,
            job_id="job-1",
            artifact_pairs=[f"migration_plan:{PLAN_URL}"],
            callback_token=CALLBACK_TOKEN,
        )
        payload = client._build_payload()
        signature, body_bytes = client._generate_signature(payload)

        expected_body_bytes = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        token_bytes = CALLBACK_TOKEN.encode("utf-8")
        expected_signature = hmac.new(
            token_bytes, expected_body_bytes, hashlib.sha256
        ).hexdigest()

        assert signature == expected_signature
        assert len(signature) == 64
        assert body_bytes == expected_body_bytes

    def test_signature_differs_for_different_payloads(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)

        client1 = ReportClient(
            url=COLLECT_URL,
            job_id="job-1",
            artifact_pairs=[f"migration_plan:{PLAN_URL}"],
            callback_token=CALLBACK_TOKEN,
        )
        client2 = ReportClient(
            url=COLLECT_URL,
            job_id="job-2",
            artifact_pairs=[f"migration_plan:{PLAN_URL}"],
            callback_token=CALLBACK_TOKEN,
        )

        payload1 = client1._build_payload()
        payload2 = client2._build_payload()
        signature1, _ = client1._generate_signature(payload1)
        signature2, _ = client2._generate_signature(payload2)

        assert signature1 != signature2


class TestReportClientSend:
    """Tests for the HTTP POST behavior."""

    @responses.activate
    def test_successful_post(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)

        responses.add(
            responses.POST,
            COLLECT_URL,
            json={"message": "Artifacts collected"},
            status=200,
        )

        client = ReportClient(
            url=COLLECT_URL,
            job_id="job-uuid-1",
            artifact_pairs=[f"migration_plan:{PLAN_URL}"],
            callback_token=CALLBACK_TOKEN,
        )
        client.send()

        assert len(responses.calls) == 1
        assert responses.calls[0].request.body is not None
        body = json.loads(responses.calls[0].request.body)
        assert body["status"] == "success"
        assert body["jobId"] == "job-uuid-1"
        assert len(body["artifacts"]) == 1
        assert body["artifacts"][0]["type"] == "migration_plan"
        assert body["artifacts"][0]["value"] == PLAN_URL

    @responses.activate
    def test_post_with_error_message(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)

        responses.add(responses.POST, COLLECT_URL, json={"message": "ok"}, status=200)

        client = ReportClient(
            url=COLLECT_URL,
            job_id="job-1",
            artifact_pairs=[f"migration_plan:{PLAN_URL}"],
            callback_token=CALLBACK_TOKEN,
            error_message="Agent failed",
        )
        client.send()

        assert responses.calls[0].request.body is not None
        body = json.loads(responses.calls[0].request.body)
        assert body["status"] == "error"
        assert body["errorDetails"] == "Agent failed"

    @responses.activate
    def test_post_with_telemetry(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        telemetry_data = {
            "phase": "init",
            "started_at": "2026-01-15T10:00:00",
            "summary": "Done",
            "agents": {},
        }
        (tmp_path / ".x2a-telemetry.json").write_text(json.dumps(telemetry_data))

        responses.add(responses.POST, COLLECT_URL, json={"message": "ok"}, status=200)

        client = ReportClient(
            url=COLLECT_URL,
            job_id="job-1",
            artifact_pairs=[f"migration_plan:{PLAN_URL}"],
            callback_token=CALLBACK_TOKEN,
        )
        client.send()

        assert responses.calls[0].request.body is not None
        body = json.loads(responses.calls[0].request.body)
        assert "telemetry" in body
        assert body["telemetry"]["phase"] == "init"
        assert body["telemetry"]["startedAt"] == "2026-01-15T10:00:00"

    @responses.activate
    def test_post_with_telemetry_from_source_dir(self, tmp_path):
        """Telemetry is read from source_dir, not CWD."""
        source_dir = tmp_path / "source"
        source_dir.mkdir()
        telemetry_data = {
            "phase": "analyze",
            "started_at": "2026-02-01T12:00:00",
            "summary": "Analyzed",
            "agents": {},
        }
        (source_dir / ".x2a-telemetry.json").write_text(json.dumps(telemetry_data))

        responses.add(responses.POST, COLLECT_URL, json={"message": "ok"}, status=200)

        client = ReportClient(
            url=COLLECT_URL,
            job_id="job-1",
            artifact_pairs=[f"migration_plan:{PLAN_URL}"],
            callback_token=CALLBACK_TOKEN,
            source_dir=str(source_dir),
        )
        client.send()

        assert responses.calls[0].request.body is not None
        body = json.loads(responses.calls[0].request.body)
        assert "telemetry" in body
        assert body["telemetry"]["phase"] == "analyze"
        assert body["telemetry"]["startedAt"] == "2026-02-01T12:00:00"

    @responses.activate
    def test_post_raises_on_server_error(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)

        responses.add(responses.POST, COLLECT_URL, status=500)

        client = ReportClient(
            url=COLLECT_URL,
            job_id="job-1",
            artifact_pairs=[f"migration_plan:{PLAN_URL}"],
            callback_token=CALLBACK_TOKEN,
        )

        with pytest.raises(HTTPError):
            client.send()

    @responses.activate
    def test_post_raises_on_not_found(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)

        responses.add(responses.POST, COLLECT_URL, status=404)

        client = ReportClient(
            url=COLLECT_URL,
            job_id="job-1",
            artifact_pairs=[f"migration_plan:{PLAN_URL}"],
            callback_token=CALLBACK_TOKEN,
        )

        with pytest.raises(HTTPError):
            client.send()

    @responses.activate
    def test_post_content_type_is_json(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)

        responses.add(responses.POST, COLLECT_URL, json={"message": "ok"}, status=200)

        client = ReportClient(
            url=COLLECT_URL,
            job_id="job-1",
            artifact_pairs=[f"migration_plan:{PLAN_URL}"],
            callback_token=CALLBACK_TOKEN,
        )
        client.send()

        assert responses.calls[0].request.headers is not None
        assert "application/json" in responses.calls[0].request.headers["Content-Type"]

    @responses.activate
    def test_post_includes_signature_header(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)

        responses.add(responses.POST, COLLECT_URL, json={"message": "ok"}, status=200)

        client = ReportClient(
            url=COLLECT_URL,
            job_id="job-1",
            artifact_pairs=[f"migration_plan:{PLAN_URL}"],
            callback_token=CALLBACK_TOKEN,
        )
        client.send()

        assert responses.calls[0].request.headers is not None
        assert "X-Callback-Signature" in responses.calls[0].request.headers
        signature = responses.calls[0].request.headers["X-Callback-Signature"]
        assert len(signature) == 64


class TestReportArtifactsFunction:
    """Tests for the public report_artifacts entry point."""

    @responses.activate
    def test_report_artifacts_success(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)

        responses.add(responses.POST, COLLECT_URL, json={"message": "ok"}, status=200)

        report_artifacts(
            url=COLLECT_URL,
            job_id="job-1",
            artifacts=[f"migration_plan:{PLAN_URL}"],
            callback_token=CALLBACK_TOKEN,
        )

        assert len(responses.calls) == 1

    @responses.activate
    def test_report_artifacts_with_error(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)

        responses.add(responses.POST, COLLECT_URL, json={"message": "ok"}, status=200)

        report_artifacts(
            url=COLLECT_URL,
            job_id="job-1",
            artifacts=[f"migration_plan:{PLAN_URL}"],
            callback_token=CALLBACK_TOKEN,
            error_message="failed",
        )

        assert responses.calls[0].request.body is not None
        body = json.loads(responses.calls[0].request.body)
        assert body["status"] == "error"
        assert body["errorDetails"] == "failed"
