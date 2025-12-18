import os
import tempfile
from flask import Flask, request, jsonify, send_file
from openai import OpenAI
from openpyxl import Workbook

app = Flask(__name__)

# Inicializa cliente OpenAI usando variável de ambiente
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


@app.route("/", methods=["GET"])
def health():
    return {"status": "ok", "message": "PromptSheet backend online"}


@app.route("/generate", methods=["POST"])
def generate_sheet():
    data = request.get_json()

    if not data or "descricao" not in data:
        return jsonify({"error": "Campo 'descricao' é obrigatório"}), 400

    descricao = data["descricao"]

    # Prompt simples para gerar estrutura da planilha
    prompt = f"""
    Crie uma estrutura de planilha em formato de lista de colunas
    para o seguinte objetivo:

    {descricao}

    Retorne apenas os nomes das colunas, uma por linha.
    """

    try:
        response = client.responses.create(
            model="gpt-5-mini",
            input=prompt
        )

        texto = response.output_text.strip()
        colunas = [linha.strip() for linha in texto.split("\n") if linha.strip()]

        # Criar planilha Excel
        wb = Workbook()
        ws = wb.active
        ws.title = "Planilha"

        for idx, coluna in enumerate(colunas, start=1):
            ws.cell(row=1, column=idx, value=coluna)

        # Criar arquivo temporário
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx")
        wb.save(temp_file.name)

        return send_file(
            temp_file.name,
            as_attachment=True,
            download_name="planilha_gerada.xlsx",
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
