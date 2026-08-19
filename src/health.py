"""Health check functions for model and AAP connectivity."""

from __future__ import annotations

from langchain_core.messages import HumanMessage

from src.config import get_settings
from src.model import get_model
from src.publishers.aap_client import AAPClient, AAPConfig
from src.publishers.galaxy_client import GalaxyClient


def check_model() -> tuple[str, str]:
    """Verify LLM connectivity by sending a minimal request.

    Returns:
        (status, message) where status is "ok" or "fail"
    """
    settings = get_settings().llm
    model_name = settings.model
    try:
        model = get_model()
        model.bind(max_tokens=1).invoke([HumanMessage(content="hi")])
        return "ok", f"Model ({model_name}): responded successfully"
    except Exception as e:
        return "fail", f"Model ({model_name}): {e}"


def check_aap() -> tuple[str, str]:
    """Verify AAP Controller connectivity via the /ping/ endpoint.

    Returns:
        (status, message) where status is "ok", "fail", or "skip"
    """
    aap_settings = get_settings().aap

    if not aap_settings.is_enabled():
        return "skip", "AAP: not configured (AAP_CONTROLLER_URL not set)"

    controller_url = aap_settings.controller_url
    try:
        cfg = AAPConfig()
        client = AAPClient(cfg)
        client._request("GET", "/ping/")
        return "ok", f"AAP ({controller_url}): ping successful"
    except Exception as e:
        return "fail", f"AAP ({controller_url}): {e}"


def check_galaxy() -> tuple[str, str]:
    """Verify Galaxy (Private Automation Hub) connectivity.

    Returns:
        (status, message) where status is "ok", "fail", or "skip"
    """
    aap_settings = get_settings().aap

    if not aap_settings.is_galaxy_enabled():
        return (
            "skip",
            "Galaxy: not configured (AAP_CONTROLLER_URL or AAP_OAUTH_TOKEN not set)",
        )

    galaxy_url = aap_settings.galaxy_url
    try:
        client = GalaxyClient(aap_settings)
        client._request("GET", "/collections/")
        return "ok", f"Galaxy ({galaxy_url}): reachable"
    except Exception as e:
        return "fail", f"Galaxy ({galaxy_url}): {e}"
