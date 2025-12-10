from fastapi import FastAPI, UploadFile, Form
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
import openpyxl
import uuid
import os

app = FastAPI()

# Permite acesso do frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.post("/gerar")
async def gerar_planilha(descricao: str = Form(...)):
    # Cria nome único
    file_name = f"planilha_{uuid.uuid4().hex}.xlsx"

    # Cria planilha simples baseada na descrição
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Planilha Gerada"

    ws["A1"] = "Descrição da planilha"
    ws["A2"] = descricao

    wb.save(file_name)

    return FileResponse(
        file_name,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename="planilha_gerada.xlsx"
    )

