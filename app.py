import os
import resend
import requests
import csv
from io import StringIO
from flask import Flask, render_template, request, flash, redirect, url_for, jsonify, make_response
from dotenv import load_dotenv
from datetime import datetime, timedelta

load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'chave_dev_padrao')
resend.api_key = os.getenv('RESEND_API_KEY')

# --- VARIÁVEIS GLOBAIS (MEMÓRIA RAM) ---
# Buffer de Cliques
BUFFER_CLIQUES = []
LIMITE_BUFFER_IMEDIATO = 10  # Se der 10 cliques, envia na hora, não espera o cron

# Cache do Portfólio (Para o site não travar carregando planilha)
PORTFOLIO_CACHE = []
ULTIMA_ATUALIZACAO_PORTFOLIO = None
CACHE_TIMEOUT_HORAS = 1  # Validade do cache em uso normal


# --- FUNÇÃO INTELIGENTE DE PORTFÓLIO ---
def get_portfolio_data(force_refresh=False):
    global PORTFOLIO_CACHE, ULTIMA_ATUALIZACAO_PORTFOLIO

    agora = datetime.now()

    # 1. Verifica se pode usar o Cache (Se não for forçado e se o cache for recente)
    if not force_refresh and PORTFOLIO_CACHE and ULTIMA_ATUALIZACAO_PORTFOLIO:
        tempo_passado = agora - ULTIMA_ATUALIZACAO_PORTFOLIO
        if tempo_passado < timedelta(hours=CACHE_TIMEOUT_HORAS):
            return PORTFOLIO_CACHE

    # 2. Se precisar buscar dados novos (Force Refresh ou Cache Vencido)
    url = os.getenv('PORTFOLIO_SHEET_URL')
    if not url:
        return []

    try:
        print("🔄 Buscando dados atualizados no Google Sheets...")
        response = requests.get(url, timeout=10)  # Timeout para não travar o server
        response.raise_for_status()

        csv_file = StringIO(response.content.decode('utf-8'))
        reader = csv.DictReader(csv_file)

        projects = []
        for row in reader:
            clean_row = {k.strip(): v.strip() for k, v in row.items()}
            projects.append(clean_row)

        # Atualiza a memória global
        PORTFOLIO_CACHE = projects
        ULTIMA_ATUALIZACAO_PORTFOLIO = agora
        print(f"✅ Portfólio atualizado! {len(projects)} projetos carregados.")

        return projects
    except Exception as e:
        print(f"❌ Erro ao buscar portfólio: {e}")
        # Em caso de erro, retorna o que tiver no cache antigo para o site não quebrar
        return PORTFOLIO_CACHE if PORTFOLIO_CACHE else []


# --- ROTAS DO SITE (FRONT-END) ---

@app.route('/')
def index():
    return render_template(
        'index.html',
        title="Merlô Digital | Engenharia de Software e Sites",
        description="Especialistas em desenvolvimento web de alta performance. Transformamos processos complexos em sistemas seguros e escaláveis com Python."
    )


@app.route('/servicos')
def servicos():
    return render_template(
        'servicos.html',
        title="Serviços de Desenvolvimento Web - Merlô Digital",
        description="Conheça nossas soluções em criação de sites, sistemas web, automação e dashboards administrativos personalizados."
    )


@app.route('/servicos/website')
def servicos_website():
    return render_template(
        'servicos_website.html',
        title="Criação de Sites Profissionais e Landing Pages | Merlô Digital",
        description="Sites rápidos, otimizados para SEO e responsivos. Do site institucional básico até catálogos dinâmicos integrados ao Google Sheets."
    )


@app.route('/servicos/sistemas')
def servicos_sistemas():
    return render_template(
        'servicos_sistemas.html',
        title="Desenvolvimento de Sistemas Web e ERPs | Merlô Digital",
        description="Sistemas sob medida em Python. Dashboards, controle de estoque, área de membros e automação de processos empresariais."
    )


@app.route('/portfolio')
def portfolio():
    # Usa a função inteligente com cache
    projects = get_portfolio_data()
    return render_template(
        'portfolio.html',
        title="Portfólio de Projetos - Merlô Digital",
        description="Veja nossos casos de sucesso. Sites institucionais e sistemas complexos desenvolvidos para gerar resultados reais.",
        projects=projects
    )


@app.route('/contato', methods=['GET', 'POST'])
def contato():
    if request.method == 'POST':
        nome = request.form.get('nome')
        email_cliente = request.form.get('email')
        empresa = request.form.get('empresa')
        mensagem_cliente = request.form.get('mensagem')
        email_destino = os.getenv('EMAIL_DESTINO')

        try:
            params = {
                "from": "Merlô Digital <contato@merlodigital.com>",
                "to": [email_destino],
                "subject": f"Novo Lead MERLÔ: {nome} - {empresa}",
                "html": f"""
                <h3>NOVA SOLICITAÇÃO DE CONTATO</h3>
                <p><strong>Nome:</strong> {nome}</p>
                <p><strong>Empresa:</strong> {empresa}</p>
                <p><strong>E-mail:</strong> {email_cliente}</p>
                <hr>
                <p><strong>Mensagem:</strong><br>{mensagem_cliente}</p>
                """
            }
            resend.Emails.send(params)
            flash('Mensagem enviada com sucesso! Em breve entraremos em contato.', 'success')
        except Exception as e:
            print(f"Erro ao enviar e-mail: {e}")
            flash('Erro ao enviar mensagem. Tente novamente ou nos chame no WhatsApp.', 'danger')

        return redirect(url_for('contato'))

    return render_template(
        'contato.html',
        title="Fale Conosco | Orçamento de Software",
        description="Entre em contato com a Merlô Digital. Atendimento via WhatsApp ou E-mail para tirar seu projeto do papel."
    )


# --- ROTAS DE API E CRON JOB (BACK-END) ---

@app.route('/api/track-click', methods=['POST'])
def track_click():
    """
    Recebe o clique do usuário e apenas guarda no Buffer.
    O envio é feito ou se encher muito (10 cliques) ou pelo Cron Job (10 min).
    """
    global BUFFER_CLIQUES

    data = request.get_json()
    hora_atual = datetime.now()

    novo_clique = {
        "botao": data.get('botao', 'Desconhecido'),
        "pagina": data.get('pagina_origem', '/'),
        "destino": data.get('url_destino', '#'),
        "hora_fmt": hora_atual.strftime("%d/%m/%Y às %H:%M:%S")
    }

    BUFFER_CLIQUES.append(novo_clique)

    # Se o buffer estourar o limite de segurança (ex: muito tráfego), envia agora mesmo
    # para não perder dados na memória RAM.
    if len(BUFFER_CLIQUES) >= LIMITE_BUFFER_IMEDIATO:
        enviar_buffer_por_email(motivo="Buffer Cheio (Envio Imediato)")
        return jsonify({'status': 'enviado', 'motivo': 'buffer_cheio'}), 200

    return jsonify({'status': 'acumulando', 'qtd': len(BUFFER_CLIQUES)}), 200


@app.route('/api/cron-job', methods=['GET'])
def cron_job():
    """
    ROTA MÁGICA:
    Essa rota deve ser chamada por um serviço externo (ex: cron-job.org) a cada 10 minutos.
    Ela serve para:
    1. Manter o Render ACORDADO (Keep-Alive).
    2. Enviar e-mails de cliques acumulados se houver.
    3. Se não houver cliques, atualizar o Cache do Portfólio (Refresh).
    """
    global BUFFER_CLIQUES

    print(f"⏰ Cron Job acionado em {datetime.now()}")

    # CENÁRIO 1: TEM CLIQUES? ENVIA E-MAIL.
    if len(BUFFER_CLIQUES) > 0:
        sucesso = enviar_buffer_por_email(motivo="Cron Job (10 min)")
        if sucesso:
            return jsonify({'status': 'ok', 'acao': 'email_enviado', 'qtd': len(BUFFER_CLIQUES)}), 200
        else:
            return jsonify({'status': 'erro', 'acao': 'falha_envio_email'}), 500

    # CENÁRIO 2: NÃO TEM CLIQUES? ATUALIZA O CACHE (Puxa e Enche).
    else:
        # Força a atualização do cache (force_refresh=True)
        projetos = get_portfolio_data(force_refresh=True)
        return jsonify({
            'status': 'ok',
            'acao': 'cache_atualizado',
            'msg': 'Sem cliques para enviar. Cache de portfólio renovado.',
            'projetos_carregados': len(projetos)
        }), 200


def enviar_buffer_por_email(motivo):
    """Função auxiliar que faz o envio real do e-mail"""
    global BUFFER_CLIQUES

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
                <small>Sistema de Monitoramento Merlô Digital.</small>
            </div>
            """
        })
        print(f"📧 E-mail de relatório enviado! Motivo: {motivo}")
        BUFFER_CLIQUES.clear()  # Limpa o buffer após sucesso
        return True
    except Exception as e:
        print(f"❌ Erro no envio do relatório: {e}")
        return False


# --- ROTAS DE SEO (SITEMAP E ROBOTS) ---

@app.route('/sitemap.xml')
def sitemap():
    host = "https://merlodigital.com"
    pages = ['/', '/servicos', '/servicos/website', '/servicos/sistemas', '/portfolio', '/contato']

    sitemap_xml = """<?xml version="1.0" encoding="UTF-8"?>
    <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">"""

    for page in pages:
        sitemap_xml += f"""
        <url>
            <loc>{host}{page}</loc>
            <changefreq>monthly</changefreq>
            <priority>{'1.0' if page == '/' else '0.8'}</priority>
        </url>"""

    sitemap_xml += "</urlset>"

    response = make_response(sitemap_xml)
    response.headers["Content-Type"] = "application/xml"
    return response


@app.route('/robots.txt')
def robots():
    lines = ["User-agent: *", "Disallow: ", "Sitemap: https://merlodigital.com/sitemap.xml"]
    response = make_response("\n".join(lines))
    response.headers["Content-Type"] = "text/plain"
    return response


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)