import os
from flask import Flask, request, jsonify
from openai import OpenAI

app = Flask(__name__)

# Cliente OpenAI usando variável de ambiente
client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY")
)

@app.route("/", methods=["GET"])
def home():
    return "PromptSheet backend está ativo!"

@app.route("/generate", methods=["POST"])
def generate():
    try:
        data = request.get_json()

        if not data or "descricao" not in data:
            return jsonify({"erro": "Campo 'descricao' é obrigatório"}), 400

        descricao = data["descricao"]

        prompt = f"""
Você é um especialista em Excel.
Com base na descrição abaixo, gere apenas uma lista de colunas
para uma planilha, em formato JSON.

Descrição:
{descricao}

Retorne apenas neste formato:
{{
  "colunas": ["Coluna 1", "Coluna 2", "Coluna 3"]
}}
"""

        response = client.responses.create(
            model="gpt-5-mini",
            input=prompt
        )

        texto = response.output_text

        return jsonify({
            "descricao": descricao,
            "resultado": texto
        })

    except Exception as e:
        return jsonify({"erro": str(e)}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
