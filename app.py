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
    "failure": "https://promptsheet-backend.onrender.com/",
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
    try:
        payment_id = request.args.get("payment_id")

        if not payment_id:
            return redirect(url_for("index"))

        # Consulta pagamento na API
        payment_response = sdk.payment().get(payment_id)
        payment = payment_response["response"]

        status = payment.get("status")

        print("Status real do pagamento:", status)

        if status == "approved":
            session["pago"] = True
            return redirect(url_for("index"))
        else:
            return "Pagamento ainda não aprovado. Aguarde a confirmação do PIX."

    except Exception as e:
        print("Erro na rota sucesso:", e)
        return "Erro ao verificar pagamento."



# ======================================
# RENDER - OBRIGATÓRIO
# ======================================

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
