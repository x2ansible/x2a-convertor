"""Report client for posting execution artifacts to the x2a API."""

import uuid
from enum import Enum
from typing import Any, ClassVar

import requests

from src.types.telemetry import TELEMETRY_FILENAME, Telemetry
from src.utils.logging import get_logger

logger = get_logger(__name__)


class ArtifactType(str, Enum):
    """Valid artifact types matching the API schema."""

    MIGRATION_PLAN = "migration_plan"
    MODULE_MIGRATION_PLAN = "module_migration_plan"
    MIGRATED_SOURCES = "migrated_sources"
    PROJECT_METADATA = "project_metadata"


class ReportClient:
    """Posts execution artifacts and telemetry to the collectArtifacts API endpoint.

    Attributes:
        url: Full URL to POST to (including query params)
        job_id: UUID of the completed job
        artifact_pairs: List of "type:url" strings
        error_message: Optional error message (sets status to "error")
    """

    VALID_ARTIFACT_TYPES: ClassVar[set[str]] = {t.value for t in ArtifactType}

    def __init__(
        self,
        url: str,
        job_id: str,
        artifact_pairs: list[str],
        error_message: str | None = None,
    ) -> None:
        self._url = url
        self._job_id = job_id
        self._artifact_pairs = artifact_pairs
        self._error_message = error_message

    def send(self) -> None:
        """Build and POST the artifacts payload to the API."""
        payload = self._build_payload()
        logger.info(
            "Posting artifacts", url=self._url, artifact_count=len(payload["artifacts"])
        )

        response = requests.post(self._url, json=payload, timeout=30)
        response.raise_for_status()
        logger.info("Report accepted", status_code=response.status_code)

    def _build_payload(self) -> dict[str, Any]:
        """Build the JSON body matching the collectArtifacts request schema."""
        status = "error" if self._error_message else "success"
        payload: dict[str, Any] = {
            "status": status,
            "jobId": self._job_id,
            "artifacts": self._build_artifacts(),
        }

        if self._error_message:
            payload["errorDetails"] = self._error_message

        telemetry = self._read_telemetry()
        if telemetry:
            payload["telemetry"] = telemetry

        return payload

    def _build_artifacts(self) -> list[dict[str, Any]]:
        """Parse artifact pairs and read file contents."""
        return [self._parse_artifact(pair) for pair in self._artifact_pairs]

    def _parse_artifact(self, pair: str) -> dict[str, Any]:
        """Parse a single 'type:url' string into an artifact dict.

        Args:
            pair: String in format "artifact_type:url"

        Returns:
            Artifact dict with id, type, and value fields
        """
        parts = pair.split(":", 1)
        if len(parts) != 2:
            raise ValueError(f"Invalid artifact format '{pair}'. Expected 'type:url'.")

        artifact_type, url = parts
        if artifact_type not in self.VALID_ARTIFACT_TYPES:
            raise ValueError(
                f"Invalid artifact type '{artifact_type}'. "
                f"Valid types: {', '.join(sorted(self.VALID_ARTIFACT_TYPES))}"
            )

        return {
            "id": str(uuid.uuid4()),
            "type": artifact_type,
            "value": url,
        }

    def _read_telemetry(self) -> dict[str, Any] | None:
        """Read telemetry from .x2a-telemetry.json and map to API schema."""
        telemetry = Telemetry.load_from()
        if not telemetry:
            logger.debug("No telemetry file found", path=TELEMETRY_FILENAME)
            return None
        return telemetry.to_api_dict()


def report_artifacts(
    url: str,
    job_id: str,
    artifacts: list[str],
    error_message: str | None = None,
) -> None:
    """Public entry point to report artifacts to the x2a API.

    Args:
        url: Full URL to POST to (including query params)
        job_id: UUID of the completed job
        artifacts: List of "type:url" strings
        error_message: Optional error message (sets status to "error")
    """
    client = ReportClient(
        url=url,
        job_id=job_id,
        artifact_pairs=artifacts,
        error_message=error_message,
    )
    client.send()
