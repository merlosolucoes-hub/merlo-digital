import os
import resend
import requests  # <--- Importar requests
import csv  # <--- Importar csv
from io import StringIO  # <--- Importar StringIO
from flask import Flask, render_template, request, flash, redirect, url_for
from dotenv import load_dotenv
from datetime import datetime, timedelta

load_dotenv()

BUFFER_CLIQUES = []
ULTIMO_ENVIO = datetime.now()  # Marca a hora que o servidor iniciou
LIMITE_BUFFER = 10             # Quantidade para envio imediato
LIMITE_TEMPO_MINUTOS = 10

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'chave_dev_padrao')

resend.api_key = os.getenv('RESEND_API_KEY')


# --- FUNÇÃO AUXILIAR PARA PEGAR DADOS DO SHEET ---
def get_portfolio_data():
    url = os.getenv('PORTFOLIO_SHEET_URL')
    if not url:
        return []

    try:
        response = requests.get(url)
        response.raise_for_status()  # Garante que deu 200 OK

        # Transforma o texto CSV em um formato de arquivo legível
        csv_file = StringIO(response.content.decode('utf-8'))

        # Lê o CSV mapeando para dicionários (assume que a 1ª linha é o cabeçalho)
        # Ordem esperada das colunas na planilha: Título, Link, Descrição, Tipo, Logo
        reader = csv.DictReader(csv_file)

        projects = []
        for row in reader:
            # Limpeza básica dos dados (remove espaços extras das chaves se houver)
            clean_row = {k.strip(): v.strip() for k, v in row.items()}
            projects.append(clean_row)

        return projects
    except Exception as e:
        print(f"Erro ao buscar portfólio: {e}")
        return []


@app.route('/')
def index():
    return render_template('index.html', title="Início")


@app.route('/servicos')
def servicos():
    return render_template('servicos.html', title="Serviços")

@app.route('/servicos/website')
def servicos_website():
    return render_template('servicos_website.html', title="Criação de Sites e Sistemas")

@app.route('/servicos/sistemas')
def servicos_sistemas():
    return render_template('servicos_sistemas.html', title="Sistemas Web Personalizados")

@app.route('/portfolio')
def portfolio():
    projects = get_portfolio_data()
    return render_template('portfolio.html', title="Portfólio", projects=projects)

@app.route('/contato', methods=['GET', 'POST'])
def contato():
    if request.method == 'POST':
        nome = request.form.get('nome')
        email_cliente = request.form.get('email')
        empresa = request.form.get('empresa')
        mensagem_cliente = request.form.get('mensagem')

        email_destino = os.getenv('EMAIL_DESTINO')

        # --- LÓGICA DE ENVIO VIA API (RESEND) ---
        # Porta 443 (HTTPS) - Nunca é bloqueada pelo Render
        try:
            params = {
                "from": "Merlô Digital <contato@merlodigital.com>",
                "to": [email_destino],
                "subject": f"Novo Lead MERLÔ: {nome} - {empresa}",
                "html": f"""
                <h3>NOVA SOLICITAÇÃO DE CONTATO</h3>
                <p><strong>Nome:</strong> {nome}</p>
                <p><strong>Empresa:</strong> {empresa}</p>
                <p><strong>E-mail do Cliente:</strong> {email_cliente}</p>
                <hr>
                <p><strong>Mensagem:</strong><br>{mensagem_cliente}</p>
                """
            }

            email = resend.Emails.send(params)
            print(f"E-mail enviado via Resend! ID: {email}")
            flash('Mensagem enviada com sucesso! Em breve entraremos em contato.', 'success')

        except Exception as e:
            print(f"Erro ao enviar e-mail: {e}")
            flash('Erro ao enviar mensagem. Tente novamente ou nos chame no WhatsApp.', 'danger')

        return redirect(url_for('contato'))

    return render_template('contato.html', title="Contato")


# No topo do arquivo, certifique-se de importar jsonify
from flask import Flask, render_template, request, flash, redirect, url_for, jsonify


# ... (seu código existente de configuração e rotas) ...

@app.route('/api/track-click', methods=['POST'])
def track_click():
    global BUFFER_CLIQUES, ULTIMO_ENVIO  # Acessa as variáveis globais

    # 1. Recebe o dado do clique
    data = request.get_json()
    hora_atual = datetime.now()

    novo_clique = {
        "botao": data.get('botao', 'Desconhecido'),
        "pagina": data.get('pagina_origem', '/'),
        "destino": data.get('url_destino', '#'),
        "hora_fmt": hora_atual.strftime("%d/%m/%Y às %H:%M:%S")
    }

    BUFFER_CLIQUES.append(novo_clique)

    # 2. Verifica as condições de envio
    # Condição A: Buffer cheio (10 cliques)
    buffer_cheio = len(BUFFER_CLIQUES) >= LIMITE_BUFFER

    # Condição B: Passou do tempo limite (10 min) E tem algo para enviar
    tempo_passado = hora_atual - ULTIMO_ENVIO
    tempo_esgotado = tempo_passado > timedelta(minutes=LIMITE_TEMPO_MINUTOS)
    tem_algo = len(BUFFER_CLIQUES) > 0

    deve_enviar = buffer_cheio or (tempo_esgotado and tem_algo)

    status_msg = f"Buffer: {len(BUFFER_CLIQUES)}/{LIMITE_BUFFER} | Tempo: {int(tempo_passado.total_seconds() / 60)}min"

    if deve_enviar:
        email_destino = os.getenv('EMAIL_DESTINO')

        # Monta lista HTML
        itens_html = ""
        for item in BUFFER_CLIQUES:
            itens_html += f"""
            <li style="margin-bottom: 8px; border-bottom: 1px solid #eee; padding-bottom: 4px;">
                <small style="color:#666">{item['hora_fmt']}</small><br>
                <strong>{item['botao']}</strong> <br>
                <span style="font-size:0.85em">De: {item['pagina']} &rarr; Para: {item['destino']}</span>
            </li>
            """

        motivo = "Lote Completo (10 cliques)" if buffer_cheio else "Time-out (10 min sem envio)"

        try:
            resend.Emails.send({
                "from": "Merlô Tracker <merlotracker@merlodigital.com>",
                "to": [email_destino],
                "subject": f"📊 Relatório de Tráfego: {len(BUFFER_CLIQUES)} novos cliques",
                "html": f"""
                <div style="font-family: sans-serif; color: #333;">
                    <h3 style="color: #16305D;">Atualização de Tráfego</h3>
                    <p><strong>Motivo do envio:</strong> {motivo}</p>
                    <ul style="list-style: none; padding: 0;">
                        {itens_html}
                    </ul>
                    <hr>
                    <small>Relógio reiniciado. Aguardando novos eventos.</small>
                </div>
                """
            })
            print(f"E-mail enviado! Motivo: {motivo}")

            # 3. Limpeza e Reset
            BUFFER_CLIQUES.clear()
            ULTIMO_ENVIO = datetime.now()  # Reseta o relógio
            return jsonify({'status': 'enviado', 'motivo': motivo}), 200

        except Exception as e:
            print(f"Erro no envio: {e}")
            return jsonify({'status': 'erro_envio'}), 500

    return jsonify({'status': 'acumulando', 'info': status_msg}), 200

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)