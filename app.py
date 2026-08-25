import io
import json
import os

from flask import Flask, request, jsonify, render_template
from anthropic import Anthropic, APIStatusError, APIConnectionError

from prompts import SYSTEM_PROMPT, build_user_message

app = Flask(__name__)

MODEL = os.environ.get("SEN_WORKSHEETS_MODEL", "claude-sonnet-4-5")


def extract_text_from_upload(file_storage) -> str:
    """Best-effort text extraction for uploaded worksheets. Supports .txt and .docx.
    PDF/image worksheets aren't parsed here yet - see README for why."""
    filename = (file_storage.filename or "").lower()
    data = file_storage.read()

    if filename.endswith(".docx"):
        from docx import Document

        doc = Document(io.BytesIO(data))
        return "\n".join(p.text for p in doc.paragraphs)

    # Fall back to treating it as plain text (.txt, .md, or anything text-ish)
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        raise ValueError(
            "Couldn't read that file as text. For now, please paste the worksheet "
            "text directly, or upload a .txt/.docx file."
        )


def call_model(api_key: str, worksheet_text: str, theme: str, notes: str) -> dict:
    client = Anthropic(api_key=api_key)
    user_message = build_user_message(worksheet_text, theme, notes)

    response = client.messages.create(
        model=MODEL,
        max_tokens=4096,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_message}],
    )

    raw = "".join(block.text for block in response.content if block.type == "text")

    # The model is instructed to return bare JSON, but strip markdown fences
    # defensively in case it wraps the output anyway.
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.startswith("json"):
            cleaned = cleaned[4:]
        cleaned = cleaned.strip()

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as e:
        raise ValueError(f"Model didn't return valid JSON: {e}\n\nRaw output:\n{raw}")


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/rewrite", methods=["POST"])
def rewrite():
    api_key = request.headers.get("X-Api-Key", "").strip()
    if not api_key:
        return jsonify({"error": "No API key provided. Add your Anthropic API key in Settings."}), 401

    theme = request.form.get("theme", "").strip()
    notes = request.form.get("notes", "").strip()
    worksheet_text = request.form.get("worksheet_text", "").strip()

    if "file" in request.files and request.files["file"].filename:
        try:
            worksheet_text = extract_text_from_upload(request.files["file"])
        except ValueError as e:
            return jsonify({"error": str(e)}), 400

    if not worksheet_text:
        return jsonify({"error": "No worksheet text found. Paste text or upload a .txt/.docx file."}), 400
    if not theme:
        return jsonify({"error": "Please enter the child's special interest / theme."}), 400

    try:
        result = call_model(api_key, worksheet_text, theme, notes)
    except APIStatusError as e:
        status = e.status_code
        if status == 401:
            msg = "That API key was rejected by Anthropic. Double check it in Settings."
        elif status == 429:
            msg = "Rate limited by the Anthropic API. Wait a moment and try again."
        else:
            msg = f"Anthropic API error ({status}): {e.message}"
        return jsonify({"error": msg}), 502
    except APIConnectionError:
        return jsonify({"error": "Couldn't reach the Anthropic API. Check your network connection."}), 502
    except ValueError as e:
        return jsonify({"error": str(e)}), 502

    if isinstance(result, dict) and result.get("error"):
        return jsonify({"error": result["error"]}), 422

    return jsonify(result)


if __name__ == "__main__":
    app.run(debug=True, host="127.0.0.1", port=5050)
