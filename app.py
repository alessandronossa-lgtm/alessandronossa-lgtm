import os
from flask import Flask, render_template, request, redirect, jsonify, session, url_for, send_file
import mercadopago
from flask_sqlalchemy import SQLAlchemy
from openpyxl import Workbook
from datetime import datetime

# ======================================
# CONFIGURAÇÃO APP
# ======================================

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "fallback-secret")

app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///database.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)

MP_ACCESS_TOKEN = os.getenv("MP_ACCESS_TOKEN")
if not MP_ACCESS_TOKEN:
    raise Exception("MP_ACCESS_TOKEN não configurado.")

sdk = mercadopago.SDK(MP_ACCESS_TOKEN)

# ======================================
# MODELO BANCO
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
# ROTAS
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

    # salva na sessão
    session["email"] = email

    # cria usuário se não existir
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
        "payer": {
            "email": email
        },
        "back_urls": {
            "success": "https://promptsheet-backend.onrender.com/sucesso",
            "failure": "https://promptsheet-backend.onrender.com/erro",
            "pending": "https://promptsheet-backend.onrender.com/pendente"
        },
        "auto_return": "approved",
        "notification_url": "https://promptsheet-backend.onrender.com/webhook",
        "external_reference": email
    }

    preference_response = sdk.preference().create(preference_data)

    return jsonify({
        "init_point": preference_response["response"]["init_point"]
    })


# ======================================
# WEBHOOK PROFISSIONAL
# ======================================

@app.route("/webhook", methods=["POST"])
def webhook():
    try:
        data = request.json
        print("Webhook recebido:", data)

        if data.get("type") == "payment":

            payment_id = data["data"]["id"]

            payment_response = sdk.payment().get(payment_id)
            payment = payment_response["response"]

            status = payment.get("status")
            email = payment.get("external_reference")

            print("Status:", status)
            print("Email:", email)

            if status == "approved" and email:

                usuario = Usuario.query.filter_by(email=email).first()

                if usuario and not usuario.pago:
                    usuario.pago = True
                    usuario.payment_id = payment_id
                    db.session.commit()
                    print("Pagamento liberado no banco.")

        return jsonify({"status": "ok"}), 200

    except Exception as e:
        print("Erro webhook:", e)
        return jsonify({"erro": "erro interno"}), 500


# ======================================
# DOWNLOAD PROTEGIDO
# ======================================

@app.route("/download")
def download():
    email = session.get("email")

    if not email:
        return redirect(url_for("index"))

    usuario = Usuario.query.filter_by(email=email).first()

    if not usuario or not usuario.pago:
        return "Acesso negado. Pagamento não confirmado."

    # gera planilha dinâmica
    wb = Workbook()
    ws = wb.active
    ws["A1"] = "PromptSheet Premium"
    ws["A2"] = f"Usuário: {email}"

    file_path = "planilha.xlsx"
    wb.save(file_path)

    return send_file(file_path, as_attachment=True)


# ======================================
# SUCESSO / ERRO / PENDENTE
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
# EXECUÇÃO RENDER
# ======================================

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
