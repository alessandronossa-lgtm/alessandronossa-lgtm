import os
import re
import requests
from io import BytesIO
from flask import Flask, request, jsonify, send_file, render_template
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter

app = Flask(__name__)

# =====================================================
# CONFIGURAÇÃO MERCADO PAGO
# =====================================================

ACCESS_TOKEN = os.environ.get("MERCADO_PAGO_ACCESS_TOKEN")

if not ACCESS_TOKEN:
    raise ValueError("MERCADO_PAGO_ACCESS_TOKEN não configurado.")

MP_URL = "https://api.mercadopago.com/checkout/preferences"

# =====================================================
# FUNÇÕES EXCEL
# =====================================================

def extrair_colunas(texto):
    texto = texto.lower()
    padrao = r"coluna[s]?:?\s*(.*)"
    match = re.search(padrao, texto)

    if match:
        partes = re.split(",| e ", match.group(1))
        return [p.strip().title() for p in partes if p.strip()]

    return ["Descrição", "Valor"]


def ajustar_largura(ws):
    for col in ws.columns:
        max_len = 0
        letra = get_column_letter(col[0].column)
        for cell in col:
            if cell.value:
                max_len = max(max_len, len(str(cell.value)))
        ws.column_dimensions[letra].width = max_len + 3


def gerar_excel(prompt):

    colunas = extrair_colunas(prompt)

    wb = Workbook()
    ws = wb.active
    ws.title = "PromptSheet"

    for idx, col in enumerate(colunas, start=1):
        cell = ws.cell(row=1, column=idx, value=col)
        cell.font = Font(bold=True)
        cell.fill = PatternFill("solid", fgColor="EAEAEA")

    ws.freeze_panes = "A2"

    ajustar_largura(ws)

    output = BytesIO()
    wb.save(output)
    output.seek(0)

    return output


# =====================================================
# ROTAS
# =====================================================

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/create-payment", methods=["POST"])
def create_payment():

    data = request.get_json()

    if not data or "prompt" not in data:
        return jsonify({"error": "Prompt vazio"}), 400

    prompt = data["prompt"]
    base_url = request.host_url.rstrip("/")

    preference_data = {
        "items": [
            {
                "title": "Planilha personalizada - PromptSheet",
                "quantity": 1,
                "unit_price": 4.90
            }
        ],
        "back_urls": {
            "success": f"{base_url}/download?prompt={prompt}",
            "failure": base_url,
            "pending": base_url
        },
        "auto_return": "approved"
    }

    headers = {
        "Authorization": f"Bearer {ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }

    response = requests.post(MP_URL, json=preference_data, headers=headers)

    if response.status_code != 201:
        return jsonify({
            "error": "Erro ao criar pagamento",
            "detalhe": response.text
        }), 500

    checkout_url = response.json()["init_point"]

    return jsonify({"checkout_url": checkout_url})


@app.route("/download")
def download():

    prompt = request.args.get("prompt")

    if not prompt:
        return "Pagamento inválido", 400

    excel_file = gerar_excel(prompt)

    return send_file(
        excel_file,
        as_attachment=True,
        download_name="PromptSheet.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )


# =====================================================
# EXECUÇÃO RENDER
# =====================================================

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
