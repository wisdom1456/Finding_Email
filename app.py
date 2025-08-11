from __future__ import annotations

import asyncio
import streamlit as st
import uuid
import time
import os

from core.main_processor import process_case_documents
from utils.helpers import handle_file_uploads

# Enhanced observability imports
from utils.logging_config import (
    setup_logging,
    app_logger,
    auth_logger,
    document_logger,
    performance_logger,
    log_authentication,
    log_document_processing,
    log_performance_metric,
    log_security_event,
    audit_logger,
    MetricsCollector
)
from utils.structured_logger import request_id_var, user_id_var, session_id_var
from utils.tracing import trace, Span
from utils.metrics import MetricsCollector

from components.ui_components import (
    case_information_form,
    file_upload_section,
    results_display_section,
)

# Import authentication modules
from utils.auth import AuthManager, Permissions, UserRole
from utils.session_manager import SessionManager, SessionMonitor
from utils.oauth import OAuthManager

# Initialize enhanced logging
setup_logging(app_name="legal-portal", level=os.getenv('LOG_LEVEL', 'INFO'))

# Initialize authentication components
auth_manager = AuthManager()
session_manager = SessionManager(timeout_minutes=30)
session_monitor = SessionMonitor()
oauth_manager = OAuthManager()

# Initialize metrics collector
metrics = MetricsCollector()


# --- Session State Initialization ---
def initialize_session_state():
    """Initializes the session state with default values including performance optimization settings."""
    # Define default values for all session state variables
    defaults = {
        "case_info": {
            "clientName": "",
            "attorneyName": "",
            "caseReference": "",
        },
        "uploaded_files": [],
        "intake_form": None,
        "case_documents": [],
        "final_results": None,
        "main_letter": None,
        "appendix": None,
        "processing_status": "idle",  # idle, active, completed, failed
        "processing_error": None,
        "cost_estimate": None,
        "cost_summary": None,
        "current_processing_cost": 0.0,
        "cost_session_id": None,
        # Performance optimization settings
        "enable_caching": True,
        "enable_parallel_processing": True,
        "max_concurrent_requests": 10,
        "cache_stats": None,
        "performance_mode": "optimized",  # "optimized" or "standard"
    }

    # Initialize any missing session state variables
    for key, default_value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = default_value


# Authentication decorator removed - running without login requirement
@trace("document.analysis")
@performance_logger.performance("document_analysis")
def start_analysis():
    """Handles the start analysis button click with comprehensive observability."""
    # Set request context
    request_id = str(uuid.uuid4())
    request_id_var.set(request_id)
    username = st.session_state.get('username', 'unknown')
    user_id_var.set(username)
    session_id = st.session_state.get('session_id', str(uuid.uuid4()))
    session_id_var.set(session_id)
    
    # Create tracing span
    span = Span("start_analysis", "document.processing")
    
    app_logger.info("Analysis start requested",
                   username=username,
                   request_id=request_id)
    
    # Record metrics
    MetricsCollector.record_counter("analysis.started", tags={'user': username})

    intake_form = st.session_state.get("intake_form")
    case_documents = st.session_state.get("case_documents", [])

    if not intake_form:
        app_logger.warning("Analysis start failed: no intake form provided",
                          username=username)
        MetricsCollector.record_error("analysis", tags={'reason': 'no_intake_form'})
        span.log("Failed: no intake form")
        span.finish(status="error")
        st.error("An intake form is required to start the analysis.")
        return

    # Log document processing start
    intake_name = intake_form.name if hasattr(intake_form, "name") else "unknown"
    log_document_processing(
        document_name=intake_name,
        action="start_analysis",
        user=username,
        documents_count=len(case_documents)
    )
    
    span.set_tag("intake_form", intake_name)
    span.set_tag("documents_count", len(case_documents))

    # Run the async processing function with performance tracking
    start_time = time.time()
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    try:
        loop.run_until_complete(process_case_documents())
        
        # Calculate processing time
        processing_time = time.time() - start_time
        
        # Log success
        app_logger.info("Document analysis completed successfully",
                       username=username,
                       processing_time_seconds=processing_time,
                       documents_processed=len(case_documents))
        
        # Record performance metrics
        log_performance_metric("document_analysis", processing_time,
                             documents_count=len(case_documents))
        MetricsCollector.record_gauge("documents.processed.total", len(case_documents))
        
        # Audit log for compliance
        audit_logger.log_document_processing(
            user=username,
            document_name=intake_name,
            action="analysis_completed",
            success=True,
            processing_time=processing_time,
            documents_count=len(case_documents)
        )
        
        span.log("Analysis completed", duration=processing_time)
        span.finish(status="success")
        
    except Exception as e:
        processing_time = time.time() - start_time
        
        app_logger.error("Document analysis failed",
                        exception=e,
                        username=username,
                        processing_time_seconds=processing_time)
        
        MetricsCollector.record_error("document_analysis")
        
        # Audit log failure
        audit_logger.log_document_processing(
            user=username,
            document_name=intake_name,
            action="analysis_failed",
            success=False,
            error=str(e),
            processing_time=processing_time
        )
        
        span.log("Analysis failed", error=str(e))
        span.finish(status="error")
        raise
    finally:
        loop.close()


def show_login_page():
    """Display the login page with authentication options and observability."""
    st.title("🔐 Legal Document Analysis Portal")
    st.subheader("Secure Enterprise Login")
    
    # Set request context for login page
    if 'login_request_id' not in st.session_state:
        st.session_state['login_request_id'] = str(uuid.uuid4())
    request_id_var.set(st.session_state['login_request_id'])
    
    # Create tabs for different login methods
    tab1, tab2, tab3 = st.tabs(["Login", "SSO Login", "Register"])
    
    with tab1:
        # Standard login form
        col1, col2 = st.columns([2, 1])
        with col1:
            name, authentication_status, username = auth_manager.login()
            
            if authentication_status:
                # Set user context
                user_id_var.set(username)
                session_id = str(uuid.uuid4())
                session_id_var.set(session_id)
                st.session_state['session_id'] = session_id
                
                # Create user session
                user_data = {
                    'name': name,
                    'role': st.session_state.get('role', UserRole.VIEWER).value
                }
                session_manager.create_user_session(username, user_data)
                
                # Log successful login with audit trail
                log_authentication(
                    username=username,
                    action="login",
                    success=True,
                    ip_address=st.session_state.get('client_ip', 'unknown')
                )
                
                # Log to session monitor
                session_monitor.log_login(username, session_id)
                
                # Rerun to show main app
                st.rerun()
            elif authentication_status == False:
                # Log failed login attempt
                log_authentication(
                    username=username or "unknown",
                    action="login",
                    success=False,
                    ip_address=st.session_state.get('client_ip', 'unknown')
                )
                
                # Security event for multiple failed attempts
                if st.session_state.get('failed_login_attempts', 0) > 3:
                    log_security_event(
                        event_type="multiple_failed_logins",
                        severity="medium",
                        description=f"Multiple failed login attempts for user {username}",
                        username=username,
                        attempts=st.session_state.get('failed_login_attempts', 0)
                    )
    
    with tab2:
        st.subheader("Enterprise SSO")
        
        # Check for OAuth callback
        userinfo = oauth_manager.handle_oauth_callback()
        if userinfo:
            # Process successful OAuth login
            email = userinfo.get('email')
            name = userinfo.get('name', email)
            
            # Register or update user in auth system
            if not auth_manager.config['credentials']['usernames'].get(email):
                auth_manager.register_user(
                    username=email,
                    email=email,
                    name=name,
                    password=secrets.token_urlsafe(32),  # Random password for SSO users
                    role='user'
                )
            
            # Set session state
            st.session_state['authentication_status'] = True
            st.session_state['username'] = email
            st.session_state['name'] = name
            st.session_state['role'] = auth_manager._get_user_role(email)
            
            # Create user session
            session_manager.create_user_session(email, userinfo)
            
            # Log SSO login
            session_monitor.log_login(email, st.session_state.get('session_id', 'unknown'))
            
            st.success(f"Welcome, {name}!")
            st.rerun()
        
        # Display available SSO providers
        available_providers = oauth_manager.get_available_providers()
        
        if available_providers:
            provider = st.selectbox(
                "Select SSO Provider",
                options=available_providers,
                format_func=lambda x: x.capitalize()
            )
            
            if st.button(f"Login with {provider.capitalize()}", type="primary"):
                oauth_provider = oauth_manager.get_provider(provider)
                if oauth_provider:
                    auth_url, _ = oauth_provider.get_authorization_url()
                    st.markdown(f'<a href="{auth_url}" target="_self">Click here to login with {provider.capitalize()}</a>', unsafe_allow_html=True)
        else:
            st.info("No SSO providers configured. Please contact your administrator.")
    
    with tab3:
        st.subheader("Register New Account")
        
        with st.form("register_form"):
            new_username = st.text_input("Username")
            new_email = st.text_input("Email")
            new_name = st.text_input("Full Name")
            new_password = st.text_input("Password", type="password")
            confirm_password = st.text_input("Confirm Password", type="password")
            
            if st.form_submit_button("Register"):
                if new_password != confirm_password:
                    st.error("Passwords don't match")
                elif len(new_password) < 8:
                    st.error("Password must be at least 8 characters long")
                elif auth_manager.register_user(new_username, new_email, new_name, new_password):
                    st.success("Registration successful! Please login.")
                    session_monitor.log_user_created(new_username, "self-registration")
                else:
                    st.error("Username already exists")


def show_admin_panel():
    """Display admin panel for user management."""
    st.title("👨‍💼 Admin Panel")
    
    tab1, tab2, tab3 = st.tabs(["User Management", "Audit Logs", "System Settings"])
    
    with tab1:
        st.subheader("User Management")
        
        # List all users
        users = auth_manager.list_users()
        
        if users:
            # Create a table of users
            user_df = st.dataframe(
                users,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "username": "Username",
                    "email": "Email",
                    "name": "Full Name",
                    "role": st.column_config.SelectboxColumn(
                        "Role",
                        options=["admin", "user", "viewer", "auditor"],
                        required=True
                    )
                }
            )
            
            # User actions
            col1, col2, col3 = st.columns(3)
            
            with col1:
                selected_user = st.selectbox("Select User", [u['username'] for u in users])
            
            with col2:
                new_role = st.selectbox("New Role", ["admin", "user", "viewer", "auditor"])
                if st.button("Update Role"):
                    if auth_manager.update_user_role(selected_user, new_role):
                        st.success(f"Updated role for {selected_user}")
                        session_monitor.log_role_changed(
                            selected_user, 
                            "unknown", 
                            new_role, 
                            st.session_state.get('username')
                        )
                        st.rerun()
            
            with col3:
                if st.button("Delete User", type="secondary"):
                    if auth_manager.delete_user(selected_user):
                        st.success(f"Deleted user {selected_user}")
                        session_monitor.log_user_deleted(
                            selected_user,
                            st.session_state.get('username')
                        )
                        st.rerun()
            
            # Password reset
            st.divider()
            st.subheader("Password Reset")
            reset_user = st.selectbox("User to Reset", [u['username'] for u in users], key="reset_user")
            new_password = st.text_input("New Password", type="password", key="reset_password")
            if st.button("Reset Password"):
                if auth_manager.reset_password(reset_user, new_password):
                    st.success(f"Password reset for {reset_user}")
                    session_monitor.log_password_change(reset_user)
    
    with tab2:
        st.subheader("Audit Logs")
        
        # Display recent audit activities
        recent_activities = session_monitor.get_recent_activities(100)
        
        if recent_activities:
            st.text_area(
                "Recent Activities",
                value="".join(recent_activities),
                height=400,
                disabled=True
            )
        else:
            st.info("No audit logs available")
        
        # Session information
        st.subheader("Active Sessions")
        st.metric("Total Active Sessions", session_manager.get_active_sessions_count())
    
    with tab3:
        st.subheader("System Settings")
        
        # Session timeout settings
        timeout = st.number_input(
            "Session Timeout (minutes)",
            min_value=5,
            max_value=120,
            value=session_manager.timeout_minutes
        )
        
        max_sessions = st.number_input(
            "Max Sessions per User",
            min_value=1,
            max_value=10,
            value=session_manager.max_sessions_per_user
        )
        
        if st.button("Update Settings"):
            session_manager.timeout_minutes = timeout
            session_manager.max_sessions_per_user = max_sessions
            st.success("Settings updated")


# --- Main Application ---
@trace("application.main")
def main():
    """Main function for the Streamlit application with comprehensive observability."""
    # Application startup metrics
    app_start_time = time.time()
    
    # Log application startup
    app_logger.info("Legal Document Analysis Portal starting up",
                   version=os.getenv('APP_VERSION', '1.0.0'),
                   environment=os.getenv('ENVIRONMENT', 'development'))
    
    # Record startup metric
    MetricsCollector.record_counter("app.startup")

    st.set_page_config(
        page_title="Legal Document Analysis Portal",
        layout="wide",
        menu_items={
            'About': "Legal Document Analysis Portal v2.1 - Enterprise Edition with Authentication"
        }
    )

    initialize_session_state()
    
    # Check session timeout with observability
    if session_manager.check_session_timeout() and st.session_state.get('authentication_status'):
        username = st.session_state.get('username', 'unknown')
        session_id = st.session_state.get('session_id', 'unknown')
        
        st.warning("Your session has expired. Please login again.")
        
        # Log session timeout
        auth_logger.warning("Session timeout",
                          username=username,
                          session_id=session_id)
        
        # Audit log for compliance
        audit_logger.log_authentication(
            username=username,
            action="session_timeout",
            success=False,
            session_id=session_id
        )
        
        # Record metric
        MetricsCollector.record_counter("sessions.timeout", tags={'user': username})
        
        session_monitor.log_timeout(username, session_id)
        st.session_state['authentication_status'] = False
    
    # AUTHENTICATION BYPASSED - Running without login requirement
    # Set up default session state for bypassed authentication
    st.session_state['authentication_status'] = True
    st.session_state['username'] = 'default_user'
    st.session_state['name'] = 'User'
    st.session_state['role'] = UserRole.ADMIN  # Give admin role for full access
    
    # Main application content without authentication
    st.title("⚖️ Legal Document Analysis Portal")
    
    # Add performance status indicator
    col1, col2, col3 = st.columns([3, 1, 1])
    with col1:
        st.caption("AI-Powered Legal Document Analysis")
    with col2:
        if st.session_state.performance_mode == "optimized":
            st.success("🚀 Performance Mode: ON")
        else:
            st.info("🐢 Standard Mode")
    with col3:
        if st.session_state.enable_caching:
            st.success("💾 Caching: ON")
        else:
            st.warning("💾 Caching: OFF")

    # Performance settings in sidebar (always show since no auth)
    with st.sidebar:
        st.header("⚙️ Performance Settings")
        
        # Performance mode toggle
        performance_mode = st.selectbox(
            "Processing Mode",
            ["optimized", "standard"],
            index=0 if st.session_state.performance_mode == "optimized" else 1,
            help="Optimized mode uses parallel processing and caching for 3-5x faster processing"
        )
        st.session_state.performance_mode = performance_mode
        
        # Enable/disable optimizations
        st.session_state.enable_caching = st.checkbox(
            "Enable Caching",
            value=st.session_state.enable_caching,
            help="Cache API responses and document analysis for faster repeated processing"
        )
        
        st.session_state.enable_parallel_processing = st.checkbox(
            "Enable Parallel Processing",
            value=st.session_state.enable_parallel_processing,
            help="Process multiple documents concurrently for faster analysis"
        )
        
        if st.session_state.enable_parallel_processing:
            st.session_state.max_concurrent_requests = st.slider(
                "Max Concurrent Requests",
                min_value=1,
                max_value=20,
                value=st.session_state.max_concurrent_requests,
                help="Maximum number of concurrent API requests"
            )

    # Main content - all permissions granted since auth is bypassed
    case_information_form()

    tab1, tab2, tab3 = st.tabs(["Upload & Process", "Results", "Performance"])

    with tab1:
        if st.session_state.processing_status in ["idle", "failed", "completed"]:
            file_upload_section()

            if (
                st.session_state.get("uploaded_files")
                and handle_file_uploads()
                and st.button("Start Analysis", type="primary")
            ):
                # Remove the decorator requirement for authentication
                # Call the function directly
                intake_form = st.session_state.get("intake_form")
                case_documents = st.session_state.get("case_documents", [])
                
                if not intake_form:
                    st.error("An intake form is required to start the analysis.")
                else:
                    # Run the async processing function
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    try:
                        loop.run_until_complete(process_case_documents())
                    finally:
                        loop.close()

        elif st.session_state.processing_status == "active":
            st.info("⚡ Analysis is currently in progress...")
            if st.session_state.performance_mode == "optimized":
                st.caption(f"Processing with {st.session_state.max_concurrent_requests} concurrent workers")

        # Show any processing errors
        if (
            st.session_state.processing_status == "failed"
            and st.session_state.processing_error
        ):
            st.error(f"Processing failed: {st.session_state.processing_error}")

    with tab2:
        if st.session_state.final_results:
            results_display_section()
        else:
            st.info("No results available. Please upload documents and start the analysis first.")
    
    with tab3:
        st.header("🚀 Performance Metrics")
        
        if st.session_state.processing_status == "completed":
            col1, col2, col3 = st.columns(3)
            
            with col1:
                st.metric(
                    "Processing Mode",
                    st.session_state.performance_mode.capitalize(),
                    delta="3-5x faster" if st.session_state.performance_mode == "optimized" else None
                )
            
            with col2:
                st.metric(
                    "Documents Processed",
                    len(st.session_state.uploaded_files) if st.session_state.uploaded_files else 0
                )
            
            with col3:
                if st.session_state.cache_stats:
                    cache_hit_rate = st.session_state.cache_stats.get("cache_hit_rate", 0)
                    st.metric(
                        "Cache Hit Rate",
                        f"{cache_hit_rate:.1%}",
                        delta=f"+{cache_hit_rate*100:.0f}% faster" if cache_hit_rate > 0 else None
                    )
        else:
            st.info("Performance metrics will be available after processing documents")


if __name__ == "__main__":
    import secrets  # Import here for SSO user registration
    main()