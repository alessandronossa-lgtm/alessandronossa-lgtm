import os
from flask import Flask, render_template, request, redirect, jsonify, send_file
import mercadopago
from openpyxl import Workbook

app = Flask(__name__)

# ======================================
# CONFIGURAÇÃO MERCADO PAGO
# ======================================

MP_ACCESS_TOKEN = os.getenv("MP_ACCESS_TOKEN")
print("TOKEN:", MP_ACCESS_TOKEN)

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
    payment_id = request.args.get("payment_id")

    if not payment_id:
        return "Pagamento não identificado."

    try:
        payment_response = sdk.payment().get(payment_id)
        payment = payment_response["response"]
    except Exception as e:
        return f"Erro ao consultar pagamento: {str(e)}"

    status = payment.get("status")

    if status == "approved":
        return render_template("sucesso.html")

    elif status == "pending":
        return """
        <h2>Pagamento pendente</h2>
        <p>Seu PIX ainda está sendo processado.</p>
        <p>Aguarde alguns segundos e atualize esta página.</p>
        """

    else:
        return f"<h2>Status do pagamento: {status}</h2>"


# ======================================
# RENDER - OBRIGATÓRIO
# ======================================

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
