from flask import Flask, request, jsonify, send_file
from openai import OpenAI
import openpyxl
import os
import uuid

app = Flask(__name__)

# Cliente OpenAI usando variável de ambiente
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

@app.route("/")
def home():
    return "PromptSheet backend está online 🚀"

@app.route("/generate", methods=["POST"])
def generate():
    data = request.get_json()

    if not data or "descricao" not in data:
        return jsonify({"erro": "Campo 'descricao' é obrigatório"}), 400

    descricao = data["descricao"]

    # Prompt para gerar estrutura da planilha
    prompt = f"""
Crie a estrutura de uma planilha Excel para: {descricao}

Retorne:
- Nome da planilha
- Nome das colunas
Sem explicações extras.
"""

    response = client.responses.create(
        model="gpt-5-mini",
        input=prompt
    )

    texto = response.output_text

    # Criar Excel
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Planilha"

    linhas = texto.split("\n")

    colunas = []
    for linha in linhas:
        linha = linha.strip("-• ")
        if linha:
            colunas.append(linha)

    # Se IA não retornar colunas, cria padrão
    if not colunas:
        colunas = ["Coluna 1", "Coluna 2", "Coluna 3"]

    ws.append(colunas)

    # Nome do arquivo
    nome_arquivo = f"planilha_{uuid.uuid4().hex}.xlsx"
    caminho = f"/tmp/{nome_arquivo}"
    wb.save(caminho)

    # Retorna o arquivo para download
    return send_file(
        caminho,
        as_attachment=True,
        download_name="planilha.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
