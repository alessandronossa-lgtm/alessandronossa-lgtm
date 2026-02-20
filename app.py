import os
import tempfile
from datetime import datetime
from functools import wraps

from flask import (
    Flask, render_template, request, redirect, jsonify,
    session, url_for, send_file
)
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from openpyxl import Workbook
import mercadopago

# ============================================================
# CONFIG
# ============================================================

app = Flask(__name__)

SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY:
    raise Exception("SECRET_KEY não configurada.")
app.secret_key = SECRET_KEY

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise Exception("DATABASE_URL não configurada.")

# Render/Postgres às vezes usa postgres:// (deprecated)
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

app.config["SQLALCHEMY_DATABASE_URI"] = DATABASE_URL
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)

MP_ACCESS_TOKEN = os.getenv("MP_ACCESS_TOKEN")
if not MP_ACCESS_TOKEN:
    raise Exception("MP_ACCESS_TOKEN não configurado.")

sdk = mercadopago.SDK(MP_ACCESS_TOKEN)

BASE_URL = os.getenv("BASE_URL", "https://promptsheet-backend.onrender.com").rstrip("/")


def external_url(endpoint: str, **kwargs) -> str:
    """Gera URL absoluta para usar no Mercado Pago (back_urls/notification_url)."""
    path = url_for(endpoint, _external=False, **kwargs)
    return f"{BASE_URL}{path}"


# ============================================================
# MODEL
# ============================================================

class Usuario(db.Model):
    __tablename__ = "usuario"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(150), unique=True, nullable=False)

    # senha (login real)
    senha_hash = db.Column(db.String(255), nullable=False)

    # acesso/pagamento
    pago = db.Column(db.Boolean, default=False)
    payment_id = db.Column(db.String(200))

    criado_em = db.Column(db.DateTime, default=datetime.utcnow)

    def set_senha(self, senha: str) -> None:
        self.senha_hash = generate_password_hash(senha)

    def verificar_senha(self, senha: str) -> bool:
        return check_password_hash(self.senha_hash, senha)


with app.app_context():
    db.create_all()


# ============================================================
# AUTH HELPERS
# ============================================================

def current_user():
    uid = session.get("user_id")
    if not uid:
        return None
    return Usuario.query.get(uid)


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated


# ============================================================
# ROUTES
# ============================================================

@app.route("/")
def index():
    usuario = current_user()
    return render_template("index.html", usuario=usuario)


# ------------------------
# REGISTER / LOGIN / LOGOUT
# ------------------------

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        senha = request.form.get("senha") or ""

        if not email or not senha:
            return "Preencha email e senha."

        if Usuario.query.filter_by(email=email).first():
            return "Usuário já existe. Faça login."

        usuario = Usuario(email=email, senha_hash="temp")
        usuario.set_senha(senha)

        db.session.add(usuario)
        db.session.commit()

        session["user_id"] = usuario.id
        return redirect(url_for("index"))

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        senha = request.form.get("senha") or ""

        usuario = Usuario.query.filter_by(email=email).first()

        if usuario and usuario.verificar_senha(senha):
            session["user_id"] = usuario.id
            return redirect(url_for("index"))

        return "Credenciais inválidas."

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))


# ------------------------
# CRIAR PREFERÊNCIA (checkout)
# ------------------------

@app.route("/criar_preferencia", methods=["POST"])
@login_required
def criar_preferencia():
    usuario = current_user()
    if not usuario:
        return jsonify({"erro": "não autenticado"}), 401

    if usuario.pago:
        return jsonify({"erro": "Usuário já possui acesso."}), 400

    preference_data = {
        "items": [
            {
                "title": "Planilha Premium PromptSheet",
                "quantity": 1,
                "currency_id": "BRL",
                "unit_price": 1.00
            }
        ],
        "payer": {"email": usuario.email},

        # URLs de retorno (melhor para PIX deixar auto_return=all)
        "back_urls": {
            "success": external_url("sucesso"),
            "failure": external_url("erro_pagamento"),
            "pending": external_url("pendente"),
        },
        "auto_return": "all",

        # Webhook definitivo
        "notification_url": external_url("webhook"),

        # Referência para achar o usuário depois no webhook
        "external_reference": usuario.email,
    }

    response = sdk.preference().create(preference_data)

    init_point = response.get("response", {}).get("init_point")
    if not init_point:
        return jsonify({"erro": "Falha ao criar preferência", "detalhe": response}), 500

    return jsonify({"init_point": init_point})


# ------------------------
# WEBHOOK (Mercado Pago)
# ------------------------

@app.route("/webhook", methods=["POST"])
def webhook():
    """
    O Mercado Pago pode enviar:
    - querystring: ?type=payment&data.id=...
    - ou body json: {"type":"payment","data":{"id":...}}
    """
    try:
        data = request.get_json(silent=True) or {}

        # 1) tenta pelo body
        event_type = data.get("type")
        payment_id = None
        if event_type == "payment":
            payment_id = (data.get("data") or {}).get("id")

        # 2) tenta pela querystring (v1/v2)
        if not payment_id:
            q_type = request.args.get("type") or request.args.get("topic")
            q_data_id = request.args.get("data.id") or request.args.get("id")
            if q_type in ("payment", "payment.created", "payment.updated") and q_data_id:
                payment_id = q_data_id

        if not payment_id:
            # outros eventos como merchant_order etc.
            return jsonify({"status": "ignored"}), 200

        # consulta o pagamento na API
        payment_response = sdk.payment().get(payment_id)
        payment = payment_response.get("response", {})
        status = payment.get("status")

        if status != "approved":
            return jsonify({"status": "not approved"}), 200

        email = payment.get("external_reference")
        if not email:
            # fallback: tenta pegar do payer
            payer = payment.get("payer") or {}
            email = payer.get("email")

        if not email:
            return jsonify({"status": "no email"}), 200

        usuario = Usuario.query.filter_by(email=email.lower()).first()
        if not usuario:
            return jsonify({"status": "user not found"}), 200

        # marca como pago
        if not usuario.pago:
            usuario.pago = True
            usuario.payment_id = str(payment_id)
            db.session.commit()

        return jsonify({"status": "success"}), 200

    except Exception as e:
        print("Erro webhook:", e)
        return jsonify({"erro": "erro interno"}), 500


# ------------------------
# PÁGINAS DE RETORNO
# ------------------------

@app.route("/sucesso")
@login_required
def sucesso():
    # Pode renderizar uma página bonita se quiser.
    return redirect(url_for("index"))


@app.route("/erro")
def erro_pagamento():
    return "Pagamento falhou."


@app.route("/pendente")
@login_required
def pendente():
    # Você já criou templates/pendente.html
    return render_template("pendente.html")


# ------------------------
# STATUS (polling do pendente.html)
# ------------------------

@app.route("/status")
@login_required
def status():
    usuario = current_user()
    return jsonify({"pago": bool(usuario and usuario.pago)})


# ------------------------
# DOWNLOAD (protegido)
# ------------------------

@app.route("/download")
@login_required
def download():
    usuario = current_user()
    if not usuario:
        return redirect(url_for("login"))

    if not usuario.pago:
        return "Acesso negado. Pagamento necessário."

    wb = Workbook()
    ws = wb.active
    ws["A1"] = "PromptSheet Premium"
    ws["A2"] = f"Usuário: {usuario.email}"
    ws["A3"] = f"Gerado em: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC"

    temp = tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx")
    wb.save(temp.name)

    return send_file(temp.name, as_attachment=True, download_name="promptsheet.xlsx")


# ============================================================
# RUN (local). No Render, quem sobe é o gunicorn.
# ============================================================

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
