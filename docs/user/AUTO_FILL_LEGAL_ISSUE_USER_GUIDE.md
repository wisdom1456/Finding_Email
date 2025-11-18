# Auto-Fill Legal Issue Feature - User Guide

**Feature:** AI-Assisted Legal Issue Selection  
**Version:** 1.0  
**Date:** November 18, 2025

---

## Overview

The system now automatically selects the most likely legal issue based on your intake form. You can verify and change it if needed.

---

## How It Works

### Step 1: Upload Your Intake Form

Upload your intake form along with any supporting documents as usual.

### Step 2: Review Screen Appears

After processing, you'll see the **Review & Confirm** screen with several sections.

### Step 3: Legal Issue Section - Now Auto-Filled! ✨

Look for the **"Define Primary Legal Issue"** section:

```
┌─────────────────────────────────────────────────────┐
│ Define Primary Legal Issue                         │
├─────────────────────────────────────────────────────┤
│ ℹ️  The AI has analyzed your intake form and       │
│    auto-selected the most likely legal issue.      │
│    Please verify and change if needed.             │
├─────────────────────────────────────────────────────┤
│ Primary Legal Issue (AI-selected, verify or change)│
│ ┌─────────────────────────────────────────────┐   │
│ │ Landlord/Tenant (Habitability)         ▼    │   │ ← AUTO-SELECTED!
│ └─────────────────────────────────────────────┘   │
│                                                     │
│ Options:                                           │
│ • Landlord/Tenant (Habitability)    ← YOU ARE HERE │
│ • Property Damage                                  │
│ • Breach of Contract (Construction)                │
│ • Real Estate (Failure to Disclose)                │
│ • Other                                            │
└─────────────────────────────────────────────────────┘
```

**Notice:**
- ✅ The dropdown already shows the AI's top pick
- ✅ No need to click and select (unless you want to change it)
- ✅ You can still change it to any other option

---

## Example Scenarios

### Scenario 1: AI Got It Right ✓

**Your Intake Form Mentions:**
- "My landlord refuses to fix the heating"
- "Water damage in bedroom"
- "Lease signed in January 2024"

**AI Auto-Selects:**
```
Primary Legal Issue: Landlord/Tenant (Habitability) ✓
```

**What You Do:**
- Verify it looks correct
- Click "Confirm & Start Full Analysis"
- Done! No manual selection needed.

---

### Scenario 2: AI Almost Got It Right ⚠️

**Your Intake Form Mentions:**
- "Contractor did poor work on kitchen"
- "Work completed 6 months ago"
- "Paid $25,000"

**AI Auto-Selects:**
```
Primary Legal Issue: Breach of Contract (Construction)
```

**But You Think:**
"Actually, the main issue is they never finished, not the quality."

**What You Do:**
1. Click the dropdown
2. Select "Breach of Contract (General)" instead
3. Click "Confirm & Start Full Analysis"

---

### Scenario 3: Unique Case - Need "Other" 🔧

**Your Intake Form Mentions:**
- Complex intellectual property dispute
- Multiple parties
- Cross-jurisdictional issues

**AI Auto-Selects:**
```
Primary Legal Issue: Business Dispute
```

**But You Think:**
"This is really a specialized IP matter."

**What You Do:**
1. Click the dropdown
2. Scroll to bottom and select "Other"
3. A text box appears: **"Please specify the legal issue:"**
4. Type: "Intellectual Property Dispute"
5. Click "Confirm & Start Full Analysis"

---

## Available Legal Issues

The AI can identify from 30+ practice areas:

### 🏠 Real Estate & Property
- Landlord/Tenant (Habitability, Eviction, Lease Dispute, Security Deposit)
- Real Estate (Failure to Disclose, Title Dispute, Boundary Dispute, Zoning/Land Use)
- Property Damage
- HOA Dispute

### 📝 Contracts & Business
- Breach of Contract (Construction, General, Employment, Real Estate)
- Business Dispute
- Partnership Dispute
- Consumer Protection
- Debt Collection Defense

### 💼 Employment
- Employment (Wrongful Termination, Discrimination, Harassment, Wage Dispute, Retaliation)

### 🚗 Personal Injury
- Personal Injury (Premises Liability, Auto Accident, Medical Malpractice)

### 💰 Insurance
- Insurance Claim (Denial, Bad Faith)

### 📦 Other
- Product Liability
- Fraud
- Breach of Fiduciary Duty
- Defamation
- And more...

---

## Frequently Asked Questions

### Q: What if the AI selects the wrong issue?

**A:** No problem! Just click the dropdown and select the correct one. The AI's selection is just a helpful starting point.

---

### Q: Can I see all 5 suggestions the AI made?

**A:** Yes! Click the dropdown and you'll see the top 5 most relevant practice areas the AI identified. They're ordered from most to least relevant.

---

### Q: What if none of the suggestions fit?

**A:** Select "Other" from the dropdown, and a text box will appear where you can type in your specific legal issue.

---

### Q: Will this affect the quality of the analysis?

**A:** The selected legal issue helps focus the AI's analysis on the most relevant statutes and case law. A more accurate selection leads to a better findings letter.

---

### Q: What happens if I don't change it?

**A:** If you're happy with the AI's selection, just click "Confirm & Start Full Analysis" and proceed. The AI is usually quite accurate.

---

### Q: How does the AI decide what to select?

**A:** The AI reads your entire intake form (all Q&A pairs) and uses GPT-4o-mini to match it against a comprehensive list of 30+ practice areas. It considers:
- Keywords and phrases in your description
- Parties involved (landlord/tenant, employer/employee, etc.)
- Types of claims mentioned
- Legal concepts referenced
- Document types uploaded

---

### Q: Can I see why the AI chose this option?

**A:** Currently, the AI's reasoning isn't displayed, but it's based on relevance to your intake form content. In future versions, we may add confidence scores or explanations.

---

## Tips for Best Results

### ✅ DO:
- Provide detailed answers in your intake form
- Mention specific legal terms if you know them (e.g., "habitability," "foreclosure")
- Include all relevant facts about your situation
- Review the AI's selection before confirming
- Change it if you think a different category fits better

### ❌ DON'T:
- Assume the AI is always 100% correct (verify!)
- Rush through without reading the selected issue
- Forget to check if "Other" with custom text is more appropriate
- Leave the intake form too vague (affects AI accuracy)

---

## Technical Notes (for advanced users)

- **Model Used:** GPT-4o-mini (fast, cost-effective)
- **Analysis Basis:** Q&A pairs from intake form
- **Number of Suggestions:** Top 5 most relevant (+ "Other")
- **Ordering:** Most relevant to least relevant
- **Fallback:** If analysis fails, defaults to "Other"
- **No Extra Cost:** Uses existing intake processing, no additional API calls

---

## Feedback

If you notice the AI consistently getting your case type wrong, please let your system administrator know. This helps us improve the practice area identification logic.

---

## Summary

**Before This Feature:**
```
1. AI analyzes intake
2. Shows dropdown with "Select an issue..."
3. YOU manually select ← Extra step!
4. Confirm and proceed
```

**With This Feature:**
```
1. AI analyzes intake
2. Shows dropdown with top pick already selected ← Auto-filled!
3. Verify (or change if needed)
4. Confirm and proceed ← Faster!
```

**Result:** Same control, less work, better experience! 🎉

