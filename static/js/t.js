document.addEventListener("DOMContentLoaded", function() {
    // Seleciona TUDO que é clicável e importante:
    // .btn (botões padrão), a (links), button (botões de form), .nav-link (menu)
    const elementosClicaveis = document.querySelectorAll('.btn, .btn-merlo, .btn-pricing, .nav-link, .navbar-brand, .whatsapp-float, a, button');

    elementosClicaveis.forEach(function(elemento) {
        elemento.addEventListener('click', function(e) {
            // 1. Identificar o nome do botão
            let nomeBotao = elemento.innerText.trim();

            // Se não tiver texto (ex: só icone), tenta pegar title ou aria-label
            if (!nomeBotao) nomeBotao = elemento.getAttribute('title');
            if (!nomeBotao) nomeBotao = elemento.getAttribute('aria-label');

            // Se for o Whats flutuante e não pegou nome
            if (elemento.classList.contains('whatsapp-float')) nomeBotao = "WhatsApp Flutuante";

            // Último recurso: mostra o link
            if (!nomeBotao && elemento.href) nomeBotao = "Link: " + elemento.getAttribute('href');
            if (!nomeBotao) nomeBotao = "Botão Sem Nome (Icone/Imagem)";

            // 2. Enviar para o Python (Backend) de forma assíncrona
            // O 'keepalive: true' garante que o envio ocorra mesmo se a página mudar
            fetch('/api/track-click', {
                method: 'POST',
                keepalive: true,
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    botao: nomeBotao,
                    pagina_origem: window.location.pathname,
                    url_destino: elemento.getAttribute('href') || 'Ação local'
                })
            }).catch(err => console.error("Erro silencioso no tracker:", err));
        });
    });
});