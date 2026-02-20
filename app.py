import os
import tempfile
from datetime import datetime
from functools import wraps

import mercadopago
from flask import (
    Flask, render_template, request, redirect, jsonify,
    session, url_for, send_file
)
from flask_sqlalchemy import SQLAlchemy
from openpyxl import Workbook
from werkzeug.security import generate_password_hash, check_password_hash


# =========================
# APP / CONFIG
# =========================
app = Flask(__name__)

SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY:
    raise Exception("SECRET_KEY não configurada.")
app.secret_key = SECRET_KEY

BASE_URL = os.getenv("BASE_URL", "https://promptsheet-backend.onrender.com").rstrip("/")

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise Exception("DATABASE_URL não configurada.")

# Ajuste Render Postgres antigo
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

app.config["SQLALCHEMY_DATABASE_URI"] = DATABASE_URL
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db = SQLAlchemy(app)

MP_ACCESS_TOKEN = os.getenv("MP_ACCESS_TOKEN")
if not MP_ACCESS_TOKEN:
    raise Exception("MP_ACCESS_TOKEN não configurado.")

sdk = mercadopago.SDK(MP_ACCESS_TOKEN)

# Mercado Pago: por padrão "approved"
MP_AUTO_RETURN = os.getenv("MP_AUTO_RETURN", "approved")


# =========================
# MODEL
# =========================
class Usuario(db.Model):
    __tablename__ = "usuario"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(150), unique=True, nullable=False)

    # Login real
    senha_hash = db.Column(db.String(255), nullable=False)

    # Pagamento
    pago = db.Column(db.Boolean, default=False)
    payment_id = db.Column(db.String(200))
    criado_em = db.Column(db.DateTime, default=datetime.utcnow)

    def set_senha(self, senha: str) -> None:
        self.senha_hash = generate_password_hash(senha)

    def verificar_senha(self, senha: str) -> bool:
        return check_password_hash(self.senha_hash, senha)


with app.app_context():
    db.create_all()


# =========================
# AUTH HELPERS
# =========================
def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return fn(*args, **kwargs)
    return wrapper


def get_usuario_logado():
    uid = session.get("user_id")
    if not uid:
        return None
    return Usuario.query.get(uid)


# =========================
# HOME
# =========================
@app.route("/")
def index():
    usuario = get_usuario_logado()
    return render_template("index.html", usuario=usuario)


# =========================
# REGISTER / LOGIN / LOGOUT
# =========================
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        senha = request.form.get("senha") or ""

        if not email or not senha:
            return "Preencha e-mail e senha.", 400

        if Usuario.query.filter_by(email=email).first():
            return "Este e-mail já está cadastrado. Faça login.", 400

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

        return "Credenciais inválidas.", 400

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))


# =========================
# MERCADO PAGO - CRIAR PREFERÊNCIA (EXIGE LOGIN)
# =========================
@app.route("/criar_preferencia", methods=["POST"])
@login_required
def criar_preferencia():
    usuario = get_usuario_logado()
    if not usuario:
        return jsonify({"erro": "Não autenticado"}), 401

    if usuario.pago:
        return jsonify({"erro": "Sua conta já tem acesso liberado."}), 400

    preference_data = {
        "items": [
            {
                "title": "PromptSheet Premium",
                "quantity": 1,
                "currency_id": "BRL",
                "unit_price": 1.00
            }
        ],
        "payer": {"email": usuario.email},

        # PIX frequentemente volta como pending → manda para /pendente sempre
        "back_urls": {
            "success": f"{BASE_URL}/pendente",
            "failure": f"{BASE_URL}/erro",
            "pending": f"{BASE_URL}/pendente"
        },

        # Deixo configurável (padrão approved)
        "auto_return": MP_AUTO_RETURN,

        # Webhook
        "notification_url": f"{BASE_URL}/webhook",

        # Referência do seu usuário
        "external_reference": usuario.email
    }

    resp = sdk.preference().create(preference_data)
    init_point = resp.get("response", {}).get("init_point")

    if not init_point:
        return jsonify({"erro": "Falha ao gerar pagamento", "detalhes": resp}), 500

    return jsonify({"init_point": init_point})


# =========================
# WEBHOOK - CONFIRMA PAGAMENTO
# =========================
@app.route("/webhook", methods=["POST"])
def webhook():
    try:
        data = request.json or {}

        # Alguns envios chegam como:
        # /webhook?data.id=XXXX&type=payment
        # Então pegamos também querystring
        if data.get("type") != "payment":
            # tenta querystring
            q_type = request.args.get("type")
            if q_type != "payment":
                return jsonify({"status": "ignored"}), 200

            payment_id = request.args.get("data.id")
        else:
            payment_id = (data.get("data") or {}).get("id")

        if not payment_id:
            return jsonify({"status": "no payment id"}), 200

        payment_response = sdk.payment().get(payment_id)
        payment = payment_response.get("response", {})

        status = payment.get("status")
        email = payment.get("external_reference")

        if status != "approved" or not email:
            return jsonify({"status": "not approved"}), 200

        usuario = Usuario.query.filter_by(email=email).first()
        if not usuario:
            return jsonify({"status": "user not found"}), 200

        if not usuario.pago:
            usuario.pago = True
            usuario.payment_id = str(payment_id)
            db.session.commit()

        return jsonify({"status": "success"}), 200

    except Exception as e:
        print("Erro webhook:", e)
        return jsonify({"erro": "erro interno"}), 500


# =========================
# STATUS - PARA PÁGINA PENDENTE POLLAR
# =========================
@app.route("/status", methods=["GET"])
@login_required
def status():
    usuario = get_usuario_logado()
    if not usuario:
        return jsonify({"ok": False, "paid": False}), 401
    return jsonify({"ok": True, "paid": bool(usuario.pago)}), 200


# =========================
# PENDENTE - MOSTRA TELA E FICA CONSULTANDO /status
# =========================
@app.route("/pendente")
@login_required
def pendente():
    usuario = get_usuario_logado()
    return render_template("pendente.html", usuario=usuario)


# =========================
# DOWNLOAD (PROTEGIDO)
# =========================
@app.route("/download")
@login_required
def download():
    usuario = get_usuario_logado()
    if not usuario:
        return redirect(url_for("login"))

    if not usuario.pago:
        return "Acesso negado. Pagamento necessário.", 403

    wb = Workbook()
    ws = wb.active
    ws["A1"] = "PromptSheet Premium"
    ws["A2"] = f"Usuário: {usuario.email}"
    ws["A3"] = f"Gerado em: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC"

    temp = tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx")
    wb.save(temp.name)

    return send_file(temp.name, as_attachment=True, download_name="promptsheet.xlsx")


# =========================
# AUXILIARES
# =========================
@app.route("/erro")
def erro():
    return "Pagamento falhou ou foi cancelado."


# =========================
# LOCAL
# =========================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
