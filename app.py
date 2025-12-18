from flask import Flask, request, jsonify, send_file
import os
import openai
import openpyxl
from openpyxl import Workbook
from tempfile import NamedTemporaryFile

app = Flask(__name__)

# Configura a chave da OpenAI via variável de ambiente
openai.api_key = os.getenv("OPENAI_API_KEY")


@app.route("/", methods=["GET"])
def home():
    return jsonify({
        "status": "ok",
        "mensagem": "PromptSheet backend ativo 🚀"
    })


@app.route("/generate", methods=["POST"])
def generate_sheet():
    try:
        data = request.get_json()
        descricao = data.get("descricao")

        if not descricao:
            return jsonify({"erro": "Campo 'descricao' é obrigatório"}), 400

        # Prompt simples para MVP
        prompt = f"""
        Crie a estrutura de uma planilha em Excel para o seguinte objetivo:
        {descricao}

        Retorne apenas os nomes das colunas, separados por vírgula.
        """

        response = openai.ChatCompletion.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "Você é um especialista em Excel."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3
        )

        colunas_texto = response.choices[0].message.content
        colunas = [c.strip() for c in colunas_texto.split(",")]

        # Cria o Excel
        wb = Workbook()
        ws = wb.active
        ws.title = "Planilha"

        for idx, coluna in enumerate(colunas, start=1):
            ws.cell(row=1, column=idx, value=coluna)

        temp_file = NamedTemporaryFile(delete=False, suffix=".xlsx")
        wb.save(temp_file.name)

        return send_file(
            temp_file.name,
            as_attachment=True,
            download_name="planilha_promptsheet.xlsx"
        )

    except Exception as e:
        return jsonify({"erro": str(e)}), 500


if __name__ == "__main__":
    app.run(debug=True)
