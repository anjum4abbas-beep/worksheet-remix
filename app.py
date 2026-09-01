import base64
import io
import json
import os
import time
from collections import defaultdict, deque

from flask import Flask, request, jsonify, render_template
from anthropic import Anthropic, APIStatusError, APIConnectionError

from prompts import SYSTEM_PROMPT, build_user_message, build_user_message_for_pdf

app = Flask(__name__)

MODEL = os.environ.get("SEN_WORKSHEETS_MODEL", "claude-sonnet-4-5")

# Kept modest to stay within the free hosting tier's limited RAM - a single
# worker process on that tier doesn't have much headroom for a large file
# held in memory plus its base64-encoded copy at the same time.
MAX_PDF_BYTES = 8 * 1024 * 1024

# --- Hosted-beta configuration (all optional; sensible defaults for local/dev use) ---
# Set ANTHROPIC_API_KEY on the server so pilot testers never need their own key.
# Set BETA_ACCESS_CODE to require a shared passphrase before anyone can generate
# (keeps a public URL from being hit by strangers/bots and running up your bill).
# RATE_LIMIT_PER_DAY caps generations per visitor per rolling 24h.
SERVER_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "").strip()
ACCESS_CODE = os.environ.get("BETA_ACCESS_CODE", "").strip()
RATE_LIMIT_PER_DAY = int(os.environ.get("RATE_LIMIT_PER_DAY", "15"))

# In-memory only: fine for a small beta on a single instance. Resets on restart
# and doesn't share state across multiple instances - not meant to survive
# real scale, just to stop accidental/malicious runaway API cost during a beta.
_request_log = defaultdict(deque)


def _client_id() -> str:
    # Best-effort visitor identity for rate limiting only, not security.
    return request.headers.get("X-Forwarded-For", request.remote_addr or "unknown").split(",")[0].strip()


def _over_rate_limit(client_id: str) -> bool:
    now = time.time()
    window = _request_log[client_id]
    while window and now - window[0] > 86400:
        window.popleft()
    if len(window) >= RATE_LIMIT_PER_DAY:
        return True
    window.append(now)
    return False


def extract_text_from_upload(file_storage) -> str:
    """Best-effort text extraction for .txt and .docx uploads. PDFs are handled
    separately in the route below - Claude reads those directly, no extraction
    needed here."""
    filename = (file_storage.filename or "").lower()
    data = file_storage.read()

    if filename.endswith(".docx"):
        from docx import Document

        doc = Document(io.BytesIO(data))
        return "\n".join(p.text for p in doc.paragraphs)

    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        raise ValueError(
            "Couldn't read that file as text. Please paste the worksheet text "
            "directly, or upload a .txt/.docx/.pdf file."
        )


def call_model(api_key: str, theme: str, notes: str, worksheet_text: str = None, pdf_bytes: bytes = None) -> dict:
    """Either worksheet_text (pasted/.txt/.docx) or pdf_bytes (a scanned or
    digital PDF worksheet) must be given - not both. When a PDF is given,
    Claude reads the worksheet directly from the document rather than us
    extracting text first, so scanned/photocopied worksheets work too."""
    client = Anthropic(api_key=api_key)

    if pdf_bytes is not None:
        content = [
            {
                "type": "document",
                "source": {
                    "type": "base64",
                    "media_type": "application/pdf",
                    "data": base64.standard_b64encode(pdf_bytes).decode("ascii"),
                },
            },
            {"type": "text", "text": build_user_message_for_pdf(theme, notes)},
        ]
    else:
        content = build_user_message(worksheet_text, theme, notes)

    response = client.messages.create(
        model=MODEL,
        max_tokens=4096,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": content}],
    )

    raw = "".join(block.text for block in response.content if block.type == "text")

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


@app.route("/api/config")
def config():
    """Tells the frontend what it needs to collect from the visitor before
    they can generate: their own API key (only if the server has none), and/or
    a shared access code (only if the operator set one)."""
    return jsonify({
        "requires_client_key": not bool(SERVER_API_KEY),
        "requires_access_code": bool(ACCESS_CODE),
    })


@app.route("/api/rewrite", methods=["POST"])
def rewrite():
    if ACCESS_CODE:
        supplied_code = request.headers.get("X-Access-Code", "").strip()
        if supplied_code != ACCESS_CODE:
            return jsonify({"error": "That access code isn't right. Check it and try again."}), 403

    api_key = SERVER_API_KEY or request.headers.get("X-Api-Key", "").strip()
    if not api_key:
        return jsonify({"error": "No API key provided. Add your Anthropic API key in Settings."}), 401

    if SERVER_API_KEY and _over_rate_limit(_client_id()):
        return jsonify({
            "error": f"This beta is limited to {RATE_LIMIT_PER_DAY} worksheets per person per day, "
                     "to keep costs in check while we're testing. Please try again tomorrow."
        }), 429

    theme = request.form.get("theme", "").strip()
    notes = request.form.get("notes", "").strip()
    worksheet_text = request.form.get("worksheet_text", "").strip()
    pdf_bytes = None

    uploaded = request.files.get("file")
    if uploaded and uploaded.filename:
        filename = uploaded.filename.lower()
        if filename.endswith(".pdf"):
            uploaded.seek(0, io.SEEK_END)
            size = uploaded.tell()
            uploaded.seek(0)
            if size > MAX_PDF_BYTES:
                return jsonify({
                    "error": f"That PDF is too large ({size // (1024*1024)}MB). "
                             f"Please upload one under {MAX_PDF_BYTES // (1024*1024)}MB."
                }), 400
            pdf_bytes = uploaded.read()
        else:
            try:
                worksheet_text = extract_text_from_upload(uploaded)
            except ValueError as e:
                return jsonify({"error": str(e)}), 400

    if not worksheet_text and not pdf_bytes:
        return jsonify({"error": "No worksheet found. Paste text or upload a .txt/.docx/.pdf file."}), 400
    if not theme:
        return jsonify({"error": "Please enter the child's special interest / theme."}), 400

    try:
        result = call_model(api_key, theme, notes, worksheet_text=worksheet_text or None, pdf_bytes=pdf_bytes)
    except APIStatusError as e:
        status = e.status_code
        if status == 401:
            msg = "That API key was rejected by Anthropic. Double check it in Settings." if not SERVER_API_KEY \
                else "The site's API key was rejected by Anthropic - the operator needs to check it."
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
    debug = os.environ.get("FLASK_DEBUG", "1") == "1"
    port = int(os.environ.get("PORT", "5050"))
    app.run(debug=debug, host="0.0.0.0", port=port)
