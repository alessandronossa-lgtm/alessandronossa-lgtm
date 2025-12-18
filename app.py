from flask import Flask, request, send_file, jsonify
import openai
import os
from io import BytesIO
from openpyxl import Workbook

app = Flask(__name__)

# Usa a chave vinda das variáveis de ambiente do Render
openai.api_key = os.getenv("OPENAI_API_KEY")


@app.route("/")
def home():
    return "PromptSheet backend está ativo!"


@app.route("/generate", methods=["POST"])
def generate():
    try:
        data = request.get_json()
        descricao = data.get("descricao")

        if not descricao:
            return jsonify({"erro": "Descrição não informada"}), 400

        # Prompt simples e controlado
        prompt = f"""
        Gere uma lista de colunas para uma planilha Excel baseada na seguinte descrição:
        "{descricao}"

        Responda apenas com os nomes das colunas, separados por vírgula.
        """

        response = openai.ChatCompletion.create(
            model="gpt-5-mini",
            messages=[
                {"role": "system", "content": "Você é um assistente que cria estruturas de planilhas."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.2
        )

        colunas_texto = response.choices[0].message.content
        colunas = [c.strip() for c in colunas_texto.split(",")]

        # Criar Excel em memória
        wb = Workbook()
        ws = wb.active
        ws.title = "Planilha"

        ws.append(colunas)

        output = BytesIO()
        wb.save(output)
        output.seek(0)

        return send_file(
            output,
            download_name="promptsheet.xlsx",
            as_attachment=True,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

    except Exception as e:
        return jsonify({"erro": str(e)}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
