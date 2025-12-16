from flask import Flask, request, jsonify

app = Flask(__name__)

@app.route("/")
def home():
    return "PromptSheet backend está vivo!"

@app.route("/generate", methods=["POST"])
def generate():
    data = request.json
    descricao = data.get("descricao", "")

    return jsonify({
        "status": "ok",
        "descricao_recebida": descricao
    })
