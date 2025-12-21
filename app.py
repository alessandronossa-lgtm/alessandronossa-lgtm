import os
import tempfile
from flask import Flask, request, send_file, render_template
from openai import OpenAI
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter

app = Flask(__name__)
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# ---------- HOME ----------
@app.route("/")
def index():
    return render_template("index.html")

# ---------- GERAÇÃO DA PLANILHA ----------
@app.route("/generate", methods=["POST"])
def generate():
    data = request.json
    descricao = data.get("descricao")

    if not descricao:
        return {"erro": "Descrição não informada"}, 400

    # 1️⃣ IA interpreta colunas
    prompt = f"""
    A partir da descrição abaixo, retorne APENAS uma lista de colunas,
    na ordem correta, separadas por ponto e vírgula.

    Descrição do cliente:
    {descricao}
    """

    response = client.responses.create(
        model="gpt-5-mini",
        input=prompt
    )

    colunas = response.output_text.strip().split(";")
    colunas = [c.strip() for c in colunas if c.strip()]

    # 2️⃣ Criar Excel
    wb = Workbook()
    ws = wb.active
    ws.title = "PromptSheet"

    header_fill = PatternFill("solid", fgColor="D9E1F2")
    header_font = Font(bold=True)

    # Cabeçalhos
    for col_idx, col_name in enumerate(colunas, start=1):
        cell = ws.cell(row=1, column=col_idx, value=col_name)
        cell.fill = header_fill
        cell.font = header_font

    # 3️⃣ Fórmulas inteligentes
    col_map = {name.lower(): idx + 1 for idx, name in enumerate(colunas)}

    has_price = any("preço" in c.lower() or "valor unit" in c.lower() for c in colunas)
    has_qty = any("quant" in c.lower() for c in colunas)
    has_total = any("total" in c.lower() or "valor final" in c.lower() for c in colunas)

    start_row = 2
    end_row = 100  # limite inicial padrão

    # Multiplicação automática
    if has_price and has_qty and has_total:
        price_col = next(c for c in col_map if "preço" in c or "valor unit" in c)
        qty_col = next(c for c in col_map if "quant" in c)
        total_col = next(c for c in col_map if "total" in c or "valor final" in c)

        for row in range(start_row, end_row):
            ws.cell(
                row=row,
                column=col_map[total_col],
                value=f"={get_column_letter(col_map[price_col])}{row}*{get_column_letter(col_map[qty_col])}{row}"
            )

    # 4️⃣ Linha de total
    total_row = end_row + 1
    ws.cell(row=total_row, column=1, value="TOTAL").font = Font(bold=True)

    for col_name, col_idx in col_map.items():
        if any(x in col_name for x in ["total", "valor", "quant"]):
            ws.cell(
                row=total_row,
                column=col_idx,
                value=f"=SUM({get_column_letter(col_idx)}{start_row}:{get_column_letter(col_idx)}{end_row})"
            ).font = Font(bold=True)

    total_fill = PatternFill("solid", fgColor="F2F2F2")
    for col in range(1, len(colunas) + 1):
        ws.cell(row=total_row, column=col).fill = total_fill

    # 5️⃣ Ajustar largura das colunas (corrigido)
    for col_idx, col_name in enumerate(colunas, start=1):
        ws.column_dimensions[get_column_letter(col_idx)].width = max(len(col_name) + 5, 18)

    # 6️⃣ Salvar arquivo
    temp = tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx")
    wb.save(temp.name)

    return send_file(
        temp.name,
        as_attachment=True,
        download_name="PromptSheet.xlsx"
    )

if __name__ == "__main__":
    app.run(debug=True)
