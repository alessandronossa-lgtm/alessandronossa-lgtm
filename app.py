import os
from flask import Flask, request, jsonify
from openai import OpenAI

app = Flask(__name__)

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

@app.route("/")
def home():
    return "O back-end do PromptSheet está ativo!"

@app.route("/generate", methods=["POST"])
def generate():
    data = request.get_json()

    descricao = data.get("descricao", "")

    if not descricao:
        return jsonify({"erro": "Descrição não informada"}), 400

    resposta = client.responses.create(
        model="gpt-5-mini",
        input=f"Crie a estrutura de uma planilha Excel para: {descricao}"
    )

    return jsonify({
        "resultado": resposta.output_text
    })
