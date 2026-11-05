# -*- coding: utf-8 -*-
"""
CENTURIO RTD STREAM - Tubasa Labs
Conector de dados em tempo real (Profit/Nelogica RTD) para o Dashboard Centurion.
"""
import time
import win32com.client
import pythoncom
import pandas as pd
from datetime import datetime

class ProfitRTDConnector:
    def __init__(self, ticker="WINZ26"):
        self.ticker = ticker
        self.rtd_server = None
        self.topic_id = None
        self.buffer = []
        self.running = False

    def conectar(self):
        """Inicializa a conexão COM com o servidor RTD do Profit."""
        pythoncom.CoInitialize() # Necessário para threads no Windows
        try:
            # O ProgID do servidor RTD do Profit pode variar. 
            # Geralmente é 'RTD.RTD' ou 'Profit.RTD' ou 'Nelogica.RTD'
            # Ajuste conforme a instalação do seu Profit.
            self.rtd_server = win32com.client.Dispatch("RTD.RTD")
            print(f"[CENTURIO] Conectado ao servidor RTD. Ticker: {self.ticker}")
            
            # Solicita a criação de um tópico RTD para o ativo
            # A string do tópico é específica do provedor. 
            # Exemplo: "WINZ26;ULT;1" ou "WINZ26;TICK"
            # Você precisará consultar o manual do Profit RTD para a string exata.
            # Aqui usamos um exemplo genérico de assinatura.
            self.topic_id = self.rtd_server.ConnectData(1, "WINZ26;ULT", True)
            print(f"[CENTURIO] Tópico RTD registrado: {self.topic_id}")
            
            self.running = True
            return True
        except Exception as e:
            print(f"[ERRO] Falha ao conectar ao RTD do Profit: {e}")
            return False

    def ler_dados(self):
        """Faz o polling dos dados RTD e atualiza o buffer."""
        if not self.running or self.rtd_server is None:
            return None
        
        try:
            # O método UpdateData força a atualização do tópico
            valor = self.rtd_server.RequestData(self.topic_id)
            if valor:
                # Formata o dado recebido (ajuste conforme o tipo de dado do Profit)
                agora = datetime.now()
                registro = {
                    'dt': agora,
                    'preco': float(valor),
                    'ticker': self.ticker
                }
                self.buffer.append(registro)
                
                # Mantém o buffer em um tamanho gerenciável (ex: últimos 10.000 ticks)
                if len(self.buffer) > 10000:
                    self.buffer = self.buffer[-10000:]
                
                return registro
        except Exception as e:
            print(f"[ERRO] Falha ao ler dados RTD: {e}")
            return None

    def desconectar(self):
        """Encerra a conexão e libera o COM."""
        self.running = False
        if self.rtd_server:
            try:
                self.rtd_server.DisconnectData(self.topic_id)
            except:
                pass
            self.rtd_server = None
        pythoncom.CoUninitialize()
        print("[CENTURIO] Desconectado do RTD.")

    def obter_dataframe(self):
        """Retorna o buffer como um DataFrame Pandas para o Dashboard/Auditor."""
        return pd.DataFrame(self.buffer)

# --- Exemplo de Uso (Loop de teste) ---
if __name__ == "__main__":
    conector = ProfitRTDConnector("WINZ26")
    if conector.conectar():
        print("[CENTURIO] Iniciando loop de captura de ticks. Pressione Ctrl+C para parar.")
        try:
            while True:
                dado = conector.ler_dados()
                if dado:
                    # Simula o que o Dashboard faria: envia para a interface ou buffer
                    print(f"Tick recebido: {dado['dt'].strftime('%H:%M:%S')} | Preço: {dado['preco']}")
                time.sleep(0.1) # Polling a cada 100ms
        except KeyboardInterrupt:
            print("\n[CENTURIO] Interrupção do usuário.")
        finally:
            conector.desconectar()