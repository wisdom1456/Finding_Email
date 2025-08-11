# Memory Bank Consolidation Plan

## 1. Overview

This document outlines the strategy for consolidating the project's fragmented documentation into a unified, canonical, and searchable knowledge base. The current state of documentation is spread across `docs/` and `memory-bank/`, with significant overlap and no clear structure.

The goal is to merge all existing markdown files into the six core `memory-bank/` documents, as defined in our project standards. This will create a single source of truth for all project knowledge, enhance searchability with front-matter metadata, and align the documentation with our new, clean codebase structure.

## 2. Inventory & Similarity Map

The first step is to inventory all `.md` files and map them to their corresponding canonical memory bank document.

| Source File | Canonical Destination | Merge Priority | Notes |
| :--- | :--- | :--- | :--- |
| `memory-bank/archive/README.md`| `projectbrief.md` | 1 | High-level project overview. |
| `memory-bank/archive/SYSTEM_PATTERNS.md`|`systemPatterns.md` | 1 | Core architectural patterns. |
| `memory-bank/archive/TECH_CONTEXT.md`| `techContext.md` | 1 | Core technical stack details. |
| `memory-bank/archive/PRODUCT_CONTEXT.md`|`productContext.md`| 1 | Business and user context. |
| `docs/COMPREHENSIVE_RISK_ASSESSMENT_REPORT.md` | `systemPatterns.md` | 2 | Crucial for understanding system vulnerabilities. |
| `docs/enhanced_file_validation.md`| `techContext.md` | 2 | Details a specific technical implementation. |
| `docs/FINAL_EFFICIENCY_REPORT.md`| `progress.md` | 2 | Provides a summary of work completed. |
| `docs/FORMATTING_LINTING_STANDARDS.md`| `techContext.md` | 2 | Defines core part of the technical standards. |
| `docs/CITATION_ENHANCEMENT_IMPLEMENTATION.md`|`activeContext.md` | 3 | Represents recent or ongoing work. |
| All other `.md` files in `docs/`| Review and merge as needed | 4 | Lower priority, but contain useful context. |

## 3. Content Merging & Refactoring Process

The consolidation will be executed in the following steps:

1.  **Create New Canonical Files**: Create the six fresh, empty memory bank files in the root of `memory-bank/`.
2.  **Merge Content**: Systematically open each source file from the inventory, copy its content, and paste it into the appropriate section of the destination canonical file.
3.  **Refactor and Summarize**: As content is merged, it will be refactored to:
    *   Eliminate redundancy.
    *   Standardize formatting (headings, lists, code blocks).
    *   Convert prose into concise bullet points where possible.
4.  **Add Front-Matter**: Each canonical file will receive a YAML front-matter block to improve searchability and provide context.

**Example Front-Matter for `techContext.md`:**

```yaml
---
title: "Technical Context"
last_updated: "2025-08-11"
owner: "Roo"
tags: ["python", "streamlit", "pydantic", "ruff", "pytest"]
---
```

## 4. Final Directory Structure

Upon completion, the documentation structure will be as follows:

```
finding-emails/
├── docs/                 # For future, auto-generated documentation ONLY
└── memory-bank/          # Canonical, hand-curated knowledge base
    ├── activeContext.md
    ├── productContext.md
    ├── projectbrief.md
    ├── progress.md
    ├── systemPatterns.md
    └── techContext.md
```

*   The `memory-bank/archive/` directory will be deleted.
*   The `docs/` directory will be cleaned of all hand-written markdown files, reserving it for any future auto-generation tools (e.g., Sphinx).

## 5. Validation

The consolidation will be considered successful when:

1.  All content from the inventoried source files has been merged into a canonical document.
2.  The old `memory-bank/archive/` and `docs/` markdown files have been deleted.
3.  Each of the six canonical memory bank files contains a valid YAML front-matter block.
