# Decision Log

This document records the key architectural and implementation decisions made throughout the project lifecycle.

## Architectural Decisions

### ADR-001: Streamlit Monolith over FastAPI Backend
- **Decision**: Use Streamlit-only architecture.
- **Rationale**: Simplified deployment, reduced complexity.
- **Consequences**: Single deployment unit, direct function calls.

### ADR-002: Service-Oriented Internal Design
- **Decision**: Modular services within monolith.
- **Rationale**: Maintainability without deployment complexity.
- **Consequences**: Clear boundaries, testable components.

### ADR-003: Performance Optimization Strategy
- **Decision**: Implement caching and concurrency.
- **Rationale**: 3-5x performance requirement.
- **Consequences**: 14.3x improvement achieved.

### ADR-004: Security-First Implementation
- **Decision**: Comprehensive security measures.
- **Rationale**: Legal document sensitivity.
- **Consequences**: PII protection, secure uploads.

### New Architecture: Prompt-Driven Multimodal Analysis (Vertex AI)
-   **Decision**: Migrate from legacy Google Cloud Video Intelligence API to Vertex AI with Gemini-2.5-flash.
-   **Rationale**: Leverage powerful multimodal capabilities to extract richer, more nuanced insights from video evidence.
-   **Consequences**: Shift from structured, single-purpose API calls to a flexible, prompt-driven system.

### AUTHENTIC Attorney Style
- **Decision**: Implement the direct, professional tone that matches real attorney examples.
- **Rationale**: Align email generator with real attorney communications.
- **Consequences**: Disable CLIENT_CLARITY_ADVISOR transformations and align all prompts with AUTHENTIC style.

## Implementation Decisions

### Ruff Formatting & Linting
- **Decision**: Use Ruff as the primary Python linter and formatter.
- **Rationale**: Faster performance and comprehensive rule coverage in a single tool.
- **Consequences**: Replaced Black, isort, and Flake8.

### Google Cloud Deployment
- **Decision**: Deploy to Google Cloud Container Registry (`gcr.io/brflorida/legal-portal`) using an automated CI/CD pipeline.
- **Rationale**: Automated, scalable, and secure deployment.
- **Consequences**: New GCP workflow, enhanced Dockerfile, and updated CI/CD integration.

### Citation Enhancement
- **Decision**: Implement enhanced citation tracking for the Findings Email generation system.
- **Rationale**: Ensure all factual statements in generated findings letters are traceable to their source documents.
- **Consequences**: New `CitationTrackingService`, enhanced email generation, and updated appendix template.

### Enhanced File Validation
- **Decision**: Implement robust file validation that goes beyond basic extension checking.
- **Rationale**: Prevent empty, corrupted, or mismatched files from entering the processing pipeline.
- **Consequences**: Magic number validation, enhanced empty file detection, and corruption detection for DOCX and PDF files.