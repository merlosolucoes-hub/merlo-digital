import os
import csv
import requests
import resend
from io import StringIO
from datetime import datetime, timedelta
from dotenv import load_dotenv
from flask import Flask, render_template, request, flash, redirect, url_for, jsonify, make_response
from user_agents import parse

load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'chave_dev_padrao')
resend.api_key = os.getenv('RESEND_API_KEY')

BUFFER_CLIQUES = []
LIMITE_BUFFER_IMEDIATO = 10
PORTFOLIO_CACHE = []
ULTIMA_ATUALIZACAO_PORTFOLIO = None
CACHE_TIMEOUT_HORAS = 1
MEUS_IPS_IGNORADOS = ['192.168.0.101', '192']
HOST_URL = "https://merlodigital.com"

def get_location_from_ip(ip_address):
    try:
        response = requests.get(f'http://ip-api.com/json/{ip_address}', timeout=1)
        data = response.json()
        if data['status'] == 'success':
            return f"{data['city']}/{data['regionName']} ({data['countryCode']})"
        return "Local Desconhecido"
    except:
        return "N/A"

def get_portfolio_data(force_refresh=False):
    global PORTFOLIO_CACHE, ULTIMA_ATUALIZACAO_PORTFOLIO
    agora = datetime.now()

    if not force_refresh and PORTFOLIO_CACHE and ULTIMA_ATUALIZACAO_PORTFOLIO:
        tempo_passado = agora - ULTIMA_ATUALIZACAO_PORTFOLIO
        if tempo_passado < timedelta(hours=CACHE_TIMEOUT_HORAS):
            return PORTFOLIO_CACHE

    url = os.getenv('PORTFOLIO_SHEET_URL')
    if not url:
        return []

    try:
        print("Buscando dados atualizados no Google Sheets...")
        response = requests.get(url, timeout=10)
        response.raise_for_status()

        csv_file = StringIO(response.content.decode('utf-8'))
        reader = csv.DictReader(csv_file)

        projects = []
        for row in reader:
            clean_row = {k.strip(): v.strip() for k, v in row.items()}
            projects.append(clean_row)

        PORTFOLIO_CACHE = projects
        ULTIMA_ATUALIZACAO_PORTFOLIO = agora
        print(f"Portfólio atualizado! {len(projects)} projetos carregados.")

        return projects
    except Exception as e:
        print(f"Erro ao buscar portfólio: {e}")
        return PORTFOLIO_CACHE if PORTFOLIO_CACHE else []

def enviar_buffer_por_email(motivo):
    global BUFFER_CLIQUES
    email_destino = os.getenv('EMAIL_DESTINO')

    if not BUFFER_CLIQUES:
        return False

    itens_html = ""
    for item in BUFFER_CLIQUES:
        local = get_location_from_ip(item['ip'])
        cor_titulo = "#16305D"
        if "WhatsApp" in item['botao'] or "Contato" in item['botao']:
            cor_titulo = "#25D366"

        itens_html += f"""
        <li style="margin-bottom: 15px; border-left: 4px solid {cor_titulo}; padding-left: 10px; list-style: none;">
            <div style="font-size: 14px; font-weight: bold; color: {cor_titulo};">
                {item['botao']}
            </div>
            <div style="font-size: 12px; color: #555; line-height: 1.5;">
                🕒 {item['hora_fmt']} <br>
                🌍 <strong>{local}</strong> <span style="color:#999">IP: {item['ip']}</span> <br>
                🔧 {item['device_str']} <br>
                🔗 {item['pagina']} &rarr; {item['destino']}
            </div>
        </li>
        <hr style="border: 0; border-top: 1px dashed #eee; margin: 10px 0;">
        """

    try:
        resend.Emails.send({
            "from": "Merlô Tracker <merlotracker@merlodigital.com>",
            "to": [email_destino],
            "subject": f"🎯 {len(BUFFER_CLIQUES)} Novos Leads/Cliques no Site",
            "html": f"""
            <div style="font-family: sans-serif; color: #333; max-width: 600px;">
                <h3 style="color: #16305D; border-bottom: 2px solid #16305D; padding-bottom: 10px;">
                    Relatório de Tráfego
                </h3>
                <p style="background-color: #f4f4f4; padding: 10px; border-radius: 5px; font-size: 12px;">
                    <strong>Status:</strong> {motivo}<br>
                    <strong>Filtro:</strong> Robôs e IPs internos ignorados.
                </p>
                <ul style="padding: 0;">
                    {itens_html}
                </ul>
                <div style="text-align: center; margin-top: 20px; font-size: 11px; color: #aaa;">
                    Merlô Digital Intelligence System v2.0
                </div>
            </div>
            """
        })
        print(f"Relatório enviado com sucesso!")
        BUFFER_CLIQUES.clear()
        return True
    except Exception as e:
        print(f"Erro no envio: {e}")
        return False

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
        # --- 1. PROTEÇÃO HONEYPOT (ARMADILHA) ---
        # Se o robô preencher este campo escondido, bloqueamos silenciosamente
        spam_trap = request.form.get('bairro_confirma')
        if spam_trap:
            print(f"BOT BLOQUEADO! Tentou preencher o honeypot.")
            # Fingimos que deu certo para o robô ir embora feliz e não tentar de novo
            flash('Solicitação enviada com sucesso!', 'success')
            return redirect(url_for('contato'))

        # --- 2. CAPTURA DE DADOS ---
        nome = request.form.get('nome')
        email_cliente = request.form.get('email')
        empresa = request.form.get('empresa')
        mensagem_cliente = request.form.get('mensagem')
        # Telefone não é obrigatório no form, mas se vier, pegamos
        telefone = request.form.get('telefone')

        # --- 3. VALIDAÇÃO DE SEGURANÇA (O que você pediu) ---
        if not email_cliente or '@' not in email_cliente or '.' not in email_cliente:
            print(f"SPAM RECUSADO: E-mail inválido ({email_cliente})")
            flash('O e-mail informado é inválido. Por favor, verifique.', 'danger')
            return redirect(url_for('contato'))

        # Se passou das barreiras acima, tenta enviar
        email_destino = os.getenv('EMAIL_DESTINO')

        try:
            params = {
                "from": "Merlô Digital <contato@merlodigital.com>",
                "to": [email_destino],
                "subject": f"🚀 Lead Site: {nome} - {empresa}",
                "html": f"""
                <div style="font-family: Arial, color: #333;">
                    <h2 style="color: #16305D;">Nova Oportunidade Comercial</h2>
                    <hr>
                    <p><strong>👤 Nome:</strong> {nome}</p>
                    <p><strong>🏢 Empresa:</strong> {empresa}</p>
                    <p><strong>📧 E-mail:</strong> {email_cliente}</p>
                    <p><strong>📱 Telefone:</strong> {telefone}</p>
                    <hr>
                    <p><strong>💬 Mensagem:</strong><br>{mensagem_cliente}</p>
                    <br>
                    <small style="color: #888;">Enviado via Site Merlô Digital (Validado)</small>
                </div>
                """
            }
            resend.Emails.send(params)
            flash('Solicitação enviada com sucesso! Em breve entraremos em contato.', 'success')
        except Exception as e:
            print(f"Erro ao enviar e-mail: {e}")
            flash('Erro ao enviar mensagem. Tente novamente ou nos chame no WhatsApp.', 'danger')

        return redirect(url_for('contato'))

    return render_template(
        'contato.html',
        title="Fale Conosco | Orçamento de Software",
        description="Entre em contato com a Merlô Digital. Atendimento via WhatsApp ou E-mail para tirar seu projeto do papel."
    )

@app.route('/api/track-click', methods=['POST'])
def track_click():
    global BUFFER_CLIQUES

    if request.headers.getlist("X-Forwarded-For"):
        user_ip = request.headers.getlist("X-Forwarded-For")[0]
    else:
        user_ip = request.remote_addr

    ua_string = request.headers.get('User-Agent')
    user_agent = parse(ua_string)

    if user_agent.is_bot:
        return jsonify({'status': 'ignorado', 'motivo': 'eh_robo'}), 200

    if user_ip in MEUS_IPS_IGNORADOS:
        return jsonify({'status': 'ignorado', 'motivo': 'eh_o_dono'}), 200

    dispositivo = f"{user_agent.os.family} {user_agent.os.version_string}"
    navegador = f"{user_agent.browser.family}"

    icone = "💻"
    if user_agent.is_mobile:
        icone = "📱"
    elif user_agent.is_tablet:
        icone = "📟"

    origem = request.headers.get('Referer')
    if not origem or HOST_URL in origem:
        origem_fmt = "Acesso Direto / Navegação Interna"
    else:
        origem_fmt = f"Veio de: {origem}"

    data = request.get_json()
    hora_atual = datetime.now()

    novo_clique = {
        "botao": data.get('botao', 'Clique Genérico'),
        "pagina": data.get('pagina_origem', '/'),
        "destino": data.get('url_destino', '#'),
        "hora_fmt": hora_atual.strftime("%H:%M:%S (%d/%m)"),
        "ip": user_ip,
        "device_str": f"{icone} {navegador} no {dispositivo}",
        "origem": origem_fmt
    }

    BUFFER_CLIQUES.append(novo_clique)

    if len(BUFFER_CLIQUES) >= LIMITE_BUFFER_IMEDIATO:
        enviar_buffer_por_email(motivo="Buffer Cheio (Alta Demanda)")
        return jsonify({'status': 'enviado', 'motivo': 'buffer_cheio'}), 200

    return jsonify({'status': 'acumulando', 'qtd': len(BUFFER_CLIQUES)}), 200

@app.route('/api/cron-job', methods=['GET'])
def cron_job():
    global BUFFER_CLIQUES
    print(f"Cron Job acionado em {datetime.now()}")

    if len(BUFFER_CLIQUES) > 0:
        sucesso = enviar_buffer_por_email(motivo="Cron Job (10 min)")
        if sucesso:
            return jsonify({'status': 'ok', 'acao': 'email_enviado', 'qtd': len(BUFFER_CLIQUES)}), 200
        else:
            return jsonify({'status': 'erro', 'acao': 'falha_envio_email'}), 500
    else:
        projetos = get_portfolio_data(force_refresh=True)
        return jsonify({
            'status': 'ok',
            'acao': 'cache_atualizado',
            'msg': 'Sem cliques para enviar. Cache de portfólio renovado.',
            'projetos_carregados': len(projetos)
        }), 200

@app.route('/sitemap.xml')
def sitemap():
    pages = ['/', '/servicos', '/servicos/website', '/servicos/sistemas', '/portfolio', '/contato']

    sitemap_xml = """<?xml version="1.0" encoding="UTF-8"?>
    <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">"""

    for page in pages:
        sitemap_xml += f"""
        <url>
            <loc>{HOST_URL}{page}</loc>
            <changefreq>monthly</changefreq>
            <priority>{'1.0' if page == '/' else '0.8'}</priority>
        </url>"""

    sitemap_xml += "</urlset>"

    response = make_response(sitemap_xml)
    response.headers["Content-Type"] = "application/xml"
    return response

@app.route('/robots.txt')
def robots():
    lines = ["User-agent: *", "Disallow: ", f"Sitemap: {HOST_URL}/sitemap.xml"]
    response = make_response("\n".join(lines))
    response.headers["Content-Type"] = "text/plain"
    return response

@app.route('/termos&privacidade')
def termos():
    return render_template(
        'termos&privacidade.html',
        title="Termos de Uso e Privacidade | Merlô Digital",
        description="Transparência total. Nossas políticas de privacidade, LGPD e termos de serviço."
    )

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)