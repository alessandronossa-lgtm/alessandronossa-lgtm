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


# =====================================================
# CONFIG
# =====================================================

app = Flask(__name__)

SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY:
    raise Exception("SECRET_KEY não configurada.")
app.secret_key = SECRET_KEY

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise Exception("DATABASE_URL não configurada.")

# Render às vezes fornece postgres:// (antigo)
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

app.config["SQLALCHEMY_DATABASE_URI"] = DATABASE_URL
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)

MP_ACCESS_TOKEN = os.getenv("MP_ACCESS_TOKEN")
if not MP_ACCESS_TOKEN:
    raise Exception("MP_ACCESS_TOKEN não configurado.")

sdk = mercadopago.SDK(MP_ACCESS_TOKEN)

# BASE_URL: recomendado setar no Render como https://promptsheet-backend.onrender.com
BASE_URL = os.getenv("BASE_URL", "https://promptsheet-backend.onrender.com").rstrip("/")


# =====================================================
# MODEL
# =====================================================

class Usuario(db.Model):
    __tablename__ = "usuario"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(150), unique=True, nullable=False)

    # senha real
    senha_hash = db.Column(db.String(255), nullable=False)

    # pagamento
    pago = db.Column(db.Boolean, default=False)
    payment_id = db.Column(db.String(100), nullable=True)

    criado_em = db.Column(db.DateTime, default=datetime.utcnow)

    def set_senha(self, senha: str) -> None:
        self.senha_hash = generate_password_hash(senha)

    def verificar_senha(self, senha: str) -> bool:
        return check_password_hash(self.senha_hash, senha)


# Criar tabelas (MVP ok)
with app.app_context():
    db.create_all()


# =====================================================
# AUTH HELPERS
# =====================================================

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated


def get_current_user():
    uid = session.get("user_id")
    if not uid:
        return None
    return Usuario.query.get(uid)


# =====================================================
# PAGES
# =====================================================

@app.route("/")
def index():
    usuario = get_current_user()
    return render_template("index.html", usuario=usuario)


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        senha = (request.form.get("senha") or "").strip()

        if not email or not senha:
            return "Preencha email e senha.", 400

        if Usuario.query.filter_by(email=email).first():
            return "Usuário já existe. Faça login.", 400

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
        senha = (request.form.get("senha") or "").strip()

        usuario = Usuario.query.filter_by(email=email).first()

        if not usuario or not usuario.verificar_senha(senha):
            return "Credenciais inválidas.", 401

        session["user_id"] = usuario.id
        return redirect(url_for("index"))

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))


# =====================================================
# MERCADO PAGO - CRIAR PREFERÊNCIA
# =====================================================

@app.route("/criar_preferencia", methods=["POST"])
@login_required
def criar_preferencia():
    usuario = get_current_user()
    if not usuario:
        return jsonify({"erro": "Usuário não autenticado."}), 401

    if usuario.pago:
        return jsonify({"erro": "Usuário já possui acesso."}), 400

    # Produto: ajuste preço aqui
    unit_price = 1.00

    preference_data = {
        "items": [
            {
                "title": "Planilha Premium PromptSheet",
                "quantity": 1,
                "currency_id": "BRL",
                "unit_price": unit_price
            }
        ],
        "payer": {"email": usuario.email},
        "back_urls": {
            "success": f"{BASE_URL}/sucesso",
            "failure": f"{BASE_URL}/erro",
            "pending": f"{BASE_URL}/pendente"
        },
        "auto_return": "approved",
        # Webhook para liberar no banco
        "notification_url": f"{BASE_URL}/webhook",
        # Amarra o pagamento ao usuário
        "external_reference": usuario.email
    }

    resp = sdk.preference().create(preference_data)
    mp_response = resp.get("response", {})
    init_point = mp_response.get("init_point")

    if not init_point:
        return jsonify({"erro": "Falha ao criar preferência no Mercado Pago.", "detalhe": mp_response}), 500

    return jsonify({"init_point": init_point})


# =====================================================
# MERCADO PAGO - WEBHOOK
# =====================================================

@app.route("/webhook", methods=["POST"])
def webhook():
    """
    Mercado Pago pode enviar formatos diferentes:
    - ?type=payment&data.id=...
    - {"type":"payment","data":{"id":"..."}}
    - topic=payment&id=...
    """
    try:
        payment_id = None

        # 1) querystring (comum)
        if request.args.get("type") == "payment" and request.args.get("data.id"):
            payment_id = request.args.get("data.id")

        # 2) querystring (topic/id)
        if request.args.get("topic") == "payment" and request.args.get("id"):
            payment_id = request.args.get("id")

        # 3) JSON body
        data = request.get_json(silent=True) or {}
        if not payment_id and data.get("type") == "payment":
            payment_id = (data.get("data") or {}).get("id")

        if not payment_id:
            return jsonify({"status": "ignored"}), 200

        payment_resp = sdk.payment().get(payment_id)
        payment = payment_resp.get("response", {})

        status = payment.get("status")
        email = payment.get("external_reference")

        # Para PIX pode vir pending por um tempo; só libera quando approved
        if status != "approved":
            return jsonify({"status": "not approved", "mp_status": status}), 200

        if not email:
            return jsonify({"status": "no email"}), 200

        usuario = Usuario.query.filter_by(email=email.strip().lower()).first()
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


# =====================================================
# ROTAS AUXILIARES (RETORNO MP)
# =====================================================

@app.route("/sucesso")
def sucesso():
    # Se o usuário estiver logado, cai na home e vê acesso liberado quando webhook marcar como pago.
    return redirect(url_for("index"))

@app.route("/erro")
def erro():
    return "Pagamento falhou."

@app.route("/pendente")
def pendente():
    return "Pagamento pendente. Aguarde a confirmação."


# =====================================================
# DOWNLOAD (SÓ LOGADO + PAGO)
# =====================================================

@app.route("/download")
@login_required
def download():
    usuario = get_current_user()
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

    return send_file(temp.name, as_attachment=True, download_name="PromptSheet.xlsx")


# =====================================================
# LOCAL
# =====================================================

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
