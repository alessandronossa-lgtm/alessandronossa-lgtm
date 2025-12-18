import os
import uuid
from flask import Flask, request, jsonify, send_file
from openpyxl import Workbook

app = Flask(__name__)

@app.route("/", methods=["GET"])
def home():
    return jsonify({"status": "ok", "mensagem": "PromptSheet backend ativo"})

@app.route("/generate", methods=["POST"])
def generate():
    data = request.get_json()

    if not data or "descricao" not in data:
        return jsonify({"erro": "Campo 'descricao' é obrigatório"}), 400

    descricao = data["descricao"]

    # Criar arquivo Excel
    wb = Workbook()
    ws = wb.active
    ws.title = "Planilha"

    ws["A1"] = "Descrição da planilha"
    ws["A2"] = descricao

    ws["A4"] = "Exemplo de dados"
    ws["A5"] = "Item"
    ws["B5"] = "Quantidade"
    ws["C5"] = "Valor"

    ws.append(["Produto A", 10, 25])
    ws.append(["Produto B", 5, 40])

    # Salvar arquivo temporário
    filename = f"promptsheet_{uuid.uuid4().hex}.xlsx"
    filepath = os.path.join("/tmp", filename)
    wb.save(filepath)

    # Retornar arquivo para download
    return send_file(
        filepath,
        as_attachment=True,
        download_name="planilha.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
