const WS_URL = 'ws://127.0.0.1:8000/ws';
let ws;

function connectWebSocket() {
    ws = new WebSocket(WS_URL);

    ws.onopen = function() {
        console.log("🟢 Conectado ao WebSocket do Centurion!");
        
        // Esconde a mensagem de espera no gráfico
        const msgGrafico = document.getElementById('msg-grafico');
        if (msgGrafico) msgGrafico.style.display = 'none';
    };

    ws.onmessage = function(event) {
        try {
            const data = JSON.parse(event.data);
            
            // 1. Atualiza o Relógio e Preço Principal
            document.getElementById('clock').innerText = data.timestamp;
            document.getElementById('preco-atual').innerText = data.preco;
            
            // 2. Atualiza os Indicadores e suas Barras Visuais
            const estocasticoEl = document.getElementById('valor-estocastico');
            const barEstocastico = document.getElementById('bar-estocastico');
            if (estocasticoEl) estocasticoEl.innerText = data.estocastico;
            if (barEstocastico) barEstocastico.style.width = data.estocastico + '%';

            const ifrEl = document.getElementById('valor-ifr');
            const barIfr = document.getElementById('bar-ifr');
            if (ifrEl) ifrEl.innerText = data.ifr;
            if (barIfr) barIfr.style.width = data.ifr + '%';

            const neblinaEl = document.getElementById('valor-neblina');
            const barNeblina = document.getElementById('bar-neblina');
            if (neblinaEl) neblinaEl.innerText = data.neblina;
            if (barNeblina) barNeblina.style.width = data.neblina + '%';

            // 3. Atualiza o Motor de Sinais (Centro inferior)
            const sinalEl = document.getElementById('sinal-motor');
            const motivoEl = document.getElementById('motivo-motor');
            
            if (sinalEl) {
                sinalEl.innerText = data.sinal;
                
                // Muda a cor do texto baseado no sinal
                if (data.sinal === "COMPRA") {
                    sinalEl.style.color = "#00ff00"; // Verde Neon
                } else if (data.sinal === "VENDA") {
                    sinalEl.style.color = "#ff0000"; // Vermelho
                } else {
                    sinalEl.style.color = "#ffd700"; // Dourado (Aguardar)
                }
            }
            
            // Atualiza o motivo (ex: "Bloqueado: Fora do Horário")
            if (motivoEl) motivoEl.innerText = data.motivo;

        } catch (error) {
            console.error("Erro ao processar os dados:", error);
        }
    };

    ws.onclose = function() {
        console.log("🔴 Desconectado. Tentando reconectar...");
        setTimeout(connectWebSocket, 3000); // Tenta reconectar sozinho
    };
}

// Inicia a conexão quando a página carregar
window.addEventListener('load', connectWebSocket);