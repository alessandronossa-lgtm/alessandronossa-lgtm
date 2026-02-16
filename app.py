import os
import uuid
import requests
from flask import Flask, render_template, request, redirect, send_file
from openpyxl import Workbook
from io import BytesIO

app = Flask(__name__)

# =====================================================
# CONFIGURAÇÃO MERCADO PAGO
# =====================================================

ACCESS_TOKEN = os.environ.get("MERCADO_PAGO_ACCESS_TOKEN")

if not ACCESS_TOKEN:
    raise ValueError("MERCADO_PAGO_ACCESS_TOKEN não configurado.")

MP_PREFERENCE_URL = "https://api.mercadopago.com/checkout/preferences"
MP_PAYMENT_URL = "https://api.mercadopago.com/v1/payments/"

# =====================================================
# ROTA INICIAL
# =====================================================

@app.route("/")
def home():
    return render_template("index.html")

# =====================================================
# CRIAR PAGAMENTO
# =====================================================

@app.route("/criar_pagamento", methods=["POST"])
def criar_pagamento():

    descricao = request.form.get("descricao")

    if not descricao:
        return "Descrição não informada."

    # Criamos um ID único para identificar essa compra
    reference_id = str(uuid.uuid4())

    preference_data = {
        "items": [
            {
                "title": "Planilha Personalizada",
                "quantity": 1,
                "currency_id": "BRL",
                "unit_price": 1.00
            }
        ],
        "external_reference": reference_id,
        "back_urls": {
            "success": "https://promptsheet-backend.onrender.com/sucesso",
            "failure": "https://promptsheet-backend.onrender.com/",
            "pending": "https://promptsheet-backend.onrender.com/"
        },
        "auto_return": "approved"
    }

    headers = {
        "Authorization": f"Bearer {ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }

    response = requests.post(MP_PREFERENCE_URL, json=preference_data, headers=headers)
    data = response.json()

    return redirect(data["init_point"])

# =====================================================
# PÁGINA DE SUCESSO
# =====================================================

@app.route("/sucesso")
def sucesso():

    payment_id = request.args.get("payment_id")

    if not payment_id:
        return "Pagamento não identificado."

    headers = {
        "Authorization": f"Bearer {ACCESS_TOKEN}"
    }

    payment_response = requests.get(MP_PAYMENT_URL + payment_id, headers=headers)
    payment_info = payment_response.json()

    if payment_info.get("status") != "approved":
        return "Pagamento não aprovado."

    return """
        <h2>Pagamento aprovado com sucesso!</h2>
        <form action="/baixar" method="post">
            <button type="submit">Gerar Planilha</button>
        </form>
    """

# =====================================================
# GERAR E BAIXAR PLANILHA
# =====================================================

@app.route("/baixar", methods=["POST"])
def baixar():

    wb = Workbook()
    ws = wb.active
    ws.title = "Planilha Personalizada"

    ws["A1"] = "Planilha gerada com sucesso!"
    ws["A2"] = "Obrigado pela compra."

    arquivo = BytesIO()
    wb.save(arquivo)
    arquivo.seek(0)

    return send_file(
        arquivo,
        as_attachment=True,
        download_name="planilha.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

# =====================================================

if __name__ == "__main__":
    app.run(debug=True)
