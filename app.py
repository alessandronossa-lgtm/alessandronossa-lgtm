from flask import Flask, request, jsonify

app = Flask(__name__)

@app.route("/")
def home():
    return "PromptSheet backend está vivo!"

@app.route("/generate", methods=["GET"])
def generate():
    return jsonify({
        "status": "ok",
        "mensagem": "rota generate funcionando"
    })
