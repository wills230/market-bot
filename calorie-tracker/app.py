"""
Personal calorie tracker. No account/login.

Log meals three ways:
  - type in calories yourself
  - describe the meal in words and let Claude estimate it
  - upload a photo of the meal and let Claude estimate it

Storage is a local SQLite file by default, or a remote Turso database when
TURSO_DATABASE_URL is set (see db.py) - used when this is deployed to a host
without a permanent disk.

Run locally with:  python app.py
Then open:          http://127.0.0.1:5000
"""

import base64
import io
import os
import uuid
from datetime import date, datetime, timedelta

from dotenv import load_dotenv
from flask import Flask, jsonify, redirect, render_template, request, url_for
from PIL import Image

import db

load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, "static", "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

ANTHROPIC_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")

app = Flask(__name__)
app.teardown_appcontext(db.close_local)


# ------------------------------------------------------------------ helpers

def get_setting(key, default=None):
    row = db.query_one("SELECT value FROM settings WHERE key = ?", (key,))
    return row["value"] if row else default


def set_setting(key, value):
    db.execute(
        "INSERT INTO settings (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )


def parse_date_arg(value):
    if value:
        try:
            return datetime.strptime(value, "%Y-%m-%d").date()
        except ValueError:
            pass
    return date.today()


def resize_image_to_jpeg_b64(file_storage, max_dim=1024):
    img = Image.open(file_storage.stream)
    img = img.convert("RGB")
    img.thumbnail((max_dim, max_dim))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return buf.getvalue()


NUTRITION_TOOL = {
    "name": "estimate_nutrition",
    "description": "Log a best-guess nutrition estimate for a meal.",
    "input_schema": {
        "type": "object",
        "properties": {
            "item": {"type": "string", "description": "Short name of the food/meal, e.g. 'Chicken burrito bowl'"},
            "calories": {"type": "integer", "description": "Best-guess total calories (kcal) for the whole meal/portion shown or described."},
            "protein_g": {"type": "number", "description": "Estimated grams of protein"},
            "carbs_g": {"type": "number", "description": "Estimated grams of carbohydrate"},
            "fat_g": {"type": "number", "description": "Estimated grams of fat"},
            "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
            "notes": {"type": "string", "description": "One short sentence on assumptions made (portion size, ingredients guessed, etc.)"},
        },
        "required": ["item", "calories", "confidence"],
    },
}

SYSTEM_PROMPT = (
    "You are a nutrition-estimation assistant inside a personal calorie tracker. "
    "You are given either a text description of a meal, or a photo of a meal (optionally with a caption). "
    "Estimate calories and macros as best you can using typical portion sizes and common recipes when exact "
    "amounts aren't given. Always call the estimate_nutrition tool with your single best estimate — never ask "
    "a clarifying question and never refuse, even if uncertain. Reflect real uncertainty in the 'confidence' field "
    "and briefly note key assumptions in 'notes' instead of asking follow-up questions."
)


def call_claude(content_blocks):
    if not ANTHROPIC_API_KEY:
        raise RuntimeError(
            "No ANTHROPIC_API_KEY set. Add it to calorie-tracker/.env to use AI analysis "
            "(manual entry still works without it)."
        )
    import anthropic

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    resp = client.messages.create(
        model=ANTHROPIC_MODEL,
        max_tokens=500,
        system=SYSTEM_PROMPT,
        tools=[NUTRITION_TOOL],
        tool_choice={"type": "tool", "name": "estimate_nutrition"},
        messages=[{"role": "user", "content": content_blocks}],
    )
    for block in resp.content:
        if block.type == "tool_use" and block.name == "estimate_nutrition":
            return block.input
    raise RuntimeError("Claude did not return a nutrition estimate. Try again.")


# -------------------------------------------------------------------- views

@app.route("/")
def index():
    day = parse_date_arg(request.args.get("date"))
    day_str = day.isoformat()
    entries = db.query(
        "SELECT * FROM entries WHERE entry_date = ? ORDER BY entry_time ASC, id ASC",
        (day_str,),
    )
    total_calories = sum(e["calories"] for e in entries)
    total_protein = sum(e["protein_g"] or 0 for e in entries)
    total_carbs = sum(e["carbs_g"] or 0 for e in entries)
    total_fat = sum(e["fat_g"] or 0 for e in entries)
    goal = get_setting("daily_goal")

    return render_template(
        "index.html",
        entries=entries,
        day=day,
        day_str=day_str,
        prev_day=(day - timedelta(days=1)).isoformat(),
        next_day=(day + timedelta(days=1)).isoformat(),
        is_today=(day == date.today()),
        total_calories=total_calories,
        total_protein=round(total_protein, 1),
        total_carbs=round(total_carbs, 1),
        total_fat=round(total_fat, 1),
        goal=goal,
        has_api_key=bool(ANTHROPIC_API_KEY),
    )


@app.route("/add", methods=["POST"])
def add_entry():
    f = request.form
    day_str = f.get("entry_date") or date.today().isoformat()

    def to_num(name):
        v = f.get(name)
        return float(v) if v not in (None, "") else None

    db.execute(
        """
        INSERT INTO entries
            (entry_date, entry_time, description, calories, protein_g, carbs_g, fat_g, source, photo_path, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            day_str,
            datetime.now().strftime("%H:%M"),
            f.get("description", "").strip(),
            int(float(f.get("calories", 0) or 0)),
            to_num("protein_g"),
            to_num("carbs_g"),
            to_num("fat_g"),
            f.get("source", "manual"),
            f.get("photo_path") or None,
            datetime.now().isoformat(timespec="seconds"),
        ),
    )
    return redirect(url_for("index", date=day_str))


@app.route("/delete/<int:entry_id>", methods=["POST"])
def delete_entry(entry_id):
    row = db.query_one("SELECT photo_path FROM entries WHERE id = ?", (entry_id,))
    if row and row["photo_path"]:
        path = os.path.join(BASE_DIR, "static", row["photo_path"].lstrip("/"))
        if os.path.exists(path):
            os.remove(path)
    db.execute("DELETE FROM entries WHERE id = ?", (entry_id,))
    return redirect(request.referrer or url_for("index"))


@app.route("/goal", methods=["POST"])
def set_goal():
    value = request.form.get("daily_goal", "").strip()
    if value:
        set_setting("daily_goal", value)
    else:
        set_setting("daily_goal", "")
    return redirect(request.referrer or url_for("index"))


@app.route("/api/analyze/text", methods=["POST"])
def analyze_text():
    data = request.get_json(force=True) or {}
    description = (data.get("description") or "").strip()
    if not description:
        return jsonify({"error": "Describe the meal first."}), 400
    try:
        estimate = call_claude([{"type": "text", "text": f"Meal description: {description}"}])
    except Exception as e:  # noqa: BLE001 - surface any failure to the UI
        return jsonify({"error": str(e)}), 400
    return jsonify(estimate)


@app.route("/api/analyze/photo", methods=["POST"])
def analyze_photo():
    photo = request.files.get("photo")
    description = (request.form.get("description") or "").strip()
    if not photo or photo.filename == "":
        return jsonify({"error": "Choose a photo first."}), 400

    try:
        jpeg_bytes = resize_image_to_jpeg_b64(photo)
    except Exception:
        return jsonify({"error": "Couldn't read that image file."}), 400

    filename = f"{uuid.uuid4().hex}.jpg"
    with open(os.path.join(UPLOAD_DIR, filename), "wb") as fh:
        fh.write(jpeg_bytes)
    photo_path = f"uploads/{filename}"

    content = [
        {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/jpeg",
                "data": base64.b64encode(jpeg_bytes).decode("ascii"),
            },
        },
        {
            "type": "text",
            "text": f"Photo of a meal. Caption from the user (may be empty): {description or '(none)'}",
        },
    ]

    try:
        estimate = call_claude(content)
    except Exception as e:  # noqa: BLE001
        return jsonify({"error": str(e), "photo_path": photo_path}), 400

    estimate["photo_path"] = photo_path
    return jsonify(estimate)


@app.route("/history")
def history():
    rows = db.query(
        """
        SELECT entry_date, SUM(calories) AS total_calories, COUNT(*) AS entry_count
        FROM entries
        GROUP BY entry_date
        ORDER BY entry_date DESC
        LIMIT 60
        """
    )
    goal = get_setting("daily_goal")
    return render_template("history.html", rows=rows, goal=goal)


with app.app_context():
    db.init_db()

if __name__ == "__main__":
    # Running under a host (e.g. Render) sets PORT - bind to all interfaces then.
    # Running on your own machine, stay on localhost only.
    port = os.environ.get("PORT")
    if port:
        print(f"\nCalorie tracker starting on port {port}.\n")
        app.run(host="0.0.0.0", port=int(port), debug=False)
    else:
        print("\nCalorie tracker running locally.")
        print("Open http://127.0.0.1:5000 in your browser.\n")
        app.run(host="127.0.0.1", port=5000, debug=True)
