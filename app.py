import re
from io import BytesIO
from flask import Flask, request, jsonify, send_file, render_template
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Border, Side
from openpyxl.utils import get_column_letter

app = Flask(__name__)

# -------------------------------
# Funções auxiliares
# -------------------------------

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


def ajustar_largura(ws):
    for col in ws.columns:
        max_len = 0
        col_letter = get_column_letter(col[0].column)
        for cell in col:
            if cell.value:
                max_len = max(max_len, len(str(cell.value)))
        ws.column_dimensions[col_letter].width = max_len + 3


# -------------------------------
# Rotas
# -------------------------------

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/generate", methods=["POST"])
def generate():
    try:
        data = request.get_json(silent=True)

        if not data or "prompt" not in data:
            return jsonify({"error": "Prompt vazio"}), 400

        prompt = data["prompt"].strip()

        if not prompt:
            return jsonify({"error": "Prompt vazio"}), 400

        colunas = extrair_colunas(prompt)

        wb = Workbook()
        ws = wb.active
        ws.title = "PromptSheet"

        # Cabeçalho
        for idx, col in enumerate(colunas, start=1):
            cell = ws.cell(row=1, column=idx, value=col)
            cell.font = Font(bold=True)
            cell.fill = PatternFill("solid", fgColor="EAEAEA")

        ws.freeze_panes = "A2"
        ws.auto_filter.ref = ws.dimensions

        # Linha TOTAL (linha 2)
        total_row = 2
        ws.cell(row=total_row, column=1, value="TOTAL").font = Font(bold=True)

        for idx, col in enumerate(colunas, start=1):
            if coluna_eh_numerica(col):
                letra = get_column_letter(idx)
                ws.cell(
                    row=total_row,
                    column=idx,
                    value=f"=SUM({letra}3:{letra}1048576)"
                ).font = Font(bold=True)

        fill_total = PatternFill("solid", fgColor="F2F2F2")
        borda = Border(top=Side(style="medium"))

        for col in range(1, len(colunas) + 1):
            c = ws.cell(row=total_row, column=col)
            c.fill = fill_total
            c.border = borda

        ajustar_largura(ws)

        output = BytesIO()
        wb.save(output)
        output.seek(0)

        return send_file(
            output,
            as_attachment=True,
            download_name="PromptSheet.xlsx",
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

    except Exception as e:
        print("ERRO NO BACKEND:", e)
        return jsonify({"error": "Erro ao gerar planilha"}), 500


if __name__ == "__main__":
    app.run(debug=True)
