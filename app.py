import os
from flask import Flask, render_template, request, redirect, jsonify, session, url_for, send_file
import mercadopago
from flask_sqlalchemy import SQLAlchemy
from openpyxl import Workbook
from datetime import datetime
import tempfile
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps

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
    senha_hash = db.Column(db.String(255), nullable=False)
    pago = db.Column(db.Boolean, default=False)
    payment_id = db.Column(db.String(100))
    criado_em = db.Column(db.DateTime, default=datetime.utcnow)

    def set_senha(self, senha):
        self.senha_hash = generate_password_hash(senha)

    def verificar_senha(self, senha):
        return check_password_hash(self.senha_hash, senha)

with app.app_context():
    db.create_all()

# ======================================
# DECORATOR LOGIN
# ======================================

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated_function

# ======================================
# HOME
# ======================================

@app.route("/")
def index():
    usuario = None
    if "user_id" in session:
        usuario = Usuario.query.get(session["user_id"])
    return render_template("index.html", usuario=usuario)

# ======================================
# REGISTRO
# ======================================

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        email = request.form.get("email")
        senha = request.form.get("senha")

        if not email or not senha:
            return "Preencha todos os campos."

        if Usuario.query.filter_by(email=email).first():
            return "Usuário já existe."

        usuario = Usuario(email=email)
        usuario.set_senha(senha)

        db.session.add(usuario)
        db.session.commit()

        session["user_id"] = usuario.id

        return redirect(url_for("index"))

    return render_template("register.html")

# ======================================
# LOGIN
# ======================================

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email")
        senha = request.form.get("senha")

        usuario = Usuario.query.filter_by(email=email).first()

        if usuario and usuario.verificar_senha(senha):
            session["user_id"] = usuario.id
            return redirect(url_for("index"))

        return "Credenciais inválidas."

    return render_template("login.html")

# ======================================
# LOGOUT
# ======================================

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))

# ======================================
# CRIAR PAGAMENTO (AGORA EXIGE LOGIN)
# ======================================

@app.route("/criar_preferencia", methods=["POST"])
@login_required
def criar_preferencia():

    usuario = Usuario.query.get(session["user_id"])

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
        "back_urls": {
            "success": os.getenv("BASE_URL") + "/sucesso",
            "failure": os.getenv("BASE_URL") + "/erro",
            "pending": os.getenv("BASE_URL") + "/pendente"
        },
        "auto_return": "approved",
        "notification_url": os.getenv("BASE_URL") + "/webhook",
        "external_reference": usuario.email
    }

    response = sdk.preference().create(preference_data)

    return jsonify({
        "init_point": response["response"]["init_point"]
    })

# ======================================
# WEBHOOK
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

        usuario = Usuario.query.filter_by(email=email).first()

        if usuario:
            usuario.pago = True
            usuario.payment_id = payment_id
            db.session.commit()

        return jsonify({"status": "success"}), 200

    except Exception as e:
        print("Erro webhook:", e)
        return jsonify({"erro": "erro interno"}), 500

# ======================================
# DOWNLOAD PROTEGIDO
# ======================================

@app.route("/download")
@login_required
def download():

    usuario = Usuario.query.get(session["user_id"])

    if not usuario.pago:
        return "Acesso negado. Pagamento necessário."

    wb = Workbook()
    ws = wb.active
    ws["A1"] = "PromptSheet Premium"
    ws["A2"] = f"Usuário: {usuario.email}"

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
