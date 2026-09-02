# Calorie Tracker

A small personal calorie tracker that runs on your own machine. No account,
no hosting, no cloud database — just a local web page backed by a SQLite
file.

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
