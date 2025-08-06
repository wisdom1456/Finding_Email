"""
Budget Sheet Component for Legal Document Analysis Portal

This component provides Streamlit UI elements for displaying cost summaries,
budget analysis, and export functionality for operational analysis.
"""

import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
from datetime import datetime
from typing import Dict, Any, List
from decimal import Decimal

from backend.utils.data_models import CostSummary, ServiceCost, ActualCosts
from backend_logic.cost_exporter import CostExporter


class BudgetSheetComponent:
    """
    Streamlit component for budget sheet display and export.
    
    Provides comprehensive cost visualization, analysis, and export capabilities
    for legal case budget monitoring and operational insights.
    """
    
    def __init__(self):
        """Initialize the budget sheet component."""
        self.cost_exporter = CostExporter()
        
    def display_budget_summary(self, cost_summary: CostSummary) -> None:
        """
        Display budget summary in Streamlit interface.
        
        Args:
            cost_summary: CostSummary object containing budget data
        """
        st.header("📊 Budget Summary")
        
        # Create columns for cost comparison
        if cost_summary.cost_estimate and cost_summary.actual_costs:
            col1, col2, col3 = st.columns(3)
            
            with col1:
                st.metric(
                    label="Estimated Cost",
                    value=f"${float(cost_summary.cost_estimate.total_estimated_cost):.4f}",
                    help="Pre-processing cost estimate based on file analysis"
                )
                
            with col2:
                st.metric(
                    label="Actual Cost",
                    value=f"${float(cost_summary.actual_costs.total_actual_cost):.4f}",
                    help="Actual costs incurred during processing"
                )
                
            with col3:
                variance = float(cost_summary.cost_variance) if cost_summary.cost_variance else 0.0
                variance_pct = cost_summary.cost_variance_percentage or 0.0
                
                st.metric(
                    label="Variance",
                    value=f"${variance:.4f}",
                    delta=f"{variance_pct:.2f}%",
                    help="Difference between estimated and actual costs"
                )
                
        elif cost_summary.cost_estimate:
            col1, col2 = st.columns(2)
            
            with col1:
                st.metric(
                    label="Estimated Cost",
                    value=f"${float(cost_summary.cost_estimate.total_estimated_cost):.4f}",
                    help="Pre-processing cost estimate"
                )
                
            with col2:
                confidence = cost_summary.cost_estimate.confidence_level * 100
                st.metric(
                    label="Confidence Level",
                    value=f"{confidence:.1f}%",
                    help="Estimation confidence based on analysis complexity"
                )
                
        elif cost_summary.actual_costs:
            st.metric(
                label="Total Processing Cost",
                value=f"${float(cost_summary.actual_costs.total_actual_cost):.4f}",
                help="Total costs incurred during case processing"
            )
        
        # Display case information
        st.info(f"**Case ID:** {cost_summary.case_id}")
        
        # Variance analysis
        if cost_summary.cost_variance is not None:
            self._display_variance_analysis(cost_summary)
    
    def display_cost_breakdown_chart(self, cost_summary: CostSummary) -> None:
        """
        Display cost breakdown as interactive charts.
        
        Args:
            cost_summary: CostSummary object to visualize
        """
        st.header("📈 Cost Breakdown Analysis")
        
        # Service-level breakdown
        if cost_summary.actual_costs:
            service_breakdown = self._generate_service_breakdown(cost_summary.actual_costs)
            
            if service_breakdown:
                # Pie chart for service distribution
                col1, col2 = st.columns(2)
                
                with col1:
                    st.subheader("Service Cost Distribution")
                    
                    services = list(service_breakdown.keys())
                    costs = [data['total_cost'] for data in service_breakdown.values()]
                    
                    fig_pie = px.pie(
                        values=costs,
                        names=services,
                        title="Cost Distribution by Service",
                        color_discrete_sequence=px.colors.qualitative.Set3
                    )
                    fig_pie.update_traces(textposition='inside', textinfo='percent+label')
                    fig_pie.update_layout(showlegend=True, height=400)
                    st.plotly_chart(fig_pie, use_container_width=True)
                
                with col2:
                    st.subheader("Service Cost Details")
                    
                    # Create DataFrame for table display
                    service_data = []
                    for service, data in service_breakdown.items():
                        service_data.append({
                            'Service': service,
                            'Cost': f"${data['total_cost']:.4f}",
                            'Percentage': f"{data['percentage']:.1f}%",
                            'Units': data['units_consumed'],
                            'Operations': ', '.join(data['operations'])
                        })
                    
                    df_services = pd.DataFrame(service_data)
                    st.dataframe(df_services, hide_index=True, use_container_width=True)
            
            # Document vs Media breakdown
            self._display_category_breakdown(cost_summary.actual_costs)
        
        # Cost comparison chart (if both estimate and actual exist)
        if cost_summary.cost_estimate and cost_summary.actual_costs:
            self._display_cost_comparison_chart(cost_summary)
    
    def create_export_buttons(self, cost_summary: CostSummary) -> None:
        """
        Create export buttons for different formats.
        
        Args:
            cost_summary: CostSummary object to export
        """
        st.header("📥 Export Budget Report")
        
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            if st.button("📄 Export CSV", help="Export detailed cost breakdown as CSV"):
                csv_data = self.cost_exporter.export_cost_summary_csv(cost_summary)
                st.download_button(
                    label="Download CSV",
                    data=csv_data,
                    file_name=f"budget_report_{cost_summary.case_id}_{datetime.now().strftime('%Y%m%d')}.csv",
                    mime="text/csv"
                )
        
        with col2:
            if st.button("📋 Export JSON", help="Export structured cost data as JSON"):
                json_data = self.cost_exporter.export_cost_summary_json(cost_summary)
                st.download_button(
                    label="Download JSON",
                    data=json_data,
                    file_name=f"budget_report_{cost_summary.case_id}_{datetime.now().strftime('%Y%m%d')}.json",
                    mime="application/json"
                )
        
        with col3:
            if st.button("🌐 Export HTML", help="Export professional HTML budget report"):
                html_data = self.cost_exporter.generate_budget_report_html(cost_summary)
                st.download_button(
                    label="Download HTML",
                    data=html_data,
                    file_name=f"budget_report_{cost_summary.case_id}_{datetime.now().strftime('%Y%m%d')}.html",
                    mime="text/html"
                )
        
        with col4:
            if st.button("📝 Export Text", help="Export human-readable text summary"):
                text_data = self.cost_exporter.generate_cost_report_text(cost_summary)
                st.download_button(
                    label="Download Text",
                    data=text_data,
                    file_name=f"budget_summary_{cost_summary.case_id}_{datetime.now().strftime('%Y%m%d')}.txt",
                    mime="text/plain"
                )
    
    def display_variance_analysis(self, cost_summary: CostSummary) -> None:
        """
        Display variance analysis with visual indicators.
        
        Args:
            cost_summary: CostSummary object containing variance data
        """
        if cost_summary.cost_variance is None:
            return
            
        st.header("📊 Variance Analysis")
        
        self._display_variance_analysis(cost_summary)
        
        # Budget insights
        budget_analysis = self.cost_exporter.create_budget_analysis(cost_summary)
        
        if budget_analysis.get('insights'):
            st.subheader("💡 Operational Insights")
            for insight in budget_analysis['insights']:
                st.info(f"• {insight}")
        
        if budget_analysis.get('optimization_opportunities'):
            st.subheader("🎯 Optimization Opportunities")
            for opportunity in budget_analysis['optimization_opportunities']:
                st.warning(f"• {opportunity}")
        
        if budget_analysis.get('risk_factors'):
            st.subheader("⚠️ Risk Factors")
            for risk in budget_analysis['risk_factors']:
                st.error(f"• {risk}")
    
    def display_detailed_cost_tables(self, cost_summary: CostSummary) -> None:
        """
        Display detailed cost breakdown tables.
        
        Args:
            cost_summary: CostSummary object to display
        """
        st.header("📋 Detailed Cost Breakdown")
        
        # Cost estimates
        if cost_summary.cost_estimate:
            st.subheader("Cost Estimates")
            
            tab1, tab2 = st.tabs(["Document Processing", "Media Processing"])
            
            with tab1:
                if cost_summary.cost_estimate.estimated_document_costs:
                    self._display_cost_table(
                        "Document Processing Estimates",
                        cost_summary.cost_estimate.estimated_document_costs
                    )
                else:
                    st.info("No document processing costs estimated.")
            
            with tab2:
                if cost_summary.cost_estimate.estimated_media_costs:
                    self._display_cost_table(
                        "Media Processing Estimates",
                        cost_summary.cost_estimate.estimated_media_costs
                    )
                else:
                    st.info("No media processing costs estimated.")
        
        # Actual costs
        if cost_summary.actual_costs:
            st.subheader("Actual Costs")
            
            tab1, tab2 = st.tabs(["Document Analysis", "Media Processing"])
            
            with tab1:
                if cost_summary.actual_costs.document_analysis_costs:
                    self._display_cost_table(
                        "Document Analysis Costs",
                        cost_summary.actual_costs.document_analysis_costs
                    )
                else:
                    st.info("No document analysis costs incurred.")
            
            with tab2:
                if cost_summary.actual_costs.media_processing_costs:
                    self._display_cost_table(
                        "Media Processing Costs",
                        cost_summary.actual_costs.media_processing_costs
                    )
                else:
                    st.info("No media processing costs incurred.")
    
    def _display_variance_analysis(self, cost_summary: CostSummary) -> None:
        """Display variance analysis section."""
        variance_pct = cost_summary.cost_variance_percentage or 0.0
        
        # Determine status and color
        if abs(variance_pct) <= 5:
            status = "✅ On Budget"
            color = "green"
        elif variance_pct > 15:
            status = "🔴 Significantly Over Budget"
            color = "red"
        elif variance_pct > 0:
            status = "🟡 Over Budget"
            color = "orange"
        else:
            status = "🔵 Under Budget"
            color = "blue"
        
        st.markdown(f"**Status:** {status}")
        
        # Variance explanation
        if abs(variance_pct) <= 5:
            explanation = "Costs were within expected range (±5%), indicating accurate estimation and efficient processing."
        elif variance_pct > 0:
            explanation = f"Costs exceeded estimate by {variance_pct:.1f}%. This may indicate higher case complexity or additional processing requirements."
        else:
            explanation = f"Costs came in {abs(variance_pct):.1f}% under estimate, suggesting efficient processing or conservative estimation."
        
        st.markdown(f"**Analysis:** {explanation}")
    
    def _generate_service_breakdown(self, actual_costs: ActualCosts) -> Dict[str, Any]:
        """Generate service-wise cost breakdown."""
        all_costs = actual_costs.document_analysis_costs + actual_costs.media_processing_costs
        
        service_totals = {}
        for cost in all_costs:
            if cost.service_name not in service_totals:
                service_totals[cost.service_name] = {
                    "total_cost": Decimal('0.00'),
                    "units_consumed": 0,
                    "operations": set()
                }
            
            service_totals[cost.service_name]["total_cost"] += cost.total_cost
            service_totals[cost.service_name]["units_consumed"] += cost.units_consumed
            service_totals[cost.service_name]["operations"].add(cost.operation_type)
        
        # Convert to display format
        breakdown = {}
        for service, data in service_totals.items():
            breakdown[service] = {
                "total_cost": float(data["total_cost"]),
                "units_consumed": data["units_consumed"],
                "operations": list(data["operations"]),
                "percentage": float((data["total_cost"] / actual_costs.total_actual_cost) * 100) if actual_costs.total_actual_cost > 0 else 0.0
            }
        
        return breakdown
    
    def _display_category_breakdown(self, actual_costs: ActualCosts) -> None:
        """Display document vs media cost breakdown."""
        doc_cost = sum(cost.total_cost for cost in actual_costs.document_analysis_costs)
        media_cost = sum(cost.total_cost for cost in actual_costs.media_processing_costs)
        total_cost = doc_cost + media_cost
        
        if total_cost > 0:
            st.subheader("Document vs Media Cost Breakdown")
            
            categories = ['Document Analysis', 'Media Processing']
            costs = [float(doc_cost), float(media_cost)]
            
            fig_bar = go.Figure(data=[
                go.Bar(
                    x=categories,
                    y=costs,
                    text=[f"${cost:.4f}" for cost in costs],
                    textposition='auto',
                    marker_color=['#3498db', '#e74c3c']
                )
            ])
            
            fig_bar.update_layout(
                title="Cost by Processing Category",
                xaxis_title="Category",
                yaxis_title="Cost ($)",
                height=400
            )
            
            st.plotly_chart(fig_bar, use_container_width=True)
    
    def _display_cost_comparison_chart(self, cost_summary: CostSummary) -> None:
        """Display estimated vs actual cost comparison."""
        st.subheader("Estimated vs Actual Cost Comparison")
        
        estimated = float(cost_summary.cost_estimate.total_estimated_cost)
        actual = float(cost_summary.actual_costs.total_actual_cost)
        
        fig_comparison = go.Figure(data=[
            go.Bar(
                x=['Estimated', 'Actual'],
                y=[estimated, actual],
                text=[f"${estimated:.4f}", f"${actual:.4f}"],
                textposition='auto',
                marker_color=['#3498db', '#27ae60']
            )
        ])
        
        fig_comparison.update_layout(
            title="Cost Estimate vs Actual",
            xaxis_title="Cost Type",
            yaxis_title="Cost ($)",
            height=400
        )
        
        st.plotly_chart(fig_comparison, use_container_width=True)
    
    def _display_cost_table(self, title: str, costs: List[ServiceCost]) -> None:
        """Display a formatted cost table."""
        if not costs:
            st.info(f"No costs in {title.lower()}.")
            return
        
        # Create DataFrame
        cost_data = []
        for cost in costs:
            cost_data.append({
                'Service': cost.service_name,
                'Operation': cost.operation_type,
                'File': cost.file_name or 'N/A',
                'Units': f"{cost.units_consumed} {cost.unit_type}",
                'Rate per Unit': f"${float(cost.rate_per_unit):.6f}",
                'Total Cost': f"${float(cost.total_cost):.4f}"
            })
        
        df_costs = pd.DataFrame(cost_data)
        
        # Display with formatting
        st.dataframe(
            df_costs,
            hide_index=True,
            use_container_width=True,
            column_config={
                "Total Cost": st.column_config.NumberColumn(
                    "Total Cost",
                    format="$%.4f"
                )
            }
        )
        
        # Total
        total_cost = sum(cost.total_cost for cost in costs)
        st.markdown(f"**Total {title}:** ${float(total_cost):.4f}")