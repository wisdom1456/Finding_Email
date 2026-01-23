# Adoption and Rollout

## What's Happening Now

This document describes the current state of Harvey AI deployment at Bernhardt Riley, the features available in production, and the adoption plan for attorney onboarding.

## Current Production Status

### System Status

**Deployment:** Live in production  
**Availability:** All attorneys can access the system immediately  
**Environment:** Deployed on Vercel with Supabase backend  
**Version:** 3.1.0 (Production Ready)  
**Last Updated:** January 23, 2026

This is not a pilot, beta test, or proof of concept. This is production software actively deployed and maintained.

## Features Live in Production

### Core Functionality

**Case Management**
- Create and organize cases by client matter
- Add case reference numbers for practice management integration
- Track case status through workflow stages (pending, processing, completed, error)
- View case history and analysis results

**Document Processing**
- Multi-format upload: PDF, DOCX, DOC, TXT, CSV, JPG, PNG, EML, HTML
- Batch uploads supporting multiple files simultaneously
- OCR processing for scanned documents using GPT-4o Vision
- Document quality indicators and status tracking
- Maximum file size: 50MB per document

**Verification Hub**
- Triage documents by status (Critical, Needs Attention, Ready, Duplicates, Excluded)
- Bulk OCR processing for multiple documents
- Individual document retry for failed extractions
- Document preview and quality verification
- Duplicate detection and exclusion

**AI-Powered Analysis**
- Multi-stage processing: extraction, fact identification, timeline construction, legal analysis, letter generation
- Auto-fill legal issue identification based on intake form content
- Statute citation validation against verified Florida (51 statutes) and New Mexico (42 statutes) legal corpus
- Multi-model AI architecture: GPT-4o Vision, GPT-4o-mini, GPT-4.1, GPT-5.2
- Real-time progress updates via Server-Sent Events (SSE)

**Findings Letter Generation**
- Attorney-style professional formatting
- Document-cited facts with clean filename references
- Editable output with HTML export
- Consistent structure across all cases
- Client-ready formatting

**Clio Integration**
- OAuth connection to Clio accounts
- Matter search by client name or matter number
- Automatic import of matter details, documents, communications, and notes
- Connection status indicator
- Persistent authorization

**Help and Documentation**
- In-app help documentation with step-by-step guides
- FAQ section addressing common questions
- Feature descriptions and best practices
- Support contact information

### Supported Jurisdictions

**Florida**
- 51 verified statutes covering:
  - Consumer protection (FDUTPA, UCC)
  - Landlord-tenant disputes
  - Foreclosure defense
  - Construction defects and mechanic's liens
  - Property damage and insurance claims
  - Personal injury (motor vehicle, premises liability)
  - Administrative law and civil procedure

**New Mexico**
- 42 verified statutes covering:
  - Consumer protection (Unfair Practices Act)
  - Landlord-tenant (Uniform Owner-Resident Relations Act)
  - Construction and mechanic's liens
  - Real estate and foreclosure
  - Insurance and torts
  - Civil procedure and statutes of limitation
- 8 verified procedural rules (NMRA)

## What Is NOT Part of This Release

### Explicitly Excluded

These features and jurisdictions are not supported in the current production system:

**Jurisdictions:**
- Federal claims or federal court matters
- States other than Florida and New Mexico
- International law

**Practice Areas:**
- Criminal law
- Immigration law
- Bankruptcy (federal jurisdiction)
- Patent and trademark law (federal jurisdiction)
- Family law
- Tax law

**Features:**
- Automatic client email delivery
- Integration with practice management systems other than Clio
- Multi-user collaboration on cases
- Advanced analytics dashboard
- Mobile app
- Voice input or transcription

**Technical Capabilities:**
- Processing files larger than 50MB
- Batch case creation
- API access for third-party integrations
- Custom AI model fine-tuning

### Why These Limitations Exist

The system is optimized for Florida and New Mexico civil litigation because:
- Legal corpus validation is complete for these jurisdictions
- Practice area coverage matches Bernhardt Riley's core business
- Statute citation accuracy requires verified corpus, which is resource-intensive to build for additional jurisdictions

Federal claims, criminal law, and specialized practice areas are excluded because:
- Legal corpus validation has not been completed for these areas
- Case complexity and risk profile require different AI approaches
- Firm practice does not focus on these areas

## Adoption Plan

### Timeline

**Today (Meeting Date):**
- Presentation delivered to all attorneys
- User accounts created for all attorneys
- Login credentials distributed
- System access verified

**This Week:**
- One-page attorney quickstart guide distributed via email
- In-app help documentation reviewed
- Attorneys create test cases and explore the interface
- Initial usage and feedback collection begins

**Next Wednesday (Q&A Session Date):**
- Live Q&A session scheduled
- Attorneys bring questions, issues, and feedback
- Technical support and training provided
- Common issues addressed in group setting

**Ongoing:**
- Feedback loop established for bug reports and feature requests
- System actively maintained and updated based on attorney input
- Technical support available through designated channels

### Account Setup

All accounts are created during the initial meeting.

**What Attorneys Receive:**
- Login credentials for Harvey AI portal
- Access to in-app help documentation
- Link to attorney quickstart one-pager
- Contact information for technical support

**First Login:**
1. Navigate to the portal URL (provided during meeting)
2. Log in with provided credentials
3. Complete any required profile setup
4. Review in-app help documentation
5. Create a test case to familiarize with the interface

### Training Resources

**One-Page Quickstart Guide:**
Distributed via email within 24 hours of the meeting. Covers:
- Five-step workflow
- Supported document formats and jurisdictions
- Best practices for document uploads
- FAQ for common questions

**In-App Help Documentation:**
Available via "Help" button in navigation. Includes:
- Getting Started guide with step-by-step workflow
- Features and Guides section covering case management, document processing, Clio integration, AI analysis, and letter generation
- FAQ section addressing common questions
- Support contact information

**One-Pager Quick Reference:**
Printable two-page reference guide for desk or office posting. Includes workflow steps, supported formats, best practices, and key reminders.

### Q&A Session

**Format:** Live meeting (in-person or video conference)  
**Duration:** 60 minutes  
**Date:** Next Wednesday (specific date to be announced)

**Agenda:**
- Brief system overview recap (5 minutes)
- Open Q&A for any questions (30 minutes)
- Live demonstration of common workflows (15 minutes)
- Troubleshooting common issues (10 minutes)

**What to Bring:**
- Questions about features or workflow
- Issues encountered during initial usage
- Feature requests or improvement suggestions
- Specific use cases for guidance

### Feedback Loop

**Reporting Issues:**
Attorneys report bugs, errors, or technical issues through:
- Direct contact with system administrator
- IT support team ticketing system
- Feedback channel (Slack, email, or shared document)

**What to Report:**
- Analysis failures or errors
- Document processing issues
- Incorrect or unreliable outputs
- User interface problems
- Performance issues or slowdowns

**Feature Requests:**
Attorneys suggest improvements or new features through the same feedback channels. Development team reviews and prioritizes requests based on:
- Number of attorneys requesting the feature
- Impact on workflow efficiency
- Technical feasibility
- Alignment with firm priorities

**Response Time:**
- Critical bugs (system unavailable): Same business day
- High-priority issues (analysis failures): Within 24 hours
- Feature requests and improvements: Reviewed in monthly development cycle

## Expectations for Adoption

### What Success Looks Like

**Short-Term (First Month):**
- All attorneys log in and create at least one test case
- 50% of attorneys use the system for at least one real client matter
- Common issues identified and resolved through feedback loop
- Attorneys report time savings on document review and intake

**Medium-Term (Three Months):**
- 80% of eligible client matters processed through Harvey AI
- Average intake time reduced by 50% compared to manual process
- Attorneys routinely use Verification Hub for document quality management
- Findings letters consistently generated for client delivery

**Long-Term (Six Months):**
- Harvey AI becomes standard workflow for all Florida and New Mexico civil litigation intake
- Attorneys provide feedback driving feature improvements
- System accuracy and reliability demonstrated through consistent usage
- Firm productivity metrics show measurable time savings

### What Is Required of Attorneys

**Minimum Commitment:**
- Log in and create at least one test case during the first week
- Review in-app help documentation and quickstart guide
- Attend Q&A session (or review recording if unable to attend)
- Provide feedback on issues and usability

**Recommended Usage:**
- Use Harvey AI for all new Florida and New Mexico civil litigation intake cases
- Upload documents within 24 hours of client consultation
- Run analysis and review findings letters within 48 hours of upload
- Report any issues or inaccuracies through feedback loop

**Professional Responsibility:**
- Always review AI-generated outputs before client delivery
- Verify citations and facts against source documents
- Use attorney judgment for all final case decisions
- Maintain client confidentiality and data security standards

### Support Channels

**Technical Support:**
Contact system administrator or IT support team for:
- Login issues or account problems
- System errors or bugs
- Document processing failures
- Performance issues

**Usage Guidance:**
Contact practice administrator or attend Q&A session for:
- Workflow questions
- Best practices for document uploads
- Feature usage and capabilities
- Case-specific guidance

**Feedback and Feature Requests:**
Submit through feedback channel (Slack, email, or shared document).

## Active Maintenance

The system is actively maintained with:
- Regular updates based on attorney feedback
- Bug fixes applied within 24-48 hours of identification
- Security patches applied as needed
- Feature improvements deployed on monthly cycle

**No Downtime Expected:**
Updates are deployed to production with zero-downtime deployment. Attorneys will not experience interruptions during system updates.

## Key Messages

### This Is Live

Harvey AI is production software available right now. Attorneys can start using it today for real client matters.

### No Learning Curve

Five-step workflow. No training manual required. The interface is designed for attorneys, not engineers.

### Attorney Remains Responsible

This system accelerates document review and drafting. It does not replace attorney judgment. All outputs require attorney review and approval before client delivery.

### Support Is Available

Technical support, usage guidance, and feedback channels are available. Attorneys are not expected to troubleshoot issues independently.

### Continuous Improvement

The system improves based on attorney feedback. Bug reports and feature requests are reviewed and prioritized regularly.

## Immediate Next Steps

After this presentation:

1. **Verify your account** — Log in to confirm your credentials work
2. **Review the quickstart guide** — Read the one-pager distributed via email
3. **Create a test case** — Upload sample documents and run a test analysis
4. **Identify a real case** — Plan to use Harvey AI on your next eligible intake
5. **Mark your calendar** — Attend the Q&A session next Wednesday

Harvey AI is live. Use it on your next case.
