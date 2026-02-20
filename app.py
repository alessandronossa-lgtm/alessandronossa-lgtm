import os
import tempfile
from datetime import datetime
from functools import wraps

from flask import (
    Flask, render_template, request, redirect,
    jsonify, session, url_for, send_file
)
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash

import mercadopago
from openpyxl import Workbook

# ======================================
# CONFIG
# ======================================

app = Flask(__name__)

SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY:
    raise RuntimeError("SECRET_KEY não configurada no Render.")
app.secret_key = SECRET_KEY

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL não configurada no Render.")

# Render às vezes fornece postgres:// (antigo)
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

app.config["SQLALCHEMY_DATABASE_URI"] = DATABASE_URL
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db = SQLAlchemy(app)

MP_ACCESS_TOKEN = os.getenv("MP_ACCESS_TOKEN")
if not MP_ACCESS_TOKEN:
    raise RuntimeError("MP_ACCESS_TOKEN não configurado no Render.")

sdk = mercadopago.SDK(MP_ACCESS_TOKEN)

# ======================================
# MODEL
# ======================================

class Usuario(db.Model):
    __tablename__ = "usuarios"  # evita conflito com tabela antiga "usuario"
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(150), unique=True, nullable=False, index=True)
    senha_hash = db.Column(db.String(255), nullable=False)

    pago = db.Column(db.Boolean, default=False, nullable=False)
    payment_id = db.Column(db.String(120))
    criado_em = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    def set_senha(self, senha: str):
        self.senha_hash = generate_password_hash(senha)

    def verificar_senha(self, senha: str) -> bool:
        return check_password_hash(self.senha_hash, senha)

with app.app_context():
    db.create_all()

# ======================================
# AUTH HELPERS
# ======================================

def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return fn(*args, **kwargs)
    return wrapper

def current_user():
    uid = session.get("user_id")
    if not uid:
        return None
    return db.session.get(Usuario, uid)

def external_url(endpoint: str, **values) -> str:
    """
    Gera URL externa. Se BASE_URL existir, usa ela.
    Se não, usa url_for(_external=True) baseado no host atual.
    """
    base = os.getenv("BASE_URL")
    if base:
        base = base.rstrip("/")
        path = url_for(endpoint, **values)
        return f"{base}{path}"
    return url_for(endpoint, _external=True, **values)

# ======================================
# ROUTES
# ======================================

@app.route("/")
def index():
    usuario = current_user()
    return render_template("index.html", usuario=usuario)

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        senha = request.form.get("senha") or ""

        if not email or not senha:
            return render_template("register.html", erro="Preencha email e senha.")

        if Usuario.query.filter_by(email=email).first():
            return render_template("register.html", erro="Esse email já está cadastrado. Faça login.")

        usuario = Usuario(email=email)
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

        return render_template("login.html", erro="Email ou senha inválidos.")

    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))

# ======================================
# PAGAMENTO (exige login)
# ======================================

@app.route("/criar_preferencia", methods=["POST"])
@login_required
def criar_preferencia():
    usuario = current_user()
    if not usuario:
        return jsonify({"erro": "Não autenticado."}), 401

    if usuario.pago:
        return jsonify({"erro": "Usuário já possui acesso."}), 400

    preference_data = {
        "items": [{
            "title": "Planilha Premium PromptSheet",
            "quantity": 1,
            "currency_id": "BRL",
            "unit_price": 1.00
        }],
        "payer": {"email": usuario.email},
        "external_reference": usuario.email,
        "back_urls": {
            "success": external_url("sucesso"),
            "failure": external_url("erro_pagamento"),
            "pending": external_url("pendente")
        },
        "auto_return": "approved",
        "notification_url": external_url("webhook")
    }

    resp = sdk.preference().create(preference_data)
    init_point = resp.get("response", {}).get("init_point")
    if not init_point:
        return jsonify({"erro": "Mercado Pago não retornou init_point.", "detalhe": resp}), 500

    return jsonify({"init_point": init_point})

# ======================================
# WEBHOOK MP
# ======================================

@app.route("/webhook", methods=["POST"])
def webhook():
    try:
        data = request.get_json(silent=True) or {}

        # MP pode mandar em formatos diferentes
        # v1: {"type":"payment","data":{"id":"123"}}
        # legacy: query params: ?type=payment&data.id=123
        event_type = data.get("type") or request.args.get("type")
        payment_id = None

        if data.get("data") and isinstance(data["data"], dict):
            payment_id = data["data"].get("id")

        if not payment_id:
            payment_id = request.args.get("data.id") or request.args.get("id")

        if event_type != "payment" or not payment_id:
            return jsonify({"status": "ignored"}), 200

        payment_resp = sdk.payment().get(payment_id)
        payment = payment_resp.get("response", {})

        status = payment.get("status")
        email = payment.get("external_reference")

        if status != "approved" or not email:
            return jsonify({"status": "not_approved"}), 200

        usuario = Usuario.query.filter_by(email=email).first()
        if usuario and not usuario.pago:
            usuario.pago = True
            usuario.payment_id = str(payment_id)
            db.session.commit()

        return jsonify({"status": "ok"}), 200

    except Exception as e:
        print("Erro webhook:", e)
        return jsonify({"erro": "erro interno"}), 500

# ======================================
# DOWNLOAD (protegido)
# ======================================

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
    ws["A3"] = f"Payment ID: {usuario.payment_id or '-'}"

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx")
    wb.save(tmp.name)

    return send_file(tmp.name, as_attachment=True, download_name="PromptSheet-Premium.xlsx")

# ======================================
# AUX
# ======================================

@app.route("/sucesso")
@login_required
def sucesso():
    return redirect(url_for("index"))

@app.route("/erro")
def erro_pagamento():
    return "Pagamento falhou."

@app.route("/pendente")
def pendente():
    return """
    <h2>Pagamento pendente...</h2>
    <p>Se você acabou de pagar no Pix, aguarde a confirmação.</p>
    <script>setTimeout(()=>location.href='/', 3000);</script>
    """

# ======================================
# LOCAL ONLY
# ======================================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", "10000"))
    app.run(host="0.0.0.0", port=port)
