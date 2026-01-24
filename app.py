import os
import csv
import requests
import resend
import threading
import uuid
from io import StringIO
from datetime import datetime, timedelta
from dotenv import load_dotenv
from flask import Flask, render_template, request, flash, redirect, url_for, jsonify, make_response
from user_agents import parse

# --- ALTERAÇÃO: Importando funções do DB ---
from db_utils import get_table_id_by_name, get_sheet_data, insert_tracking_event

load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'chave_dev_padrao')
resend.api_key = os.getenv('RESEND_API_KEY')

BUFFER_CLIQUES = []
LIMITE_BUFFER_IMEDIATO = 10
PORTFOLIO_CACHE = []
ULTIMA_ATUALIZACAO_PORTFOLIO = None
CACHE_TIMEOUT_HORAS = 1
MEUS_IPS_IGNORADOS = ['177.5.139.35']
HOST_URL = "https://merlodigital.com"

# Nome do Site para o DB
SITE_SOURCE_NAME = "Merlô Digital - Site"


def get_location_data_rich(ip_address):
    """
    Busca dados enriquecidos de GeoIP.
    """
    try:
        url = f'http://ip-api.com/json/{ip_address}?fields=status,message,countryCode,regionName,city,isp,org,zip'
        response = requests.get(url, timeout=3)
        data = response.json()

        if data['status'] == 'success':
            local_base = f"{data['city']}/{data['regionName']} ({data['countryCode']})"
            detalhe_rede = data['org'] if data['org'] else data['isp']
            if data['isp'] and data['isp'] != data['org']:
                detalhe_rede = f"{data['isp']} ({data['org']})"

            return {
                "local": local_base,
                "rede": detalhe_rede,
                "zip": data['zip']
            }
        return {"local": "Local Desconhecido", "rede": "N/A", "zip": ""}
    except Exception as e:
        print(f"Erro no GeoIP: {e}")
        return {"local": "N/A", "rede": "N/A", "zip": ""}


def get_portfolio_data(force_refresh=False):
    """
    Busca dados direto do Banco Neon (PostgreSQL).
    """
    global PORTFOLIO_CACHE, ULTIMA_ATUALIZACAO_PORTFOLIO
    agora = datetime.now()

    if not force_refresh and PORTFOLIO_CACHE and ULTIMA_ATUALIZACAO_PORTFOLIO:
        tempo_passado = agora - ULTIMA_ATUALIZACAO_PORTFOLIO
        if tempo_passado < timedelta(hours=CACHE_TIMEOUT_HORAS):
            return PORTFOLIO_CACHE

    try:
        print("🔌 Conectando ao Neon DB para buscar Portfolio...")
        portfolio_tab_id = get_table_id_by_name('Portfolio')
        if not portfolio_tab_id:
            portfolio_tab_id = get_table_id_by_name('Portfólio')

        if not portfolio_tab_id:
            print("⚠️ Aviso: Tabela Portfolio não encontrada no Banco de Dados.")
            return PORTFOLIO_CACHE or []

        projects = get_sheet_data(portfolio_tab_id)
        final_projects = []
        for row in projects:
            titulo = row.get('Título', '')
            if not titulo: continue

            logo_url = row.get('Logo', '').strip()
            if 'drive.google.com' in logo_url and 'id=' in logo_url:
                try:
                    file_id = logo_url.split('id=')[1].split('&')[0]
                    logo_url = f"https://lh3.googleusercontent.com/d/{file_id}"
                except:
                    pass

            item = {
                'Título': titulo.strip(),
                'Descrição': row.get('Descrição', '').strip(),
                'Link': row.get('Link do site', '').strip(),
                'Logo': logo_url,
                'Tipo': row.get('Tipo', '').strip()
            }
            final_projects.append(item)

        PORTFOLIO_CACHE = final_projects
        ULTIMA_ATUALIZACAO_PORTFOLIO = agora
        print(f"🚀 Portfólio atualizado via DB! {len(final_projects)} projetos.")

        return final_projects

    except Exception as e:
        print(f"❌ Erro crítico ao buscar portfólio: {e}")
        return PORTFOLIO_CACHE if PORTFOLIO_CACHE else []


def processar_envio_background(lista_cliques, motivo):
    """
    Roda em Thread separada para envio de e-mails.
    """
    email_destino = os.getenv('EMAIL_DESTINO')
    if not lista_cliques or not email_destino:
        return

    itens_html = ""
    for item in lista_cliques:
        # A lista já vem com geolocalização processada do 'save_click_async'
        loc = item.get('localizacao', 'Processando...')
        rede = item.get('provedor', 'Processando...')

        cor_titulo = "#16305D"
        icone_status = "🖱️"
        bg_card = "#f8f9fa"

        if "WhatsApp" in item['botao'] or "Contato" in item['botao']:
            cor_titulo = "#25D366"
            icone_status = "💬"
            bg_card = "#e8f5e9"

        tag_visitante = "👤 Novo" if item.get('is_new_user') else "🔄 Retorno"

        itens_html += f"""
        <li style="margin-bottom: 15px; border-left: 4px solid {cor_titulo}; list-style: none; background-color: {bg_card}; padding: 12px; border-radius: 6px; font-family: sans-serif;">
            <div style="font-size: 14px; font-weight: bold; color: {cor_titulo}; display: flex; justify-content: space-between; align-items: center;">
                <span>{icone_status} {item['botao']}</span>
                <span style="font-size: 10px; background: #fff; border: 1px solid #ddd; padding: 2px 8px; border-radius: 12px; color: #555; text-transform: uppercase;">{tag_visitante}</span>
            </div>
            <div style="font-size: 12px; color: #555; line-height: 1.6; margin-top: 8px;">
                🕒 <strong>Hora:</strong> {item['hora_fmt']} <br>
                🌍 <strong>Local:</strong> {loc} <br>
                🏢 <strong>Rede:</strong> {rede} <br>
                🔧 <strong>Device:</strong> {item['device_str']} <br>
                🔗 <a href="{HOST_URL}{item['pagina_origem']}" style="color: #666;">{item['pagina_origem']}</a> → {item['url_destino']}
            </div>
        </li>
        """

    try:
        resend.Emails.send({
            "from": "Merlô Tracker <merlotracker@merlodigital.com>",
            "to": [email_destino],
            "subject": f"🎯 {len(lista_cliques)} Interações (Merlô Track v3)",
            "html": f"""
            <div style="font-family: sans-serif; color: #333; max-width: 600px;">
                <div style="padding: 15px; border-bottom: 2px solid #16305D;">
                    <h3 style="color: #16305D; margin: 0;">Relatório de Inteligência</h3>
                    <p style="font-size: 12px; color: #777; margin: 5px 0 0 0;">
                        Motivo: {motivo} • Processamento Assíncrono
                    </p>
                </div>
                <ul style="padding: 0; margin-top: 20px;">
                    {itens_html}
                </ul>
            </div>
            """
        })
        print(f"✅ E-mail de relatório enviado (Background).")
    except Exception as e:
        print(f"❌ Erro ao enviar e-mail: {e}")


def save_click_async(clique_data):
    """
    Thread de processamento:
    1. Busca GeoIP (lento)
    2. Salva no DB com hora BR
    3. Buffer E-mail
    """
    global BUFFER_CLIQUES

    geo_data = get_location_data_rich(clique_data['ip_address'])

    clique_data['localizacao'] = geo_data['local']
    clique_data['provedor'] = geo_data['rede']

    # Adiciona a fonte do site e salva
    clique_data['site_source'] = SITE_SOURCE_NAME
    insert_tracking_event(clique_data)

    BUFFER_CLIQUES.append(clique_data)

    if len(BUFFER_CLIQUES) >= LIMITE_BUFFER_IMEDIATO:
        lote_atual = list(BUFFER_CLIQUES)
        BUFFER_CLIQUES.clear()
        processar_envio_background(lote_atual, "Buffer Cheio")


# --- ROTAS VIEW (SEO E TEXTOS ORIGINAIS RESTAURADOS) ---

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
        spam_trap = request.form.get('bairro_confirma')
        if spam_trap:
            flash('Solicitação enviada com sucesso!', 'success')
            return redirect(url_for('contato'))

        nome = request.form.get('nome')
        email_cliente = request.form.get('email')
        empresa = request.form.get('empresa')
        mensagem_cliente = request.form.get('mensagem')
        telefone = request.form.get('telefone')

        if not email_cliente or '@' not in email_cliente or '.' not in email_cliente:
            flash('O e-mail informado é inválido. Por favor, verifique.', 'danger')
            return redirect(url_for('contato'))

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


# --- API TRACKING ---
@app.route('/api/track-click', methods=['POST'])
def track_click():
    if request.headers.getlist("X-Forwarded-For"):
        user_ip = request.headers.getlist("X-Forwarded-For")[0]
    else:
        user_ip = request.remote_addr

    ua_string = request.headers.get('User-Agent')
    user_agent = parse(ua_string)

    if user_agent.is_bot:
        return jsonify({'status': 'ignorado'}), 200
    if user_ip in MEUS_IPS_IGNORADOS:
        return jsonify({'status': 'ignorado'}), 200

    usuario_id = request.cookies.get('merlo_uid')
    is_new_user = False

    if not usuario_id:
        usuario_id = str(uuid.uuid4())
        is_new_user = True

    dispositivo = f"{user_agent.os.family} {user_agent.os.version_string}"
    navegador = f"{user_agent.browser.family}"
    icone = "📱" if user_agent.is_mobile else "💻"

    data_req = request.get_json()

    # --- CORREÇÃO DE DATA: Captura a hora BR (-3) para o Banco ---
    hora_atual = datetime.utcnow() - timedelta(hours=3)

    novo_clique = {
        "uid": usuario_id,
        "is_new_user": is_new_user,
        "botao": data_req.get('botao', 'Clique Genérico'),
        "pagina_origem": data_req.get('pagina_origem', '/'),
        "url_destino": data_req.get('url_destino', '#'),

        # Strings para o E-mail e Log
        "hora_fmt": hora_atual.strftime("%H:%M:%S"),
        "device_str": f"{icone} {navegador} no {dispositivo}",

        # Dados para o Banco (Incluindo created_at)
        "ip_address": user_ip,
        "dispositivo": f"{icone} {navegador}",
        "created_at": hora_atual
    }

    t = threading.Thread(target=save_click_async, args=(novo_clique,))
    t.start()

    resp = make_response(jsonify({'status': 'processando_background'}))
    if is_new_user:
        resp.set_cookie('merlo_uid', usuario_id, max_age=31536000, httponly=True, samesite='Lax')

    return resp


@app.route('/api/cron-job', methods=['GET'])
def cron_job():
    global BUFFER_CLIQUES
    hora_br = datetime.utcnow() - timedelta(hours=3)
    print(f"⏰ Cron Job acionado em {hora_br.strftime('%H:%M:%S')}")

    if len(BUFFER_CLIQUES) > 0:
        lote_atual = list(BUFFER_CLIQUES)
        BUFFER_CLIQUES.clear()
        t = threading.Thread(target=processar_envio_background, args=(lote_atual, "Cron Job (Rotina)"))
        t.start()
        return jsonify({'status': 'ok', 'acao': 'thread_iniciada'}), 200
    else:
        # Atualiza cache do portfolio via DB
        projetos = get_portfolio_data(force_refresh=True)
        return jsonify({'status': 'ok', 'msg': 'Sem cliques. Cache renovado.'}), 200


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

# --- ROTA DE ERRO 404 ---
@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html', title="404 | Página Não Encontrada"), 404


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)