import os
from flask import Flask, render_template, request, redirect, jsonify
import mercadopago
from openpyxl import Workbook

app = Flask(__name__)

# ======================================
# CONFIGURAÇÃO MERCADO PAGO
# ======================================

MP_ACCESS_TOKEN = os.getenv("MP_ACCESS_TOKEN")
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

    return redirect("/download")


@app.route("/download")
def download():
    return send_file("planilha_gerada.xlsx", as_attachment=True)


if __name__ == "__main__":
    app.run(debug=True)
