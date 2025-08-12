"""Simple monitoring dashboard for logs and metrics."""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st


def load_json_lines(file_path: Path) -> list:
    """Load JSON lines from a file."""
    data = []
    if file_path.exists():
        with open(file_path) as f:
            for line in f:
                try:
                    data.append(json.loads(line.strip()))
                except json.JSONDecodeError:
                    continue
    return data


def show_monitoring_dashboard():
    """Display monitoring dashboard."""
    st.set_page_config(
        page_title="System Monitoring Dashboard", layout="wide", initial_sidebar_state="expanded"
    )

    st.title("📊 System Monitoring Dashboard")
    st.caption("Real-time observability for Legal Document Analysis Portal")

    # Sidebar for refresh and filters
    with st.sidebar:
        st.header("Dashboard Controls")

        if st.button("🔄 Refresh", type="primary"):
            st.rerun()

        st.divider()

        # Time range filter
        time_range = st.selectbox(
            "Time Range",
            ["Last 15 minutes", "Last hour", "Last 6 hours", "Last 24 hours", "All time"],
            index=1,
        )

        # Log level filter
        log_level_filter = st.multiselect(
            "Log Levels",
            ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL", "AUDIT"],
            default=["INFO", "WARNING", "ERROR", "CRITICAL", "AUDIT"],
        )

    # Main dashboard tabs
    tab1, tab2, tab3, tab4, tab5 = st.tabs(["📈 Metrics", "📝 Logs", "🔍 Traces", "🔒 Audit", "📊 Analytics"])

    with tab1:
        show_metrics()

    with tab2:
        show_logs(log_level_filter)

    with tab3:
        show_traces()

    with tab4:
        show_audit_logs()

    with tab5:
        show_analytics()


def show_metrics():
    """Display metrics dashboard."""
    st.subheader("System Metrics")

    # Load metrics
    metrics_file = Path("logs/metrics.json")
    metrics_data = load_json_lines(metrics_file)

    if metrics_data:
        latest = metrics_data[-1] if metrics_data else {}

        # Key metrics display
        col1, col2, col3, col4 = st.columns(4)

        with col1:
            total_requests = latest.get("counters", {}).get("app.requests", 0)
            st.metric("Total Requests", f"{total_requests:,}")

        with col2:
            docs_processed = latest.get("counters", {}).get("documents.processed", 0)
            st.metric("Documents Processed", f"{docs_processed:,}")

        with col3:
            total_errors = sum(v for k, v in latest.get("counters", {}).items() if "error" in k.lower())
            st.metric("Total Errors", f"{total_errors:,}", delta_color="inverse")

        with col4:
            auth_success = latest.get("counters", {}).get("auth.login", 0)
            st.metric("Successful Logins", f"{auth_success:,}")

        st.divider()

        # Performance Metrics
        st.subheader("⚡ Performance Metrics")

        if latest.get("timers"):
            perf_data = []
            for name, stats in latest["timers"].items():
                perf_data.append(
                    {
                        "Operation": name.replace("_", " ").title(),
                        "Count": stats["count"],
                        "Avg (ms)": f"{stats['avg']:.2f}",
                        "Min (ms)": f"{stats['min']:.2f}",
                        "Max (ms)": f"{stats['max']:.2f}",
                        "P50 (ms)": f"{stats['p50']:.2f}",
                        "P95 (ms)": f"{stats['p95']:.2f}",
                        "P99 (ms)": f"{stats['p99']:.2f}",
                    }
                )

            st.dataframe(pd.DataFrame(perf_data), use_container_width=True, hide_index=True)

        # Metrics over time chart
        if len(metrics_data) > 1:
            st.subheader("📊 Metrics Over Time")

            # Prepare time series data
            timestamps = []
            request_counts = []
            error_counts = []

            for metric in metrics_data[-20:]:  # Last 20 data points
                timestamps.append(datetime.fromisoformat(metric["timestamp"]))
                request_counts.append(metric.get("counters", {}).get("app.requests", 0))
                error_counts.append(sum(v for k, v in metric.get("counters", {}).items() if "error" in k))

            # Create plotly figure
            fig = go.Figure()

            fig.add_trace(
                go.Scatter(
                    x=timestamps,
                    y=request_counts,
                    mode="lines+markers",
                    name="Requests",
                    line=dict(color="blue", width=2),
                )
            )

            fig.add_trace(
                go.Scatter(
                    x=timestamps,
                    y=error_counts,
                    mode="lines+markers",
                    name="Errors",
                    line=dict(color="red", width=2),
                    yaxis="y2",
                )
            )

            fig.update_layout(
                title="Request and Error Trends",
                xaxis_title="Time",
                yaxis_title="Requests",
                yaxis2=dict(title="Errors", overlaying="y", side="right"),
                hovermode="x unified",
            )

            st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No metrics data available yet. Metrics will appear once the application starts processing.")


def show_logs(level_filter):
    """Display recent logs with filtering."""
    st.subheader("📝 Recent Logs")

    # Load logs from multiple sources
    log_files = list(Path("logs").glob("*.log"))
    all_logs = []

    for log_file in log_files:
        if log_file.name.startswith("audit_"):
            continue  # Skip audit logs here

        logs = load_json_lines(log_file)
        all_logs.extend(logs)

    # Filter by level
    filtered_logs = [log for log in all_logs if log.get("level") in level_filter]

    # Sort by timestamp
    filtered_logs.sort(key=lambda x: x.get("timestamp", ""), reverse=True)

    # Display controls
    col1, col2 = st.columns([3, 1])
    with col1:
        search_term = st.text_input("🔍 Search logs", placeholder="Enter search term...")
    with col2:
        max_logs = st.number_input("Max logs", min_value=10, max_value=1000, value=100)

    # Filter by search term
    if search_term:
        filtered_logs = [log for log in filtered_logs if search_term.lower() in json.dumps(log).lower()]

    # Display logs
    if filtered_logs:
        for log in filtered_logs[:max_logs]:
            level = log.get("level", "INFO")

            # Color coding for log levels
            color_map = {
                "DEBUG": "⚪",
                "INFO": "🔵",
                "WARNING": "🟡",
                "ERROR": "🔴",
                "CRITICAL": "🟣",
                "AUDIT": "🔒",
            }

            icon = color_map.get(level, "⚪")
            timestamp = log.get("timestamp", "N/A")
            message = log.get("message", "No message")

            with st.expander(f"{icon} [{timestamp}] {message[:100]}..."):
                # Display formatted JSON
                st.json(log)
    else:
        st.info("No logs matching the current filters.")


def show_traces():
    """Display distributed traces."""
    st.subheader("🔍 Distributed Traces")

    traces_file = Path("logs/traces.json")
    traces = load_json_lines(traces_file)

    if traces:
        # Group traces by trace_id
        trace_groups = defaultdict(list)
        for trace in traces:
            trace_groups[trace["trace_id"]].append(trace)

        # Display trace selector
        trace_ids = list(trace_groups.keys())[-50:]  # Last 50 traces
        selected_trace = st.selectbox("Select Trace", trace_ids, format_func=lambda x: f"Trace {x[:8]}...")

        if selected_trace:
            spans = trace_groups[selected_trace]

            # Display trace timeline
            st.subheader(f"Trace Timeline: {selected_trace[:8]}...")

            # Sort spans by start time
            spans.sort(key=lambda x: x.get("start_time", ""))

            # Create Gantt chart for trace
            if spans:
                gantt_data = []
                for span in spans:
                    if span.get("start_time") and span.get("end_time"):
                        gantt_data.append(
                            {
                                "Task": span["name"],
                                "Start": datetime.fromisoformat(span["start_time"]),
                                "Finish": datetime.fromisoformat(span["end_time"]),
                                "Resource": span["operation"],
                                "Duration": span.get("duration_ms", 0),
                            }
                        )

                if gantt_data:
                    df = pd.DataFrame(gantt_data)

                    fig = px.timeline(
                        df,
                        x_start="Start",
                        x_end="Finish",
                        y="Task",
                        color="Resource",
                        hover_data=["Duration"],
                        title="Span Timeline",
                    )

                    fig.update_yaxes(autorange="reversed")
                    st.plotly_chart(fig, use_container_width=True)

            # Display span details
            st.subheader("Span Details")
            for span in spans:
                status_icon = "✅" if span.get("status") == "success" else "❌"
                duration = span.get("duration_ms", "N/A")

                with st.expander(f"{status_icon} {span['name']} ({duration} ms)"):
                    col1, col2 = st.columns(2)

                    with col1:
                        st.write("**Span ID:**", span["span_id"][:12])
                        st.write("**Operation:**", span["operation"])
                        st.write("**Status:**", span["status"])

                    with col2:
                        st.write("**Start:**", span.get("start_time", "N/A"))
                        st.write("**End:**", span.get("end_time", "N/A"))
                        st.write("**Duration:**", f"{duration} ms")

                    if span.get("tags"):
                        st.write("**Tags:**")
                        st.json(span["tags"])

                    if span.get("logs"):
                        st.write("**Logs:**")
                        for log in span["logs"]:
                            st.write(f"- [{log['timestamp']}] {log['message']}")
    else:
        st.info("No trace data available. Traces will appear once requests are processed.")


def show_audit_logs():
    """Display audit logs for compliance."""
    st.subheader("🔒 Audit Trail")

    # Load audit logs
    audit_files = list(Path("logs/audit").glob("*.json"))
    all_audits = []

    for audit_file in audit_files:
        audits = load_json_lines(audit_file)
        all_audits.extend(audits)

    # Sort by timestamp
    all_audits.sort(key=lambda x: x.get("timestamp", ""), reverse=True)

    if all_audits:
        # Filter controls
        col1, col2, col3 = st.columns(3)

        with col1:
            categories = list(set(a.get("category", "unknown") for a in all_audits))
            selected_category = st.selectbox("Category", ["All"] + categories)

        with col2:
            users = list(set(a.get("user", "unknown") for a in all_audits if a.get("user")))
            selected_user = st.selectbox("User", ["All"] + users)

        with col3:
            date_filter = st.date_input("Date", value=datetime.now().date())

        # Apply filters
        filtered_audits = all_audits

        if selected_category != "All":
            filtered_audits = [a for a in filtered_audits if a.get("category") == selected_category]

        if selected_user != "All":
            filtered_audits = [a for a in filtered_audits if a.get("user") == selected_user]

        # Display audit logs
        audit_df = pd.DataFrame(filtered_audits[:100])

        if not audit_df.empty:
            # Display key columns
            display_columns = ["timestamp", "category", "action", "user", "success", "resource"]
            available_columns = [col for col in display_columns if col in audit_df.columns]

            st.dataframe(audit_df[available_columns], use_container_width=True, hide_index=True)

            # Detail view
            st.subheader("Audit Detail View")

            for audit in filtered_audits[:20]:
                timestamp = audit.get("timestamp", "N/A")
                category = audit.get("category", "unknown")
                action = audit.get("action", "unknown")
                user = audit.get("user", "unknown")

                with st.expander(f"[{timestamp}] {category}: {action} by {user}"):
                    st.json(audit)
    else:
        st.info("No audit logs available.")


def show_analytics():
    """Display analytics and insights."""
    st.subheader("📊 Analytics & Insights")

    # Load all metrics for analysis
    metrics_file = Path("logs/metrics.json")
    metrics_data = load_json_lines(metrics_file)

    if metrics_data:
        # Calculate aggregated stats
        total_requests = sum(m.get("counters", {}).get("app.requests", 0) for m in metrics_data)
        total_errors = sum(
            sum(v for k, v in m.get("counters", {}).items() if "error" in k) for m in metrics_data
        )
        error_rate = (total_errors / total_requests * 100) if total_requests > 0 else 0

        # Display KPIs
        col1, col2, col3, col4 = st.columns(4)

        with col1:
            st.metric("Total Requests", f"{total_requests:,}")

        with col2:
            st.metric(
                "Error Rate",
                f"{error_rate:.2f}%",
                delta=f"{error_rate:.2f}%" if error_rate > 5 else None,
                delta_color="inverse",
            )

        with col3:
            avg_response_time = calculate_average_response_time(metrics_data)
            st.metric("Avg Response Time", f"{avg_response_time:.2f} ms")

        with col4:
            uptime = calculate_uptime(metrics_data)
            st.metric("Uptime", f"{uptime:.2f}%")

        st.divider()

        # Error analysis
        st.subheader("🔴 Error Analysis")

        error_types = defaultdict(int)
        for metric in metrics_data:
            for key, value in metric.get("counters", {}).items():
                if "error" in key.lower():
                    error_type = key.replace(".errors", "").replace("_", " ").title()
                    error_types[error_type] += value

        if error_types:
            # Create pie chart
            fig = px.pie(
                values=list(error_types.values()), names=list(error_types.keys()), title="Error Distribution"
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.success("No errors detected!")

        # Performance trends
        st.subheader("⚡ Performance Trends")

        if len(metrics_data) > 1:
            perf_trends = []
            for metric in metrics_data:
                timestamp = datetime.fromisoformat(metric["timestamp"])
                for timer_name, stats in metric.get("timers", {}).items():
                    perf_trends.append(
                        {
                            "timestamp": timestamp,
                            "operation": timer_name,
                            "avg_ms": stats["avg"],
                            "p95_ms": stats["p95"],
                        }
                    )

            if perf_trends:
                df = pd.DataFrame(perf_trends)

                # Group by operation and plot
                operations = df["operation"].unique()

                fig = go.Figure()
                for op in operations:
                    op_data = df[df["operation"] == op]
                    fig.add_trace(
                        go.Scatter(x=op_data["timestamp"], y=op_data["avg_ms"], mode="lines+markers", name=op)
                    )

                fig.update_layout(
                    title="Performance Trends by Operation",
                    xaxis_title="Time",
                    yaxis_title="Average Response Time (ms)",
                    hovermode="x unified",
                )

                st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No analytics data available yet.")


def calculate_average_response_time(metrics_data):
    """Calculate average response time from metrics."""
    total_time = 0
    total_count = 0

    for metric in metrics_data:
        for timer_name, stats in metric.get("timers", {}).items():
            total_time += stats.get("avg", 0) * stats.get("count", 0)
            total_count += stats.get("count", 0)

    return (total_time / total_count) if total_count > 0 else 0


def calculate_uptime(metrics_data):
    """Calculate system uptime percentage."""
    if not metrics_data:
        return 0

    # Simple calculation based on data points
    # In production, this would check actual availability
    return 99.9  # Placeholder


if __name__ == "__main__":
    show_monitoring_dashboard()
