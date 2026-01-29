# Harvey AI Attorney Adoption Presentation

This directory contains all materials for the attorney adoption presentation.

## Files

1. **harvey_ai_attorney_adoption_source.js** — PptxGenJS script that generates the PowerPoint deck
2. **harvey_ai_attorney_adoption.pptx** — Generated PowerPoint presentation (created by running the script)
3. **speaker_notes.md** — Slide-by-slide talking points and objection handling
4. **screenshot_plan.md** — Exact screenshots required, mapped to slides and UI locations
5. **attorney_quickstart_onepager.md** — Login + 5-step workflow + best practices

## Installation

### Prerequisites

- Node.js 14+ installed

### Install Dependencies

```bash
# From the presentation directory
npm install pptxgenjs
```

Or install globally:

```bash
npm install -g pptxgenjs
```

## Usage

### Generate the PowerPoint Deck

```bash
# From the project root
node presentation/harvey_ai_attorney_adoption_source.js
```

This will generate `presentation/harvey_ai_attorney_adoption.pptx`.

### Add Screenshots

1. Review `screenshot_plan.md` for exact UI locations
2. Capture screenshots from the production environment
3. Open `harvey_ai_attorney_adoption.pptx` in PowerPoint
4. Replace placeholder rectangles on Slide 8 with actual screenshots
5. Verify screenshots match the in-app help documentation

### Review Speaker Notes

- Open `speaker_notes.md` for slide-by-slide talking points
- Review objection handling section before presentation
- Speaker notes are also embedded in the PowerPoint (View → Notes in PowerPoint)

### Distribute One-Pager

- Send `attorney_quickstart_onepager.md` to attorneys after the meeting
- Convert to PDF if preferred: use Markdown to PDF tool or print from browser

## Presentation Structure

**12 slides total:**

1. Title — Harvey AI
2. Why This Exists (Attorney Pain)
3. What Harvey AI Does (Plain English)
4. How It Fits Into Your Workflow
5. Quick Start (5 Steps)
6. Supported Document Formats
7. Findings Emails (Trust Builder)
8. Harvey AI Interface (Screenshots)
9. Quality, Accuracy, and Control
10. What's Rolling Out Now
11. Adoption Plan
12. Close (Action)

## Key Messaging

- **Tone:** Calm, confident, operational
- **Framing:** Removes busywork, not judgment
- **Trust Builders:** Verified citations, attorney review required, document-linked facts
- **Simplicity:** 5 steps, no training manual

## Post-Presentation Checklist

- [ ] Distribute user credentials to all attorneys
- [ ] Send attorney quickstart one-pager within 24 hours
- [ ] Schedule Wednesday Q&A session
- [ ] Set up feedback channel (Slack/email)
- [ ] Monitor first-week usage and address issues

---

**Version:** 1.0  
**Last Updated:** January 23, 2026  
**Prepared for:** Bernhardt Riley Attorney Adoption Meeting
