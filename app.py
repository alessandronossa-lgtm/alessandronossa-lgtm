import re
import uuid
import requests
from io import BytesIO
from flask import Flask, request, jsonify, send_file, render_template, redirect
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Border, Side
from openpyxl.utils import get_column_letter

app = Flask(__name__)

# ================================
# CONFIGURAÇÃO MERCADO PAGO
# ================================

ACCESS_TOKEN = "https://mpago.li/2UPf1zT"

BASE_URL = "https://api.mercadopago.com/checkout/preferences"


# ================================
# FUNÇÕES EXCEL
# ================================

def extrair_colunas(texto):
    texto = texto.lower()
    padrao = r"coluna[s]?:?\s*(.*)"
    match = re.search(padrao, texto)

    if match:
        partes = re.split(",| e ", match.group(1))
        return [p.strip().title() for p in partes if p.strip()]

    return ["Descrição", "Valor"]


def coluna_eh_numerica(nome):
    palavras_chave = [
        "quant", "valor", "preço", "preco", "total",
        "saldo", "entrada", "saida", "saída"
    ]
    nome = nome.lower()
    return any(p in nome for p in palavras_chave)


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


def ajustar_largura(ws):
    for col in ws.columns:
        max_len = 0
        col_letter = get_column_letter(col[0].column)
        for cell in col:
            if cell.value:
                max_len = max(max_len, len(str(cell.value)))
        ws.column_dimensions[col_letter].width = max_len + 3


# ================================
# ROTAS
# ================================

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/create-payment", methods=["POST"])
def create_payment():

    data = request.get_json()
    prompt = data.get("prompt")

    if not prompt:
        return jsonify({"error": "Prompt vazio"}), 400

    unique_id = str(uuid.uuid4())

    preference_data = {
        "items": [
            {
                "title": "Planilha personalizada - PromptSheet",
                "quantity": 1,
                "unit_price": 4.90
            }
        ],
        "back_urls": {
            "success": f"https://promptsheet-backend.onrender.com/download?id={unique_id}&prompt={prompt}",
            "failure": "https://promptsheet-backend.onrender.com",
            "pending": "https://promptsheet-backend.onrender.com"
        },
        "auto_return": "approved"
    }

    headers = {
        "Authorization": f"Bearer {ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }

    response = requests.post(BASE_URL, json=preference_data, headers=headers)

    if response.status_code != 201:
        return jsonify({"error": "Erro ao criar pagamento"}), 500

    init_point = response.json()["init_point"]

    return jsonify({"checkout_url": init_point})


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
