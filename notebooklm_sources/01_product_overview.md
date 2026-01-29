# Product Overview

## What Is This Tool?

The Legal Document Analysis Portal, referred to internally as Harvey AI, is a production-ready legal technology system deployed at Bernhardt Riley. It analyzes legal documents using artificial intelligence and generates professional findings emails with verified citations.

## Plain-English Description

This system processes case documents uploaded by attorneys and produces structured legal analysis. It extracts text from multiple document formats, identifies relevant facts and timelines, analyzes potential legal issues, and generates attorney-style findings emails. Each fact in the generated output is cited to its source document, enabling attorneys to verify any statement against the original material.

## Problems It Solves for Attorneys

### Time Efficiency

Manual document review for intake cases requires attorneys to read through multiple PDFs, emails, contracts, and supporting documents to extract basic facts. This work is necessary but does not require attorney-level judgment. The portal automates fact extraction and initial document review, reducing intake time from hours to minutes.

### Consistency and Structure

Findings letters follow predictable structures, but creating them from scratch is time-consuming. The portal generates professionally formatted letters with proper structure, citations, and legal analysis, giving attorneys an 80% complete first draft.

### Citation Accuracy

Manual citation of facts across multiple documents is error-prone. Missing a citation or citing the wrong source damages client trust and creates liability risk. The portal automatically links every fact to its source document, making verification straightforward.

### Hallucination Prevention

AI systems sometimes generate false legal citations. The portal validates all statute citations against verified legal corpus for Florida (51 statutes) and New Mexico (42 statutes), preventing the AI from inventing non-existent legal references.

## What It Does

The portal performs these specific functions:

**Document Processing**
- Accepts PDF, DOCX, DOC, TXT, CSV, JPG, PNG, EML, and HTML files
- Extracts text from digital documents
- Performs OCR on scanned documents and images using GPT-4o Vision
- Supports batch uploads up to 50MB per file

**AI Analysis**
- Identifies key facts from uploaded documents
- Constructs timelines from extracted information
- Identifies the most likely legal issue based on intake form content
- Validates statute citations against verified legal corpus
- Generates comprehensive case analysis with structured data

**Letter Generation**
- Produces attorney-style findings emails
- Cites every fact to its source document using clean filename references
- Formats output for professional client delivery
- Provides editable HTML output for further revision

**Practice Management Integration**
- Connects to Clio via OAuth
- Imports matters, documents, and communications directly from Clio
- Maintains case reference numbers for workflow continuity

## What It Does NOT Do

The portal does not:

- Replace attorney judgment or decision-making
- Send communications directly to clients
- Provide legal advice autonomously
- Handle federal claims, criminal law, immigration, bankruptcy, or patent/trademark matters
- Process cases outside Florida and New Mexico civil litigation
- Make final decisions about case strategy or client recommendations

## Key Guardrails

### Attorney Review Required

The system is designed for attorney review before any client delivery. Generated letters are drafts, not final work product. Attorneys remain responsible for verifying facts, checking citations, and approving all output.

### Jurisdiction Limitations

The system is optimized exclusively for Florida and New Mexico civil litigation matters. Attempts to use it for federal claims, criminal cases, or matters outside these jurisdictions will produce unreliable results.

### Citation Verification

While the system cites facts to source documents, attorneys must verify that citations are accurate and that extracted facts match the original document context.

### Quality Control

Document extraction quality varies based on scan quality and file format. The Verification Hub provides tools to identify and fix document issues before analysis, but attorney oversight of document quality is required.

## Positioning

This is acceleration software, not automation software. It removes low-value document review work so attorneys can focus on strategy, client communication, and legal judgment. Think of it as a junior associate that handles initial document review and drafting, with all final decisions remaining with the attorney.

The system is production-ready and actively used at Bernhardt Riley. It is not a prototype, demo, or proof of concept.

## Supported Jurisdictions and Practice Areas

### Florida Civil Litigation

The portal supports these Florida practice areas with verified statute coverage:

**Consumer Protection and Business Misconduct**
- Contract disputes (UCC Chapters 671-672)
- Consumer protection violations (FDUTPA - Chapter 501 Part II)
- Business organization disputes (Chapter 605 LLC, Chapter 607 Corporations)

**Real Estate and Property Disputes**
- Landlord-tenant disputes (Chapter 83)
- Foreclosure defense (Chapter 702)
- Property damage and insurance claims (Chapter 627)
- Construction defects (Chapter 558)
- Mechanic's liens (Chapter 713)

**Civil Litigation and Administrative Law**
- Statutes of limitation (Chapter 95)
- Administrative procedure matters (Chapter 120)
- Attorney fees and sanctions (Chapter 57)

**Selective Personal Injury**
- Motor vehicle accidents (Chapter 316 traffic law)
- Limited medical malpractice matters (Chapter 766)

### New Mexico Civil Litigation

The portal supports these New Mexico practice areas with verified statute coverage:

**Consumer Protection**
- Unfair Practices Act (Chapter 57, Article 12)

**Landlord-Tenant**
- Uniform Owner-Resident Relations Act (Chapter 47, Article 8)

**Construction and Liens**
- Construction indemnification (Chapter 56, Article 7)
- Mechanic's liens (Chapter 48, Article 2)

**Real Estate and Foreclosure**
- Mortgages and redemption (Chapter 48, Article 7)

**Insurance and Torts**
- Unfair claims practices (Chapter 59A, Article 16)
- Several liability (Chapter 41, Article 3A)

**Civil Procedure**
- Statutes of limitation (Chapter 37, Article 1)
- Civil procedure rules (NMRA)

## Technical Foundation

The system uses multiple specialized AI models for different tasks:

- GPT-4o Vision for OCR and image text extraction
- GPT-4o-mini for fast legal issue identification
- GPT-4.1 for comprehensive document analysis
- GPT-5.2 for professional letter generation with complex reasoning

Document processing uses PyMuPDF for PDFs, python-docx for Word documents, and Pillow for image handling. The system is deployed on Vercel with a SvelteKit frontend and FastAPI backend, using Supabase for authentication and data storage.

## Version and Status

**System Name (Internal):** Legal Document Analysis Portal  
**System Name (Public):** Harvey AI  
**Version:** 3.1.0  
**Status:** Production Ready  
**Last Updated:** January 23, 2026  
**Deployment:** Live at Bernhardt Riley
