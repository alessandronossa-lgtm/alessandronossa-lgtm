import os
import json
import tempfile
from datetime import datetime, timedelta, timezone
from functools import wraps

from flask import (
    Flask, render_template, request, redirect, jsonify,
    session, url_for, send_file, abort
)

import mercadopago
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash

# requests é usado para assinatura (preapproval)
import requests


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

# Render/Postgres: às vezes vem postgres:// e precisa ser postgresql://
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

app.config["SQLALCHEMY_DATABASE_URI"] = DATABASE_URL
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)

MP_ACCESS_TOKEN = os.getenv("MP_ACCESS_TOKEN")
if not MP_ACCESS_TOKEN:
    raise Exception("MP_ACCESS_TOKEN não configurado.")
sdk = mercadopago.SDK(MP_ACCESS_TOKEN)

# preços (pode mudar depois)
PRICE_AVULSO_24H = 9.90
PRICE_PREMIUM_MENSAL = 19.90


def now_utc():
    return datetime.now(timezone.utc)


def base_url():
    """
    Ideal: configurar BASE_URL no Render (ex: https://promptsheet-backend.onrender.com)
    Fallback: usar request.host_url
    """
    env = os.getenv("BASE_URL")
    if env and env.strip():
        return env.rstrip("/")
    # fallback (quando chamado dentro de request)
    return request.host_url.rstrip("/")


# =====================================================
# MODELS
# =====================================================

class Usuario(db.Model):
    __tablename__ = "usuario"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(150), unique=True, nullable=False)

    senha_hash = db.Column(db.String(255), nullable=False)

    # Premium (assinatura)
    subscription_status = db.Column(db.String(50), default="none")  # none|authorized|active|paused|cancelled
    subscription_id = db.Column(db.String(120), nullable=True)
    free_premium_until = db.Column(db.DateTime(timezone=True), nullable=True)

    created_at = db.Column(db.DateTime(timezone=True), default=now_utc)

    def set_senha(self, senha: str):
        self.senha_hash = generate_password_hash(senha)

    def verificar_senha(self, senha: str) -> bool:
        return check_password_hash(self.senha_hash, senha)

    def premium_ativo(self) -> bool:
        if self.subscription_status in ("authorized", "active"):
            return True
        if self.free_premium_until and self.free_premium_until > now_utc():
            return True
        return False


class Projeto(db.Model):
    __tablename__ = "projeto"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("usuario.id"), nullable=False)
    nome = db.Column(db.String(120), nullable=False)
    prompt = db.Column(db.Text, nullable=True)

    created_at = db.Column(db.DateTime(timezone=True), default=now_utc)


class AcessoProjeto(db.Model):
    __tablename__ = "acesso_projeto"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("usuario.id"), nullable=False)
    projeto_id = db.Column(db.Integer, db.ForeignKey("projeto.id"), nullable=False)

    # Avulso 24h
    expires_at = db.Column(db.DateTime(timezone=True), nullable=False)

    # rastreio
    payment_id = db.Column(db.String(120), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), default=now_utc)


with app.app_context():
    db.create_all()


# =====================================================
# AUTH HELPERS
# =====================================================

def current_user():
    uid = session.get("user_id")
    if not uid:
        return None
    return Usuario.query.get(uid)


def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not session.get("user_id"):
            return redirect(url_for("login"))
        return fn(*args, **kwargs)
    return wrapper


# =====================================================
# AUTH ROUTES
# =====================================================

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        senha = request.form.get("senha") or ""

        if not email or not senha:
            return render_template("register.html", erro="Preencha email e senha.")

        if Usuario.query.filter_by(email=email).first():
            return render_template("register.html", erro="Esse email já está cadastrado.")

        u = Usuario(email=email)
        u.set_senha(senha)

        db.session.add(u)
        db.session.commit()

        session["user_id"] = u.id
        return redirect(url_for("app_home"))

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        senha = request.form.get("senha") or ""

        u = Usuario.query.filter_by(email=email).first()
        if not u or not u.verificar_senha(senha):
            return render_template("login.html", erro="Email ou senha inválidos.")

        session["user_id"] = u.id
        return redirect(url_for("app_home"))

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))


# =====================================================
# PÁGINAS
# =====================================================

@app.route("/")
def index():
    u = current_user()
    # se logado, manda pro painel
    if u:
        return redirect(url_for("app_home"))
    return render_template("index.html", usuario=u)


@app.route("/app", methods=["GET", "POST"])
@login_required
def app_home():
    u = current_user()

    if request.method == "POST":
        nome = (request.form.get("nome") or "").strip()
        prompt = (request.form.get("prompt") or "").strip()

        if not nome:
            return render_template("app.html", usuario=u, projetos=Projeto.query.filter_by(user_id=u.id).all(),
                                   erro="Dê um nome ao projeto.")

        p = Projeto(user_id=u.id, nome=nome, prompt=prompt)
        db.session.add(p)
        db.session.commit()
        return redirect(url_for("projeto_view", projeto_id=p.id))

    projetos = Projeto.query.filter_by(user_id=u.id).order_by(Projeto.created_at.desc()).all()
    return render_template("app.html", usuario=u, projetos=projetos)


@app.route("/projeto/<int:projeto_id>")
@login_required
def projeto_view(projeto_id):
    u = current_user()
    p = Projeto.query.filter_by(id=projeto_id, user_id=u.id).first_or_404()

    premium = u.premium_ativo()

    acesso = AcessoProjeto.query.filter_by(user_id=u.id, projeto_id=p.id).order_by(AcessoProjeto.expires_at.desc()).first()
    acesso_ativo = False
    expira_em = None
    if acesso and acesso.expires_at > now_utc():
        acesso_ativo = True
        expira_em = acesso.expires_at

    return render_template(
        "projeto.html",
        usuario=u,
        projeto=p,
        premium=premium,
        acesso_ativo=acesso_ativo,
        expira_em=expira_em
    )


# =====================================================
# PREMIUM (PÁGINA + ASSINATURA REAL)
# =====================================================

@app.route("/premium")
@login_required
def premium_page():
    u = current_user()
    return render_template("premium.html", usuario=u, price_premium=PRICE_PREMIUM_MENSAL)


@app.route("/premium/assinar", methods=["POST"])
@login_required
def premium_assinar():
    """
    Cria uma assinatura recorrente (Mercado Pago Subscriptions /preapproval)
    e retorna init_point para o usuário autorizar.
    """
    u = current_user()

    # Se já é premium, não cria de novo
    if u.premium_ativo():
        return jsonify({"erro": "Você já possui Premium ativo."}), 400

    # Mercado Pago Subscriptions: /preapproval
    # Docs: https://www.mercadopago.com.br/developers/en/reference/subscriptions/_preapproval/post
    # Vamos criar sem plano, recorrência mensal.
    url = "https://api.mercadopago.com/preapproval"
    headers = {
        "Authorization": f"Bearer {MP_ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }

    payload = {
        "reason": "PromptSheet Premium - Acesso ilimitado",
        "payer_email": u.email,
        "auto_recurring": {
            "frequency": 1,
            "frequency_type": "months",
            "transaction_amount": float(PRICE_PREMIUM_MENSAL),
            "currency_id": "BRL"
        },
        # back_url é a página que o MP usa quando o usuário volta
        "back_url": f"{base_url()}/premium/retorno",
        # referência externa para relacionar com o usuário
        "external_reference": f"user:{u.id}"
    }

    r = requests.post(url, headers=headers, data=json.dumps(payload), timeout=30)
    if r.status_code >= 400:
        return jsonify({"erro": "Falha ao criar assinatura.", "detalhes": r.text}), 500

    resp = r.json()
    init_point = resp.get("init_point")
    sub_id = resp.get("id")

    if not init_point or not sub_id:
        return jsonify({"erro": "Resposta inesperada do Mercado Pago.", "detalhes": resp}), 500

    # registra no usuário como "iniciada"
    u.subscription_id = sub_id
    u.subscription_status = resp.get("status") or "pending"
    db.session.commit()

    return jsonify({"init_point": init_point})


@app.route("/premium/retorno")
@login_required
def premium_retorno():
    """
    O MP geralmente volta aqui após autorização.
    O status definitivo chega por webhook; aqui só damos uma mensagem e mandamos para /app.
    """
    return redirect(url_for("app_home"))


# =====================================================
# AVULSO 24H POR PROJETO (Checkout Pro Preference)
# =====================================================

@app.route("/projeto/<int:projeto_id>/comprar_diaria", methods=["POST"])
@login_required
def comprar_diaria(projeto_id):
    u = current_user()
    p = Projeto.query.filter_by(id=projeto_id, user_id=u.id).first_or_404()

    # Se é premium, não precisa comprar diária
    if u.premium_ativo():
        return jsonify({"erro": "Você já é Premium."}), 400

    # external_reference para identificar no webhook
    external_reference = f"user:{u.id}|project:{p.id}|kind:daily"

    preference_data = {
        "items": [{
            "title": f"Acesso 24h - Projeto {p.nome}",
            "quantity": 1,
            "currency_id": "BRL",
            "unit_price": float(PRICE_AVULSO_24H)
        }],
        "payer": {"email": u.email},
        "external_reference": external_reference,
        "notification_url": f"{base_url()}/webhook",
        "back_urls": {
            "success": f"{base_url()}/pendente/{p.id}",
            "failure": f"{base_url()}/pendente/{p.id}",
            "pending": f"{base_url()}/pendente/{p.id}",
        },
        # PIX tende a ficar pending; auto_return "all" ajuda quando houver retorno,
        # mas a liberação real é via webhook + /status.
        "auto_return": "all"
    }

    response = sdk.preference().create(preference_data)
    init_point = response.get("response", {}).get("init_point")

    if not init_point:
        return jsonify({"erro": "Não foi possível gerar o link de pagamento.", "detalhes": response}), 500

    return jsonify({"init_point": init_point})


@app.route("/pendente/<int:projeto_id>")
@login_required
def pendente_page(projeto_id):
    u = current_user()
    p = Projeto.query.filter_by(id=projeto_id, user_id=u.id).first_or_404()
    return render_template("pendente.html", projeto=p)


@app.route("/status")
@login_required
def status():
    """
    Usado pelo pendente.html para checar se já pagou.
    - Para diária: precisa projeto_id
    - Para premium: pode checar premium direto
    """
    u = current_user()

    projeto_id = request.args.get("projeto_id", type=int)

    premium = u.premium_ativo()
    if premium:
        return jsonify({"paid": True, "premium": True})

    if not projeto_id:
        return jsonify({"paid": False, "premium": False})

    acesso = AcessoProjeto.query.filter_by(user_id=u.id, projeto_id=projeto_id).order_by(AcessoProjeto.expires_at.desc()).first()
    if acesso and acesso.expires_at > now_utc():
        return jsonify({"paid": True, "premium": False, "expires_at": acesso.expires_at.isoformat()})

    return jsonify({"paid": False, "premium": False})


# =====================================================
# DOWNLOAD (protege por premium OU diária ativa)
# =====================================================

@app.route("/projeto/<int:projeto_id>/download")
@login_required
def download_projeto(projeto_id):
    u = current_user()
    p = Projeto.query.filter_by(id=projeto_id, user_id=u.id).first_or_404()

    if not u.premium_ativo():
        acesso = AcessoProjeto.query.filter_by(user_id=u.id, projeto_id=p.id).order_by(AcessoProjeto.expires_at.desc()).first()
        if not acesso or acesso.expires_at <= now_utc():
            return "Acesso negado. Compre a diária (24h) ou assine o Premium.", 403

    # gera planilha (simples por enquanto; você pode ligar com seu gerador dinâmico depois)
    wb = Workbook()
    ws = wb.active
    ws.title = "PromptSheet"
    ws["A1"] = "PromptSheet"
    ws["A2"] = f"Usuário: {u.email}"
    ws["A3"] = f"Projeto: {p.nome}"
    ws["A4"] = f"Prompt: {p.prompt or ''}"

    temp = tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx")
    wb.save(temp.name)

    return send_file(temp.name, as_attachment=True, download_name=f"{p.nome}.xlsx")


# =====================================================
# WEBHOOK (payment + preapproval)
# =====================================================

def parse_webhook_event():
    """
    MP pode enviar:
    - query params: ?data.id=...&type=payment
    - query params: ?id=...&topic=payment / merchant_order
    - json: {"type":"payment","data":{"id":...}}
    """
    # 1) JSON padrão
    data = request.get_json(silent=True) or {}

    if isinstance(data, dict) and data.get("type") and isinstance(data.get("data"), dict) and data["data"].get("id"):
        return data.get("type"), str(data["data"]["id"])

    # 2) query: data.id e type
    t = request.args.get("type")
    did = request.args.get("data.id")
    if t and did:
        return t, str(did)

    # 3) query: topic e id
    topic = request.args.get("topic")
    _id = request.args.get("id")
    if topic and _id:
        # topic pode ser payment / merchant_order / preapproval
        return topic, str(_id)

    return None, None


def handle_payment(payment_id: str):
    pay_resp = sdk.payment().get(payment_id)
    payment = pay_resp.get("response", {})

    status = payment.get("status")
    if status != "approved":
        return

    external_reference = payment.get("external_reference") or ""
    # exemplo: user:1|project:2|kind:daily
    if "kind:daily" in external_reference and "project:" in external_reference and "user:" in external_reference:
        try:
            parts = external_reference.split("|")
            uid = int(parts[0].split(":")[1])
            pid = int(parts[1].split(":")[1])
        except Exception:
            return

        user = Usuario.query.get(uid)
        proj = Projeto.query.get(pid)
        if not user or not proj or proj.user_id != user.id:
            return

        expires = now_utc() + timedelta(hours=24)

        acesso = AcessoProjeto.query.filter_by(user_id=user.id, projeto_id=proj.id).order_by(AcessoProjeto.expires_at.desc()).first()
        if acesso and acesso.expires_at > now_utc():
            # se já tem ativo, estende +24h (opcional)
            expires = acesso.expires_at + timedelta(hours=24)

        novo = AcessoProjeto(
            user_id=user.id,
            projeto_id=proj.id,
            expires_at=expires,
            payment_id=payment_id
        )
        db.session.add(novo)
        db.session.commit()


def handle_preapproval(preapproval_id: str):
    """
    Consulta a assinatura e atualiza o usuário.
    GET /preapproval/{id}
    """
    url = f"https://api.mercadopago.com/preapproval/{preapproval_id}"
    headers = {"Authorization": f"Bearer {MP_ACCESS_TOKEN}"}
    r = requests.get(url, headers=headers, timeout=30)
    if r.status_code >= 400:
        return

    sub = r.json()
    status = (sub.get("status") or "").lower()  # authorized, paused, cancelled, etc.
    ext = sub.get("external_reference") or ""

    # external_reference: user:<id>
    uid = None
    if ext.startswith("user:"):
        try:
            uid = int(ext.split(":")[1])
        except Exception:
            uid = None

    # fallback: localizar por payer_email
    user = None
    if uid:
        user = Usuario.query.get(uid)
    if not user:
        payer_email = sub.get("payer_email")
        if payer_email:
            user = Usuario.query.filter_by(email=payer_email.lower()).first()

    if not user:
        return

    user.subscription_id = preapproval_id
    user.subscription_status = status or "unknown"
    db.session.commit()


@app.route("/webhook", methods=["POST", "GET"])
def webhook():
    try:
        event_type, event_id = parse_webhook_event()

        # silencioso quando não identifica
        if not event_type or not event_id:
            return jsonify({"status": "ignored"}), 200

        # payment
        if event_type in ("payment",):
            with app.app_context():
                handle_payment(event_id)
            return jsonify({"status": "ok"}), 200

        # subscriptions preapproval
        if event_type in ("preapproval",):
            with app.app_context():
                handle_preapproval(event_id)
            return jsonify({"status": "ok"}), 200

        # merchant_order etc: ignora (ou você pode tratar depois)
        return jsonify({"status": "ignored"}), 200

    except Exception as e:
        print("Erro webhook:", e)
        return jsonify({"erro": "erro interno"}), 500


# =====================================================
# RUN
# =====================================================

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
