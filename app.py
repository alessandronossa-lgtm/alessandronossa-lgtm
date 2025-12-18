import os
from flask import Flask, request, jsonify
from openai import OpenAI

app = Flask(__name__)

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

@app.route("/")
def home():
    return "PromptSheet backend está ativo 🚀"

@app.route("/generate", methods=["POST"])
def generate():
    data = request.get_json()

    if not data or "descricao" not in data:
        return jsonify({"erro": "Campo 'descricao' é obrigatório"}), 400

    descricao = data["descricao"]

    prompt = f"""
Você é um especialista em planilhas.
Com base na descrição abaixo, gere uma estrutura de planilha em JSON.

Descrição:
{descricao}

Responda APENAS em JSON no formato:
{{
  "planilha": {{
    "nome": "Nome da planilha",
    "colunas": [
      "Coluna 1",
      "Coluna 2",
      "Coluna 3"
    ]
  }}
}}
"""

    response = client.responses.create(
        model="gpt-5-mini",
        input=prompt
    )

    texto = response.output_text

    return jsonify({
        "resultado": texto
    })
