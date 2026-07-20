# Amazon SP-API conversion tracker — setup guide

This kit tracks your Amazon content uploads and pulls daily conversion data so
you can measure whether an image or A+ Content change actually moved your
conversion rate. It runs automatically, for free, 6 times a day using GitHub
Actions — no server to manage.

## What's in this folder

| File | What it does |
|---|---|
| `sync_sp_api.py` | The main script: checks upload status, pulls conversion data, saves it to a database file |
| `analyze.py` | Run this whenever you want to see a before/after comparison for an ASIN |
| `conversion.db` | The database (created automatically — a single file, no separate database server needed) |
| `.env.example` | Template for your credentials |
| `.github/workflows/schedule.yml` | The scheduler that runs the sync script 6x/day |
| `requirements.txt` | List of Python packages needed |

---

## Part 1 — Get your SP-API credentials

You said you already have SP-API access, so some of this may already be done.
If not:

1. **Register as a developer** in Seller Central: Settings → User Permissions
   → "Manage your apps" (or Apps & Services → Develop apps).
2. **Create an app** ("Develop apps for Amazon" → "Add new app client"). Choose
   the roles you need — at minimum: **Listings**, **Product Listing**, and
   **Reports**. This gives you an **LWA Client ID** and **LWA Client Secret**.
3. **Authorize the app against your own seller account**: in the same section,
   generate a self-authorization. This produces a **refresh token** — this is
   the credential your script will use to get fresh access tokens
   automatically (they expire hourly, but the refresh token doesn't).
4. Note down your **Seller ID** (Settings → Account Info).

You should now have four values: LWA Client ID, LWA Client Secret, refresh
token, and Seller ID. Keep these private — treat them like a password.

---

## Part 2 — Get the code onto your computer

You don't need to know how to code, but you do need a free **GitHub** account
and a place to run things once to test.

1. **Create a GitHub account** at github.com if you don't have one.
2. **Create a new repository** (the "+" icon top right → "New repository").
   Name it something like `sp-conversion-tracker`. Keep it **private**
   (important — it will contain your database and code, even though your
   actual secret credentials will be stored separately and safely).
3. **Upload these files** into that repository. On the repo page, click
   "Add file" → "Upload files", then drag in every file from this folder
   (keep the `.github/workflows/schedule.yml` file in that same folder
   structure — GitHub will preserve it if you drag the whole folder).

---

## Part 3 — Store your credentials safely in GitHub

Never put real credentials in a file you upload. Instead:

1. In your repository, go to **Settings → Secrets and variables → Actions**.
2. Click **New repository secret** and add each of these one at a time:
   - `SP_API_REFRESH_TOKEN`
   - `SP_API_LWA_APP_ID`
   - `SP_API_LWA_CLIENT_SECRET`
   - `SP_API_SELLER_ID`
   - `SP_API_MARKETPLACE` (e.g. `US`)

These secrets are encrypted and only get injected into the script when it
runs — they're never visible in your code or logs.

---

## Part 4 — Turn on the schedule

The file `.github/workflows/schedule.yml` is already configured to run 6
times a day (every 4 hours). Once it's in your repo with the secrets set up:

1. Go to the **Actions** tab in your GitHub repo.
2. You should see "Sync SP-API data" listed as a workflow.
3. Click it, then click **Run workflow** to trigger it manually the first
   time and confirm it works.
4. Check the run's logs (click into it) — you should see messages like
   "Requesting Sales & Traffic report..." and "Saved N rows of metrics."
5. After that first successful run, it will keep running automatically on
   schedule — you don't need to do anything else.

If a run fails, click into it — the error message will usually tell you
directly what's wrong (most common: a typo'd secret, or a missing role on
your SP-API app).

---

## Part 5 — Log an upload when you post new content

Whenever you upload a new image or A+ Content module to an ASIN, tell the
tracker about it so it knows when to start measuring "after." The easiest
way, since you're not writing code day-to-day: use GitHub's **Actions →
Run workflow** manual trigger, or run this one line from a Python console:

```python
from sync_sp_api import log_upload
log_upload("B0EXAMPLE123", "image", notes="Updated main image, added lifestyle shot")
```

If you'd rather not touch Python at all, let me know and I'll set up a second,
simpler workflow with a form-style trigger so you can log an upload directly
from the GitHub Actions tab without writing anything.

---

## Part 6 — Check your results

Once you've got a couple weeks of data before and after an upload, run:

```
python analyze.py B0EXAMPLE123
```

This prints the average conversion rate before vs. after the content went
live, and the percentage change. It needs at least a few days of data on
each side to give a meaningful answer — check back after ~2 weeks
post-upload for a real read.

---

## A note on realistic expectations

- **A+ Content approval takes time** (often 1-7 business days) — the script
  currently checks basic listing/image status; full A+ approval-status
  checking is noted as a TODO in `sync_sp_api.py` since it uses a separate
  API. I can build that part out next if you want it fully automatic.
- **Conversion rate is noisy day to day**, especially on lower-traffic ASINs
  — don't read too much into a single day's swing either direction.
- **Other things move conversion rate too** — price changes, stockouts, and
  ad spend changes will all show up in the same data. Worth jotting a note
  in the `uploads` table (`notes` column) any time one of those happens
  alongside a content change, so you're not misattributing a swing.

---

## If you get stuck

Come back here and tell me what happened — paste the exact error message
from a failed GitHub Actions run and I can tell you exactly what to fix.
