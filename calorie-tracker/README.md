# Calorie Tracker

A small personal calorie tracker. Runs great on your own machine (no
account, no hosting, just a local web page backed by SQLite), or can be
deployed to a free host if you only have a phone — see "Deploying" below.

Log meals three ways:
- Type in calories yourself.
- Describe the meal in words ("two eggs, toast, black coffee") and let
  Claude estimate calories/macros.
- Upload a photo of the meal and let Claude estimate it from the picture.

Every AI estimate is shown to you first (editable) before it's saved, so
you can correct it if it's off.

## Setup

```bash
cd calorie-tracker
python -m venv venv && source venv/bin/activate   # optional but recommended
pip install -r requirements.txt
cp .env.example .env
```

Edit `.env` and add your Anthropic API key (from
https://console.anthropic.com/settings/keys) to enable the AI analysis
tabs. Without a key, manual entry still works fine — you'll just see a
notice that AI analysis is off.

## Run

```bash
python app.py
```

Then open http://127.0.0.1:5000 in your browser. Stop it with Ctrl+C.

The AI features do call out to Anthropic's API over the internet — that's
the "AI" part. Everything else (the app, your data, your photos) stays on
your machine in `calorie-tracker/data/calories.db` and
`calorie-tracker/static/uploads/`.

## Notes

- Set a daily calorie goal from the "Set goal" box on the main page — it
  shows a progress bar under today's total.
- Use the prev/next links to log or review other days; "History" gives a
  per-day list.
- Uploaded photos are resized before being sent to Claude, so even large
  phone photos are cheap/fast to analyze.

## Deploying (e.g. if you only have a phone)

This app can run on a free host like [Render](https://render.com) so you
just open a link in your phone's browser instead of running a terminal.

Two things to know about hosting it:

1. **Root directory**: this app lives in the `calorie-tracker/` subfolder
   of the repo, not the repo root. Point your host's "Root Directory" at
   `calorie-tracker`.
2. **Build/start commands**: build with `pip install -r requirements.txt`,
   start with `gunicorn app:app`. Set the `PORT` env var if your host
   doesn't set it automatically (Render does).
3. **Storage**: a free host's disk usually doesn't survive redeploys or
   restarts. Set `TURSO_DATABASE_URL` and `TURSO_AUTH_TOKEN` (see
   `.env.example`) to use a free [Turso](https://turso.tech) database
   instead, so your logged meals persist no matter what happens to the
   hosting. Without those set, it falls back to a local SQLite file that
   may get wiped on redeploy.
4. Set `ANTHROPIC_API_KEY` as an environment variable on the host the same
   way you'd put it in `.env` locally.
