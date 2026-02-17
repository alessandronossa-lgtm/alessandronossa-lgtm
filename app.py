import os
from flask import Flask, render_template, request, redirect, jsonify, send_file, session, url_for
import mercadopago
from openpyxl import Workbook

app = Flask(__name__)
app.secret_key = "supersecretkey"


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
    "failure": "https://promptsheet-backend.onrender.com/sucesso",
    "pending": "https://promptsheet-backend.onrender.com/sucesso"
},
"auto_return": "all"
    }

    preference_response = sdk.preference().create(preference_data)
    preference = preference_response["response"]

    return jsonify({
        "init_point": preference["init_point"]
    })


@app.route("/sucesso")
def sucesso():
    payment_id = request.args.get("payment_id")

    print("=== ROTA SUCESSO CHAMADA ===")
    print("Payment ID recebido:", payment_id)
    print("Args completos:", request.args)

    if not payment_id:
        return "Payment ID não recebido."

    try:
        payment_response = sdk.payment().get(payment_id)
        print("Resposta completa API:", payment_response)

        payment = payment_response["response"]
        status = payment.get("status")

        print("Status real:", status)

        if status == "approved":
            session["pago"] = True
            return "Pagamento APROVADO!"
        else:
            return f"Pagamento ainda não aprovado. Status atual: {status}"

    except Exception as e:
        print("Erro na consulta:", str(e))
        return f"Erro ao consultar pagamento: {str(e)}"



# ======================================
# RENDER - OBRIGATÓRIO
# ======================================

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
