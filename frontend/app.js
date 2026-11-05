// Relógio em tempo real
setInterval(() => {
    const now = new Date();
    document.getElementById('clock').innerText = now.toLocaleTimeString('pt-BR');
}, 1000);

// ========================================================
// CONEXÃO WEBSOCKET COM O BACK-END PYTHON
// ========================================================
const ws = new WebSocket('ws://127.0.0.1:8000/ws');

ws.onopen = () => {
    console.log('🟢 Conectado ao servidor Centurion Backend (Python)');
    // Poderíamos mudar a bolinha de status para verde real aqui
};

ws.onmessage = (event) => {
    // Recebe os dados do Python
    const data = JSON.parse(event.data);
    
    // Atualiza o Preço
    const priceElement = document.querySelector('.price');
    if(priceElement) {
        const oldPrice = parseFloat(priceElement.innerText.replace('.', ''));
        priceElement.innerText = data.preco.toLocaleString('pt-BR');
        
        // Pisca em verde se subiu, vermelho se caiu
        if (data.preco > oldPrice) {
            priceElement.style.color = '#00ff66';
        } else if (data.preco < oldPrice) {
            priceElement.style.color = '#ff3333';
        }
    }

    // Atualiza o Sinal de Execução (Painel Central)
    const signalDiv = document.querySelector('.signal');
    const signalH2 = signalDiv.querySelector('h2');
    
    if (data.sinal === 'COMPRA') {
        signalDiv.className = 'signal buy';
        signalH2.innerText = 'COMPRA';
    } else if (data.sinal === 'VENDA') {
        signalDiv.className = 'signal sell';
        signalDiv.style.background = 'rgba(255, 51, 51, 0.1)';
        signalDiv.style.borderLeft = '4px solid #ff3333';
        signalH2.innerText = 'VENDA';
        signalH2.style.color = '#ff3333';
    } else {
        signalDiv.className = 'signal wait';
        signalDiv.style.background = 'rgba(255, 255, 255, 0.1)';
        signalDiv.style.borderLeft = '4px solid #fff';
        signalH2.innerText = 'AGUARDAR';
        signalH2.style.color = '#fff';
    }

    // Atualiza a Neblina (Shannon)
    const neblinaBar = document.querySelectorAll('.bar .fill')[2]; // Terceira barra (Shannon)
    if(neblinaBar) {
        neblinaBar.style.width = `${data.neblina}%`;
        // Se a neblina for alta (muita entropia), fica vermelho. Se baixa, verde.
        if (data.neblina > 60) {
            neblinaBar.className = 'fill danger';
        } else {
            neblinaBar.className = 'fill';
        }
    }
};

ws.onerror = (error) => {
    console.error('🔴 Erro no WebSocket:', error);
};