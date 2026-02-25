"""CLIO API client for accessing CLIO Manage data.

This module provides a Python wrapper for the CLIO API v4.
Adapted for FastAPI/Vercel deployment.
"""

from __future__ import annotations

import random
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

import requests
from pydantic import BaseModel


class ClioAPIError(Exception):
    """Base exception for CLIO API errors."""

    pass


class ClioAuthError(ClioAPIError):
    """Authentication/authorization error."""

    pass


class ClioRateLimitError(ClioAPIError):
    """Rate limit exceeded error."""

    pass


# Pydantic models for type safety
class ClioContact(BaseModel):
    """Clio contact model."""

    id: int
    name: str
    type: str
    email: Optional[str] = None
    phone: Optional[str] = None


class ClioMatter(BaseModel):
    """Clio matter model."""

    id: int
    display_number: str
    description: Optional[str] = None
    client_name: str
    practice_area: Optional[str] = None
    status: str
    open_date: Optional[datetime] = None
    close_date: Optional[datetime] = None
    custom_fields: Dict[str, Any] = {}


class ClioCommunication(BaseModel):
    """Clio communication model."""

    id: int
    subject: str
    date: Optional[datetime] = None
    sender: ClioContact
    recipients: List[ClioContact]
    body: str
    communication_type: str
    matter_id: int


class ClioClient:
    """Client for CLIO API v4."""

    def __init__(self, access_token: str):
        """Initialize CLIO API client.

        Args:
        ----
            access_token: OAuth access token

        """
        self.access_token = access_token
        self.base_url = "https://app.clio.com/api/v4"
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            }
        )

        # Rate limiting: CLIO allows 30 requests per 10 seconds
        self.rate_limit_delay = 0.4  # ~2.5 requests/sec to stay under shared account bursts
        self.last_request_time = 0

    def _wait_for_rate_limit(self):
        """Enforce rate limiting between requests."""
        elapsed = time.time() - self.last_request_time
        if elapsed < self.rate_limit_delay:
            time.sleep(self.rate_limit_delay - elapsed)
        self.last_request_time = time.time()

    def _make_request(
        self, method: str, endpoint: str, params: Dict = None, data: Dict = None, max_retries: int = 5
    ) -> Dict[str, Any]:
        """Make HTTP request to CLIO API with error handling.

        Args:
        ----
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint (without base URL)
            params: Query parameters
            data: Request body data
            max_retries: Maximum retry attempts for rate limits

        Returns:
        -------
            Dict: JSON response data

        Raises:
        ------
            ClioAuthError: Authentication/authorization error
            ClioRateLimitError: Rate limit exceeded
            ClioAPIError: Other API errors

        """
        self._wait_for_rate_limit()

        # Allow either relative endpoints (e.g. "documents.json") or absolute next-page URLs from Clio.
        if isinstance(endpoint, str) and endpoint.startswith("http"):
            url = endpoint
        else:
            url = f"{self.base_url}/{endpoint}"

        for attempt in range(max_retries):
            try:
                response = self.session.request(method=method, url=url, params=params, json=data, timeout=30)

                # Handle rate limiting with exponential backoff
                if response.status_code == 429:
                    if attempt < max_retries - 1:
                        retry_after_header = (response.headers or {}).get("Retry-After")
                        wait_time: float
                        if retry_after_header:
                            try:
                                wait_time = max(float(retry_after_header), 1.0)
                            except (TypeError, ValueError):
                                wait_time = float(min(2 ** (attempt + 1), 20))
                        else:
                            # 2s, 4s, 8s, 16s (+ jitter) gives Clio enough recovery window.
                            wait_time = float(min(2 ** (attempt + 1), 20)) + random.uniform(0, 0.5)
                        time.sleep(wait_time)
                        continue
                    else:
                        raise ClioRateLimitError(f"Rate limit exceeded after {max_retries} retries")

                # Handle authentication errors
                if response.status_code == 401:
                    raise ClioAuthError("Access token expired or invalid")

                if response.status_code == 403:
                    raise ClioAuthError("Insufficient permissions for this resource")

                # Handle other errors
                if response.status_code >= 400:
                    error_msg = f"API error {response.status_code}: {response.text}"
                    raise ClioAPIError(error_msg)

                return response.json()

            except requests.exceptions.RequestException as e:
                if attempt < max_retries - 1:
                    time.sleep(1)
                    continue
                else:
                    raise ClioAPIError(f"Request failed: {e}") from e

        raise ClioAPIError("Max retries exceeded")

    def get_matter(self, matter_id: int) -> ClioMatter:
        """Get details for a specific matter.

        Args:
        ----
            matter_id: CLIO matter ID

        Returns:
        -------
            ClioMatter object with full details

        """
        params = {
            "fields": "id,display_number,description,client,practice_area,status,open_date,close_date",
        }

        try:
            response = self._make_request("GET", f"matters/{matter_id}.json", params=params)
            matter_data = response.get("data", {})

            # Parse matter data
            client = matter_data.get("client", {})
            practice_area_data = matter_data.get("practice_area", {})

            return ClioMatter(
                id=matter_data["id"],
                display_number=matter_data.get("display_number", ""),
                description=matter_data.get("description", ""),
                client_name=client.get("name", "Unknown Client"),
                practice_area=practice_area_data.get("name") if practice_area_data else None,
                status=matter_data.get("status", ""),
                open_date=self._parse_date(matter_data.get("open_date")),
                close_date=self._parse_date(matter_data.get("close_date")),
            )

        except ClioAPIError:
            raise
        except Exception as e:
            raise ClioAPIError(f"Failed to fetch matter: {e}") from e

    def search_matters(self, query: str, limit: int = 20) -> List[ClioMatter]:
        """Search matters by client name or matter number.

        Args:
        ----
            query: Search query (client name, matter number, etc.)
            limit: Maximum number of results

        Returns:
        -------
            List of ClioMatter objects

        """
        params = {
            "query": query,
            "fields": "id,display_number,description,client,practice_area,status,open_date",
            "limit": limit,
        }

        try:
            response = self._make_request("GET", "matters.json", params=params)

            matters = []
            for matter_data in response.get("data", []):
                # Parse matter data
                client = matter_data.get("client", {})
                practice_area_data = matter_data.get("practice_area", {})

                matter = ClioMatter(
                    id=matter_data["id"],
                    display_number=matter_data.get("display_number", ""),
                    description=matter_data.get("description", ""),
                    client_name=client.get("name", "Unknown Client"),
                    practice_area=practice_area_data.get("name") if practice_area_data else None,
                    status=matter_data.get("status", ""),
                    open_date=self._parse_date(matter_data.get("open_date")),
                    close_date=self._parse_date(matter_data.get("close_date")),
                )
                matters.append(matter)

            return matters

        except ClioAPIError:
            raise
        except Exception as e:
            raise ClioAPIError(f"Failed to parse matters: {e}") from e

    def get_communications(
        self, matter_id: int, limit: int = 100, since_date: Optional[datetime] = None
    ) -> List[ClioCommunication]:
        """Get all communications for a matter.

        Args:
        ----
            matter_id: CLIO matter ID
            limit: Maximum number of communications per page
            since_date: Optional filter for communications after this date

        Returns:
        -------
            List of ClioCommunication objects

        """
        params = {
            "matter_id": matter_id,
            "fields": "id,subject,date,senders,receivers,body,type",
            "order": "date(asc)",
            "limit": min(limit, 200),  # CLIO max is 200 per page
        }

        if since_date:
            params["created_since"] = since_date.isoformat()

        all_communications = []
        page = 1

        try:
            while True:
                params["page"] = page
                response = self._make_request("GET", "communications.json", params=params)

                communications_data = response.get("data", [])
                if not communications_data:
                    break

                for comm_data in communications_data:
                    try:
                        # Parse senders (CLIO returns array, take first)
                        senders_data = comm_data.get("senders", [])
                        if senders_data:
                            sender_data = senders_data[0]
                            sender = ClioContact(
                                id=sender_data.get("id", 0),
                                name=sender_data.get("name", "Unknown"),
                                type=sender_data.get("type", "Person"),
                                email=sender_data.get("email"),
                                phone=sender_data.get("phone"),
                            )
                        else:
                            # Fallback if no sender
                            sender = ClioContact(
                                id=0,
                                name="Unknown Sender",
                                type="Person",
                                email=None,
                                phone=None,
                            )

                        # Parse receivers
                        recipients = []
                        for recipient_data in comm_data.get("receivers", []):
                            recipient = ClioContact(
                                id=recipient_data.get("id", 0),
                                name=recipient_data.get("name", "Unknown"),
                                type=recipient_data.get("type", "Person"),
                                email=recipient_data.get("email"),
                                phone=recipient_data.get("phone"),
                            )
                            recipients.append(recipient)

                        communication = ClioCommunication(
                            id=comm_data["id"],
                            subject=comm_data.get("subject", "No Subject"),
                            date=self._parse_date(comm_data.get("date")),
                            sender=sender,
                            recipients=recipients,
                            body=comm_data.get("body", ""),
                            communication_type=comm_data.get("type", "Email"),
                            matter_id=matter_id,
                        )
                        all_communications.append(communication)

                    except Exception:
                        # Skip individual communication parsing errors
                        continue

                # Check if there are more pages
                if len(communications_data) < params["limit"]:
                    break

                page += 1

            return all_communications

        except ClioAPIError:
            raise
        except Exception as e:
            raise ClioAPIError(f"Failed to fetch communications: {e}") from e

    def get_notes(self, matter_id: int) -> List[Dict]:
        """Get case notes for a matter.

        Args:
        ----
            matter_id: CLIO matter ID

        Returns:
        -------
            List of note dictionaries

        """
        params = {
            "matter_id": matter_id,
            "type": "matter",
            "fields": "id,subject,detail,date",
            "limit": 100,
        }

        all_notes = []
        page = 1

        try:
            while True:
                params["page"] = page
                response = self._make_request("GET", "notes.json", params=params)

                notes_data = response.get("data", [])
                if not notes_data:
                    break

                for note_data in notes_data:
                    note = {
                        "id": note_data.get("id"),
                        "subject": note_data.get("subject", ""),
                        "detail": note_data.get("detail", ""),
                        "date": note_data.get("date", ""),
                    }
                    all_notes.append(note)

                # Check if there are more pages
                if len(notes_data) < params["limit"]:
                    break

                page += 1

            return all_notes

        except ClioAPIError:
            raise
        except Exception as e:
            raise ClioAPIError(f"Failed to fetch notes: {e}") from e

    def get_documents(self, matter_id: int) -> List[Dict]:
        """Get document list with download URLs for a matter.

        Args:
        ----
            matter_id: CLIO matter ID

        Returns:
        -------
            List of document metadata dictionaries with latest_document_version

        """
        base_params = {
            "matter_id": matter_id,
            "fields": "id,name,content_type,size,created_at,latest_document_version",
            "limit": 100,
        }

        all_documents = []
        seen_next_urls: set[str] = set()

        try:
            next_endpoint: str = "documents.json"
            next_params: Optional[Dict[str, Any]] = dict(base_params)

            while True:
                response = self._make_request("GET", next_endpoint, params=next_params)

                documents_data = response.get("data", [])
                if not documents_data:
                    break

                for doc_data in documents_data:
                    document = {
                        "id": doc_data.get("id"),
                        "name": doc_data.get("name", ""),
                        "content_type": doc_data.get("content_type", ""),
                        "size": doc_data.get("size", 0),
                        "created_at": doc_data.get("created_at", ""),
                        "latest_document_version": doc_data.get("latest_document_version"),
                    }
                    all_documents.append(document)

                # Clio uses page_token pagination via meta.paging.next for documents.
                # If present, follow that exact URL; otherwise stop.
                next_url = ((response.get("meta") or {}).get("paging") or {}).get("next")
                if next_url:
                    if next_url in seen_next_urls:
                        raise ClioAPIError("Detected repeated document pagination URL from Clio")
                    seen_next_urls.add(next_url)
                    next_endpoint = next_url
                    next_params = None
                    continue
                break

            return all_documents

        except ClioAPIError:
            raise
        except Exception as e:
            raise ClioAPIError(f"Failed to fetch documents: {e}") from e

    def _parse_date(self, date_str: Optional[str]) -> Optional[datetime]:
        """Parse ISO date string to datetime object.

        Args:
        ----
            date_str: ISO format date string

        Returns:
        -------
            datetime object or None

        """
        if not date_str:
            return None

        try:
            # Handle various ISO formats
            if "T" in date_str:
                return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            else:
                return datetime.fromisoformat(date_str)
        except (ValueError, AttributeError):
            return None
