import os
import tempfile
from flask import Flask, request, jsonify, send_file
from openai import OpenAI
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
from openpyxl.utils import get_column_letter

app = Flask(__name__)

# OpenAI client
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# -----------------------------
# GUIA VISUAL PROMPTSHEET v1
# -----------------------------
HEADER_FILL = PatternFill("solid", fgColor="217346")  # Verde PromptSheet
HEADER_FONT = Font(color="FFFFFF", bold=True)
HEADER_ALIGNMENT = Alignment(horizontal="center", vertical="center")

BODY_ALIGNMENT = Alignment(vertical="center")
THIN_BORDER = Border(
    left=Side(style="thin"),
    right=Side(style="thin"),
    top=Side(style="thin"),
    bottom=Side(style="thin"),
)

# -----------------------------
# ROTAS
# -----------------------------

@app.route("/")
def home():
    return send_file("templates/index.html")


@app.route("/generate", methods=["POST"])
def generate():
    data = request.get_json()
    descricao = data.get("descricao", "").strip()

    if not descricao:
        return jsonify({"erro": "Descrição não informada"}), 400

    # -----------------------------
    # 1. IA extrai colunas conforme pedido do cliente
    # -----------------------------
    prompt = f"""
Você é um especialista em Excel profissional.

A partir da descrição do cliente abaixo, extraia APENAS a lista de colunas
que a planilha deve ter, respeitando exatamente o que o cliente pediu.

Se o cliente mencionar colunas específicas, use somente elas.
Não invente colunas extras.
Responda apenas em formato de lista simples, separada por vírgulas.

Descrição do cliente:
{descricao}
"""

    response = client.responses.create(
        model="gpt-5-mini",
        input=prompt
    )

    colunas_texto = response.output_text.strip()
    colunas = [c.strip() for c in colunas_texto.split(",") if c.strip()]

    if not colunas:
        return jsonify({"erro": "Não foi possível identificar colunas"}), 400

    # -----------------------------
    # 2. Criar Excel profissional
    # -----------------------------
    wb = Workbook()
    ws = wb.active
    ws.title = "Planilha"

    # Cabeçalhos
    for col_idx, coluna in enumerate(colunas, start=1):
        cell = ws.cell(row=1, column=col_idx, value=coluna)
        cell.font = HEADER_FONT
        cell.fill = HEADER_FILL
        cell.alignment = HEADER_ALIGNMENT
        cell.border = THIN_BORDER

    # Linhas iniciais (10 linhas vazias formatadas)
    for row in range(2, 12):
        for col_idx in range(1, len(colunas) + 1):
            cell = ws.cell(row=row, column=col_idx, value="")
            cell.alignment = BODY_ALIGNMENT
            cell.border = THIN_BORDER

    # Ajustar largura automática
    for col_idx, coluna in enumerate(colunas, start=1):
        ws.column_dimensions[get_column_letter(col_idx)].width = max(18, len(coluna) + 5)

    ws.freeze_panes = "A2"

    # -----------------------------
    # 3. Salvar arquivo temporário
    # -----------------------------
    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx")
    wb.save(temp_file.name)
    temp_file.close()

    return send_file(
        temp_file.name,
        as_attachment=True,
        download_name="PromptSheet.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )


if __name__ == "__main__":
    app.run(debug=True)
