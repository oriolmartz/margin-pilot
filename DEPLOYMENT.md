# Deploying MarginPilot

Two things worth saying before the steps: this repo was built in a
sandbox with no Docker and no hosting-account access, so nothing below was
actually deployed end to end from there. The steps are accurate as of
mid-2026 (checked against Render's current docs while writing this), and
the Dockerfile/compose setup mirrors the exact commands already verified
locally (`uvicorn api.main:app ...` / `streamlit run dashboard/app.py
...`) -- but the Render Blueprint itself is a starting point to verify
against Render's dashboard when you actually run it, not a guarantee.

## Option A: Render (recommended -- free tier, no credit card)

1. Push this repo to GitHub (`git push` -- see the commit history already
   in this repo for a starting point).
2. In the Render dashboard: **New → Blueprint**, connect the repo. Render
   reads `render.yaml` and proposes two web services (`marginpilot-api`,
   `marginpilot-dashboard`) sharing the one `Dockerfile`.
3. Click **Deploy Blueprint**. Render builds the image once and runs each
   service with its own start command.
4. Once both are live, open the `marginpilot-dashboard` URL — that's the
   demo link.
5. (Optional) In the `marginpilot-api` service's **Environment** tab, add
   `ANTHROPIC_API_KEY` to switch the copilot from the offline fallback to
   a real Claude agent.

**Honest caveats, not glossed over:**
- Render's free web services spin down after 15 minutes of inactivity and
  take 30-60 seconds to wake back up on the next request. Fine for a demo
  link in a portfolio or an interview; say so if anyone's watching the
  first load.
- The SQLite files (`data/*.db`) live inside the container's own
  filesystem. On the free plan (no persistent disk), they reset on every
  restart or redeploy — the approval workflow and audit trail work
  correctly *within* a running instance, but don't survive a redeploy.
  A persistent disk (paid plan) or swapping SQLite for Render's managed
  Postgres would fix this; out of scope here, worth knowing before
  demoing the "survives a restart" claim from `ARCHITECTURE.md` — that
  claim was tested as two separate local processes sharing one file, not
  as a Render redeploy.

## Option B: Fly.io

Similar shape (Dockerfile-based, per-service `fly.toml`), and a similar
ephemeral-SQLite caveat applies unless you attach a Fly Volume. Not
written out step by step here since Render's Blueprint flow needed less
guesswork to get right from a sandbox with no way to click through either
dashboard.

## Running it locally without either

```bash
docker compose up --build
```

This is the one path actually exercisable in spirit here (the compose
file's commands match what was run directly via `uvicorn`/`streamlit`
throughout development) — just not literally `docker build`-tested,
since Docker wasn't available in the build sandbox either.
