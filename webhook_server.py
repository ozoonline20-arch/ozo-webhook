import os
import requests
from flask import Flask, request, jsonify

app = Flask(__name__)


@app.after_request
def add_cors_headers(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    return response


BOT_TOKEN = os.environ["BOT_TOKEN"]
ADMIN_CHAT_ID = os.environ["ADMIN_CHAT_ID"]
VALID_CODES = set(
    code.strip() for code in os.environ.get("VALID_CODES", "").split(",") if code.strip()
)

TELEGRAM_API = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"


def send_telegram(text):
    resp = requests.post(
        TELEGRAM_API,
        json={"chat_id": ADMIN_CHAT_ID, "text": text},
        timeout=10,
    )
    return resp.ok


@app.route("/order", methods=["POST", "OPTIONS"])
def order():
    if request.method == "OPTIONS":
        return "", 200

    data = request.get_json(force=True) or {}
    code = str(data.get("code", "")).strip()
    pseudo = str(data.get("pseudo", "")).strip() or "non renseigne"
    flavor = str(data.get("flavor", "")).strip() or "non choisi"
    time_slot = str(data.get("time_slot", "")).strip() or "non choisi"

    if code not in VALID_CODES:
        return jsonify({"ok": False, "error": "invalid_code"}), 403

    text = (
        "Nouvelle commande (lien web)\n"
        f"Pseudo Snapchat : {pseudo}\n"
        f"Gout : {flavor}\n"
        f"Creneau : {time_slot}"
    )

    if not send_telegram(text):
        return jsonify({"ok": False, "error": "telegram_error"}), 502

    return jsonify({"ok": True})


@app.route("/request-access", methods=["POST", "OPTIONS"])
def request_access():
    if request.method == "OPTIONS":
        return "", 200

    data = request.get_json(force=True) or {}
    pseudo = str(data.get("pseudo", "")).strip() or "non renseigne"
    referrer = str(data.get("referrer", "")).strip() or "non renseigne"

    text = (
        "Nouvelle demande d'acces (lien web)\n"
        f"Pseudo Snapchat : {pseudo}\n"
        f"Recommande par : {referrer}"
    )

    if not send_telegram(text):
        return jsonify({"ok": False, "error": "telegram_error"}), 502

    return jsonify({"ok": True})


@app.route("/", methods=["GET"])
def health():
    return "ok"


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
