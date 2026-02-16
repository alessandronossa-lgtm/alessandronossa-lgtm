import os
import requests
from flask import Flask, render_template, request, redirect, jsonify, send_file
from openpyxl import Workbook
from io import BytesIO

app = Flask(__name__)

# =====================================================
# CONFIGURAÇÃO MERCADO PAGO
# =====================================================

ACCESS_TOKEN = os.environ.get("MERCADO_PAGO_ACCESS_TOKEN")

if not ACCESS_TOKEN:
    raise ValueError("MERCADO_PAGO_ACCESS_TOKEN não configurado.")

MP_URL = "https://api.mercadopago.com/checkout/preferences"

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

    preference_data = {
        "items": [
            {
                "title": "Planilha Inteligente",
                "quantity": 1,
                "currency_id": "BRL",
                "unit_price": 4.90
            }
        ],
        "back_urls": {
            "success": "https://promptsheet-backend.onrender.com",
            "failure": "https://promptsheet-backend.onrender.com/",
            "pending": "https://promptsheet-backend.onrender.com/"
        },
        "auto_return": "approved"
    }

    headers = {
        "Authorization": f"Bearer {ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }

    response = requests.post(MP_URL, json=preference_data, headers=headers)
    data = response.json()

    return redirect(data["init_point"])

# =====================================================
# PÁGINA DE SUCESSO
# =====================================================

@app.route("/sucesso")
def sucesso():
    return """
    <h2>Pagamento aprovado com sucesso!</h2>
    <form action="/baixar" method="post">
        <button type="submit">Baixar Planilha</button>
    </form>
    """

# =====================================================
# GERAR E BAIXAR PLANILHA
# =====================================================

@app.route("/baixar", methods=["POST"])
def baixar():

    wb = Workbook()
    ws = wb.active
    ws.title = "Planilha"

    ws["A1"] = "Produto"
    ws["B1"] = "Valor"

    ws.append(["Planilha Inteligente", "R$ 4,90"])

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
