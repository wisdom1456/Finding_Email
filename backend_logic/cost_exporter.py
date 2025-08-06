"""
Cost Exporter Service for Legal Document Analysis Portal

This service provides comprehensive cost export capabilities for operational analysis
and budget reporting, building upon the existing cost tracking infrastructure.
"""

import csv
import json
import io
from decimal import Decimal
from typing import Dict, Any, List, Optional
from datetime import datetime
from jinja2 import Environment, FileSystemLoader

from backend.utils.data_models import CostSummary, ActualCosts


class CostExporter:
    """
    Export cost data for operational analysis and budget reporting.
    
    Provides multiple export formats and comprehensive budget analysis capabilities
    for law firm operational insights and client billing transparency.
    """
    
    def __init__(self, template_dir: str = "backend/assets/templates"):
        """
        Initialize cost exporter with template configuration.
        
        Args:
            template_dir: Directory containing Jinja2 templates
        """
        self.template_dir = template_dir
        self.jinja_env = Environment(
            loader=FileSystemLoader(template_dir),
            autoescape=True
        )
    
    def export_cost_summary_csv(self, cost_summary: CostSummary) -> str:
        """
        Export detailed cost summary to CSV format.
        
        Args:
            cost_summary: CostSummary object to export
            
        Returns:
            CSV formatted string with detailed cost breakdown
        """
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Header information
        writer.writerow(['Legal Document Analysis Portal - Cost Report'])
        writer.writerow(['Case ID:', cost_summary.case_id])
        writer.writerow(['Generated:', datetime.now().strftime('%Y-%m-%d %H:%M:%S')])
        writer.writerow([])  # Empty row
        
        # Cost estimates section
        if cost_summary.cost_estimate:
            writer.writerow(['COST ESTIMATES'])
            writer.writerow(['Service', 'Operation', 'File', 'Units', 'Unit Type', 'Rate per Unit', 'Total Cost'])
            
            # Document costs
            for cost in cost_summary.cost_estimate.estimated_document_costs:
                writer.writerow([
                    cost.service_name,
                    cost.operation_type,
                    cost.file_name or 'N/A',
                    cost.units_consumed,
                    cost.unit_type,
                    f"${float(cost.rate_per_unit):.6f}",
                    f"${float(cost.total_cost):.4f}"
                ])
            
            # Media costs
            for cost in cost_summary.cost_estimate.estimated_media_costs:
                writer.writerow([
                    cost.service_name,
                    cost.operation_type,
                    cost.file_name or 'N/A',
                    cost.units_consumed,
                    cost.unit_type,
                    f"${float(cost.rate_per_unit):.6f}",
                    f"${float(cost.total_cost):.4f}"
                ])
            
            writer.writerow(['', '', '', '', '', 'TOTAL ESTIMATED:', f"${float(cost_summary.cost_estimate.total_estimated_cost):.4f}"])
            writer.writerow([])
        
        # Actual costs section
        if cost_summary.actual_costs:
            writer.writerow(['ACTUAL COSTS'])
            writer.writerow(['Service', 'Operation', 'File', 'Units', 'Unit Type', 'Rate per Unit', 'Total Cost'])
            
            # Document analysis costs
            for cost in cost_summary.actual_costs.document_analysis_costs:
                writer.writerow([
                    cost.service_name,
                    cost.operation_type,
                    cost.file_name or 'N/A',
                    cost.units_consumed,
                    cost.unit_type,
                    f"${float(cost.rate_per_unit):.6f}",
                    f"${float(cost.total_cost):.4f}"
                ])
            
            # Media processing costs
            for cost in cost_summary.actual_costs.media_processing_costs:
                writer.writerow([
                    cost.service_name,
                    cost.operation_type,
                    cost.file_name or 'N/A',
                    cost.units_consumed,
                    cost.unit_type,
                    f"${float(cost.rate_per_unit):.6f}",
                    f"${float(cost.total_cost):.4f}"
                ])
            
            writer.writerow(['', '', '', '', '', 'TOTAL ACTUAL:', f"${float(cost_summary.actual_costs.total_actual_cost):.4f}"])
            writer.writerow([])
        
        # Variance analysis
        if cost_summary.cost_variance is not None:
            writer.writerow(['VARIANCE ANALYSIS'])
            writer.writerow(['Metric', 'Value'])
            writer.writerow(['Cost Variance', f"${float(cost_summary.cost_variance):.4f}"])
            writer.writerow(['Variance Percentage', f"{cost_summary.cost_variance_percentage:.2f}%"])
            writer.writerow(['Variance Status', self._classify_variance(cost_summary.cost_variance_percentage)])
        
        return output.getvalue()
    
    def export_cost_summary_json(self, cost_summary: CostSummary) -> str:
        """
        Export cost summary to JSON format for API integration.
        
        Args:
            cost_summary: CostSummary object to export
            
        Returns:
            JSON formatted string with structured cost data
        """
        export_data = {
            "case_id": cost_summary.case_id,
            "export_timestamp": datetime.now().isoformat(),
            "cost_estimate": None,
            "actual_costs": None,
            "variance_analysis": None,
            "budget_insights": self.create_budget_analysis(cost_summary)
        }
        
        # Cost estimate data
        if cost_summary.cost_estimate:
            export_data["cost_estimate"] = {
                "total_estimated_cost": float(cost_summary.cost_estimate.total_estimated_cost),
                "confidence_level": cost_summary.cost_estimate.confidence_level,
                "estimation_timestamp": cost_summary.cost_estimate.estimation_timestamp.isoformat(),
                "document_costs": [
                    {
                        "service": cost.service_name,
                        "operation": cost.operation_type,
                        "file_name": cost.file_name,
                        "units_consumed": cost.units_consumed,
                        "unit_type": cost.unit_type,
                        "rate_per_unit": float(cost.rate_per_unit),
                        "total_cost": float(cost.total_cost)
                    }
                    for cost in cost_summary.cost_estimate.estimated_document_costs
                ],
                "media_costs": [
                    {
                        "service": cost.service_name,
                        "operation": cost.operation_type,
                        "file_name": cost.file_name,
                        "units_consumed": cost.units_consumed,
                        "unit_type": cost.unit_type,
                        "rate_per_unit": float(cost.rate_per_unit),
                        "total_cost": float(cost.total_cost)
                    }
                    for cost in cost_summary.cost_estimate.estimated_media_costs
                ]
            }
        
        # Actual costs data
        if cost_summary.actual_costs:
            export_data["actual_costs"] = {
                "total_actual_cost": float(cost_summary.actual_costs.total_actual_cost),
                "processing_timestamp": cost_summary.actual_costs.processing_timestamp.isoformat(),
                "document_analysis_costs": [
                    {
                        "service": cost.service_name,
                        "operation": cost.operation_type,
                        "file_name": cost.file_name,
                        "units_consumed": cost.units_consumed,
                        "unit_type": cost.unit_type,
                        "rate_per_unit": float(cost.rate_per_unit),
                        "total_cost": float(cost.total_cost)
                    }
                    for cost in cost_summary.actual_costs.document_analysis_costs
                ],
                "media_processing_costs": [
                    {
                        "service": cost.service_name,
                        "operation": cost.operation_type,
                        "file_name": cost.file_name,
                        "units_consumed": cost.units_consumed,
                        "unit_type": cost.unit_type,
                        "rate_per_unit": float(cost.rate_per_unit),
                        "total_cost": float(cost.total_cost)
                    }
                    for cost in cost_summary.actual_costs.media_processing_costs
                ]
            }
        
        # Variance analysis
        if cost_summary.cost_variance is not None:
            export_data["variance_analysis"] = {
                "cost_variance": float(cost_summary.cost_variance),
                "cost_variance_percentage": cost_summary.cost_variance_percentage,
                "variance_classification": self._classify_variance(cost_summary.cost_variance_percentage),
                "variance_explanation": self._generate_variance_explanation(cost_summary)
            }
        
        return json.dumps(export_data, indent=2, default=str)
    
    def generate_budget_report_html(self, cost_summary: CostSummary) -> str:
        """
        Generate formatted HTML budget report.
        
        Args:
            cost_summary: CostSummary object to generate report for
            
        Returns:
            HTML formatted budget report
        """
        try:
            template = self.jinja_env.get_template('budget_sheet.jinja2')
            
            # Prepare template context
            context = {
                "cost_summary": cost_summary,
                "budget_analysis": self.create_budget_analysis(cost_summary),
                "variance_indicators": self._get_variance_indicators(cost_summary),
                "service_breakdown": self._generate_service_breakdown(cost_summary.actual_costs) if cost_summary.actual_costs else {},
                "recommendations": self._generate_operational_recommendations(cost_summary),
                "report_timestamp": datetime.now(),
                "format_currency": self._format_currency,
                "format_percentage": self._format_percentage
            }
            
            return template.render(**context)
            
        except Exception:
            # Fallback to basic HTML generation
            return self._generate_fallback_html_report(cost_summary)
    
    def generate_cost_report_text(self, cost_summary: CostSummary) -> str:
        """
        Generate human-readable text cost summary.
        
        Args:
            cost_summary: CostSummary object to summarize
            
        Returns:
            Human-readable text summary
        """
        lines = []
        lines.append("=" * 60)
        lines.append("LEGAL DOCUMENT ANALYSIS PORTAL - COST REPORT")
        lines.append("=" * 60)
        lines.append(f"Case ID: {cost_summary.case_id}")
        lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append("")
        
        # Cost Estimates Section
        if cost_summary.cost_estimate:
            lines.append("COST ESTIMATES")
            lines.append("-" * 20)
            lines.append(f"Total Estimated Cost: ${float(cost_summary.cost_estimate.total_estimated_cost):.4f}")
            lines.append(f"Confidence Level: {cost_summary.cost_estimate.confidence_level * 100:.1f}%")
            lines.append(f"Estimation Time: {cost_summary.cost_estimate.estimation_timestamp.strftime('%Y-%m-%d %H:%M:%S')}")
            lines.append("")
            
            # Service breakdown for estimates
            if cost_summary.cost_estimate.estimated_document_costs:
                lines.append("Document Processing Estimates:")
                for cost in cost_summary.cost_estimate.estimated_document_costs:
                    lines.append(f"  • {cost.service_name} ({cost.operation_type}): ${float(cost.total_cost):.4f}")
            
            if cost_summary.cost_estimate.estimated_media_costs:
                lines.append("Media Processing Estimates:")
                for cost in cost_summary.cost_estimate.estimated_media_costs:
                    lines.append(f"  • {cost.service_name} ({cost.operation_type}): ${float(cost.total_cost):.4f}")
            
            lines.append("")
        
        # Actual Costs Section
        if cost_summary.actual_costs:
            lines.append("ACTUAL COSTS")
            lines.append("-" * 15)
            lines.append(f"Total Actual Cost: ${float(cost_summary.actual_costs.total_actual_cost):.4f}")
            lines.append(f"Processing Time: {cost_summary.actual_costs.processing_timestamp.strftime('%Y-%m-%d %H:%M:%S')}")
            lines.append("")
            
            # Service breakdown for actual costs
            if cost_summary.actual_costs.document_analysis_costs:
                lines.append("Document Analysis Costs:")
                for cost in cost_summary.actual_costs.document_analysis_costs:
                    lines.append(f"  • {cost.service_name}: ${float(cost.total_cost):.4f} ({cost.file_name or 'N/A'})")
            
            if cost_summary.actual_costs.media_processing_costs:
                lines.append("Media Processing Costs:")
                for cost in cost_summary.actual_costs.media_processing_costs:
                    lines.append(f"  • {cost.service_name}: ${float(cost.total_cost):.4f} ({cost.file_name or 'N/A'})")
            
            lines.append("")
        
        # Variance Analysis
        if cost_summary.cost_variance is not None:
            lines.append("VARIANCE ANALYSIS")
            lines.append("-" * 20)
            lines.append(f"Cost Variance: ${float(cost_summary.cost_variance):.4f}")
            lines.append(f"Variance Percentage: {cost_summary.cost_variance_percentage:.2f}%")
            lines.append(f"Status: {self._classify_variance(cost_summary.cost_variance_percentage)}")
            lines.append(f"Analysis: {self._generate_variance_explanation(cost_summary)}")
            lines.append("")
        
        # Budget Insights
        budget_analysis = self.create_budget_analysis(cost_summary)
        if budget_analysis.get("insights"):
            lines.append("OPERATIONAL INSIGHTS")
            lines.append("-" * 25)
            for insight in budget_analysis["insights"]:
                lines.append(f"• {insight}")
            lines.append("")
        
        # Recommendations
        recommendations = self._generate_operational_recommendations(cost_summary)
        if recommendations:
            lines.append("RECOMMENDATIONS")
            lines.append("-" * 20)
            for recommendation in recommendations:
                lines.append(f"• {recommendation}")
        
        lines.append("")
        lines.append("=" * 60)
        
        return "\n".join(lines)
    
    def create_budget_analysis(self, cost_summary: CostSummary) -> Dict[str, Any]:
        """
        Generate budget analysis with insights and recommendations.
        
        Args:
            cost_summary: CostSummary object to analyze
            
        Returns:
            Dictionary containing budget analysis and insights
        """
        analysis = {
            "case_id": cost_summary.case_id,
            "analysis_timestamp": datetime.now().isoformat(),
            "cost_efficiency_score": None,
            "budget_compliance": None,
            "insights": [],
            "risk_factors": [],
            "optimization_opportunities": []
        }
        
        # Calculate cost efficiency score
        if cost_summary.cost_estimate and cost_summary.actual_costs:
            estimated = float(cost_summary.cost_estimate.total_estimated_cost)
            actual = float(cost_summary.actual_costs.total_actual_cost)
            
            if estimated > 0:
                efficiency_ratio = actual / estimated
                if efficiency_ratio <= 0.95:
                    analysis["cost_efficiency_score"] = "Excellent"
                    analysis["insights"].append("Actual costs came in significantly under estimate, indicating excellent cost control.")
                elif efficiency_ratio <= 1.05:
                    analysis["cost_efficiency_score"] = "Good"
                    analysis["insights"].append("Actual costs were very close to estimates, showing accurate forecasting.")
                elif efficiency_ratio <= 1.15:
                    analysis["cost_efficiency_score"] = "Fair"
                    analysis["insights"].append("Actual costs exceeded estimates moderately. Review estimation models.")
                else:
                    analysis["cost_efficiency_score"] = "Poor"
                    analysis["insights"].append("Actual costs significantly exceeded estimates. Immediate review required.")
        
        # Budget compliance analysis
        if cost_summary.cost_variance_percentage is not None:
            variance_pct = cost_summary.cost_variance_percentage
            if abs(variance_pct) <= 5:
                analysis["budget_compliance"] = "Compliant"
            elif abs(variance_pct) <= 15:
                analysis["budget_compliance"] = "Acceptable Variance"
            else:
                analysis["budget_compliance"] = "Non-Compliant"
                analysis["risk_factors"].append("High cost variance indicates potential budgeting or estimation issues.")
        
        # Service-specific insights
        if cost_summary.actual_costs:
            service_breakdown = self._generate_service_breakdown(cost_summary.actual_costs)
            
            # Find dominant cost drivers
            if service_breakdown:
                max_service = max(service_breakdown.items(), key=lambda x: x[1]['total_cost'])
                if max_service[1]['percentage'] > 60:
                    analysis["insights"].append(f"{max_service[0]} represents {max_service[1]['percentage']:.1f}% of total costs.")
                    analysis["optimization_opportunities"].append(f"Consider optimizing {max_service[0]} usage for cost reduction.")
        
        # Document vs Media cost analysis
        if cost_summary.actual_costs:
            doc_costs = sum(cost.total_cost for cost in cost_summary.actual_costs.document_analysis_costs)
            media_costs = sum(cost.total_cost for cost in cost_summary.actual_costs.media_processing_costs)
            total_costs = doc_costs + media_costs
            
            if total_costs > 0:
                doc_percentage = (doc_costs / total_costs) * 100
                media_percentage = (media_costs / total_costs) * 100
                
                analysis["insights"].append(f"Cost distribution: {doc_percentage:.1f}% document analysis, {media_percentage:.1f}% media processing.")
                
                if media_percentage > 40:
                    analysis["optimization_opportunities"].append("High media processing costs detected. Consider batch processing for efficiency.")
        
        return analysis
    
    def _classify_variance(self, variance_percentage: Optional[float]) -> str:
        """Classify cost variance into categories."""
        if variance_percentage is None:
            return "Unknown"
        
        if variance_percentage < -10:
            return "Significantly Under Budget"
        elif variance_percentage < -5:
            return "Under Budget"
        elif variance_percentage <= 5:
            return "On Budget"
        elif variance_percentage <= 15:
            return "Over Budget"
        else:
            return "Significantly Over Budget"
    
    def _generate_variance_explanation(self, cost_summary: CostSummary) -> str:
        """Generate human-readable variance explanation."""
        if not cost_summary.cost_variance_percentage:
            return "No variance analysis available."
        
        variance_pct = cost_summary.cost_variance_percentage
        variance_amount = float(cost_summary.cost_variance) if cost_summary.cost_variance else 0.0
        
        if abs(variance_pct) <= 5:
            return f"Costs were within expected range (±5%). Variance: {variance_pct:.1f}% (${variance_amount:.2f})"
        elif variance_pct > 0:
            return f"Costs exceeded estimate by {variance_pct:.1f}% (${variance_amount:.2f}). Consider reviewing estimation models."
        else:
            return f"Costs came in {abs(variance_pct):.1f}% under estimate (${abs(variance_amount):.2f} savings)."
    
    def _get_variance_indicators(self, cost_summary: CostSummary) -> Dict[str, Any]:
        """Get variance indicators for visual display."""
        indicators = {
            "color": "gray",
            "icon": "neutral",
            "status": "unknown"
        }
        
        if cost_summary.cost_variance_percentage is not None:
            variance_pct = cost_summary.cost_variance_percentage
            
            if abs(variance_pct) <= 5:
                indicators.update({"color": "green", "icon": "check", "status": "good"})
            elif variance_pct > 15:
                indicators.update({"color": "red", "icon": "warning", "status": "poor"})
            elif variance_pct > 0:
                indicators.update({"color": "orange", "icon": "alert", "status": "caution"})
            else:
                indicators.update({"color": "blue", "icon": "info", "status": "good"})
        
        return indicators
    
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
        
        # Convert to JSON-serializable format
        breakdown = {}
        for service, data in service_totals.items():
            breakdown[service] = {
                "total_cost": float(data["total_cost"]),
                "units_consumed": data["units_consumed"],
                "operations": list(data["operations"]),
                "percentage": float((data["total_cost"] / actual_costs.total_actual_cost) * 100) if actual_costs.total_actual_cost > 0 else 0.0
            }
        
        return breakdown
    
    def _generate_operational_recommendations(self, cost_summary: CostSummary) -> List[str]:
        """Generate operational recommendations based on cost analysis."""
        recommendations = []
        
        if cost_summary.cost_variance_percentage is not None:
            if cost_summary.cost_variance_percentage > 15:
                recommendations.append("Review and recalibrate cost estimation models for improved accuracy.")
                recommendations.append("Implement stricter budget controls for future cases.")
            elif cost_summary.cost_variance_percentage < -10:
                recommendations.append("Consider if estimation models are too conservative, potentially impacting resource allocation.")
        
        if cost_summary.actual_costs:
            # Check for high-cost services
            service_breakdown = self._generate_service_breakdown(cost_summary.actual_costs)
            for service, data in service_breakdown.items():
                if data['percentage'] > 50:
                    recommendations.append(f"Optimize {service} usage as it represents {data['percentage']:.1f}% of total costs.")
        
        # Always include general recommendations
        recommendations.extend([
            "Monitor cost trends across similar cases for pattern identification.",
            "Consider implementing cost alerts for real-time budget monitoring.",
            "Review service pricing regularly to optimize vendor relationships."
        ])
        
        return recommendations
    
    def _generate_fallback_html_report(self, cost_summary: CostSummary) -> str:
        """Generate basic HTML report when template is not available."""
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Budget Report - {cost_summary.case_id}</title>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 20px; }}
                .header {{ background-color: #f5f5f5; padding: 15px; border-radius: 5px; }}
                .section {{ margin: 20px 0; }}
                .cost-item {{ background-color: #fafafa; padding: 10px; margin: 5px 0; border-left: 3px solid #007bff; }}
                .variance {{ padding: 10px; border-radius: 5px; }}
                .variance.good {{ background-color: #d4edda; }}
                .variance.warning {{ background-color: #fff3cd; }}
                .variance.danger {{ background-color: #f8d7da; }}
            </style>
        </head>
        <body>
            <div class="header">
                <h1>Budget Report</h1>
                <p><strong>Case ID:</strong> {cost_summary.case_id}</p>
                <p><strong>Generated:</strong> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
            </div>
        """
        
        if cost_summary.cost_estimate:
            html += f"""
            <div class="section">
                <h2>Cost Estimate</h2>
                <p><strong>Total Estimated:</strong> ${float(cost_summary.cost_estimate.total_estimated_cost):.4f}</p>
            </div>
            """
        
        if cost_summary.actual_costs:
            html += f"""
            <div class="section">
                <h2>Actual Costs</h2>
                <p><strong>Total Actual:</strong> ${float(cost_summary.actual_costs.total_actual_cost):.4f}</p>
            </div>
            """
        
        if cost_summary.cost_variance is not None:
            variance_class = "good" if abs(cost_summary.cost_variance_percentage) <= 5 else "warning" if abs(cost_summary.cost_variance_percentage) <= 15 else "danger"
            html += f"""
            <div class="section">
                <h2>Variance Analysis</h2>
                <div class="variance {variance_class}">
                    <p><strong>Variance:</strong> ${float(cost_summary.cost_variance):.4f} ({cost_summary.cost_variance_percentage:.2f}%)</p>
                    <p><strong>Status:</strong> {self._classify_variance(cost_summary.cost_variance_percentage)}</p>
                </div>
            </div>
            """
        
        html += """
        </body>
        </html>
        """
        
        return html
    
    def _format_currency(self, amount: float) -> str:
        """Format currency for display."""
        return f"${amount:.4f}"
    
    def _format_percentage(self, percentage: float) -> str:
        """Format percentage for display."""
        return f"{percentage:.2f}%"