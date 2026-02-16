import os
from flask import Flask, render_template, request, redirect, jsonify, send_file
import mercadopago
from openpyxl import Workbook

app = Flask(__name__)

# ======================================
# CONFIGURAÇÃO MERCADO PAGO
# ======================================

MP_ACCESS_TOKEN = os.getenv("MP_ACCESS_TOKEN")

if not MP_ACCESS_TOKEN:
    raise Exception("MP_ACCESS_TOKEN não configurado no Render")

sdk = mercadopago.SDK(MP_ACCESS_TOKEN)

# ======================================
# ROTAS
# ======================================

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/criar_preferencia", methods=["POST"])
def criar_preferencia():
    preference_data = {
        "items": [
            {
                "title": "Geração de Planilha PromptSheet",
                "quantity": 1,
                "currency_id": "BRL",
                "unit_price": 1.00
            }
        ],
        "back_urls": {
            "success": "https://promptsheet-backend.onrender.com/sucesso",
            "failure": "https://promptsheet-backend.onrender.com/",
            "pending": "https://promptsheet-backend.onrender.com/"
        },
        "auto_return": "approved"
    }

    preference_response = sdk.preference().create(preference_data)
    preference = preference_response["response"]

    return jsonify({
        "init_point": preference["init_point"]
    })


@app.route("/sucesso")
def sucesso():
    return render_template("sucesso.html")


@app.route("/gerar_planilha", methods=["POST"])
def gerar_planilha():
    descricao = request.form.get("descricao")

    wb = Workbook()
    ws = wb.active
    ws.title = "Planilha Gerada"

    ws["A1"] = "Descrição solicitada:"
    ws["A2"] = descricao

    caminho = "planilha_gerada.xlsx"
    wb.save(caminho)

    return send_file(caminho, as_attachment=True)


# ======================================
# RENDER - OBRIGATÓRIO
# ======================================

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
