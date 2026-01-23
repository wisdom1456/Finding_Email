/**
 * Harvey AI Attorney Adoption Presentation
 * Bernhardt Riley Brand Guidelines - STRICT MODE
 * 
 * Generate PowerPoint deck using PptxGenJS
 * Run: node presentation/harvey_ai_attorney_adoption_source.js
 */

const PptxGenJS = require('pptxgenjs');

// Initialize presentation
const pres = new PptxGenJS();

// Configure slide master (16:9)
pres.layout = 'LAYOUT_16x9';
pres.author = 'Bernhardt Riley';
pres.company = 'Bernhardt Riley';
pres.subject = 'Harvey AI Attorney Adoption';
pres.title = 'Harvey AI: Legal Document Analysis Portal';

// Bernhardt Riley Brand Colors (EXACT)
const BRAND = {
  contrast: '181A31',      // Dark blue - headings
  contrast2: '39428E',     // Medium blue - body text
  accent: '5AB7A3',        // Teal - accents
  accentHover: '49998A',   // Darker teal - secondary
  base: 'FFFFFF',          // White - background
  lightBg: 'F7F9FB',       // Very light tint
  footerBg: 'EEF2F6'       // Footer band
};

// Typography (with fallbacks)
const FONTS = {
  heading: 'Raleway',      // Fallback: Calibri
  body: 'Montserrat'       // Fallback: Calibri
};

// Use Calibri as fallback if Raleway/Montserrat unavailable
const HEAD_FONT = 'Calibri'; // Changed to Calibri for reliability
const BODY_FONT = 'Calibri'; // Changed to Calibri for reliability

// ============================================
// SLIDE 1: TITLE SLIDE (LAYOUT A)
// ============================================
let slide = pres.addSlide();
slide.background = { color: BRAND.base };

// Title
slide.addText('Harvey AI', {
  x: 1.0,
  y: 2.7,
  w: 11.33,
  h: 0.8,
  fontFace: HEAD_FONT,
  fontSize: 44,
  bold: true,
  color: BRAND.contrast,
  align: 'center',
  valign: 'middle'
});

// Subtitle
slide.addText('Legal Document Analysis Portal', {
  x: 1.0,
  y: 3.7,
  w: 11.33,
  h: 0.5,
  fontFace: BODY_FONT,
  fontSize: 22,
  color: BRAND.contrast2,
  align: 'center',
  valign: 'middle'
});

slide.addText('Attorney Adoption Presentation\nBernhardt Riley | January 2026', {
  x: 1.0,
  y: 4.4,
  w: 11.33,
  h: 0.8,
  fontFace: BODY_FONT,
  fontSize: 18,
  color: BRAND.contrast2,
  align: 'center',
  valign: 'middle'
});

slide.addNotes(
  'This is not a prototype or a beta test. This is production-ready software (Version 3.1.0) deployed live today to accelerate your document review and drafting process.'
);

// ============================================
// SLIDE 2: THE PROBLEM (LAYOUT C)
// ============================================
slide = pres.addSlide();
slide.background = { color: BRAND.base };

// Title
slide.addText('The Problem: Inefficient Intake', {
  x: 1.0,
  y: 0.8,
  w: 11.33,
  h: 1.2,
  fontFace: HEAD_FONT,
  fontSize: 36,
  bold: true,
  color: BRAND.contrast,
  align: 'left',
  valign: 'middle'
});

// Bullets
slide.addText([
  { text: 'Manual document review requires hours to extract basic facts', options: { bullet: true, breakLine: false } },
  { text: 'Initial review consumes attorney time without requiring senior judgment', options: { bullet: true, breakLine: false } },
  { text: 'Creating findings letters from scratch leads to inconsistencies', options: { bullet: true, breakLine: false } },
  { text: 'Manual citation is error-prone and creates liability risk', options: { bullet: true, breakLine: false } }
], {
  x: 1.5,
  y: 2.1,
  w: 10.3,
  h: 4.7,
  fontFace: BODY_FONT,
  fontSize: 20,
  color: BRAND.contrast2,
  align: 'left',
  lineSpacing: 32
});

// Emphasis Footer (LAYOUT E)
slide.addShape(pres.ShapeType.rect, {
  x: 0.0,
  y: 6.3,
  w: 13.33,
  h: 1.2,
  fill: { color: BRAND.footerBg },
  line: { type: 'none' }
});

slide.addText('This tool removes the busywork, not your judgment.', {
  x: 1.0,
  y: 6.55,
  w: 11.33,
  h: 0.6,
  fontFace: HEAD_FONT,
  fontSize: 22,
  bold: true,
  color: BRAND.contrast,
  align: 'center',
  valign: 'middle'
});

slide.addNotes(
  'We are solving for the bottleneck in case intake. The goal is to remove the "busywork" of reading 50 pages just to understand the basic timeline, allowing you to focus on strategy immediately.'
);

// ============================================
// SLIDE 3: THE SOLUTION (LAYOUT C)
// ============================================
slide = pres.addSlide();
slide.background = { color: BRAND.base };

slide.addText('The Solution: Harvey AI', {
  x: 1.0,
  y: 0.8,
  w: 11.33,
  h: 1.2,
  fontFace: HEAD_FONT,
  fontSize: 36,
  bold: true,
  color: BRAND.contrast,
  align: 'left',
  valign: 'middle'
});

slide.addText([
  { text: 'Production software that analyzes documents and generates findings letters', options: { bullet: true, breakLine: false } },
  { text: 'Extracts text, identifies facts, and constructs timelines automatically', options: { bullet: true, breakLine: false } },
  { text: 'Validates statute citations against verified legal corpus', options: { bullet: true, breakLine: false } },
  { text: 'Every fact cited directly to its source document', options: { bullet: true, breakLine: false } }
], {
  x: 1.5,
  y: 2.1,
  w: 10.3,
  h: 4.7,
  fontFace: BODY_FONT,
  fontSize: 20,
  color: BRAND.contrast2,
  align: 'left',
  lineSpacing: 32
});

// Emphasis Footer
slide.addShape(pres.ShapeType.rect, {
  x: 0.0,
  y: 6.3,
  w: 13.33,
  h: 1.2,
  fill: { color: BRAND.accent },
  line: { type: 'none' },
  transparency: 10
});

slide.addText('Think of this as a tireless junior associate.', {
  x: 1.0,
  y: 6.55,
  w: 11.33,
  h: 0.6,
  fontFace: HEAD_FONT,
  fontSize: 22,
  bold: true,
  color: BRAND.contrast,
  align: 'center',
  valign: 'middle'
});

slide.addNotes(
  'Think of this tool as a tireless junior associate. It handles the initial review and drafting, giving you an 80% complete draft. You remain responsible for the final review and approval.'
);

// ============================================
// SLIDE 4: THE WORKFLOW (LAYOUT C - CUSTOM)
// ============================================
slide = pres.addSlide();
slide.background = { color: BRAND.base };

slide.addText('The Attorney Workflow', {
  x: 1.0,
  y: 0.8,
  w: 11.33,
  h: 1.2,
  fontFace: HEAD_FONT,
  fontSize: 36,
  bold: true,
  color: BRAND.contrast,
  align: 'left',
  valign: 'middle'
});

const steps = [
  'Create Case: Initialize case record with client name and reference number',
  'Upload Documents: Drag-and-drop files or import directly from Clio',
  'Run Analysis: AI processes documents (1–8 minutes)',
  'Review Results: Verify findings letter, timeline, and document summaries',
  'Export: Edit letter in-browser and export to HTML/Word'
];

let yPos = 2.1;
steps.forEach((step, idx) => {
  // Number circle
  slide.addShape(pres.ShapeType.ellipse, {
    x: 1.2,
    y: yPos - 0.05,
    w: 0.4,
    h: 0.4,
    fill: { color: BRAND.accent }
  });
  
  slide.addText(String(idx + 1), {
    x: 1.2,
    y: yPos - 0.05,
    w: 0.4,
    h: 0.4,
    fontFace: HEAD_FONT,
    fontSize: 18,
    bold: true,
    color: BRAND.base,
    align: 'center',
    valign: 'middle'
  });
  
  // Step text
  slide.addText(step, {
    x: 1.8,
    y: yPos,
    w: 9.5,
    h: 0.5,
    fontFace: BODY_FONT,
    fontSize: 18,
    color: BRAND.contrast2,
    align: 'left',
    valign: 'top'
  });
  
  yPos += 0.75;
});

slide.addNotes(
  'The workflow is designed to be simple. There is no complex manual to study. You can run your first analysis in less than 5 minutes.'
);

// ============================================
// SLIDE 5: SUPPORTED DOCUMENTS (LAYOUT C)
// ============================================
slide = pres.addSlide();
slide.background = { color: BRAND.base };

slide.addText('Supported Documents & Intake', {
  x: 1.0,
  y: 0.8,
  w: 11.33,
  h: 1.2,
  fontFace: HEAD_FONT,
  fontSize: 36,
  bold: true,
  color: BRAND.contrast,
  align: 'left',
  valign: 'middle'
});

slide.addText([
  { text: 'Broad format support: PDF, DOCX, TXT, CSV, JPG, PNG, EML, HTML', options: { bullet: true, breakLine: false } },
  { text: 'Integrated OCR processes scanned documents using GPT-4o Vision', options: { bullet: true, breakLine: false } },
  { text: 'Clio integration imports matters and documents directly', options: { bullet: true, breakLine: false } },
  { text: 'Verification Hub fixes or excludes poor-quality documents', options: { bullet: true, breakLine: false } }
], {
  x: 1.5,
  y: 2.1,
  w: 10.3,
  h: 4.7,
  fontFace: BODY_FONT,
  fontSize: 20,
  color: BRAND.contrast2,
  align: 'left',
  lineSpacing: 32
});

// Emphasis Footer
slide.addShape(pres.ShapeType.rect, {
  x: 0.0,
  y: 6.3,
  w: 13.33,
  h: 1.2,
  fill: { color: BRAND.footerBg },
  line: { type: 'none' }
});

slide.addText('Upload core documents first: intake forms, police reports, contracts', {
  x: 1.0,
  y: 6.55,
  w: 11.33,
  h: 0.6,
  fontFace: BODY_FONT,
  fontSize: 20,
  bold: true,
  color: BRAND.contrast,
  align: 'center',
  valign: 'middle'
});

slide.addNotes(
  'For best results, upload core documents first: intake forms, police reports, contracts, and key correspondence. The system handles files up to 50MB each.'
);

// ============================================
// SLIDE 6: FINDINGS LETTERS (LAYOUT C)
// ============================================
slide = pres.addSlide();
slide.background = { color: BRAND.base };

slide.addText('Findings Letters & Citations', {
  x: 1.0,
  y: 0.8,
  w: 11.33,
  h: 1.2,
  fontFace: HEAD_FONT,
  fontSize: 36,
  bold: true,
  color: BRAND.contrast,
  align: 'left',
  valign: 'middle'
});

slide.addText([
  { text: 'Professional format: Structured, attorney-style letters', options: { bullet: true, breakLine: false } },
  { text: 'Source linking: Every fact includes inline citation (e.g., [Client_Intake.pdf])', options: { bullet: true, breakLine: false } },
  { text: 'Instant verification: Click any citation to view the original source', options: { bullet: true, breakLine: false } },
  { text: 'Draft status: All outputs designed for attorney review', options: { bullet: true, breakLine: false } }
], {
  x: 1.5,
  y: 2.1,
  w: 10.3,
  h: 4.7,
  fontFace: BODY_FONT,
  fontSize: 20,
  color: BRAND.contrast2,
  align: 'left',
  lineSpacing: 32
});

// Emphasis Footer
slide.addShape(pres.ShapeType.rect, {
  x: 0.0,
  y: 6.3,
  w: 13.33,
  h: 1.2,
  fill: { color: BRAND.accent },
  line: { type: 'none' },
  transparency: 10
});

slide.addText('You can audit the AI\'s work by clicking the citations.', {
  x: 1.0,
  y: 6.55,
  w: 11.33,
  h: 0.6,
  fontFace: HEAD_FONT,
  fontSize: 22,
  bold: true,
  color: BRAND.contrast,
  align: 'center',
  valign: 'middle'
});

slide.addNotes(
  'This is the most critical feature for trust. You do not have to guess where a fact came from. You can audit the AI\'s work by clicking the citations.'
);

// ============================================
// SLIDE 7: QUALITY & CONTROL (LAYOUT C)
// ============================================
slide = pres.addSlide();
slide.background = { color: BRAND.base };

slide.addText('Quality, Accuracy & Control', {
  x: 1.0,
  y: 0.8,
  w: 11.33,
  h: 1.2,
  fontFace: HEAD_FONT,
  fontSize: 36,
  bold: true,
  color: BRAND.contrast,
  align: 'left',
  valign: 'middle'
});

slide.addText([
  { text: 'Verified legal corpus: AI checks citations against 51 FL + 42 NM statutes', options: { bullet: true, breakLine: false } },
  { text: 'Hallucination guardrails: Citations rejected if not in verified corpus', options: { bullet: true, breakLine: false } },
  { text: 'Jurisdiction limits: Optimized only for Florida and New Mexico civil litigation', options: { bullet: true, breakLine: false } },
  { text: 'Attorney responsibility: You verify cited statutes are strategically applicable', options: { bullet: true, breakLine: false } }
], {
  x: 1.5,
  y: 2.1,
  w: 10.3,
  h: 4.7,
  fontFace: BODY_FONT,
  fontSize: 20,
  color: BRAND.contrast2,
  align: 'left',
  lineSpacing: 32
});

// Emphasis Footer
slide.addShape(pres.ShapeType.rect, {
  x: 0.0,
  y: 6.3,
  w: 13.33,
  h: 1.2,
  fill: { color: BRAND.footerBg },
  line: { type: 'none' }
});

slide.addText('You are the final decision-maker.', {
  x: 1.0,
  y: 6.55,
  w: 11.33,
  h: 0.6,
  fontFace: HEAD_FONT,
  fontSize: 22,
  bold: true,
  color: BRAND.contrast,
  align: 'center',
  valign: 'middle'
});

slide.addNotes(
  'The system prevents the AI from inventing laws. However, it cannot replace your judgment on whether a law is appropriate for the case strategy. You are the final decision-maker.'
);

// ============================================
// SLIDE 8: WHAT'S ROLLING OUT (LAYOUT C)
// ============================================
slide = pres.addSlide();
slide.background = { color: BRAND.base };

slide.addText('What Is Rolling Out Now', {
  x: 1.0,
  y: 0.8,
  w: 11.33,
  h: 1.2,
  fontFace: HEAD_FONT,
  fontSize: 36,
  bold: true,
  color: BRAND.contrast,
  align: 'left',
  valign: 'middle'
});

slide.addText([
  { text: 'Live jurisdictions: Florida and New Mexico civil litigation', options: { bullet: true, breakLine: false } },
  { text: 'Included areas: Consumer protection, landlord-tenant, foreclosure, construction, contracts', options: { bullet: true, breakLine: false } },
  { text: 'Explicit exclusions: No federal claims, criminal law, immigration, bankruptcy, family law', options: { bullet: true, breakLine: false } },
  { text: 'Status: Version 3.1.0 is live and available for immediate use', options: { bullet: true, breakLine: false } }
], {
  x: 1.5,
  y: 2.1,
  w: 10.3,
  h: 4.7,
  fontFace: BODY_FONT,
  fontSize: 20,
  color: BRAND.contrast2,
  align: 'left',
  lineSpacing: 32
});

// Emphasis Footer
slide.addShape(pres.ShapeType.rect, {
  x: 0.0,
  y: 6.3,
  w: 13.33,
  h: 1.2,
  fill: { color: BRAND.accent },
  line: { type: 'none' },
  transparency: 10
});

slide.addText('Do not use for federal cases or criminal law.', {
  x: 1.0,
  y: 6.55,
  w: 11.33,
  h: 0.6,
  fontFace: BODY_FONT,
  fontSize: 20,
  bold: true,
  color: BRAND.contrast,
  align: 'center',
  valign: 'middle'
});

slide.addNotes(
  'Do not use this for federal cases or criminal law. The legal validation corpus does not cover those areas, and results will be unreliable.'
);

// ============================================
// SLIDE 9: ADOPTION PLAN (LAYOUT C)
// ============================================
slide = pres.addSlide();
slide.background = { color: BRAND.base };

slide.addText('Adoption Plan & Expectations', {
  x: 1.0,
  y: 0.8,
  w: 11.33,
  h: 1.2,
  fontFace: HEAD_FONT,
  fontSize: 36,
  bold: true,
  color: BRAND.contrast,
  align: 'left',
  valign: 'middle'
});

slide.addText([
  { text: 'Immediate access: Your accounts are created; credentials distributed', options: { bullet: true, breakLine: false } },
  { text: 'Resources: One-page Quickstart Guide emailed to you', options: { bullet: true, breakLine: false } },
  { text: 'Training: Live Q&A session next Wednesday for questions', options: { bullet: true, breakLine: false } },
  { text: 'Support: Dedicated channels for technical issues and feature requests', options: { bullet: true, breakLine: false } }
], {
  x: 1.5,
  y: 2.1,
  w: 10.3,
  h: 4.7,
  fontFace: BODY_FONT,
  fontSize: 20,
  color: BRAND.contrast2,
  align: 'left',
  lineSpacing: 32
});

// Emphasis Footer
slide.addShape(pres.ShapeType.rect, {
  x: 0.0,
  y: 6.3,
  w: 13.33,
  h: 1.2,
  fill: { color: BRAND.footerBg },
  line: { type: 'none' }
});

slide.addText('Expectation: Log in and create a test case this week', {
  x: 1.0,
  y: 6.55,
  w: 11.33,
  h: 0.6,
  fontFace: BODY_FONT,
  fontSize: 20,
  bold: true,
  color: BRAND.contrast,
  align: 'center',
  valign: 'middle'
});

slide.addNotes(
  'We expect every attorney to log in and create a test case this week. Success is defined by using this on real client matters to reduce your intake time.'
);

// ============================================
// SLIDE 10: IMMEDIATE NEXT STEPS (LAYOUT C)
// ============================================
slide = pres.addSlide();
slide.background = { color: BRAND.base };

slide.addText('Immediate Next Steps', {
  x: 1.0,
  y: 0.8,
  w: 11.33,
  h: 1.2,
  fontFace: HEAD_FONT,
  fontSize: 36,
  bold: true,
  color: BRAND.contrast,
  align: 'left',
  valign: 'middle'
});

const nextSteps = [
  'Verify Access: Log in to the portal today',
  'Create Test Case: Upload sample documents to familiarize yourself',
  'Real Intake: Use Harvey AI for your next eligible case',
  'Attend Q&A: Bring questions and feedback to next Wednesday\'s session'
];

yPos = 2.1;
nextSteps.forEach((step, idx) => {
  // Number box
  slide.addShape(pres.ShapeType.rect, {
    x: 1.2,
    y: yPos - 0.05,
    w: 0.4,
    h: 0.4,
    fill: { color: BRAND.accent }
  });
  
  slide.addText(String(idx + 1), {
    x: 1.2,
    y: yPos - 0.05,
    w: 0.4,
    h: 0.4,
    fontFace: HEAD_FONT,
    fontSize: 18,
    bold: true,
    color: BRAND.base,
    align: 'center',
    valign: 'middle'
  });
  
  // Step text
  slide.addText(step, {
    x: 1.8,
    y: yPos,
    w: 9.5,
    h: 0.5,
    fontFace: BODY_FONT,
    fontSize: 18,
    color: BRAND.contrast2,
    align: 'left',
    valign: 'top'
  });
  
  yPos += 0.8;
});

// CTA Button
slide.addShape(pres.ShapeType.roundRect, {
  x: 4.5,
  y: 5.5,
  w: 4.33,
  h: 0.7,
  fill: { color: BRAND.accent },
  line: { type: 'none' }
});

slide.addText('This is live. Use it on your next intake.', {
  x: 4.5,
  y: 5.5,
  w: 4.33,
  h: 0.7,
  fontFace: HEAD_FONT,
  fontSize: 20,
  bold: true,
  color: BRAND.base,
  align: 'center',
  valign: 'middle'
});

slide.addNotes(
  'The system is live. Please log in after this meeting and try it out. Trust the system to handle the reading, but verify the output before you send it.'
);

// ============================================
// SAVE PRESENTATION
// ============================================
pres.writeFile({ fileName: 'presentation/harvey_ai_attorney_adoption.pptx' })
  .then(() => {
    console.log('✓ Presentation generated: harvey_ai_attorney_adoption.pptx');
    console.log('✓ Brand guidelines: Bernhardt Riley (strict mode)');
    console.log('✓ Layout: 16:9, precise positioning');
  })
  .catch(err => {
    console.error('Error generating presentation:', err);
    process.exit(1);
  });
