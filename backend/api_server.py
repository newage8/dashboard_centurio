from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
import asyncio
import json
import random
from datetime import datetime
import os
from dotenv import load_dotenv

# Carrega as variáveis do arquivo .env
load_dotenv()

app = FastAPI()

# Permite que o frontend acesse o backend sem bloqueios de CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Rota simples para testar se o servidor está no ar
@app.get("/")
def read_root():
    return {"status": "Centurion API Online", "aguardando_dll": True}

# Rota do WebSocket para dados em tempo real
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    print("🟢 Frontend conectado ao WebSocket!")
    
    try:
        while True:
            # ========================================================
            # MOCK DATA (Simulação com os novos filtros do Motor)
            # ========================================================
            
            # Simula a variação do WIN (ex: 129.650 a 129.700)
            preco_atual = round(129650 + random.uniform(-50, 50))
            
            # Simula os indicadores
            estocastico = round(random.uniform(10, 90), 1)
            ifr = round(random.uniform(20, 80), 1)
            neblina = round(random.uniform(0, 100), 1) # Entropia de Shannon
            
            # Simula o range do candle (em pontos)
            range_candle = random.randint(20, 200)
            
            # Pega a hora atual do sistema
            agora = datetime.now()

            # --------------------------------------------------------
            # LÓGICA DO MOTOR E FILTROS DE ELITE
            # --------------------------------------------------------
            sinal = "AGUARDAR"
            motivo = ""

            # Regras dos Filtros
            horario_permitido = (agora.hour >= 11 and agora.hour < 15) # 11:00 às 15:00
            range_permitido = range_candle <= 150
            neblina_permitida = neblina < 70

            # Lógica de Gatilho (Reversal Puro)
            gatilho_compra = estocastico < 20 and ifr < 30
            gatilho_venda = estocastico > 80 and ifr > 70

            # Verifica se há gatilho e aplica os filtros
            if gatilho_compra or gatilho_venda:
                if not horario_permitido:
                    motivo = "Bloqueado: Fora do Horário"
                elif not range_permitido:
                    motivo = f"Bloqueado: Candle Esticado ({range_candle} pts)"
                elif not neblina_permitida:
                    motivo = "Bloqueado: Neblina Alta"
                else:
                    sinal = "COMPRA" if gatilho_compra else "VENDA"
                    motivo = "Gatilho Válido"
            else:
                motivo = "Aguardando Reversal"

            # Payload que o Frontend vai receber
            payload = {
                "timestamp": agora.strftime("%H:%M:%S"),
                "preco": preco_atual,
                "estocastico": estocastico,
                "ifr": ifr,
                "neblina": neblina,
                "range_candle": range_candle,
                "sinal": sinal,
                "motivo": motivo # Novo campo de auditoria
            }
            
            # Envia os dados para o Front-end
            await websocket.send_text(json.dumps(payload))
            
            # Atualiza a cada 1 segundo
            await asyncio.sleep(1)
            
    except WebSocketDisconnect:
        print("🔴 Frontend desconectado.")

if __name__ == "__main__":
    import uvicorn
    # Roda o servidor na porta 8000
    uvicorn.run(app, host="127.0.0.1", port=8000)