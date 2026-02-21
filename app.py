import os
import tempfile
from datetime import datetime, timedelta
from functools import wraps

import mercadopago
from flask import (
    Flask, render_template, request, redirect, jsonify,
    session, url_for, send_file, abort
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

BASE_URL = os.getenv("BASE_URL", "https://promptsheet-backend.onrender.com").rstrip("/")

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

# Preços
PRICE_ONE_TIME_24H = 9.90
PRICE_PREMIUM_MONTH = 19.90

# Mercado Pago: pode manter approved. PIX quase sempre volta pending → usamos /pendente/<id>
MP_AUTO_RETURN = os.getenv("MP_AUTO_RETURN", "approved")


# =====================================================
# MODELS
# =====================================================
class Usuario(db.Model):
    __tablename__ = "usuario"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(150), unique=True, nullable=False)
    senha_hash = db.Column(db.String(255), nullable=False)

    # Premium pago (assinatura)
    subscription_status = db.Column(db.String(30), default="none")  # none | active | canceled
    subscription_id = db.Column(db.String(120), nullable=True)

    # Premium grátis para testers (feedback)
    free_premium_until = db.Column(db.DateTime, nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def set_senha(self, senha: str) -> None:
        self.senha_hash = generate_password_hash(senha)

    def verificar_senha(self, senha: str) -> bool:
        return check_password_hash(self.senha_hash, senha)


class Projeto(db.Model):
    __tablename__ = "projeto"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("usuario.id"), nullable=False)
    titulo = db.Column(db.String(200), nullable=False)
    prompt = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship("Usuario", backref="projetos")


class AcessoProjeto(db.Model):
    __tablename__ = "acesso_projeto"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("usuario.id"), nullable=False)
    project_id = db.Column(db.Integer, db.ForeignKey("projeto.id"), nullable=False)

    expires_at = db.Column(db.DateTime, nullable=False)
    payment_id = db.Column(db.String(120), nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship("Usuario")
    projeto = db.relationship("Projeto")


with app.app_context():
    db.create_all()


# =====================================================
# HELPERS
# =====================================================
def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return fn(*args, **kwargs)
    return wrapper


def usuario_logado():
    uid = session.get("user_id")
    if not uid:
        return None
    return Usuario.query.get(uid)


def is_premium_active(user: Usuario) -> bool:
    if not user:
        return False

    if user.subscription_status == "active":
        return True

    if user.free_premium_until and user.free_premium_until > datetime.utcnow():
        return True

    return False


def has_project_access(user: Usuario, projeto: Projeto) -> bool:
    # Premium ativo → acesso total
    if is_premium_active(user):
        return True

    # Acesso avulso 24h por projeto
    now = datetime.utcnow()
    acesso = (
        AcessoProjeto.query
        .filter_by(user_id=user.id, project_id=projeto.id)
        .order_by(AcessoProjeto.expires_at.desc())
        .first()
    )

    return bool(acesso and acesso.expires_at > now)


def project_owned_or_404(user: Usuario, project_id: int) -> Projeto:
    projeto = Projeto.query.get(project_id)
    if not projeto:
        abort(404)
    if projeto.user_id != user.id:
        abort(403)
    return projeto


def parse_external_reference(ext: str):
    """
    Formato: "u:<user_id>|p:<project_id>|t:<tipo>"
    Ex: u:12|p:55|t:one_time_24h
    """
    try:
        parts = ext.split("|")
        d = {}
        for part in parts:
            k, v = part.split(":", 1)
            d[k] = v
        return d
    except Exception:
        return None


# =====================================================
# AUTH ROUTES
# =====================================================
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        senha = request.form.get("senha") or ""

        if not email or not senha:
            return "Preencha e-mail e senha.", 400

        if Usuario.query.filter_by(email=email).first():
            return "Este e-mail já está cadastrado. Faça login.", 400

        user = Usuario(email=email)
        user.set_senha(senha)
        db.session.add(user)
        db.session.commit()

        session["user_id"] = user.id
        return redirect(url_for("dashboard"))

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        senha = request.form.get("senha") or ""

        user = Usuario.query.filter_by(email=email).first()
        if user and user.verificar_senha(senha):
            session["user_id"] = user.id
            return redirect(url_for("dashboard"))

        return "Credenciais inválidas.", 400

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("home"))


# =====================================================
# HOME / DASHBOARD
# =====================================================
@app.route("/")
def home():
    user = usuario_logado()
    if user:
        return redirect(url_for("dashboard"))
    return render_template("home_public.html")


@app.route("/app")
@login_required
def dashboard():
    user = usuario_logado()
    projetos = Projeto.query.filter_by(user_id=user.id).order_by(Projeto.id.desc()).all()
    return render_template(
        "dashboard.html",
        usuario=user,
        projetos=projetos,
        premium=is_premium_active(user),
        price_one_time=PRICE_ONE_TIME_24H,
        price_premium=PRICE_PREMIUM_MONTH
    )


# =====================================================
# PROJECTS
# =====================================================
@app.route("/projeto/novo", methods=["POST"])
@login_required
def projeto_novo():
    user = usuario_logado()
    titulo = (request.form.get("titulo") or "").strip()
    prompt = (request.form.get("prompt") or "").strip()

    if not titulo:
        titulo = "Novo Projeto"

    if not prompt:
        return "Descreva o que você precisa (prompt).", 400

    proj = Projeto(user_id=user.id, titulo=titulo, prompt=prompt)
    db.session.add(proj)
    db.session.commit()

    return redirect(url_for("projeto_view", project_id=proj.id))


@app.route("/projeto/<int:project_id>")
@login_required
def projeto_view(project_id):
    user = usuario_logado()
    projeto = project_owned_or_404(user, project_id)
    acesso = has_project_access(user, projeto)

    return render_template(
        "projeto.html",
        usuario=user,
        projeto=projeto,
        acesso=acesso,
        premium=is_premium_active(user),
        price_one_time=PRICE_ONE_TIME_24H,
        price_premium=PRICE_PREMIUM_MONTH
    )


@app.route("/projeto/<int:project_id>/editar", methods=["POST"])
@login_required
def projeto_editar(project_id):
    user = usuario_logado()
    projeto = project_owned_or_404(user, project_id)

    titulo = (request.form.get("titulo") or "").strip()
    prompt = (request.form.get("prompt") or "").strip()

    if titulo:
        projeto.titulo = titulo
    if prompt:
        projeto.prompt = prompt

    db.session.commit()
    return redirect(url_for("projeto_view", project_id=project_id))


# =====================================================
# PAYMENT - ONE TIME 24H (R$ 9,90)
# =====================================================
@app.route("/pagamento/avulso/<int:project_id>", methods=["POST"])
@login_required
def pagamento_avulso(project_id):
    user = usuario_logado()
    projeto = project_owned_or_404(user, project_id)

    # Se já tem acesso (premium ou 24h ativa), manda pra projeto direto
    if has_project_access(user, projeto):
        return jsonify({"ok": True, "redirect": url_for("projeto_view", project_id=project_id)})

    external_reference = f"u:{user.id}|p:{projeto.id}|t:one_time_24h"

    preference_data = {
        "items": [
            {
                "title": f"PromptSheet - Acesso 24h (Projeto #{projeto.id})",
                "quantity": 1,
                "currency_id": "BRL",
                "unit_price": float(PRICE_ONE_TIME_24H)
            }
        ],
        "payer": {"email": user.email},
        "external_reference": external_reference,
        "back_urls": {
            "success": f"{BASE_URL}/pendente/{projeto.id}",
            "failure": f"{BASE_URL}/erro",
            "pending": f"{BASE_URL}/pendente/{projeto.id}"
        },
        "auto_return": MP_AUTO_RETURN,
        "notification_url": f"{BASE_URL}/webhook"
    }

    resp = sdk.preference().create(preference_data)
    init_point = resp.get("response", {}).get("init_point")
    if not init_point:
        return jsonify({"ok": False, "erro": "Falha ao gerar pagamento", "detalhes": resp}), 500

    return jsonify({"ok": True, "init_point": init_point})


# =====================================================
# PREMIUM - (estrutura pronta)
# Observação: assinatura real no Mercado Pago usa Preapproval/Subcriptions.
# Aqui deixamos a rota pronta para você plugar quando ativar.
# =====================================================
@app.route("/premium", methods=["POST"])
@login_required
def premium_assinar():
    # Vamos deixar o “premium de verdade” para o próximo passo (assinatura recorrente).
    # Por enquanto, retornamos uma mensagem clara para não quebrar nada.
    return jsonify({
        "ok": False,
        "erro": "Assinatura Premium ainda não ativada no Mercado Pago (próximo passo)."
    }), 501


# =====================================================
# PENDING PAGE + STATUS
# =====================================================
@app.route("/pendente/<int:project_id>")
@login_required
def pendente(project_id):
    user = usuario_logado()
    projeto = project_owned_or_404(user, project_id)
    return render_template("pendente.html", usuario=user, projeto=projeto)


@app.route("/status/<int:project_id>")
@login_required
def status(project_id):
    user = usuario_logado()
    projeto = project_owned_or_404(user, project_id)

    return jsonify({
        "ok": True,
        "paid": has_project_access(user, projeto),
        "premium": is_premium_active(user)
    })


# =====================================================
# WEBHOOK
# =====================================================
@app.route("/webhook", methods=["POST"])
def webhook():
    try:
        data = request.json or {}

        # Muitos envios chegam via querystring:
        # /webhook?data.id=xxx&type=payment
        payment_id = None
        event_type = data.get("type")

        if event_type == "payment":
            payment_id = (data.get("data") or {}).get("id")
        else:
            # tenta querystring
            q_type = request.args.get("type")
            if q_type == "payment":
                payment_id = request.args.get("data.id")

        if not payment_id:
            return jsonify({"status": "ignored"}), 200

        pay_resp = sdk.payment().get(payment_id)
        payment = pay_resp.get("response", {})

        if payment.get("status") != "approved":
            return jsonify({"status": "not approved"}), 200

        ext = payment.get("external_reference") or ""
        parsed = parse_external_reference(ext)
        if not parsed:
            return jsonify({"status": "no external_reference"}), 200

        if parsed.get("t") != "one_time_24h":
            return jsonify({"status": "unknown type"}), 200

        user_id = int(parsed.get("u"))
        project_id = int(parsed.get("p"))

        # Cria/renova acesso 24h para esse projeto
        expires = datetime.utcnow() + timedelta(hours=24)

        acesso = AcessoProjeto(
            user_id=user_id,
            project_id=project_id,
            expires_at=expires,
            payment_id=str(payment_id)
        )
        db.session.add(acesso)
        db.session.commit()

        return jsonify({"status": "ok"}), 200

    except Exception as e:
        print("Erro webhook:", e)
        return jsonify({"erro": "erro interno"}), 500


# =====================================================
# DOWNLOAD (PROTEGIDO POR PROJETO)
# =====================================================
@app.route("/projeto/<int:project_id>/download")
@login_required
def projeto_download(project_id):
    user = usuario_logado()
    projeto = project_owned_or_404(user, project_id)

    if not has_project_access(user, projeto):
        return redirect(url_for("projeto_view", project_id=project_id))

    # Geração simples (MVP). Depois plugamos a geração real por prompt.
    wb = Workbook()
    ws = wb.active
    ws.title = "PromptSheet"

    ws["A1"] = "PromptSheet"
    ws["A2"] = f"Projeto: {projeto.titulo}"
    ws["A3"] = f"Usuário: {user.email}"
    ws["A4"] = f"Prompt:"
    ws["A5"] = projeto.prompt

    temp = tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx")
    wb.save(temp.name)

    filename = f"promptsheet_projeto_{project_id}.xlsx"
    return send_file(temp.name, as_attachment=True, download_name=filename)


# =====================================================
# AUX
# =====================================================
@app.route("/erro")
def erro():
    return "Pagamento falhou ou foi cancelado."


# =====================================================
# LOCAL
# =====================================================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
