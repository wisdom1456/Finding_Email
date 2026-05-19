# Admin scripts

Read-only operational queries against the production database. All scripts
use `SUPABASE_SERVICE_KEY` from `.env`, paginate properly (PostgREST's
default 1000-row cap is a real foot-gun), and never mutate state.

## When to run each

| Script | Question it answers | Typical cadence |
|---|---|---|
| `monitor_jobs.py [--days N]` | "Is the analysis worker healthy? Anything stuck?" | After deploys, when a user reports slowness |
| `audit_quality.py [--days N]` | "Are users getting quality letters? Who's failing QA?" | Weekly check |
| `cases_needing_attention.py` | "Which cases have docs uploaded but were never analyzed?" | Monthly, before user check-ins |

## Postgres views (preferred when available)

Once migration `20260519000000_add_letter_quality_views.sql` is applied,
the same data is available via SQL:

```sql
-- Letter quality signals
SELECT * FROM letter_quality_signals
 WHERE qa_term_explainer_passed = false
 ORDER BY completed_at DESC LIMIT 20;

-- Cases stuck without analysis
SELECT * FROM cases_needing_attention
 WHERE NOT has_ever_been_analyzed AND docs_ready > 0
 ORDER BY case_updated_at DESC;
```

Run those from Supabase Dashboard → SQL Editor for a faster pass. The
Python scripts are the fallback when SQL Editor isn't handy or for
formatted CLI output.

## Letter generation events (after migration 20260519000001)

```sql
-- Recent letter failures
SELECT requested_at, letter_type, error
  FROM letter_generation_events
 WHERE status = 'failed'
 ORDER BY requested_at DESC LIMIT 20;

-- Quality flag rate over last 7 days
SELECT letter_type,
       COUNT(*) FILTER (WHERE qa_passed = true)  AS clean,
       COUNT(*) FILTER (WHERE qa_passed = false) AS flagged,
       COUNT(*) FILTER (WHERE qa_passed IS NULL) AS unmeasured
  FROM letter_generation_events
 WHERE requested_at > NOW() - INTERVAL '7 days'
 GROUP BY letter_type;
```

## Usage

```bash
cd /Users/BRFlorida/Projects/Work/Finding_Emails
source venv/bin/activate
python scripts/admin/monitor_jobs.py
python scripts/admin/audit_quality.py --days 14
python scripts/admin/cases_needing_attention.py
```
