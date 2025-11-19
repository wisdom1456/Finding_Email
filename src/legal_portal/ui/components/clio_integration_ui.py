"""CLIO integration UI components.

Provides user interface for connecting to CLIO and searching matters.
"""

from __future__ import annotations

import streamlit as st
from legal_portal.services.clio_auth_service import ClioAuthService
from legal_portal.services.clio_client import ClioAPIError, ClioAuthError, ClioClient
from legal_portal.utils.logging_config import get_module_logger

logger = get_module_logger(__name__)


def clio_connection_section():
    """OAuth connection interface."""
    st.subheader("Connect to CLIO")

    if st.session_state.get("clio_authenticated"):
        st.success("✅ Connected to CLIO")
        if st.button("Disconnect"):
            st.session_state.clio_authenticated = False
            st.session_state.clio_access_token = None
            st.rerun()
    else:
        st.info("Click below to authorize access to your CLIO account")

        try:
            auth_service = ClioAuthService()

            # Pass auth token in state to preserve authentication across OAuth redirect
            auth_token = st.session_state.get("auth_token", "")
            state_data = f"auth:{auth_token}" if auth_token else None
            auth_url = auth_service.get_authorization_url(state=state_data)

            st.markdown(f"[🔗 Authorize CLIO Access]({auth_url})", unsafe_allow_html=True)
            st.caption("You'll be redirected to CLIO to grant access, then return here automatically.")

            # Check for OAuth callback
            query_params = st.query_params
            if "code" in query_params:
                with st.spinner("Completing authorization..."):
                    try:
                        code = query_params["code"]
                        state = query_params.get("state", "")

                        # Extract auth token from state to restore authentication
                        restored_auth_token = None
                        if state and state.startswith("auth:"):
                            auth_token = state.split(":", 1)[1]
                            if auth_token and len(auth_token) == 32:
                                st.session_state.authenticated = True
                                st.session_state.auth_token = auth_token
                                restored_auth_token = auth_token
                                logger.info("Restored authentication from OAuth state")

                        tokens = auth_service.handle_oauth_callback(code)

                        st.session_state.clio_authenticated = True
                        st.session_state.clio_access_token = tokens["access_token"]
                        st.session_state.clio_refresh_token = tokens["refresh_token"]
                        st.session_state.clio_token_expires_at = tokens["expires_at"]

                        # Clear query params and add auth_token so check_authentication() can find it
                        st.query_params.clear()
                        if restored_auth_token:
                            st.query_params["auth_token"] = restored_auth_token

                        st.success("✅ Successfully connected to CLIO!")
                        st.rerun()

                    except Exception as e:
                        st.error(f"Authorization failed: {e}")
                        logger.error(f"OAuth callback error: {e}")
                        # Clear the code parameter
                        st.query_params.clear()

        except ValueError as e:
            st.error(f"CLIO not configured: {e}")
            st.info(
                "To enable CLIO integration, add CLIO_CLIENT_ID and CLIO_CLIENT_SECRET "
                "to your .env file. See documentation for setup instructions."
            )


def matter_search_section():
    """Search and select CLIO matter."""
    st.subheader("Search for Matter")

    search_query = st.text_input(
        "Client Name",
        placeholder="Enter client name to search...",
        key="clio_matter_search",
        help="Search by client name or matter number",
    )

    if search_query and len(search_query) >= 3:
        try:
            client = ClioClient(st.session_state.clio_access_token)

            with st.spinner("Searching CLIO..."):
                matters = client.search_matters(search_query)

            if matters:
                st.success(f"Found {len(matters)} matter(s)")

                for matter in matters:
                    with st.container():
                        col1, col2 = st.columns([3, 1])

                        with col1:
                            st.write(f"**{matter.display_number}** - {matter.client_name}")
                            if matter.description:
                                desc = (
                                    matter.description
                                    if len(matter.description) <= 100
                                    else matter.description[:100] + "..."
                                )
                                st.write(f"_{desc}_")
                            else:
                                st.write("_No description_")

                            caption_parts = []
                            if matter.practice_area:
                                caption_parts.append(matter.practice_area)
                            caption_parts.append(matter.status)
                            caption_parts.append(f"Opened: {matter.open_date.strftime('%b %Y')}")
                            st.caption(" | ".join(caption_parts))

                        with col2:
                            if st.button("Select", key=f"select_{matter.id}"):
                                st.session_state.clio_selected_matter = matter
                                st.success(f"✅ Selected matter {matter.display_number}")
                                st.rerun()

                        st.divider()
            else:
                st.warning("No matters found matching that search")
                st.info("Try a different search term or check if the matter exists in CLIO")

        except ClioAuthError as e:
            st.error(f"Authentication error: {e}")
            st.info("Your CLIO session may have expired. Try disconnecting and reconnecting.")
            logger.error(f"CLIO auth error in search: {e}")

        except ClioAPIError as e:
            st.error(f"Error searching CLIO: {e}")
            logger.error(f"CLIO API error in search: {e}")

        except Exception as e:
            st.error(f"Unexpected error: {e}")
            logger.exception("Unexpected error in matter search")

    elif search_query and len(search_query) < 3:
        st.info("Enter at least 3 characters to search")
