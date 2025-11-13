# Documentation Similarity Map

This document provides a comprehensive analysis of the project's documentation, outlining the relationships between files and providing recommendations for consolidation.

| File Path | Key Topics / Purpose | Relationship / Overlap | Recommendation |
| :--- | :--- | :--- | :--- |
| **`docs/` Directory** | | | |
| `docs/ARCHITECTURE.md` | System architecture, design patterns, data flow | Foundational document. Overlaps with `memory-bank/systemPatterns.md`. | **Keep as Canonical** |
| `docs/AUTHENTIC_ATTORNEY_IMPLEMENTATION_PLAN.md` | Plan to align email generator with attorney communication styles. | Specific implementation plan. Conflicts with `CLIENT_CLARITY_ADVISOR_IMPLEMENTATION.md`. | **Archive** |
| `docs/CITATION_ENHANCEMENT_IMPLEMENTATION.md` | Details the implementation of citation tracking in findings letters. | Standalone feature documentation. | **Keep as Canonical** |
| `docs/CLIENT_CLARITY_ADVISOR_IMPLEMENTATION.md` | Implementation of a client-centric communication framework. | Conflicts with `AUTHENTIC_ATTORNEY_IMPLEMENTATION_PLAN.md`. | **Archive** |
| `docs/COMPREHENSIVE_RISK_ASSESSMENT_REPORT.md` | Risk analysis of the Streamlit/FastAPI to unified Streamlit-Python refactor. | Supersedes initial risk assessments. | **Keep as Canonical** |
| `docs/COST_TRACKING_TEST_REPORT.md` | Test report for the cost tracking system. | Standalone test report. | **Keep as Canonical** |
| `docs/enhanced_file_validation.md` | Documentation for the enhanced file validation system. | Addresses a finding from `FINAL_EFFICIENCY_REPORT.md`. | **Keep as Canonical** |
| `docs/FINAL_ARCHITECTURAL_REFINEMENT_PLAN.md`| Plan to shift from inference-based model to a deterministic, configuration-driven approach. | Specific refinement plan. | **Archive** |
| `docs/FINAL_EFFICIENCY_REPORT.md` | Consolidated findings from code path efficiency, assumption auditing, and performance analysis. | Summarizes multiple analyses. | **Keep as Canonical** |
| `docs/FINAL_VALIDATION_REPORT.md` | Complete validation results for the Streamlit/FastAPI to unified Streamlit-Python refactor. | Supersedes other validation reports. | **Keep as Canonical** |
| `docs/FORMATTING_LINTING_STANDARDS.md` | Outlines formatting and linting standards using `Ruff`. | Technical standard document. | **Keep as Canonical** |
| `docs/GOOGLE_CLOUD_DEPLOYMENT.md` | Guide for deploying the application to Google Cloud. | Foundational deployment document. | **Keep as Canonical** |
| `docs/master_schema.md` | Defines the comprehensive JSON schema for the legal findings letter. | Overlaps with `FINAL_ARCHITECTURAL_REFINEMENT_PLAN.md`. | **Merge into `docs/ARCHITECTURE.md`** |
| `docs/ORCHESTRATOR_EMAIL_GENERATOR_FIX.md` | Plan to fix the email generator's prompting system. | Specific fix plan. | **Archive** |
| `docs/PERFORMANCE_VALIDATION_REPORT.md` | Validation report for performance and error handling. | Partially superseded by `FINAL_VALIDATION_REPORT.md`. | **Merge into `docs/PERFORMANCE.md`** |
| `docs/PERFORMANCE.md` | Details performance optimization strategies and benchmarks. | Foundational performance document. | **Keep as Canonical** |
| `docs/PROMPT_IMPROVEMENT_PLAN.md` | Plan to improve prompts in `universal_legal_config.yaml`. | Specific improvement plan. | **Archive** |
| `docs/refactoring_plan.md` | Plan to refactor redundant logic in the test suite and backend services. | Specific refactoring plan. | **Archive** |
| `docs/RUFF_CLEANUP_PLAN.md` | Action plan for resolving code quality issues identified by `Ruff`. | Specific cleanup plan. | **Archive** |
| `docs/SECURITY_AUDIT_REPORT.md` | Report of known vulnerabilities from `pip-audit`. | Overlapped by `docs/SECURITY.md`. | **Merge into `docs/SECURITY.md`** |
| `docs/SECURITY_IMPROVEMENTS.md` | Documents security improvements for blind exception handling. | Partial overlap with `docs/SECURITY.md`. | **Merge into `docs/SECURITY.md`** |
| `docs/SECURITY.md` | Details comprehensive security measures for the application. | Foundational security document. | **Keep as Canonical** |
| `docs/VALIDATION_CHECKLIST.md` | Checklist for validating the consolidated Streamlit-Python application. | Superseded by `FINAL_VALIDATION_REPORT.md`. | **Archive** |
| **`memory-bank/` Directory** | | | |
| `memory-bank/activeContext.md` | High-level summary of current project state, recent changes, and active decisions. | Temporal, reflects a point in time. | **Archive** |
| `memory-bank/client_clarity_advisor_framework.md` | Details the client-centric communication framework. | Superseded by `docs/CLIENT_CLARITY_ADVISOR_IMPLEMENTATION.md`. | **Archive** |
| `memory-bank/criminal_video_processing.md` | Documentation for criminal law video processing features. | Standalone feature documentation. | **Merge into `docs/ARCHITECTURE.md`** |
| `memory-bank/debugging_lessons_learned.md` | Lessons learned from debugging critical errors. | Useful for historical context. | **Archive** |
| `memory-bank/optimization_recommendations.md` | Recommendations for performance optimization. | Superseded by `docs/PERFORMANCE.md`. | **Archive** |
| `memory-bank/performance_bottleneck_report.md` | Report on performance bottlenecks. | Superseded by `docs/PERFORMANCE.md`. | **Archive** |
| `memory-bank/productContext.md` | Rationale for the project, user needs, and UX objectives. | Foundational context. Should be part of the canonical docs. | **Merge into `docs/README.md`** |
| `memory-bank/progress.md` | Log of completed tasks and project evolution. | Temporal progress log. | **Archive** |
| `memory-bank/projectbrief.md` | Project scope, goals, requirements, and success criteria. | Foundational context. Should be part of the canonical docs. | **Merge into `docs/README.md`** |
| `memory-bank/systemPatterns.md` | Overview of system architecture and design patterns. | Superseded by `docs/ARCHITECTURE.md`. | **Archive** |
| `memory-bank/techContext.md` | Details on the technology stack, development environment, and deployment. | Superseded by `docs/ARCHITECTURE.md` and `docs/GOOGLE_CLOUD_DEPLOYMENT.md`. | **Archive** |
| `memory-bank/vertex_ai_video_analysis.md` | Guide for integrating Vertex AI video analysis. | Specific feature documentation. | **Merge into `docs/ARCHITECTURE.md`** |
| `memory-bank/video_preservation_plan.md` | Technical plan to resolve video processing token limit violations. | Specific implementation plan. | **Archive** |
| `memory-bank/archive/*` | All files in the archive directory. | Already archived. | **Keep as Archive** |