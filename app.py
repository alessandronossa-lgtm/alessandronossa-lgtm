import os
import tempfile
from flask import Flask, request, jsonify, send_file, render_template
from openai import OpenAI
from openpyxl import Workbook

app = Flask(__name__)

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

@app.route("/")
def index():
    return render_template("index.html")

# =========================
# ROTA BACKEND / IA + EXCEL
# =========================
@app.route("/generate", methods=["POST"])
def generate():
    data = request.get_json()

    if not data or "descricao" not in data:
        return jsonify({"erro": "Descrição não enviada"}), 400

    descricao = data["descricao"]

    # Chamada à OpenAI
    response = client.responses.create(
        model="gpt-5-mini",
        input=f"""
        Crie uma estrutura de planilha Excel para o seguinte pedido:
        {descricao}

        Retorne apenas os nomes das colunas, separados por vírgula.
        """
    )

    colunas_texto = response.output_text.strip()
    colunas = [c.strip() for c in colunas_texto.split(",")]

    # Criar arquivo Excel temporário
    wb = Workbook()
    ws = wb.active
    ws.title = "Planilha"

    ws.append(colunas)

    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx")
    wb.save(temp_file.name)

    return send_file(
        temp_file.name,
        as_attachment=True,
        download_name="planilha_promptsheet.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

# =========================
# START
# =========================
if __name__ == "__main__":
    app.run(debug=True)
