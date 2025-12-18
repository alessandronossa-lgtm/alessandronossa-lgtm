import os
import io
from flask import Flask, request, send_file, jsonify
from openai import OpenAI
from openpyxl import Workbook

app = Flask(__name__)

# Cliente OpenAI usando variável de ambiente
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


@app.route("/", methods=["GET"])
def home():
    return {"status": "ok", "mensagem": "PromptSheet backend online"}


@app.route("/generate", methods=["POST"])
def generate():
    try:
        data = request.get_json()

        if not data or "descricao" not in data:
            return jsonify({"erro": "Campo 'descricao' é obrigatório"}), 400

        descricao = data["descricao"]

        # Prompt simples (MVP)
        prompt = f"""
Crie uma estrutura de planilha em formato de tabela para:
{descricao}

Retorne apenas os nomes das colunas, separados por vírgula.
"""

        response = client.responses.create(
            model="gpt-5-mini",
            input=prompt
        )

        texto = response.output_text.strip()

        colunas = [c.strip() for c in texto.split(",") if c.strip()]

        if not colunas:
            return jsonify({"erro": "IA não retornou colunas"}), 500

        # Criar Excel
        wb = Workbook()
        ws = wb.active
        ws.title = "Planilha"

        ws.append(colunas)

        # Salvar em memória
        output = io.BytesIO()
        wb.save(output)
        output.seek(0)

        return send_file(
            output,
            as_attachment=True,
            download_name="planilha.xlsx",
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

    except Exception as e:
        return jsonify({"erro": str(e)}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
