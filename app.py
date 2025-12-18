import os
from flask import Flask, request, send_file, jsonify
from openai import OpenAI
from openpyxl import Workbook
from io import BytesIO

app = Flask(__name__)

# Cliente OpenAI usando variável de ambiente
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

@app.route("/")
def home():
    return "PromptSheet backend está ativo"

@app.route("/generate", methods=["POST"])
def generate():
    try:
        data = request.get_json()
        descricao = data.get("descricao")

        if not descricao:
            return jsonify({"erro": "Descrição não informada"}), 400

        # Prompt para gerar colunas da planilha
        prompt = f"""
        Gere uma lista de colunas para uma planilha Excel com base nesta descrição:
        "{descricao}"

        Retorne apenas os nomes das colunas, separados por vírgula.
        """

        response = client.responses.create(
            model="gpt-5-mini",
            input=prompt
        )

        texto = response.output_text
        colunas = [c.strip() for c in texto.split(",") if c.strip()]

        if not colunas:
            return jsonify({"erro": "Não foi possível gerar colunas"}), 500

        # Criar planilha Excel
        wb = Workbook()
        ws = wb.active
        ws.title = "Planilha"

        ws.append(colunas)

        # Salvar em memória
        arquivo = BytesIO()
        wb.save(arquivo)
        arquivo.seek(0)

        return send_file(
            arquivo,
            as_attachment=True,
            download_name="planilha.xlsx",
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

    except Exception as e:
        return jsonify({"erro": str(e)}), 500


if __name__ == "__main__":
    app.run(debug=True)
