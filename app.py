from flask import Flask, request, send_file, render_template
from io import BytesIO
from openpyxl import Workbook
import re

app = Flask(__name__)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/generate', methods=['POST'])
def generate():
    description = request.form.get('description', '').strip()
    template = detect_template(description)
    wb = create_workbook_from_template(template)

    bio = BytesIO()
    wb.save(bio)
    bio.seek(0)

    return send_file(
        bio,
        as_attachment=True,
        download_name="prompt-sheet.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

def detect_template(text):
    t = text.lower()
    if re.search(r"venda|vendas|comercial|cliente", t):
        return "sales"
    if re.search(r"estoque|produto|quantidade", t):
        return "inventory"
    if re.search(r"fluxo de caixa|caixa|receita|despesa", t):
        return "cash"
    return "generic"

def create_workbook_from_template(template):
    wb = Workbook()
    ws = wb.active

    if template == "sales":
        ws.title = "Vendas"
        ws.append(["Data", "Cliente", "Produto", "Qtd", "Preço Unit.", "Total"])
    elif template == "inventory":
        ws.title = "Estoque"
        ws.append(["SKU", "Produto", "Categoria", "Quantidade", "Ponto de Reposição"])
    elif template == "cash":
        ws.title = "Fluxo de Caixa"
        ws.append(["Data", "Descrição", "Entrada", "Saída", "Saldo"])
    else:
        ws.title = "Planilha"
        ws.append(["Item", "Valor"])

    return wb

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
