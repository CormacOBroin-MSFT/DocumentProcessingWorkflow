"""
Azure Content Understanding Client
Lightweight REST wrapper based on the official Azure Samples SDK:
https://github.com/Azure-Samples/azure-ai-content-understanding-python

Only includes the methods needed for this project:
- Setting model deployment defaults
- Creating/checking analyzers
- Analyzing documents (URL-based)
- Polling for async results
"""
import json
import logging
import time
import requests
from typing import Any, Dict, Optional
from requests.models import Response

logger = logging.getLogger(__name__)

POLL_TIMEOUT_SECONDS = 180


class ContentUnderstandingClient:
    """Minimal Content Understanding REST client."""

    def __init__(
        self,
        endpoint: str,
        api_version: str = "2025-11-01",
        subscription_key: str = None,
        token_provider: callable = None,
    ):
        if not subscription_key and not token_provider:
            raise ValueError("Either subscription_key or token_provider must be provided.")
        if not endpoint:
            raise ValueError("Endpoint must be provided.")

        self._endpoint = endpoint.rstrip("/")
        self._api_version = api_version
        self._token_provider = token_provider

        if subscription_key:
            self._headers = {"Ocp-Apim-Subscription-Key": subscription_key}
        else:
            token = token_provider()
            self._headers = {"Authorization": f"Bearer {token}"}

    def _refresh_token(self):
        """Refresh the bearer token if using token-based auth."""
        if self._token_provider:
            token = self._token_provider()
            self._headers = {"Authorization": f"Bearer {token}"}

    def _raise_for_status(self, response: Response):
        """Raise HTTPError with detailed error info from response body."""
        if response.ok:
            return
        detail = ""
        try:
            body = response.json()
            if "error" in body:
                err = body["error"]
                detail = f" - {err.get('code', '')}: {err.get('message', '')}"
        except Exception:
            if response.text:
                detail = f" - {response.text[:300]}"
        msg = f"HTTP {response.status_code}{detail}"
        raise requests.exceptions.HTTPError(msg, response=response)

    # ── URL builders ──────────────────────────────────────────────

    def _analyzer_url(self, analyzer_id: str) -> str:
        return f"{self._endpoint}/contentunderstanding/analyzers/{analyzer_id}?api-version={self._api_version}"

    def _analyze_url(self, analyzer_id: str) -> str:
        return f"{self._endpoint}/contentunderstanding/analyzers/{analyzer_id}:analyze?api-version={self._api_version}"

    def _defaults_url(self) -> str:
        return f"{self._endpoint}/contentunderstanding/defaults?api-version={self._api_version}"

    # ── Defaults (model deployment mappings) ──────────────────────

    def get_defaults(self) -> Dict[str, Any]:
        self._refresh_token()
        resp = requests.get(self._defaults_url(), headers=self._headers)
        self._raise_for_status(resp)
        return resp.json()

    def update_defaults(self, model_deployments: Dict[str, Optional[str]]) -> Dict[str, Any]:
        """Set model deployment mappings (e.g. {"gpt-4.1": "my-deployment"})."""
        self._refresh_token()
        headers = {**self._headers, "Content-Type": "application/merge-patch+json"}
        body = {"modelDeployments": model_deployments}
        resp = requests.patch(self._defaults_url(), headers=headers, json=body)
        self._raise_for_status(resp)
        return resp.json()

    # ── Analyzer CRUD ─────────────────────────────────────────────

    def get_analyzer(self, analyzer_id: str) -> Dict[str, Any]:
        """Get analyzer details. Raises HTTPError (404) if not found."""
        self._refresh_token()
        resp = requests.get(self._analyzer_url(analyzer_id), headers=self._headers)
        self._raise_for_status(resp)
        return resp.json()

    def begin_create_analyzer(self, analyzer_id: str, analyzer_template: dict) -> Response:
        """Start async analyzer creation. Returns response with operation-location header."""
        self._refresh_token()
        headers = {**self._headers, "Content-Type": "application/json"}
        resp = requests.put(self._analyzer_url(analyzer_id), headers=headers, json=analyzer_template)
        self._raise_for_status(resp)
        logger.info(f"Analyzer '{analyzer_id}' create request accepted.")
        return resp

    def delete_analyzer(self, analyzer_id: str) -> Response:
        self._refresh_token()
        resp = requests.delete(self._analyzer_url(analyzer_id), headers=self._headers)
        self._raise_for_status(resp)
        return resp

    # ── Analyze ───────────────────────────────────────────────────

    def begin_analyze(self, analyzer_id: str, url: str) -> Response:
        """Start async analysis of a document at the given URL."""
        self._refresh_token()
        headers = {**self._headers, "Content-Type": "application/json"}
        body = {"inputs": [{"url": url}]}
        resp = requests.post(self._analyze_url(analyzer_id), headers=headers, json=body)
        self._raise_for_status(resp)
        return resp

    # ── Poll ──────────────────────────────────────────────────────

    def poll_result(
        self,
        response: Response,
        timeout_seconds: int = POLL_TIMEOUT_SECONDS,
        polling_interval: int = 2,
    ) -> Dict[str, Any]:
        """Poll operation-location until succeeded/failed/timeout."""
        operation_location = response.headers.get("operation-location", "")
        if not operation_location:
            raise ValueError("No operation-location header in response.")

        start = time.time()
        while True:
            if time.time() - start > timeout_seconds:
                raise TimeoutError(f"Operation timed out after {timeout_seconds}s")

            self._refresh_token()
            resp = requests.get(operation_location, headers=self._headers)
            self._raise_for_status(resp)
            result = resp.json()
            status = result.get("status", "").lower()

            if status == "succeeded":
                logger.info(f"Operation completed in {time.time() - start:.1f}s")
                return result
            elif status == "failed":
                error = result.get("error", {}).get("message", "Unknown")
                raise RuntimeError(f"Operation failed: {error}")

            time.sleep(polling_interval)
