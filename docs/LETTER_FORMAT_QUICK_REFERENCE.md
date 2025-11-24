# Letter Format Quick Reference Guide

## Decision Tree: Which Format Should the AI Use?

```
START
  │
  ├─ How many primary legal issues?
  │
  ├─ 1-4 issues? ──→ Any truly complex procedures?*
  │                  │
  │                  ├─ NO ──→ ✅ SIMPLE BULLETS FORMAT
  │                  │
  │                  └─ YES ──→ ⚠️ NUMBERED SECTIONS FORMAT
  │
  └─ 5+ issues? ──→ ✅ NUMBERED SECTIONS FORMAT


*Complex procedures = Multi-jurisdiction filings, specialized tribunals, etc.
NOT Chapter 558 pre-suit notices (standard for FL construction)
```

---

## Format 1: Simple Bullets (DEFAULT - Use for Most Cases)

### When to Use
- ✅ 1-4 primary legal issues
- ✅ Standard procedural requirements
- ✅ Most construction defect cases
- ✅ Most landlord-tenant cases
- ✅ Straightforward contract disputes

### Structure Template

```markdown
Dear [Client],

[Opening paragraph]

1. FACTUAL SUMMARY

[2-4 paragraphs with bullet points for compound facts]

Here are the key points of our analysis:

• **[Legal Issue 1]**: [Substantive paragraph explaining the law, 
  applying it to facts, and noting remedies/procedures]

• **[Legal Issue 2]**: [Substantive paragraph...]

• **[Legal Issue 3]**: [Substantive paragraph...]

• **[Legal Issue 4]**: [Substantive paragraph...]

2. RECOMMENDED ACTION & NEXT STEPS

[Integrated paragraph with timeline/urgency woven in]

[Call to action]

Thank you,
[Attorney Name]
[Title]

[Disclaimer]
```

### Real Examples Using This Format
- Erik Devlin (construction defect - 4 issues)
- Miguel Velasco (landlord-tenant - 3 issues)  
- Balaji Badam (tenant debt - 2 issues)
- Clifton Price (contract dispute - 3 issues)

---

## Format 2: Numbered Sections (RARE - Only for Complex Cases)

### When to Use
- ✅ 5+ distinct legal theories
- ✅ Truly complex procedural requirements
- ✅ Multi-jurisdiction disputes
- ✅ Specialized regulatory matters

### Structure Template

```markdown
Dear [Client],

[Opening paragraph]

1. FACTUAL SUMMARY

[2-4 paragraphs]

Key Findings

2. [FIRST LEGAL ISSUE]

[Dedicated section with law, application, remedies]

3. [SECOND LEGAL ISSUE]

[Dedicated section...]

4. [THIRD LEGAL ISSUE]

[Dedicated section...]

5. [FOURTH LEGAL ISSUE]

[Dedicated section...]

6. [FIFTH LEGAL ISSUE]

[Dedicated section...]

7. [SIXTH LEGAL ISSUE]

[Dedicated section...]

8. RECOMMENDED ACTION & NEXT STEPS

[Integrated paragraph]

[Call to action]

Sincerely,
[Attorney Name], Esq.
[Title]

[Disclaimer]
```

### Real Examples Using This Format
- Christopher Eastman (7+ legal theories across jurisdictions)
- Complex bankruptcy adversary proceedings

---

## What Counts as "Complex Procedure"?

### ❌ NOT Complex (Standard for Case Type)

These are **ROUTINE** and should use **Simple Bullets**:

- **Florida Chapter 558 pre-suit notice** (60-day notice requirement)
  - Standard for ALL FL construction defect cases
  - Not "complex" just because it has steps
  
- **Florida 3-day/7-day eviction notices**
  - Standard for FL landlord-tenant cases
  
- **Standard statute of limitations**
  - Routine timing requirement
  
- **Basic demand letters**
  - Common preliminary step

### ✅ Actually Complex (Triggers Numbered Format)

These justify **Numbered Sections**:

- **Multi-jurisdiction filing requirements**
  - File in multiple courts with different procedures
  
- **Federal court removal procedures**
  - Complex interaction between state and federal courts
  
- **Specialized licensing board appeals**
  - Unusual tribunal with unique rules
  
- **Administrative exhaustion requirements**
  - Multiple agency steps before litigation
  
- **Complex bankruptcy adversary proceedings**
  - Specialized bankruptcy court procedures

---

## Common Mistakes to Avoid

### ❌ Mistake 1: Treating Chapter 558 as "Complex"
```python
# WRONG - Flags standard construction procedure as complex
if "chapter 558" in procedural_requirements:
    has_complex_procedures = True  # ❌
```

**Fix:** Chapter 558 is **standard baseline** for FL construction, not complex.

---

### ❌ Mistake 2: Using Numbered Sections for 3-4 Issue Cases
```python
# WRONG - Too low threshold
if num_issues >= 3:  # ❌
    return numbered_sections_format
```

**Fix:** Use **`>= 5`** threshold. Most cases have 3-4 issues.

---

### ❌ Mistake 3: Creating Standalone "Procedural Requirements" Section

**Wrong:**
```markdown
2. IMPLIED WARRANTY & CONSTRUCTION DEFECTS
[paragraph]

3. PROCEDURAL REQUIREMENTS
• 60-day notice requirement
• 45-day contractor response
• Cannot file suit without completing process

4. BREACH OF CONTRACT
[paragraph]
```

**Correct:**
```markdown
Here are the key points of our analysis:

• **Implied Warranty & Construction Defects (Florida Statutes Chapter 558)**: 
Under Florida law, an implied warranty exists...

**Pre-Litigation Requirements:**
Before pursuing litigation, Florida Statutes Chapter 558 requires:
• You must provide 60 days' written notice...
• The contractor then has 45 days to respond...
• You CANNOT file suit without completing this process

• **Breach of Contract**: The contract with LLW Construction...
```

---

## Visual Scanability Test

### ✅ Good (Simple Bullets)
```
Opening
1. FACTUAL SUMMARY
   Here are the key points:
   • Issue 1 ─────────────┐
   • Issue 2 ─────────────┤ Easy to scan
   • Issue 3 ─────────────┤ All at same level
   • Issue 4 ─────────────┘
2. RECOMMENDED ACTION
Closing
```

Client can quickly see all legal issues at a glance.

---

### ❌ Bad (Too Many Numbered Sections)
```
Opening
1. FACTUAL SUMMARY
2. ISSUE 1 ────────────┐
3. ISSUE 2 ────────────┤ Hard to scan
4. ISSUE 3 ────────────┤ Too many levels
5. ISSUE 4 ────────────┘ Feels cluttered
6. RECOMMENDED ACTION
Closing
```

Client has to scroll through many section headers.

---

## Code Reference

**File:** `src/legal_portal/services/multi_stage_analyzer.py`  
**Function:** `_determine_letter_structure()`

### Current Logic (After Fix)

```python
# Count primary issues
num_primary_issues = len(issue_map.primary_issues)

# Check for TRULY complex procedures (exclude standard Chapter 558)
has_complex_procedures = False
for issue_analysis in analysis.issue_analyses:
    if issue_analysis.procedural_requirements:
        for proc_req in issue_analysis.procedural_requirements:
            req_lower = proc_req.requirement.lower()
            # Skip standard construction pre-suit requirements
            if "chapter 558" in req_lower or "60 day" in req_lower:
                continue
            # Non-standard = complex
            has_complex_procedures = True
            break

# Decision logic
if num_primary_issues <= 4 and not has_complex_procedures:
    return LetterStructure(style="simple_bullets", ...)
elif num_primary_issues >= 5 or has_complex_procedures:
    return LetterStructure(style="numbered_findings", ...)
```

---

## Testing Checklist

When reviewing AI-generated letters, verify:

### ✅ For 1-4 Issue Cases (Most Common)
- [ ] Uses "Here are the key points of our analysis:" intro
- [ ] Legal issues presented as **bullet paragraphs** (not numbered sections)
- [ ] No standalone "Procedural Requirements" section
- [ ] Chapter 558 requirements integrated within bullet points
- [ ] Only 2 main numbered sections (1. FACTUAL, 2. RECOMMENDED)

### ✅ For 5+ Issue Cases (Rare)
- [ ] Uses "Key Findings" intro (no "Here are...")
- [ ] Each issue gets dedicated numbered section (2., 3., 4., ...)
- [ ] Justified by truly complex case (not just 5 simple issues)
- [ ] Procedural requirements still integrated (not standalone)

### ✅ For All Cases
- [ ] Opening uses warm tone: "I hope you are doing well"
- [ ] Second person throughout ("you/your", not "Mr. Smith/the client")
- [ ] Statute citations in headers when applicable
- [ ] Consequence chains with ALL CAPS for ultimate risks
- [ ] Date math included (e.g., "over 8 months ago")
- [ ] Total word count: 800-1,200 words

---

## Summary

| Case Characteristics | Format | Intro Line |
|---------------------|--------|-----------|
| 1-4 issues, standard procedures | Simple Bullets | "Here are the key points of our analysis:" |
| 5+ issues OR truly complex procedures | Numbered Sections | "Key Findings" |

**Default to Simple Bullets.** Only use Numbered Sections when absolutely justified.

**Chapter 558 = Standard, not complex.**

**Most construction defect cases = Simple Bullets format.**

