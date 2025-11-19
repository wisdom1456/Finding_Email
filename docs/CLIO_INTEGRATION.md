# CLIO Integration Guide

This guide explains how to set up and use the CLIO Manage integration with the Legal Document Analysis Portal.

## Table of Contents

- [Overview](#overview)
- [Benefits](#benefits)
- [Prerequisites](#prerequisites)
- [Setup Instructions](#setup-instructions)
- [Using the CLIO Integration](#using-the-clio-integration)
- [Understanding the Data Summary](#understanding-the-data-summary)
- [Troubleshooting](#troubleshooting)
- [Security & Privacy](#security--privacy)
- [FAQ](#faq)

## Overview

The CLIO integration allows you to import matter data directly from CLIO Manage, including:

- **Communications** (emails)
- **Case notes**
- **Contact information**
- **Matter details**

This data is automatically analyzed to:

- Pre-populate the intake form with client information
- Build a communication timeline
- Identify party relationships
- Detect communication gaps
- Generate higher-quality letters with specific date references

## Benefits

### 1. Reduced Data Entry (50-70% less typing)
The system automatically extracts:
- Client name
- Matter description
- Practice area
- Custom field data

### 2. Richer Context
Instead of generic statements like "based on communications," your letters will reference:
- Specific emails by date and sender
- Communication gaps (e.g., "45-day silence despite follow-ups")
- Response patterns

### 3. Superior Letter Quality

**Before CLIO Integration:**
> "Based on the communications provided, the opposing party has been unresponsive."

**After CLIO Integration:**
> "Following your demand letter on January 18, 2024, Jones Construction failed to respond for 45 days. Despite follow-up emails on February 2nd and March 4th, they only replied on March 6th—a pattern suggesting avoidance rather than good-faith negotiation."

## Prerequisites

Before you can use the CLIO integration, you need:

1. A CLIO Manage account with administrative access
2. Ability to create OAuth apps in CLIO (Admin level)
3. Access to your server's `.env` file

## Setup Instructions

### Step 1: Create a CLIO OAuth Application

1. Log in to your CLIO account at [app.clio.com](https://app.clio.com)

2. Navigate to **Settings** → **Integrations** → **API & Developer Apps**

3. Click **Create New App**

4. Fill in the application details:
   - **App Name**: `Legal Document Portal`
   - **Description**: `Internal document analysis and letter generation`
   - **Redirect URI**: `http://localhost:8501` (for local development)
     - For production: Use your actual domain (e.g., `https://yourdomain.com`)
   - **Scopes**: Select the following permissions:
     - `matters:read`
     - `communications:read`
     - `documents:read`
     - `notes:read`
     - `contacts:read`

5. Click **Create Application**

6. **Save the credentials** (you'll need these in Step 2):
   - Client ID
   - Client Secret

### Step 2: Configure Environment Variables

1. Open your `.env` file in the project root

2. Add the following variables:

```bash
# CLIO Integration (Optional)
CLIO_CLIENT_ID=your_client_id_from_step_1
CLIO_CLIENT_SECRET=your_client_secret_from_step_1
CLIO_REDIRECT_URI=http://localhost:8501
CLIO_ENVIRONMENT=sandbox  # or 'production'
```

3. Replace `your_client_id_from_step_1` and `your_client_secret_from_step_1` with the actual values from Step 1

4. Save the `.env` file

5. Restart the application:

```bash
# Stop the current application (Ctrl+C)
# Then restart:
streamlit run src/legal_portal/ui/main.py
```

### Step 3: Verify Installation

1. Open the application in your browser

2. You should see a **"Connect to CLIO"** tab on the upload screen

3. If you don't see this tab, check:
   - `.env` file has correct values
   - Application was restarted after adding credentials
   - No syntax errors in `.env` file

## Using the CLIO Integration

### Connecting to CLIO

1. **On the upload screen**, click the **"🔗 Connect to CLIO"** tab

2. Click the **"Authorize CLIO Access"** link

3. You'll be redirected to CLIO's authorization page

4. **Review the permissions** and click **"Authorize"**

5. You'll be automatically redirected back to the portal

6. You should see a **"✅ Connected to CLIO"** message

### Searching for a Matter

1. After connecting, enter the **client name** in the search box

2. Type at least **3 characters** to start searching

3. Results will show:
   - Matter number
   - Client name
   - Description
   - Practice area and status
   - Open date

4. Click **"Select"** on the matter you want to import

### Importing Matter Data

1. After selecting a matter, choose what to import:
   - **📧 Communications (Emails)** - Recommended, enabled by default
   - **📝 Case Notes** - Recommended, enabled by default
   - **📄 Documents** - Coming in Phase 3

2. Click **"Import Data"** to begin

3. The system will:
   - Fetch communications from CLIO
   - Fetch case notes
   - Retrieve all related contacts
   - Analyze communication patterns
   - Build timeline and context

This typically takes **10-30 seconds** depending on the amount of data.

### Reviewing Imported Data

After import, you'll see a comprehensive summary:

#### Statistics Dashboard
- Number of communications imported
- Number of documents
- Number of notes
- Number of contacts identified

#### Matter Details
- Matter number and status
- Client name
- Practice area
- Date range of communications

#### Communication Timeline
- Recent communications (last 10 shown)
- Date, subject, sender, and recipients for each
- Notable communication gaps (>30 days)

#### Party Relationships
Automatically categorized as:
- **Clients** ✓ (high bidirectional activity)
- **Opposing Parties** ⚠️ (receives demands, low responsiveness)
- **Third Parties** • (CC'd frequently, low activity)

#### Communication Patterns
- Attorney-initiated communications
- Client-initiated communications
- Opposing party response rate
- Key insights about communication behavior

#### Pre-Populated Information
The system extracts from the matter:
- Client name
- Legal issue description
- Practice area
- Custom fields (incident date, property address, etc.)

### Proceeding to Review

1. Review the imported data summary

2. Click **"Continue to Review →"** to proceed

3. The **intake form will be pre-populated** with CLIO data

4. You can **edit any information** in the review screen

5. Continue with normal workflow (Review → Analysis → Letter)

## Understanding the Data Summary

### Communication Gaps

**What it means:** Periods of >30 days with no communications

**Why it matters:** Gaps can indicate:
- Opposing party delays or avoidance
- Missed deadlines
- Prolonged disputes

**Example usage in letters:**
> "Following your February 10th request for clarification, no response was received for 47 days, suggesting a pattern of avoidance."

### Party Role Detection

The system uses heuristics to classify contacts:

| Role | Criteria | Example Usage |
|------|----------|---------------|
| **Client** | High bidirectional activity (>10 sends, >10 receives) | "You advised that..." |
| **Opposing Party** | Receives more than sends, or only receives | "Jones Construction failed to respond..." |
| **Third Party** | Low activity, frequently CC'd | "The property manager was copied..." |

### Communication Statistics

**Attorney-Initiated:** Communications sent by the attorney
**Client-Initiated:** Communications sent by the client
**Response Rate:** Percentage of communications from opposing party

**Insights** are automatically generated, such as:
- "Opposing party shows limited responsiveness" (response rate <30%)
- "Client has been proactive with 8 communications"

## Troubleshooting

### "CLIO not configured" error

**Cause:** Environment variables not set correctly

**Solution:**
1. Check `.env` file has `CLIO_CLIENT_ID` and `CLIO_CLIENT_SECRET`
2. Verify no extra spaces or quotes around values
3. Restart the application

### "Authorization failed" error

**Cause:** OAuth flow didn't complete

**Solution:**
1. Clear your browser cache
2. Try disconnecting and reconnecting
3. Verify your CLIO account has API access enabled
4. Check that the Redirect URI in CLIO app matches `.env` value

### "Access token expired" error

**Cause:** CLIO tokens expire after 1 hour

**Solution:**
1. Click "Disconnect" in the CLIO tab
2. Click "Authorize CLIO Access" again to reconnect
3. The system will automatically refresh tokens in the future

### No matters found

**Cause:** Search term doesn't match any matters

**Solution:**
1. Try a different search term
2. Search by matter number instead of client name
3. Verify the matter exists in CLIO
4. Check your CLIO account has access to the matter

### Import takes too long

**Cause:** Matter has hundreds of communications

**Solution:**
- Wait for import to complete (may take 1-2 minutes for large matters)
- The system limits imports to 500 communications for performance
- Consider using date filters (coming in Phase 3)

### Letter doesn't use CLIO context

**Cause:** Context wasn't passed to letter generation

**Solution:**
1. Verify you see the import summary before proceeding to review
2. Check that "Continue to Review" was clicked from the summary screen
3. Look for "Using CLIO matter context" in application logs

## Security & Privacy

### Data Storage

- **OAuth tokens** are stored only in session state (browser memory)
- Tokens are **cleared when you close the browser**
- **No CLIO data is persisted to disk** by the portal
- All API calls use **HTTPS encryption**

### Permissions

The CLIO integration requests **read-only access**:
- Cannot create or modify matters
- Cannot send communications
- Cannot delete or edit data
- Can only read data you already have access to in CLIO

### Audit Trail

All CLIO connections are logged:
- Connection timestamp
- User who connected
- Matter accessed
- Data imported

Logs are stored in `logs/` directory for audit purposes.

### Best Practices

1. **Never share** your CLIO Client ID and Secret
2. **Use separate apps** for development and production
3. **Rotate credentials** periodically (every 90 days)
4. **Limit access** to the `.env` file
5. **Review permissions** before authorizing

## FAQ

### Do I need CLIO to use the portal?

No, CLIO is completely optional. The portal works with manual document uploads if CLIO is not configured.

### Can I use both CLIO and manual uploads?

Not simultaneously, but you can:
- Import from CLIO, then manually add more documents (Phase 3 feature)
- Use CLIO for some cases and manual upload for others

### Which CLIO plan do I need?

Any CLIO plan with API access. This typically includes:
- CLIO Manage (all tiers)
- CLIO Suite

### Does this work with CLIO Grow?

No, this integration is for **CLIO Manage** only (practice management software).

### How much does the CLIO API cost?

CLIO API access is **included with your CLIO subscription** at no additional cost.

### Can I import documents from CLIO?

Not yet. Document downloads are planned for Phase 3. Currently supports:
- ✅ Communications (emails)
- ✅ Case notes
- ⏳ Documents (coming soon)

### What if my custom fields don't match?

The system maps common custom fields automatically:
- `incident_date` → "When did this incident occur?"
- `property_address` → "What is the property address?"
- `opposing_counsel` → "Who represents the other party?"

Unmapped fields are ignored but can be added in `clio_context_builder.py`.

### Can I filter communications by date?

Not yet. Date range filtering is planned for Phase 3.

### How many communications can I import?

The system imports up to **500 communications** per matter for performance. For matters with more communications, the most recent 500 are imported.

### Does this slow down letter generation?

No, the additional context adds ~5-10 seconds to the import process but does not affect letter generation speed.

### Can I see what data was imported?

Yes, the **Data Summary** screen shows:
- Exact count of items imported
- Date range covered
- List of contacts
- Communication timeline

### What happens if CLIO is down?

If CLIO's API is unavailable:
1. You'll see an error message
2. You can **still use manual upload**
3. Previously generated letters are unaffected

### Can multiple users share the same CLIO connection?

No, each user must authorize CLIO individually. Tokens are session-specific and not shared between users.

### How do I disconnect from CLIO?

1. Go to the **"Connect to CLIO"** tab
2. Click **"Disconnect"**
3. Your tokens will be cleared immediately

You can reconnect at any time.

---

## Need Help?

If you encounter issues not covered in this guide:

1. Check the application logs in `logs/` directory
2. Look for error messages in the UI
3. Verify your CLIO app configuration
4. Contact your system administrator

## Future Enhancements

Planned for upcoming releases:

- **Phase 2:**
  - Party relationship visualization
  - Enhanced timeline view
  - Communication gap warnings in UI

- **Phase 3:**
  - Document downloads from CLIO
  - Attachment handling
  - Hybrid workflow (CLIO + manual upload)
  - Date range filtering
  - Bulk matter processing

- **Future:**
  - Bi-directional sync (save letter to CLIO)
  - Task/deadline integration
  - Custom field mapping configuration
  - Communication threading

