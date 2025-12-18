from flask import Flask, request, jsonify
import os
import openai

# Cria o app Flask
app = Flask(__name__)

# Lê a chave da OpenAI da variável de ambiente
openai.api_key = os.getenv("OPENAI_API_KEY")


@app.route("/", methods=["GET"])
def home():
    return "PromptSheet backend online 🚀", 200


@app.route("/generate", methods=["POST"])
def generate():
    try:
        data = request.get_json()

        if not data or "descricao" not in data:
            return jsonify({
                "status": "erro",
                "mensagem": "Campo 'descricao' é obrigatório"
            }), 400

        descricao = data["descricao"]

        # Chamada simples à OpenAI
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {
                    "role": "system",
                    "content": "Você é um assistente especialista em criar estruturas de planilhas em Excel."
                },
                {
                    "role": "user",
                    "content": f"Crie a estrutura de uma planilha de Excel para: {descricao}"
                }
            ],
            temperature=0.3
        )

        texto_gerado = response.choices[0].message.content

        return jsonify({
            "status": "ok",
            "resultado": texto_gerado
        })

    except Exception as e:
        return jsonify({
            "status": "erro",
            "mensagem": str(e)
        }), 500


# Necessário para o Render + Gunicorn
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
