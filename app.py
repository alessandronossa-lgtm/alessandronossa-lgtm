import os
import tempfile
from flask import Flask, request, send_file, jsonify
from openai import OpenAI
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Border, Side, Alignment
from openpyxl.utils import get_column_letter

app = Flask(__name__)

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# =========================
# ROTA PRINCIPAL (HTML)
# =========================
@app.route("/")
def home():
    from flask import render_template
    return render_template("index.html")


# =========================
# GERAR PLANILHA
# =========================
@app.route("/generate", methods=["POST"])
def generate():
    data = request.get_json()
    descricao = data.get("descricao")

    if not descricao:
        return jsonify({"erro": "Descrição não enviada"}), 400

    # =========================
    # 1️⃣ IA INTERPRETA A ESTRUTURA
    # =========================
    prompt = f"""
Você é um especialista em Excel.

A partir do texto do usuário, extraia SOMENTE a lista de colunas desejadas.
Respeite exatamente o que o usuário pediu.
Não invente colunas extras.

Texto do usuário:
"{descricao}"

Responda apenas com as colunas, separadas por vírgula.
Exemplo:
Data, Produto, Quantidade
"""

    response = client.responses.create(
        model="gpt-5-mini",
        input=prompt
    )

    colunas_texto = response.output_text.strip()
    colunas = [c.strip() for c in colunas_texto.split(",") if c.strip()]

    if not colunas:
        return jsonify({"erro": "Não foi possível identificar as colunas"}), 400

    # =========================
    # 2️⃣ CRIAR EXCEL
    # =========================
    wb = Workbook()
    ws = wb.active
    ws.title = "Planilha"

    # Estilos PromptSheet v2
    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill("solid", fgColor="217346")  # Verde PromptSheet
    border = Border(
        left=Side(style="thin"),
        right=Side(style="thin"),
        top=Side(style="thin"),
        bottom=Side(style="thin")
    )

    # =========================
    # 3️⃣ CABEÇALHO
    # =========================
    for col_idx, coluna in enumerate(colunas, start=1):
        cell = ws.cell(row=1, column=col_idx, value=coluna)
        cell.font = header_font
        cell.fill = header_fill
        cell.border = border
        cell.alignment = Alignment(horizontal="center", vertical="center")

    # Congelar cabeçalho
    ws.freeze_panes = "A2"

    # =========================
    # 4️⃣ AJUSTAR LARGURA
    # =========================
    for col_idx in range(1, len(colunas) + 1):
        ws.column_dimensions[get_column_letter(col_idx)].width = 22

    # =========================
    # 5️⃣ SALVAR ARQUIVO
    # =========================
    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx")
    wb.save(temp_file.name)

    return send_file(
        temp_file.name,
        as_attachment=True,
        download_name="PromptSheet.xlsx"
    )


if __name__ == "__main__":
    app.run(debug=True)
