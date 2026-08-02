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

# --- Supabase (traçabilité des codes) ---
# Ces deux variables sont a definir dans Render (Environment) :
#   SUPABASE_URL = https://xxxx.supabase.co
#   SUPABASE_KEY = ta cle secrete (sb_secret...)
SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")

TELEGRAM_API = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"


def send_telegram(text):
    resp = requests.post(
        TELEGRAM_API,
        json={"chat_id": ADMIN_CHAT_ID, "text": text},
        timeout=10,
    )
    return resp.ok


def supabase_enabled():
    """Vrai seulement si les deux variables Supabase sont configurees."""
    return bool(SUPABASE_URL and SUPABASE_KEY)


def supabase_headers():
    return {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
    }


def enregistrer_usage_code(code, pseudo):
    """Associe le pseudo au code dans la table `codes` (colonnes pseudo + statut).
    Ne bloque jamais la commande : en cas de souci, on ignore l'erreur.
    Retourne (ok, info) pour l'affichage dans la notification."""
    if not supabase_enabled():
        return False, "supabase non configure"
    try:
        # 1) On regarde a qui appartient deja ce code (pour reperer un partage)
        get_url = (
            f"{SUPABASE_URL}/rest/v1/codes"
            f"?code=eq.{code}&select=pseudo,statut"
        )
        r = requests.get(get_url, headers=supabase_headers(), timeout=8)
        print(f"[SUPABASE GET] status={r.status_code} body={r.text[:300]}", flush=True)
        ancien_pseudo = ""
        if r.ok and isinstance(r.json(), list) and r.json():
            ancien_pseudo = (r.json()[0].get("pseudo") or "").strip()

        # 2) On met a jour la ligne du code : on note le pseudo et statut "utilise"
        patch_url = f"{SUPABASE_URL}/rest/v1/codes?code=eq.{code}"
        payload = {"pseudo": pseudo, "statut": "utilise"}
        rp = requests.patch(
            patch_url,
            headers=supabase_headers(),
            json=payload,
            timeout=8,
        )
        print(f"[SUPABASE PATCH] status={rp.status_code} body={rp.text[:300]}", flush=True)
        if not rp.ok:
            return False, "echec enregistrement"

        # 3) Info utile : si le code etait deja associe a quelqu'un d'autre
        if ancien_pseudo and ancien_pseudo.lower() != pseudo.lower():
            return True, f"ATTENTION : code deja associe a {ancien_pseudo}"
        return True, "enregistre"
    except Exception as e:
        print(f"[SUPABASE EXCEPTION] {repr(e)}", flush=True)
        return False, "erreur reseau supabase"


@app.route("/order", methods=["POST", "OPTIONS"])
def order():
    if request.method == "OPTIONS":
        return "", 200

    data = request.get_json(force=True) or {}
    code = str(data.get("code", "")).strip()
    pseudo = str(data.get("pseudo", "")).strip() or "non renseigne"
    adresse = str(data.get("adresse", "")).strip() or "non renseignee"
    modele = str(data.get("modele", "")).strip() or "non choisi"
    flavor = str(data.get("flavor", "")).strip() or "non renseigne"
    time_slot = str(data.get("time_slot", "")).strip() or "non choisi"
    payment = str(data.get("payment", "")).strip() or "non choisi"
    note = str(data.get("note", "")).strip() or "aucune"
    total = str(data.get("total", "")).strip()

    if code not in VALID_CODES:
        return jsonify({"ok": False, "error": "invalid_code"}), 403

    # Traçabilité Supabase (n'empeche jamais la commande de partir)
    trace_info = ""
    if supabase_enabled():
        ok_trace, info = enregistrer_usage_code(code, pseudo)
        trace_info = info

    text = (
        "Nouvelle commande (lien web)\n"
        f"Pseudo Snapchat : {pseudo}\n"
        f"Code utilise : {code}\n"
        f"Adresse : {adresse}\n"
        f"Modele : {modele}\n"
        f"Gout : {flavor}\n"
        f"Creneau : {time_slot}\n"
        f"Paiement : {payment}\n"
        f"Note : {note}"
    )
    if total:
        text += f"\nTotal : {total} EUR"
    # On ajoute un avertissement dans la notif seulement si code deja associe a qqn d'autre
    if trace_info.startswith("ATTENTION"):
        text += f"\n\u26A0 {trace_info}"

    if not send_telegram(text):
        return jsonify({"ok": False, "error": "telegram_error"}), 502

    return jsonify({"ok": True})


@app.route("/check-code", methods=["POST", "OPTIONS"])
def check_code():
    if request.method == "OPTIONS":
        return "", 200

    data = request.get_json(force=True) or {}
    code = str(data.get("code", "")).strip()

    if code not in VALID_CODES:
        return jsonify({"ok": False, "error": "invalid_code"}), 403

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
