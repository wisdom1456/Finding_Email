"""
Cost Session Manager for Legal Document Analysis Portal

This service manages session-based cost tracking throughout the case processing
lifecycle, including estimates, actual costs, and variance analysis.
"""

import uuid
import json
import os
from decimal import Decimal
from typing import Dict, Any, Optional, List
from datetime import datetime

from backend.utils.data_models import (
    CostEstimate,
    ActualCosts, 
    CostSummary,
    ServiceCost,
    CaseAnalysisResult,
    ProcessedDocument
)
from backend_logic.cost_estimator import CostEstimator
from backend_logic.cost_calculator import CostCalculator
from backend_logic.cost_exporter import CostExporter


class CostSessionManager:
    """
    Manages cost tracking sessions for legal case processing.
    
    Provides session-based cost tracking that persists cost estimates,
    accumulates actual costs during processing, and generates comprehensive
    cost summaries with variance analysis for operational insights.
    """
    
    def __init__(self, session_storage_dir: str = "cost_sessions"):
        """
        Initialize cost session manager.
        
        Args:
            session_storage_dir: Directory for storing cost session data
        """
        self.session_storage_dir = session_storage_dir
        self.cost_estimator = CostEstimator()
        self.cost_calculator = CostCalculator()
        self.cost_exporter = CostExporter()
        self.active_sessions: Dict[str, CostSummary] = {}
        
        # Ensure storage directory exists
        os.makedirs(session_storage_dir, exist_ok=True)
    
    def initialize_cost_session(
        self,
        case_id: Optional[str] = None,
        documents: List[ProcessedDocument] = None,
        audio_files: List[Dict[str, Any]] = None,
        video_files: List[Dict[str, Any]] = None
    ) -> str:
        """
        Initialize a new cost tracking session for a case.
        
        Args:
            case_id: Optional case identifier (generates UUID if not provided)
            documents: List of documents to process
            audio_files: List of audio file metadata
            video_files: List of video file metadata
            
        Returns:
            Case ID for the cost tracking session
        """
        if not case_id:
            case_id = str(uuid.uuid4())
        
        # Generate cost estimate
        cost_estimate = self.cost_estimator.generate_cost_estimate(
            documents=documents,
            audio_files=audio_files,
            video_files=video_files
        )
        
        # Create cost summary
        cost_summary = CostSummary(
            case_id=case_id,
            cost_estimate=cost_estimate,
            actual_costs=None,
            cost_variance=None,
            cost_variance_percentage=None
        )
        
        # Store in active sessions
        self.active_sessions[case_id] = cost_summary
        
        # Persist to storage
        self._save_session(case_id, cost_summary)
        
        return case_id
    
    def update_actual_costs(
        self,
        case_id: str,
        case_analysis_result: CaseAnalysisResult,
        processing_logs: Dict[str, Any] = None
    ) -> CostSummary:
        """
        Update session with actual costs incurred during processing.
        
        Args:
            case_id: Case identifier
            case_analysis_result: Complete analysis results
            processing_logs: Optional detailed processing logs
            
        Returns:
            Updated CostSummary with actual costs and variance
        """
        # Load session if not in active sessions
        if case_id not in self.active_sessions:
            cost_summary = self._load_session(case_id)
            if not cost_summary:
                raise ValueError(f"Cost session not found for case_id: {case_id}")
            self.active_sessions[case_id] = cost_summary
        
        cost_summary = self.active_sessions[case_id]
        
        # Calculate actual costs
        actual_costs = self.cost_calculator.calculate_total_actual_costs(
            analyzed_documents=case_analysis_result.analyzed_documents,
            transcripted_media=case_analysis_result.transcripted_media,
            video_insights=case_analysis_result.video_insights,
            processing_logs=processing_logs
        )
        
        # Update cost summary
        cost_summary.actual_costs = actual_costs
        
        # Calculate variance if estimate exists
        if cost_summary.cost_estimate:
            cost_summary.cost_variance = (
                actual_costs.total_actual_cost - 
                cost_summary.cost_estimate.total_estimated_cost
            )
            
            if cost_summary.cost_estimate.total_estimated_cost > 0:
                cost_summary.cost_variance_percentage = float(
                    (cost_summary.cost_variance / cost_summary.cost_estimate.total_estimated_cost) * 100
                )
            else:
                cost_summary.cost_variance_percentage = 0.0
        
        # Update active session and persist
        self.active_sessions[case_id] = cost_summary
        self._save_session(case_id, cost_summary)
        
        return cost_summary
    
    def get_cost_summary(self, case_id: str) -> Optional[CostSummary]:
        """
        Retrieve cost summary for a case.
        
        Args:
            case_id: Case identifier
            
        Returns:
            CostSummary if found, None otherwise
        """
        # Check active sessions first
        if case_id in self.active_sessions:
            return self.active_sessions[case_id]
        
        # Load from storage
        return self._load_session(case_id)
    
    def finalize_cost_session(self, case_id: str) -> CostSummary:
        """
        Finalize cost tracking session and generate final summary.
        
        Args:
            case_id: Case identifier
            
        Returns:
            Final CostSummary with complete analysis
        """
        cost_summary = self.get_cost_summary(case_id)
        if not cost_summary:
            raise ValueError(f"Cost session not found for case_id: {case_id}")
        
        # Ensure session is saved
        self._save_session(case_id, cost_summary)
        
        # Remove from active sessions to free memory
        if case_id in self.active_sessions:
            del self.active_sessions[case_id]
        
        return cost_summary
    
    def generate_cost_report(self, case_id: str) -> Dict[str, Any]:
        """
        Generate detailed cost report for a case.
        
        Args:
            case_id: Case identifier
            
        Returns:
            Detailed cost analysis report
        """
        cost_summary = self.get_cost_summary(case_id)
        if not cost_summary:
            raise ValueError(f"Cost session not found for case_id: {case_id}")
        
        report = {
            "case_id": case_id,
            "report_generated": datetime.now().isoformat(),
            "cost_estimate": None,
            "actual_costs": None,
            "variance_analysis": None,
            "service_breakdown": None
        }
        
        # Cost estimate section
        if cost_summary.cost_estimate:
            report["cost_estimate"] = {
                "total_estimated_cost": float(cost_summary.cost_estimate.total_estimated_cost),
                "confidence_level": cost_summary.cost_estimate.confidence_level,
                "estimation_timestamp": cost_summary.cost_estimate.estimation_timestamp.isoformat(),
                "document_costs": [
                    {
                        "service": cost.service_name,
                        "operation": cost.operation_type,
                        "units": cost.units_consumed,
                        "unit_type": cost.unit_type,
                        "cost": float(cost.total_cost),
                        "file": cost.file_name
                    }
                    for cost in cost_summary.cost_estimate.estimated_document_costs
                ],
                "media_costs": [
                    {
                        "service": cost.service_name,
                        "operation": cost.operation_type,
                        "units": cost.units_consumed,
                        "unit_type": cost.unit_type,
                        "cost": float(cost.total_cost),
                        "file": cost.file_name
                    }
                    for cost in cost_summary.cost_estimate.estimated_media_costs
                ]
            }
        
        # Actual costs section
        if cost_summary.actual_costs:
            report["actual_costs"] = {
                "total_actual_cost": float(cost_summary.actual_costs.total_actual_cost),
                "processing_timestamp": cost_summary.actual_costs.processing_timestamp.isoformat(),
                "document_analysis_costs": [
                    {
                        "service": cost.service_name,
                        "operation": cost.operation_type,
                        "units": cost.units_consumed,
                        "unit_type": cost.unit_type,
                        "cost": float(cost.total_cost),
                        "file": cost.file_name
                    }
                    for cost in cost_summary.actual_costs.document_analysis_costs
                ],
                "media_processing_costs": [
                    {
                        "service": cost.service_name,
                        "operation": cost.operation_type,
                        "units": cost.units_consumed,
                        "unit_type": cost.unit_type,
                        "cost": float(cost.total_cost),
                        "file": cost.file_name
                    }
                    for cost in cost_summary.actual_costs.media_processing_costs
                ]
            }
        
        # Variance analysis
        if cost_summary.cost_variance is not None:
            report["variance_analysis"] = {
                "cost_variance": float(cost_summary.cost_variance),
                "cost_variance_percentage": cost_summary.cost_variance_percentage,
                "variance_status": self._classify_variance(cost_summary.cost_variance_percentage),
                "analysis": self._generate_variance_analysis(cost_summary)
            }
        
        # Service breakdown
        if cost_summary.actual_costs:
            report["service_breakdown"] = self._generate_service_breakdown(cost_summary.actual_costs)
        
        return report
    
    def export_cost_data_for_budget_analysis(self, case_ids: List[str] = None) -> Dict[str, Any]:
        """
        Export cost data in format suitable for budget analysis.
        
        Args:
            case_ids: Optional list of specific case IDs to export
            
        Returns:
            Budget analysis data export
        """
        if case_ids is None:
            # Get all available sessions
            case_ids = self._get_all_session_ids()
        
        export_data = {
            "export_timestamp": datetime.now().isoformat(),
            "total_cases": len(case_ids),
            "cases": [],
            "summary_statistics": {}
        }
        
        total_estimated = Decimal('0.00')
        total_actual = Decimal('0.00')
        variance_list = []
        
        for case_id in case_ids:
            cost_summary = self.get_cost_summary(case_id)
            if not cost_summary:
                continue
            
            case_data = {
                "case_id": case_id,
                "estimated_cost": float(cost_summary.cost_estimate.total_estimated_cost) if cost_summary.cost_estimate else 0.0,
                "actual_cost": float(cost_summary.actual_costs.total_actual_cost) if cost_summary.actual_costs else 0.0,
                "variance": float(cost_summary.cost_variance) if cost_summary.cost_variance else 0.0,
                "variance_percentage": cost_summary.cost_variance_percentage if cost_summary.cost_variance_percentage else 0.0
            }
            
            export_data["cases"].append(case_data)
            
            if cost_summary.cost_estimate:
                total_estimated += cost_summary.cost_estimate.total_estimated_cost
            if cost_summary.actual_costs:
                total_actual += cost_summary.actual_costs.total_actual_cost
            if cost_summary.cost_variance_percentage is not None:
                variance_list.append(cost_summary.cost_variance_percentage)
        
        # Calculate summary statistics
        export_data["summary_statistics"] = {
            "total_estimated_cost": float(total_estimated),
            "total_actual_cost": float(total_actual),
            "total_variance": float(total_actual - total_estimated),
            "average_variance_percentage": sum(variance_list) / len(variance_list) if variance_list else 0.0,
            "cases_over_budget": len([v for v in variance_list if v > 0]),
            "cases_under_budget": len([v for v in variance_list if v < 0])
        }
        
        return export_data
    
    def _save_session(self, case_id: str, cost_summary: CostSummary) -> None:
        """Save cost session to persistent storage."""
        session_file = os.path.join(self.session_storage_dir, f"{case_id}.json")
        
        # Convert to JSON-serializable format
        session_data = {
            "case_id": cost_summary.case_id,
            "cost_estimate": cost_summary.cost_estimate.model_dump() if cost_summary.cost_estimate else None,
            "actual_costs": cost_summary.actual_costs.model_dump() if cost_summary.actual_costs else None,
            "cost_variance": float(cost_summary.cost_variance) if cost_summary.cost_variance else None,
            "cost_variance_percentage": cost_summary.cost_variance_percentage
        }
        
        with open(session_file, 'w') as f:
            json.dump(session_data, f, indent=2, default=str)
    
    def _load_session(self, case_id: str) -> Optional[CostSummary]:
        """Load cost session from persistent storage."""
        session_file = os.path.join(self.session_storage_dir, f"{case_id}.json")
        
        if not os.path.exists(session_file):
            return None
        
        try:
            with open(session_file, 'r') as f:
                session_data = json.load(f)
            
            # Reconstruct CostSummary object
            cost_estimate = None
            if session_data.get("cost_estimate"):
                cost_estimate = CostEstimate.model_validate(session_data["cost_estimate"])
            
            actual_costs = None
            if session_data.get("actual_costs"):
                actual_costs = ActualCosts.model_validate(session_data["actual_costs"])
            
            cost_variance = None
            if session_data.get("cost_variance") is not None:
                cost_variance = Decimal(str(session_data["cost_variance"]))
            
            return CostSummary(
                case_id=session_data["case_id"],
                cost_estimate=cost_estimate,
                actual_costs=actual_costs,
                cost_variance=cost_variance,
                cost_variance_percentage=session_data.get("cost_variance_percentage")
            )
        
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            print(f"Error loading cost session {case_id}: {e}")
            return None
    
    def _get_all_session_ids(self) -> List[str]:
        """Get all available session IDs from storage."""
        if not os.path.exists(self.session_storage_dir):
            return []
        
        session_files = [
            f[:-5]  # Remove .json extension
            for f in os.listdir(self.session_storage_dir)
            if f.endswith('.json')
        ]
        
        return session_files
    
    def _classify_variance(self, variance_percentage: Optional[float]) -> str:
        """Classify cost variance into categories."""
        if variance_percentage is None:
            return "unknown"
        
        if variance_percentage < -10:
            return "significantly_under_budget"
        elif variance_percentage < -5:
            return "under_budget"
        elif variance_percentage <= 5:
            return "on_budget"
        elif variance_percentage <= 15:
            return "over_budget"
        else:
            return "significantly_over_budget"
    
    def _generate_variance_analysis(self, cost_summary: CostSummary) -> str:
        """Generate human-readable variance analysis."""
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
    
    def export_session_budget(self, session_id: str, format: str = 'csv') -> str:
        """
        Export complete session budget in specified format.
        
        Args:
            session_id: Case identifier for the session
            format: Export format ('csv', 'json', 'html', 'text')
            
        Returns:
            Exported budget data as string
            
        Raises:
            ValueError: If session not found or invalid format
        """
        cost_summary = self.get_cost_summary(session_id)
        if not cost_summary:
            raise ValueError(f"Cost session not found for session_id: {session_id}")
        
        format_lower = format.lower()
        
        if format_lower == 'csv':
            return self.cost_exporter.export_cost_summary_csv(cost_summary)
        elif format_lower == 'json':
            return self.cost_exporter.export_cost_summary_json(cost_summary)
        elif format_lower == 'html':
            return self.cost_exporter.generate_budget_report_html(cost_summary)
        elif format_lower == 'text':
            return self.cost_exporter.generate_cost_report_text(cost_summary)
        else:
            raise ValueError(f"Unsupported export format: {format}. Supported formats: csv, json, html, text")
    
    def get_budget_insights(self, session_id: str) -> Dict[str, Any]:
        """
        Generate budget insights and recommendations for a session.
        
        Args:
            session_id: Case identifier for the session
            
        Returns:
            Dictionary containing budget analysis and insights
            
        Raises:
            ValueError: If session not found
        """
        cost_summary = self.get_cost_summary(session_id)
        if not cost_summary:
            raise ValueError(f"Cost session not found for session_id: {session_id}")
        
        return self.cost_exporter.create_budget_analysis(cost_summary)
    
    def export_multiple_sessions(
        self,
        session_ids: List[str],
        format: str = 'csv'
    ) -> str:
        """
        Export budget data for multiple sessions in a consolidated format.
        
        Args:
            session_ids: List of case identifiers to export
            format: Export format ('csv', 'json')
            
        Returns:
            Consolidated export data as string
            
        Raises:
            ValueError: If invalid format specified
        """
        if format.lower() == 'csv':
            return self._export_multiple_sessions_csv(session_ids)
        elif format.lower() == 'json':
            return self._export_multiple_sessions_json(session_ids)
        else:
            raise ValueError(f"Unsupported format for multiple sessions: {format}. Supported: csv, json")
    
    def get_session_budget_summary(self, session_id: str) -> Dict[str, Any]:
        """
        Get a simplified budget summary for quick reference.
        
        Args:
            session_id: Case identifier for the session
            
        Returns:
            Dictionary with summary budget information
            
        Raises:
            ValueError: If session not found
        """
        cost_summary = self.get_cost_summary(session_id)
        if not cost_summary:
            raise ValueError(f"Cost session not found for session_id: {session_id}")
        
        summary = {
            "case_id": cost_summary.case_id,
            "estimated_cost": float(cost_summary.cost_estimate.total_estimated_cost) if cost_summary.cost_estimate else None,
            "actual_cost": float(cost_summary.actual_costs.total_actual_cost) if cost_summary.actual_costs else None,
            "variance": float(cost_summary.cost_variance) if cost_summary.cost_variance else None,
            "variance_percentage": cost_summary.cost_variance_percentage,
            "status": self._classify_variance(cost_summary.cost_variance_percentage) if cost_summary.cost_variance_percentage is not None else "pending"
        }
        
        return summary
    
    def _export_multiple_sessions_csv(self, session_ids: List[str]) -> str:
        """Export multiple sessions to consolidated CSV format."""
        import csv
        import io
        
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Header
        writer.writerow([
            'Case ID', 'Estimated Cost', 'Actual Cost', 'Variance',
            'Variance %', 'Status', 'Document Costs', 'Media Costs'
        ])
        
        for session_id in session_ids:
            cost_summary = self.get_cost_summary(session_id)
            if not cost_summary:
                continue
            
            estimated = float(cost_summary.cost_estimate.total_estimated_cost) if cost_summary.cost_estimate else 0.0
            actual = float(cost_summary.actual_costs.total_actual_cost) if cost_summary.actual_costs else 0.0
            variance = float(cost_summary.cost_variance) if cost_summary.cost_variance else 0.0
            variance_pct = cost_summary.cost_variance_percentage or 0.0
            status = self._classify_variance(variance_pct) if cost_summary.cost_variance_percentage is not None else "pending"
            
            # Calculate document and media costs
            doc_costs = 0.0
            media_costs = 0.0
            if cost_summary.actual_costs:
                doc_costs = float(sum(cost.total_cost for cost in cost_summary.actual_costs.document_analysis_costs))
                media_costs = float(sum(cost.total_cost for cost in cost_summary.actual_costs.media_processing_costs))
            
            writer.writerow([
                session_id, f"${estimated:.4f}", f"${actual:.4f}", f"${variance:.4f}",
                f"{variance_pct:.2f}%", status, f"${doc_costs:.4f}", f"${media_costs:.4f}"
            ])
        
        return output.getvalue()
    
    def _export_multiple_sessions_json(self, session_ids: List[str]) -> str:
        """Export multiple sessions to consolidated JSON format."""
        sessions_data = []
        
        for session_id in session_ids:
            cost_summary = self.get_cost_summary(session_id)
            if not cost_summary:
                continue
            
            session_data = {
                "case_id": session_id,
                "budget_summary": self.get_session_budget_summary(session_id),
                "budget_insights": self.get_budget_insights(session_id)
            }
            sessions_data.append(session_data)
        
        consolidated_export = {
            "export_timestamp": datetime.now().isoformat(),
            "total_sessions": len(sessions_data),
            "sessions": sessions_data,
            "aggregate_statistics": self._calculate_aggregate_statistics(session_ids)
        }
        
        return json.dumps(consolidated_export, indent=2, default=str)
    
    def _calculate_aggregate_statistics(self, session_ids: List[str]) -> Dict[str, Any]:
        """Calculate aggregate statistics across multiple sessions."""
        total_estimated = Decimal('0.00')
        total_actual = Decimal('0.00')
        variance_list = []
        session_count = 0
        
        for session_id in session_ids:
            cost_summary = self.get_cost_summary(session_id)
            if not cost_summary:
                continue
            
            session_count += 1
            
            if cost_summary.cost_estimate:
                total_estimated += cost_summary.cost_estimate.total_estimated_cost
            if cost_summary.actual_costs:
                total_actual += cost_summary.actual_costs.total_actual_cost
            if cost_summary.cost_variance_percentage is not None:
                variance_list.append(cost_summary.cost_variance_percentage)
        
        return {
            "total_sessions_analyzed": session_count,
            "total_estimated_cost": float(total_estimated),
            "total_actual_cost": float(total_actual),
            "total_variance": float(total_actual - total_estimated),
            "average_variance_percentage": sum(variance_list) / len(variance_list) if variance_list else 0.0,
            "sessions_over_budget": len([v for v in variance_list if v > 0]),
            "sessions_under_budget": len([v for v in variance_list if v < 0]),
            "sessions_on_budget": len([v for v in variance_list if abs(v) <= 5])
        }