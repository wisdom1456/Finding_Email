# Demand Letter Formatting - Quick Reference

## CSS Styling Quick Reference

### Typography
```css
font-family: 'Times New Roman', Times, serif;
font-size: 12pt;
line-height: 2.0;  /* Double-spaced */
color: #000000;
```

### Page Layout
```css
padding: 1in 1.25in;  /* Top/Bottom: 1", Left/Right: 1.25" */
max-width: 8.5in;      /* Standard letter width */
margin: 0 auto;        /* Center on page */
```

### Paragraphs
```css
margin: 0 0 12pt 0;    /* 12pt bottom spacing */
line-height: 2.0;      /* Double-spaced */
text-align: left;      /* Not justified */
```

### Lists
```css
/* Standard lists */
margin: 12pt 0;
padding-left: 0.5in;
line-height: 2.0;

/* Demand lists (bold numbers, hanging indent) */
counter-increment: demand-counter;
margin: 12pt 0 12pt 0.3in;
text-indent: -0.3in;
```

### Blockquotes (Contract Language)
```css
margin: 12pt 0 12pt 0.5in;
padding: 12pt;
border-left: 3px solid #cccccc;
background-color: #f9f9f9;
font-style: italic;
line-height: 1.8;
```

### Signature Block
```css
margin-top: 36pt;      /* Extra spacing before signature */
line-height: 1.5;      /* Tighter than body */
```

### Print Optimization
```css
@media print {
    body {
        padding: 0.5in 1in;
        line-height: 1.8;
    }
    
    h1, h2, h3 {
        page-break-after: avoid;  /* Keep headings with content */
    }
    
    p, ul, ol {
        page-break-inside: avoid;  /* Don't break paragraphs */
    }
}
```

---

## Markdown Formatting Guidelines

### Header Section
```markdown
Date: November 22, 2025


Sent via certified mail:


John Doe
123 Main Street
City, FL 12345


**RE: Demand Letter Regarding [Brief Description]**
**Property Address:** 456 Oak Avenue, City, FL 12345


Dear Mr. Doe:
```

**Key Points:**
- Blank line after date
- Blank line after "Sent via certified mail:"
- Each address line separate
- Blank line after address
- Bold RE: line
- Blank line after RE: section
- Blank line after salutation

---

### Introduction Paragraph
```markdown
Our law firm has been retained by Jane Smith (hereinafter "Client") in 
connection with [brief description]. This correspondence serves as a formal 
demand regarding [issue]. Please direct all future communications regarding 
this matter to my attention at the contact information provided below.
```

**Key Points:**
- Use "hereinafter" for key terms
- Define: Client, Contract, Property, etc.
- State purpose clearly
- Direct future communications

---

### Background Section
```markdown
On or about March 15, 2025, Jane Smith entered into a contract with John Doe 
Construction, Inc. (hereinafter "Contractor") for renovation work valued at 
One Hundred Thousand U.S. Dollars and Zero Cents ($100,000.00). Pursuant to 
the terms of the contract, Jane Smith paid Fifty Thousand U.S. Dollars and 
Zero Cents ($50,000.00) as an initial deposit.


However, as of November 2025, only minimal work has been completed, despite 
repeated requests for performance. It is undisputed that the Contractor 
accepted payment and began work, establishing a clear contractual relationship.


[Continue with 3-5 substantive paragraphs]
```

**Key Points:**
- Use "on or about [date]" format
- Monetary amounts: Written form + numeric in parentheses
- Double blank lines between paragraphs (for double-spacing effect)
- Formal language: "pursuant to", "it is undisputed", "as you are aware"
- 4-6 sentences per paragraph minimum

---

### Legal Analysis Section
```markdown
It is undisputed that the parties entered into a valid contract on or about 
March 15, 2025. Under Florida law, a breach of contract claim requires: (1) 
a valid contract; (2) a material breach; and (3) damages. As established in 
*Murry v. Zynyx Mktg. Communs., Inc.*, 774 So. 2d 714, 715 (Fla. 3d DCA 
2000), all three elements must be proven.


The contract specifically provides:

> Article 5 titled 'Performance Obligations' states: "Contractor agrees to 
> complete all work described in Exhibit A within 120 days of the contract 
> date. All work shall be performed in a workmanlike manner and in compliance 
> with applicable building codes and industry standards."


Under Florida Statute § 95.031, Jane Smith has five years from the date of 
breach to bring an action for breach of written contract. The statute of 
limitations is clearly satisfied in this matter.


[Continue with analysis]
```

**Key Points:**
- Use > for blockquotes (contract language)
- Use *italics* for case names (automatic via markdown2)
- Include statute citations: § 95.031 format
- Explain legal elements
- Apply facts to law
- 4-6 sentences per paragraph

---

### Demand Section
```markdown
As such, let this correspondence serve as a formal demand that:


1. John Doe Construction, Inc. immediately complete all remaining work as 
   specified in the contract, or provide a full refund of the unearned 
   portion of the payment.

2. John Doe Construction, Inc. provide written confirmation that no 
   construction lien will be filed against the property, or release any 
   improperly filed liens within five business days.

3. John Doe Construction, Inc. compensate Jane Smith for damages incurred 
   as a result of the breach, including but not limited to delay damages 
   and costs of securing alternative contractors.


We demand the payment of Twenty-Five Thousand U.S. Dollars and Zero Cents 
($25,000.00) as compensation for the breach of contract, to be received 
within ten (10) business days from receipt of this letter.


Should we fail to receive any response within this timeframe, we will assume 
you intend to reject this demand and will proceed to take any necessary legal 
action afforded to our Client, including filing a lawsuit for breach of 
contract, seeking specific performance, pursuing construction liens, and 
recovering attorney's fees and costs as provided by law.
```

**Key Points:**
- Opening line: "As such, let this correspondence serve as a formal demand that:"
- Blank line after opening
- Numbered list with specific demands
- Blank line after list
- Monetary demand in separate paragraph (written + numeric)
- Blank line
- Consequences paragraph with specific remedies
- No hedging - be direct and assertive

---

### Closing Section
```markdown
Thank you for your prompt attention to this matter, and we look forward to 
your compliance with the above. Please do not hesitate to reach out to our 
office at (555) 123-4567 or via e-mail at attorney@lawfirm.com.


Sincerely,


/s/ Attorney Name

Attorney Name, Esq.

Division Attorney

Law Firm Name

Attorney for Jane Smith
```

**Key Points:**
- Single closing paragraph
- Include phone and email
- Blank line before "Sincerely,"
- Blank line after "Sincerely,"
- Each signature line separate
- End with "Attorney for [Client Name]"

---

## Common Formatting Patterns

### Monetary Amounts
```markdown
❌ $100,000.00
❌ One hundred thousand dollars ($100,000.00)
✅ One Hundred Thousand U.S. Dollars and Zero Cents ($100,000.00)
```

### Dates
```markdown
❌ March 15th, 2025
❌ 3/15/2025
✅ on or about March 15, 2025
✅ March 15, 2025 (for specific dates like letter date)
```

### Party References
```markdown
❌ "the client"
❌ "our client"
✅ Jane Smith (first reference with hereinafter)
✅ Client (subsequent references after hereinafter definition)
✅ the Client (with "the" for formal tone)
```

### Statute Citations
```markdown
❌ Florida Statute 95.031
❌ F.S. 95.031
✅ Florida Statute § 95.031
```

### Case Citations
```markdown
✅ *Murry v. Zynyx Mktg. Communs., Inc.*, 774 So. 2d 714, 715 (Fla. 3d DCA 2000)
```
*(Italics will be applied automatically by markdown2)*

### Contract References
```markdown
❌ The contract says...
✅ The Contract specifically provides:

> [Verbatim quote]

✅ Article 5 titled 'Performance Obligations' provides...
```

---

## Spacing Cheat Sheet

| Element | Spacing |
|---------|---------|
| Between header lines | 1 blank line |
| After header section | 1 blank line |
| After salutation | 1 blank line |
| Between paragraphs | 1 blank line (renders as double-space) |
| Before demands list | 1 blank line |
| After demands list | 1 blank line |
| Before closing | 1 blank line |
| After "Sincerely," | 1 blank line |
| Between signature lines | 0 blank lines (each on own line) |

---

## Print Checklist

Before finalizing a demand letter, verify:

- [ ] Times New Roman 12pt font
- [ ] Double-spacing (2.0 line-height)
- [ ] 1" - 1.25" margins
- [ ] Page width 8.5" or less
- [ ] Header section properly formatted
- [ ] Blank lines between sections
- [ ] Monetary amounts in written + numeric format
- [ ] Dates in "on or about" format (where appropriate)
- [ ] Demands numbered with bold numbers
- [ ] Contract quotes in blockquotes
- [ ] Case citations in italics
- [ ] Signature block properly spaced
- [ ] Contact information included
- [ ] Professional appearance in print preview

---

## File Location Reference

### Service Files:
- **Formatter:** `src/legal_portal/services/document_formatter.py`
- **Generator:** `src/legal_portal/services/demand_letter_service.py`

### Prompt File:
- **Template:** `src/legal_portal/prompts/demand_letter_prompt.txt`

### Documentation:
- **Full Guide:** `docs/DEMAND_LETTER_FORMATTING_IMPROVEMENTS.md`
- **Comparison:** `docs/DEMAND_LETTER_FORMATTING_COMPARISON.md`
- **Quick Reference:** `docs/DEMAND_LETTER_FORMATTING_QUICK_REFERENCE.md` (this file)

---

## Quick Usage Example

```python
from legal_portal.services.demand_letter_service import DemandLetterService
from legal_portal.utils.openai_client import OpenAIClient

openai_client = OpenAIClient()
service = DemandLetterService(openai_client)

letter = await service.generate_demand_letter(
    fact_matrix_dict={...},
    deep_analysis_dict={...},
    target_party_name="John Doe",
    demand_amount=25000.00,
    demand_deadline="10 business days",
    specific_demands=[...],
    attorney_info={
        "name": "Jane Attorney",
        "firm": "Law Firm LLP",
        "phone": "(555) 123-4567",
        "email": "jane@lawfirm.com"
    },
    client_name="John Client"
)

# letter contains professionally formatted HTML
# Ready for display, print, or PDF generation
```

---

## Troubleshooting

### Problem: Letter looks cramped
**Solution:** Check that line-height is 2.0 and paragraph margins are 12pt

### Problem: Poor print quality
**Solution:** Verify print media queries are applied and margins are 1" - 1.25"

### Problem: Contract quotes not standing out
**Solution:** Ensure blockquote (>) syntax is used and CSS includes border/background

### Problem: Demands not prominent
**Solution:** Verify numbered list formatting with bold numbers and hanging indent

### Problem: Signature block cramped
**Solution:** Check that margin-top is 36pt and line-height is 1.5

---

## Additional Resources

- **Full Documentation:** See `docs/DEMAND_LETTER_FORMATTING_IMPROVEMENTS.md`
- **Visual Comparison:** See `docs/DEMAND_LETTER_FORMATTING_COMPARISON.md`
- **Original Requirements:** See `docs/DEMAND_LETTER_IMPROVEMENTS.md`



