from flask import Flask, request, jsonify

app = Flask(__name__)

@app.route("/")
def home():
    return "PromptSheet backend está vivo!"

@app.route("/generate", methods=["POST"])
def generate():
    data = request.get_json(silent=True)

    if not data or "descricao" not in data:
        return jsonify({
            "status": "erro",
            "mensagem": "Campo 'descricao' não enviado"
        }), 400

    descricao = data["descricao"]

    return jsonify({
        "status": "ok",
        "descricao_recebida": descricao
    })
