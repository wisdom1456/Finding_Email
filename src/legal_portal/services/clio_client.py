"""CLIO API client for accessing CLIO Manage data.

This module provides a Python wrapper for the CLIO API v4.
"""

from __future__ import annotations

import time
from datetime import datetime
from typing import Any, Dict, List, Optional

import requests
from legal_portal.core.data_models import ClioCommunication, ClioContact, ClioMatter
from legal_portal.utils.logging_config import get_module_logger

logger = get_module_logger(__name__)


class ClioAPIError(Exception):
    """Base exception for CLIO API errors."""

    pass


class ClioAuthError(ClioAPIError):
    """Authentication/authorization error."""

    pass


class ClioRateLimitError(ClioAPIError):
    """Rate limit exceeded error."""

    pass


class ClioClient:
    """Client for CLIO API v4."""

    def __init__(self, access_token: str):  # noqa: D417
        """Initialize CLIO API client.

        Parameters
        ----------
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
        self.rate_limit_delay = 0.34  # ~3 requests per second to stay safe
        self.last_request_time = 0

    def _wait_for_rate_limit(self):
        """Enforce rate limiting between requests."""
        elapsed = time.time() - self.last_request_time
        if elapsed < self.rate_limit_delay:
            time.sleep(self.rate_limit_delay - elapsed)
        self.last_request_time = time.time()

    def _make_request(  # noqa: D417
        self, method: str, endpoint: str, params: Dict = None, data: Dict = None, max_retries: int = 3
    ) -> Dict[str, Any]:
        """Make HTTP request to CLIO API with error handling.

        Parameters
        ----------
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint (without base URL)
            params: Query parameters
            data: Request body data
            max_retries: Maximum retry attempts for rate limits

        Returns
        -------
            Dict: JSON response data

        Raises
        ------
            ClioAuthError: Authentication/authorization error
            ClioRateLimitError: Rate limit exceeded
            ClioAPIError: Other API errors
        """
        self._wait_for_rate_limit()

        url = f"{self.base_url}/{endpoint}"

        for attempt in range(max_retries):
            try:
                response = self.session.request(method=method, url=url, params=params, json=data, timeout=30)

                # Handle rate limiting with exponential backoff
                if response.status_code == 429:
                    if attempt < max_retries - 1:
                        wait_time = 2**attempt  # 1s, 2s, 4s
                        logger.warning(f"Rate limit hit, waiting {wait_time}s before retry")
                        time.sleep(wait_time)
                        continue
                    else:
                        raise ClioRateLimitError("Rate limit exceeded after retries")

                # Handle authentication errors
                if response.status_code == 401:
                    raise ClioAuthError("Access token expired or invalid")

                if response.status_code == 403:
                    raise ClioAuthError("Insufficient permissions for this resource")

                # Handle other errors
                if response.status_code >= 400:
                    error_msg = f"API error {response.status_code}: {response.text}"
                    logger.error(error_msg)
                    raise ClioAPIError(error_msg)

                return response.json()

            except requests.exceptions.RequestException as e:
                if attempt < max_retries - 1:
                    logger.warning(f"Request failed, retrying: {e}")
                    time.sleep(1)
                    continue
                else:
                    raise ClioAPIError(f"Request failed: {e}") from e

        raise ClioAPIError("Max retries exceeded")

    def search_matters(self, query: str, limit: int = 20) -> List[ClioMatter]:  # noqa: D417
        """Search matters by client name or matter number.

        Parameters
        ----------
            query: Search query (client name, matter number, etc.)
            limit: Maximum number of results

        Returns
        -------
            List of ClioMatter objects
        """
        logger.info(f"Searching CLIO matters: query='{query}', limit={limit}")

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

            logger.info(f"Found {len(matters)} matters")
            return matters

        except ClioAPIError:
            raise
        except Exception as e:
            logger.error(f"Error parsing matters: {e}")
            raise ClioAPIError(f"Failed to parse matters: {e}") from e

    def get_matter_details(self, matter_id: int) -> ClioMatter:  # noqa: D417
        """Get full matter details including custom fields.

        Parameters
        ----------
            matter_id: CLIO matter ID

        Returns
        -------
            ClioMatter object with full details
        """
        logger.info(f"Fetching matter details: id={matter_id}")

        params = {
            "fields": (
                "id,display_number,description,client,practice_area,"
                "status,open_date,close_date,custom_field_values"
            ),
        }

        try:
            response = self._make_request("GET", f"matters/{matter_id}.json", params=params)

            matter_data = response.get("data", {})
            client = matter_data.get("client", {})
            practice_area_data = matter_data.get("practice_area", {})

            # Parse custom fields
            custom_fields = {}
            for cf in matter_data.get("custom_field_values", []):
                field_name = cf.get("field_name", "")
                field_value = cf.get("value", "")
                if field_name and field_value:
                    custom_fields[field_name.lower().replace(" ", "_")] = field_value

            matter = ClioMatter(
                id=matter_data["id"],
                display_number=matter_data.get("display_number", ""),
                description=matter_data.get("description", ""),
                client_name=client.get("name", "Unknown Client"),
                practice_area=practice_area_data.get("name") if practice_area_data else None,
                status=matter_data.get("status", ""),
                open_date=self._parse_date(matter_data.get("open_date")),
                close_date=self._parse_date(matter_data.get("close_date")),
                custom_fields=custom_fields,
            )

            logger.info(f"Retrieved matter: {matter.display_number}")
            return matter

        except ClioAPIError:
            raise
        except Exception as e:
            logger.error(f"Error parsing matter details: {e}")
            raise ClioAPIError(f"Failed to parse matter details: {e}") from e

    def get_communications(  # noqa: D417
        self, matter_id: int, limit: int = 100, since_date: Optional[datetime] = None
    ) -> List[ClioCommunication]:
        """Get all communications for a matter.

        Parameters
        ----------
            matter_id: CLIO matter ID
            limit: Maximum number of communications per page
            since_date: Optional filter for communications after this date

        Returns
        -------
            List of ClioCommunication objects
        """
        logger.info(f"Fetching communications: matter_id={matter_id}, limit={limit}")

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

                    except Exception as e:
                        logger.warning(f"Failed to parse communication {comm_data.get('id')}: {e}")
                        continue

                # Check if there are more pages
                if len(communications_data) < params["limit"]:
                    break

                page += 1

                # Safety limit: don't fetch more than 500 communications
                if len(all_communications) >= 500:
                    logger.warning(f"Reached limit of 500 communications for matter {matter_id}")
                    break

            logger.info(f"Retrieved {len(all_communications)} communications")
            return all_communications

        except ClioAPIError:
            raise
        except Exception as e:
            logger.error(f"Error fetching communications: {e}")
            raise ClioAPIError(f"Failed to fetch communications: {e}") from e

    def get_contacts(self, contact_ids: List[int]) -> List[ClioContact]:  # noqa: D417
        """Batch fetch contacts by IDs.

        Parameters
        ----------
            contact_ids: List of contact IDs

        Returns
        -------
            List of ClioContact objects
        """
        if not contact_ids:
            return []

        logger.info(f"Fetching {len(contact_ids)} contacts")

        # CLIO API may have limits on batch fetching, so fetch individually if needed
        contacts = []

        for contact_id in contact_ids:
            try:
                params = {"fields": "id,name,type,email_addresses,phone_numbers"}
                response = self._make_request("GET", f"contacts/{contact_id}.json", params=params)

                contact_data = response.get("data", {})

                # Get primary email
                email = None
                for email_data in contact_data.get("email_addresses", []):
                    if email_data.get("default_email"):
                        email = email_data.get("address")
                        break

                # Get primary phone
                phone = None
                for phone_data in contact_data.get("phone_numbers", []):
                    if phone_data.get("default_number"):
                        phone = phone_data.get("number")
                        break

                contact = ClioContact(
                    id=contact_data["id"],
                    name=contact_data.get("name", "Unknown"),
                    type=contact_data.get("type", "Person"),
                    email=email,
                    phone=phone,
                )
                contacts.append(contact)

            except Exception as e:
                logger.warning(f"Failed to fetch contact {contact_id}: {e}")
                continue

        logger.info(f"Retrieved {len(contacts)} contacts")
        return contacts

    def get_notes(self, matter_id: int) -> List[Dict]:  # noqa: D417
        """Get case notes for a matter.

        Parameters
        ----------
            matter_id: CLIO matter ID

        Returns
        -------
            List of note dictionaries
        """
        logger.info(f"Fetching notes: matter_id={matter_id}")

        params = {
            "matter_id": matter_id,
            "type": "matter",
            "fields": "id,subject,detail,date",
            "limit": 100,
        }

        try:
            response = self._make_request("GET", "notes.json", params=params)

            notes = []
            for note_data in response.get("data", []):
                note = {
                    "id": note_data.get("id"),
                    "subject": note_data.get("subject", ""),
                    "detail": note_data.get("detail", ""),
                    "date": note_data.get("date", ""),
                }
                notes.append(note)

            logger.info(f"Retrieved {len(notes)} notes")
            return notes

        except ClioAPIError:
            raise
        except Exception as e:
            logger.error(f"Error fetching notes: {e}")
            raise ClioAPIError(f"Failed to fetch notes: {e}") from e

    def get_documents(self, matter_id: int) -> List[Dict]:  # noqa: D417
        """Get document list (metadata only) for a matter.

        Parameters
        ----------
            matter_id: CLIO matter ID

        Returns
        -------
            List of document metadata dictionaries
        """
        logger.info(f"Fetching documents: matter_id={matter_id}")

        params = {
            "matter_id": matter_id,
            "fields": "id,name,content_type,size,created_at",
            "limit": 100,
        }

        try:
            response = self._make_request("GET", "documents.json", params=params)

            documents = []
            for doc_data in response.get("data", []):
                document = {
                    "id": doc_data.get("id"),
                    "name": doc_data.get("name", ""),
                    "content_type": doc_data.get("content_type", ""),
                    "size": doc_data.get("size", 0),
                    "created_at": doc_data.get("created_at", ""),
                }
                documents.append(document)

            logger.info(f"Retrieved {len(documents)} documents")
            return documents

        except ClioAPIError:
            raise
        except Exception as e:
            logger.error(f"Error fetching documents: {e}")
            raise ClioAPIError(f"Failed to fetch documents: {e}") from e

    def download_document(self, document_id: int) -> bytes:  # noqa: D417
        """Download document content.

        Parameters
        ----------
            document_id: CLIO document ID

        Returns
        -------
            bytes: Document content
        """
        logger.info(f"Downloading document: id={document_id}")

        try:
            self._wait_for_rate_limit()

            url = f"{self.base_url}/documents/{document_id}/download"
            response = self.session.get(url, timeout=60)

            if response.status_code == 401:
                raise ClioAuthError("Access token expired or invalid")

            if response.status_code >= 400:
                raise ClioAPIError(f"Download failed: {response.status_code}")

            logger.info(f"Downloaded document: size={len(response.content)} bytes")
            return response.content

        except requests.exceptions.RequestException as e:
            logger.error(f"Error downloading document: {e}")
            raise ClioAPIError(f"Failed to download document: {e}") from e

    def _parse_date(self, date_str: Optional[str]) -> Optional[datetime]:  # noqa: D417
        """Parse ISO date string to datetime object.

        Parameters
        ----------
            date_str: ISO format date string

        Returns
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
            logger.warning(f"Failed to parse date: {date_str}")
            return None
