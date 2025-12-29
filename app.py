import os
import tempfile
from flask import Flask, request, jsonify, send_file
from openai import OpenAI
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter

app = Flask(__name__)

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# =========================
# Função: extrair colunas do texto do cliente
# =========================
def extract_columns_from_prompt(prompt: str):
    """
    A IA só extrai colunas explicitamente citadas pelo cliente.
    Se o cliente não listar colunas, a IA escolhe o mínimo essencial (2–3),
    coerente com o contexto (estoque, vendas, financeiro).
    """

    system_prompt = """
Você é um assistente especializado em Excel.

REGRAS OBRIGATÓRIAS:
1. Se o cliente listar colunas explicitamente, use SOMENTE essas colunas.
2. NÃO crie colunas extras.
3. Se o cliente NÃO listar colunas, escolha APENAS 2 ou 3 colunas essenciais,
   coerentes com o contexto.
4. Retorne APENAS uma lista simples, separada por ponto e vírgula.
5. Não explique nada.
"""

    response = client.responses.create(
        model="gpt-5-mini",
        input=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt}
        ]
    )

    raw = response.output_text.strip()
    columns = [c.strip() for c in raw.split(";") if c.strip()]
    return columns


# =========================
# Função: criar planilha formatada
# =========================
def create_excel(columns):
    wb = Workbook()
    ws = wb.active
    ws.title = "Planilha"

    # Estilos PromptSheet v1 (leve e moderno)
    header_fill = PatternFill("solid", fgColor="E9F5EC")
    header_font = Font(bold=True)
    header_align = Alignment(horizontal="center", vertical="center")

    # Cabeçalhos
    for col_index, col_name in enumerate(columns, start=1):
        cell = ws.cell(row=1, column=col_index, value=col_name)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = header_align

    # Ajustar largura automática
    for col_index, col_name in enumerate(columns, start=1):
        ws.column_dimensions[get_column_letter(col_index)].width = max(
            len(col_name) + 4, 18
        )

    return wb


# =========================
# ROTAS
# =========================
@app.route("/")
def home():
    return "PromptSheet — backend ativo"


@app.route("/generate", methods=["POST"])
def generate():
    data = request.get_json()
    descricao = data.get("descricao", "").strip()

    if not descricao:
        return jsonify({"error": "Descrição não informada"}), 400

    # 1. Extrair colunas conforme premissa acordada
    columns = extract_columns_from_prompt(descricao)

    if not columns:
        return jsonify({"error": "Não foi possível identificar colunas"}), 400

    # 2. Criar Excel
    wb = create_excel(columns)

    # 3. Salvar arquivo temporário
    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx")
    wb.save(temp_file.name)

    # 4. Enviar para download
    return send_file(
        temp_file.name,
        as_attachment=True,
        download_name="PromptSheet.xlsx"
    )


if __name__ == "__main__":
    app.run()
