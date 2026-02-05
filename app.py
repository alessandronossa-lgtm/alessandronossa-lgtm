import os
import tempfile
from flask import Flask, request, jsonify, send_file
from openai import OpenAI
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

app = Flask(__name__)
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# =========================
# 1. IA — Extrair colunas e tipos
# =========================
def extract_structure(prompt: str):
    system_prompt = """
Você é um especialista em Excel.

REGRAS:
1. Se o cliente listar colunas explicitamente, use SOMENTE essas colunas.
2. Não crie colunas extras.
3. Se o cliente for vago, escolha APENAS 2 ou 3 colunas essenciais.
4. Para cada coluna, defina o tipo: texto, data, numero ou moeda.
5. Retorne APENAS JSON no formato:
[
  {"nome": "Coluna", "tipo": "texto|data|numero|moeda"}
]
"""

    response = client.responses.create(
        model="gpt-5-mini",
        input=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt}
        ]
    )

    return response.output_parsed


# =========================
# 2. Criar Excel profissional
# =========================
def create_excel(structure):
    wb = Workbook()
    ws = wb.active
    ws.title = "PromptSheet"

    # Estilos
    header_fill = PatternFill("solid", fgColor="E9F5EC")
    header_font = Font(bold=True)
    header_align = Alignment(horizontal="center", vertical="center")
    thin_border = Border(
        left=Side(style="thin"),
        right=Side(style="thin"),
        top=Side(style="thin"),
        bottom=Side(style="thin")
    )

    # Cabeçalho
    for col_idx, col in enumerate(structure, start=1):
        cell = ws.cell(row=1, column=col_idx, value=col["nome"])
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = header_align
        cell.border = thin_border
        ws.column_dimensions[get_column_letter(col_idx)].width = max(len(col["nome"]) + 4, 18)

    ws.freeze_panes = "A2"

    # Criar 10 linhas vazias prontas
    for row in range(2, 12):
        for col_idx, col in enumerate(structure, start=1):
            cell = ws.cell(row=row, column=col_idx)
            cell.border = thin_border

            if col["tipo"] == "data":
                cell.number_format = "DD/MM/YYYY"
            elif col["tipo"] == "moeda":
                cell.number_format = '"R$" #,##0.00'
            elif col["tipo"] == "numero":
                cell.number_format = '#,##0.00'

    # Fórmula automática: Quantidade x Preço = Total
    nomes = [c["nome"].lower() for c in structure]
    if "quantidade" in nomes and "preço" in nomes:
        q_col = nomes.index("quantidade") + 1
        p_col = nomes.index("preço") + 1

        # Criar coluna Total automaticamente
        total_col = len(structure) + 1
        ws.cell(row=1, column=total_col, value="Total").fill = header_fill
        ws.cell(row=1, column=total_col).font = header_font
        ws.cell(row=1, column=total_col).alignment = header_align
        ws.column_dimensions[get_column_letter(total_col)].width = 20

        for row in range(2, 12):
            ws.cell(
                row=row,
                column=total_col,
                value=f"={get_column_letter(q_col)}{row}*{get_column_letter(p_col)}{row}"
            ).number_format = '"R$" #,##0.00'

    return wb


# =========================
# 3. Rotas
# =========================
@app.route("/")
def home():
    return "PromptSheet backend ativo"

@app.route("/generate", methods=["POST"])
def generate():
    data = request.get_json()
    descricao = data.get("descricao", "").strip()

    if not descricao:
        return jsonify({"error": "Descrição não informada"}), 400

    structure = extract_structure(descricao)

    wb = create_excel(structure)

    temp = tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx")
    wb.save(temp.name)

    return send_file(
        temp.name,
        as_attachment=True,
        download_name="PromptSheet.xlsx"
    )

if __name__ == "__main__":
    app.run()
