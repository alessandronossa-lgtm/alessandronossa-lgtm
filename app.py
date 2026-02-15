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
    ws.t
