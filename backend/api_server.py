from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
import asyncio
import json
import random
from datetime import datetime

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
            # MOCK DATA (Simulação)
            # Quando a DLL conectar, esta parte será substituída pelos 
            # dados reais do centurio_dll_stream.py
            # ========================================================
            
            # Simula a variação do WIN (ex: 129.650 a 129.700)
            preco_atual = round(129650 + random.uniform(-50, 50))
            
            # Simula os indicadores
            estocastico = round(random.uniform(10, 90), 1)
            ifr = round(random.uniform(20, 80), 1)
            neblina = round(random.uniform(0, 100), 1) # Entropia de Shannon
            
            # Lógica simplificada de sinal para visualização
            sinal = "COMPRA" if estocastico < 20 and ifr < 30 else "VENDA" if estocastico > 80 and ifr > 70 else "AGUARDAR"
            
            # Payload que o Frontend vai receber
            payload = {
                "timestamp": datetime.now().strftime("%H:%M:%S"),
                "preco": preco_atual,
                "estocastico": estocastico,
                "ifr": ifr,
                "neblina": neblina,
                "sinal": sinal
            }
            
            # Envia os dados para o Front-end
            await websocket.send_text(json.dumps(payload))
            
            # Atualiza a cada 1 segundo (simulando ticks)
            await asyncio.sleep(1)
            
    except WebSocketDisconnect:
        print("🔴 Frontend desconectado.")

if __name__ == "__main__":
    import uvicorn
    # Roda o servidor na porta 8000
    uvicorn.run(app, host="127.0.0.1", port=8000)