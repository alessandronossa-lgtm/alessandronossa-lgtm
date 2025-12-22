import os
import tempfile
from flask import Flask, request, send_file, render_template
from openai import OpenAI
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.chart import BarChart, LineChart, Reference

app = Flask(__name__)

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/generate", methods=["POST"])
def generate():
    descricao = request.form.get("descricao")

    # ===== 1. USAR IA PARA ENTENDER ESTRUTURA =====
    prompt = f"""
    A partir da descrição abaixo, retorne apenas uma lista de colunas para uma planilha Excel.
    Não explique nada. Apenas as colunas separadas por vírgula.

    Descrição:
    {descricao}
    """

    resposta = client.responses.create(
        model="gpt-5-mini",
        input=prompt
    )

    colunas = resposta.output_text.strip().split(",")

    # ===== 2. CRIAR PLANILHA =====
    wb = Workbook()
    ws = wb.active
    ws.title = "Planilha"

    header_fill = PatternFill("solid", fgColor="E8F0FE")
    header_font = Font(bold=True)

    # Cabeçalhos
    for col_index, coluna in enumerate(colunas, start=1):
        cell = ws.cell(row=1, column=col_index, value=coluna.strip())
        cell.fill = header_fill
        cell.font = header_font
        ws.column_dimensions[cell.column_letter].width = max(18, len(coluna) + 4)

    # ===== 3. LINHA DE TOTAL (AUTOMÁTICA) =====
    total_row = 20
    ws.cell(row=total_row, column=1, value="TOTAL").font = Font(bold=True)

    for col in range(2, len(colunas) + 1):
        ws.cell(
            row=total_row,
            column=col,
            value=f"=SUM({ws.cell(row=2, column=col).coordinate}:{ws.cell(row=total_row-1, column=col).coordinate})"
        )

    ws.cell(row=total_row, column=1).fill = PatternFill("solid", fgColor="DFF0D8")

    # ===== 4. GRÁFICO AUTOMÁTICO =====
    chart = BarChart()
    chart.title = "Resumo Visual"
    chart.style = 10
    chart.y_axis.title = "Valores"
    chart.x_axis.title = colunas[0]

    data = Reference(ws, min_col=2, min_row=1, max_col=len(colunas), max_row=total_row-1)
    categories = Reference(ws, min_col=1, min_row=2, max_row=total_row-1)

    chart.add_data(data, titles_from_data=True)
    chart.set_categories(categories)

    ws.add_chart(chart, f"{chr(65 + len(colunas) + 2)}2")

    # ===== 5. SALVAR E ENVIAR =====
    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx")
    wb.save(temp_file.name)

    return send_file(
        temp_file.name,
        as_attachment=True,
        download_name="PromptSheet.xlsx"
    )
