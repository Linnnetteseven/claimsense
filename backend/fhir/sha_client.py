"""
SHA Kenya eClaims FHIR client.

Targets the SHA UAT HAPI FHIR R4B server.

This client deliberately does NOT assume that the UAT server accepts
provider Claim Bundles until that operation is confirmed.
"""

import logging
from typing import Any

import httpx

from config import config

logger = logging.getLogger(__name__)


class SHAClient:
    def __init__(self) -> None:
        self.base_url = config.SHA_FHIR_URL.rstrip("/")

        self.headers = {
            "Accept": "application/fhir+json",
            "Content-Type": "application/fhir+json",
        }

        if config.SHA_FHIR_TOKEN:
            self.headers["Authorization"] = (
                f"Bearer {config.SHA_FHIR_TOKEN}"
            )

    async def validate_claim(self, claim: dict) -> dict:
        """
        Validate a Claim against the SHA UAT FHIR server.

        SHA UAT advertises POST /Claim/$validate.
        """
        url = f"{self.base_url}/Claim/$validate"

        logger.info("SHA validating Claim")

        async with httpx.AsyncClient(
            headers=self.headers,
            verify=config.SHA_FHIR_VERIFY_SSL,
            timeout=httpx.Timeout(30.0),
        ) as client:
            response = await client.post(
                url,
                json=claim,
            )

            logger.info(
                "SHA validation response: %s",
                response.status_code,
            )

            return self._parse_response(response)

    async def validate_bundle(self, bundle: dict) -> dict:
        """
        Attempt Bundle validation.

        This is kept separate because the UAT server's exact Bundle
        operation needs confirmation.
        """
        url = f"{self.base_url}/Bundle/$validate"

        logger.info("SHA validating Bundle")

        async with httpx.AsyncClient(
            headers=self.headers,
            verify=config.SHA_FHIR_VERIFY_SSL,
            timeout=httpx.Timeout(30.0),
        ) as client:
            response = await client.post(
                url,
                json=bundle,
            )

            logger.info(
                "SHA Bundle validation response: %s",
                response.status_code,
            )

            return self._parse_response(response)

    async def submit_bundle(self, bundle: dict) -> dict:
        """
        Submit a provider Bundle.

        IMPORTANT:
        The Kenya eClaims IG describes POST /fhir/Bundle as the
        provider transaction, but UAT authorization/operation support
        still needs confirmation.
        """
        url = f"{self.base_url}/Bundle"

        logger.info("Submitting eClaims Bundle to SHA")

        async with httpx.AsyncClient(
            headers=self.headers,
            verify=config.SHA_FHIR_VERIFY_SSL,
            timeout=httpx.Timeout(30.0),
        ) as client:
            response = await client.post(
                url,
                json=bundle,
            )

            logger.info(
                "SHA Bundle submission response: %s",
                response.status_code,
            )

            return self._parse_response(response)

    async def get_claim(self, claim_id: str) -> dict:
        """Read a Claim from SHA UAT."""
        url = f"{self.base_url}/Claim/{claim_id}"

        async with httpx.AsyncClient(
            headers=self.headers,
            verify=config.SHA_FHIR_VERIFY_SSL,
            timeout=httpx.Timeout(20.0),
        ) as client:
            response = await client.get(url)
            return self._parse_response(response)

    @staticmethod
    def _parse_response(response: httpx.Response) -> dict:
        try:
            body: Any = response.json()
        except Exception:
            body = {
                "raw": response.text,
            }

        return {
            "http_status": response.status_code,
            "ok": response.is_success,
            "resource": body,
        }


sha_client = SHAClient()
