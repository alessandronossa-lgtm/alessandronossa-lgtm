import os
from flask import Flask, render_template, request, redirect, jsonify, session, url_for, send_file
import mercadopago
from flask_sqlalchemy import SQLAlchemy
from openpyxl import Workbook
from datetime import datetime
import tempfile

# ======================================
# CONFIGURAÇÃO
# ======================================

app = Flask(__name__)

if not os.getenv("SECRET_KEY"):
    raise Exception("SECRET_KEY não configurada.")

app.secret_key = os.getenv("SECRET_KEY")

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise Exception("DATABASE_URL não configurada.")

# Ajuste necessário para Render/Postgres
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

app.config["SQLALCHEMY_DATABASE_URI"] = DATABASE_URL
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)

MP_ACCESS_TOKEN = os.getenv("MP_ACCESS_TOKEN")
if not MP_ACCESS_TOKEN:
    raise Exception("MP_ACCESS_TOKEN não configurado.")

sdk = mercadopago.SDK(MP_ACCESS_TOKEN)

# ======================================
# MODELO
# ======================================

class Usuario(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(150), unique=True, nullable=False)
    pago = db.Column(db.Boolean, default=False)
    payment_id = db.Column(db.String(100))
    criado_em = db.Column(db.DateTime, default=datetime.utcnow)

with app.app_context():
    db.create_all()

# ======================================
# HOME
# ======================================

@app.route("/")
def index():
    email = session.get("email")
    usuario = None

    if email:
        usuario = Usuario.query.filter_by(email=email).first()

    return render_template("index.html", usuario=usuario)

# ======================================
# CRIAR PAGAMENTO
# ======================================

@app.route("/criar_preferencia", methods=["POST"])
def criar_preferencia():

    email = request.form.get("email")

    if not email:
        return jsonify({"erro": "Email obrigatório"}), 400

    session["email"] = email

    usuario = Usuario.query.filter_by(email=email).first()
    if not usuario:
        usuario = Usuario(email=email)
        db.session.add(usuario)
        db.session.commit()

    preference_data = {
        "items": [
            {
                "title": "Planilha Premium PromptSheet",
                "quantity": 1,
                "currency_id": "BRL",
                "unit_price": 1.00
            }
        ],
        "payer": {"email": email},
        "back_urls": {
            "success": os.getenv("BASE_URL") + "/sucesso",
            "failure": os.getenv("BASE_URL") + "/erro",
            "pending": os.getenv("BASE_URL") + "/pendente"
        },
        "auto_return": "approved",
        "notification_url": os.getenv("BASE_URL") + "/webhook",
        "external_reference": email
    }

    response = sdk.preference().create(preference_data)

    return jsonify({
        "init_point": response["response"]["init_point"]
    })

# ======================================
# WEBHOOK PROFISSIONAL
# ======================================

@app.route("/webhook", methods=["POST"])
def webhook():
    try:
        data = request.json

        if data.get("type") != "payment":
            return jsonify({"status": "ignored"}), 200

        payment_id = data["data"]["id"]

        payment_response = sdk.payment().get(payment_id)
        payment = payment_response["response"]

        if payment.get("status") != "approved":
            return jsonify({"status": "not approved"}), 200

        email = payment.get("external_reference")

        if not email:
            return jsonify({"status": "no email"}), 200

        usuario = Usuario.query.filter_by(email=email).first()

        if usuario and not usuario.pago:
            usuario.pago = True
            usuario.payment_id = payment_id
            db.session.commit()

        return jsonify({"status": "success"}), 200

    except Exception as e:
        print("Erro webhook:", e)
        return jsonify({"erro": "erro interno"}), 500

# ======================================
# DOWNLOAD SEGURO
# ======================================

@app.route("/download")
def download():
    email = session.get("email")

    if not email:
        return redirect(url_for("index"))

    usuario = Usuario.query.filter_by(email=email).first()

    if not usuario or not usuario.pago:
        return "Acesso negado."

    wb = Workbook()
    ws = wb.active
    ws["A1"] = "PromptSheet Premium"
    ws["A2"] = f"Usuário: {email}"

    temp = tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx")
    wb.save(temp.name)

    return send_file(temp.name, as_attachment=True)

# ======================================
# ROTAS AUXILIARES
# ======================================

@app.route("/sucesso")
def sucesso():
    return redirect(url_for("index"))

@app.route("/erro")
def erro():
    return "Pagamento falhou."

@app.route("/pendente")
def pendente():
    return "Pagamento pendente."

# ======================================
# RENDER
# ======================================

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
