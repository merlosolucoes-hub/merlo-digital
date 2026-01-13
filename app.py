import os
import csv
import requests
import resend
import threading  # NOVO: Para não travar o site
import uuid  # NOVO: Para gerar ID do visitante
from io import StringIO
from datetime import datetime, timedelta
from dotenv import load_dotenv
from flask import Flask, render_template, request, flash, redirect, url_for, jsonify, make_response
from user_agents import parse

# --- ALTERAÇÃO AQUI: Importando funções do My O System ---
from google_utils import get_connections_sheet, get_sheet_data

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


def get_location_data_rich(ip_address):
    """
    Busca dados enriquecidos. Não traz rua exata (impossível via IP),
    mas traz o Provedor (ISP) e a Empresa (Org), que valem ouro no B2B.
    """
    try:
        # Adicionamos fields para pedir ISP e Org
        url = f'http://ip-api.com/json/{ip_address}?fields=status,message,countryCode,regionName,city,isp,org,zip'
        response = requests.get(url, timeout=3)  # Timeout maior pois roda em thread
        data = response.json()

        if data['status'] == 'success':
            # Formata: "Blumenau/SC (BR)"
            local_base = f"{data['city']}/{data['regionName']} ({data['countryCode']})"

            # Formata: "Unifique Telecom" ou "Banco do Brasil S.A."
            # Se ISP e Org forem iguais, mostra só um.
            detalhe_rede = data['org'] if data['org'] else data['isp']
            if data['isp'] and data['isp'] != data['org']:
                detalhe_rede = f"{data['isp']} ({data['org']})"

            return {
                "local": local_base,
                "rede": detalhe_rede,
                "zip": data['zip']  # CEP Genérico da região
            }
        return {"local": "Local Desconhecido", "rede": "N/A", "zip": ""}
    except Exception as e:
        print(f"Erro no GeoIP: {e}")
        return {"local": "N/A", "rede": "N/A", "zip": ""}


def get_portfolio_data(force_refresh=False):
    """
    ATUALIZADO: Busca dados do My O e corrige links de imagem do Drive.
    Usa o domínio 'lh3.googleusercontent.com' que permite exibição em sites.
    """
    global PORTFOLIO_CACHE, ULTIMA_ATUALIZACAO_PORTFOLIO
    agora = datetime.now()

    if not force_refresh and PORTFOLIO_CACHE and ULTIMA_ATUALIZACAO_PORTFOLIO:
        tempo_passado = agora - ULTIMA_ATUALIZACAO_PORTFOLIO
        if tempo_passado < timedelta(hours=CACHE_TIMEOUT_HORAS):
            return PORTFOLIO_CACHE

    try:
        print("🔌 Conectando ao My O System para buscar Portfolio...")

        conn_ws = get_connections_sheet()
        if not conn_ws:
            print("❌ Erro: Não foi possível conectar à Mestra.")
            return PORTFOLIO_CACHE or []

        records = conn_ws.get_all_records()
        portfolio_tab_id = None

        for row in records:
            s_name = str(row['Sheet_Name']).lower()
            s_id = str(row['Sheet_ID']).lower()

            if 'portfolio' in s_name or 'portfólio' in s_name or 'portfolio' in s_id or 'portfólio' in s_id:
                portfolio_tab_id = row['Sheet_ID']
                print(f"✅ Tabela encontrada: {row['Sheet_Name']} (ID: {portfolio_tab_id})")
                break

        if not portfolio_tab_id:
            print("⚠️ Aviso: Tabela Portfolio não encontrada.")
            return PORTFOLIO_CACHE or []

        projects = get_sheet_data(portfolio_tab_id)

        final_projects = []
        for row in projects:
            if not row.get('Título'): continue

            # --- CORREÇÃO DEFINITIVA DE IMAGEM ---
            logo_url = row.get('Logo', '').strip()

            # Se for um link do Google Drive, extraímos o ID e montamos o link direto
            if 'drive.google.com' in logo_url and 'id=' in logo_url:
                try:
                    # Pega o ID que está entre 'id=' e o próximo '&' (se houver)
                    file_id = logo_url.split('id=')[1].split('&')[0]
                    # Link mágico que funciona em tags <img>
                    logo_url = f"https://lh3.googleusercontent.com/d/{file_id}"
                except:
                    pass  # Se der erro, mantém o original

            item = {
                'Título': row.get('Título', '').strip(),
                'Descrição': row.get('Descrição', '').strip(),
                'Link': row.get('Link do site', '').strip(),
                'Logo': logo_url,
                'Tipo': row.get('Tipo', '').strip()
            }
            final_projects.append(item)

        PORTFOLIO_CACHE = final_projects
        ULTIMA_ATUALIZACAO_PORTFOLIO = agora
        print(f"🚀 Portfólio atualizado! {len(final_projects)} projetos carregados.")

        return final_projects

    except Exception as e:
        print(f"❌ Erro crítico ao buscar portfólio: {e}")
        return PORTFOLIO_CACHE if PORTFOLIO_CACHE else []


# --- FUNÇÃO DE ENVIO ASSÍNCRONO (RODA EM THREAD) ---
def processar_envio_background(lista_cliques, motivo):
    """
    Roda em Thread separada. O usuário navega rápido enquanto o servidor
    trabalha pesado aqui (GeoIP + E-mail) sem travar ninguém.
    """
    email_destino = os.getenv('EMAIL_DESTINO')
    if not lista_cliques or not email_destino:
        return

    itens_html = ""
    for item in lista_cliques:
        # GeoIP detalhado roda aqui, sem pressa
        geo_data = get_location_data_rich(item['ip'])

        cor_titulo = "#16305D"
        icone_status = "🖱️"
        bg_card = "#f8f9fa"

        # Destaque visual para conversões
        if "WhatsApp" in item['botao'] or "Contato" in item['botao']:
            cor_titulo = "#25D366"
            icone_status = "💬"
            bg_card = "#e8f5e9"  # Fundo verdinho leve

        tag_visitante = "👤 Novo" if item.get('is_new_user') else "🔄 Retorno"

        itens_html += f"""
        <li style="margin-bottom: 15px; border-left: 4px solid {cor_titulo}; list-style: none; background-color: {bg_card}; padding: 12px; border-radius: 6px; font-family: sans-serif;">
            <div style="font-size: 14px; font-weight: bold; color: {cor_titulo}; display: flex; justify-content: space-between; align-items: center;">
                <span>{icone_status} {item['botao']}</span>
                <span style="font-size: 10px; background: #fff; border: 1px solid #ddd; padding: 2px 8px; border-radius: 12px; color: #555; text-transform: uppercase;">{tag_visitante}</span>
            </div>
            <div style="font-size: 12px; color: #555; line-height: 1.6; margin-top: 8px;">
                🕒 <strong>Hora:</strong> {item['hora_fmt']} <br>
                🌍 <strong>Local:</strong> {geo_data['local']} <br>
                🏢 <strong>Rede/Empresa:</strong> {geo_data['rede']} <br>
                🔧 <strong>Device:</strong> {item['device_str']} <br>
                🔗 <a href="{HOST_URL}{item['pagina']}" style="color: #666;">{item['pagina']}</a> &rarr; {item['destino']}
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

    # 1. Filtros de Segurança
    if request.headers.getlist("X-Forwarded-For"):
        user_ip = request.headers.getlist("X-Forwarded-For")[0]
    else:
        user_ip = request.remote_addr

    ua_string = request.headers.get('User-Agent')
    user_agent = parse(ua_string)

    if user_agent.is_bot:
        return jsonify({'status': 'ignorado', 'motivo': 'robo'}), 200
    if user_ip in MEUS_IPS_IGNORADOS:
        return jsonify({'status': 'ignorado', 'motivo': 'admin'}), 200

    # 2. Identificação Inteligente (COOKIES)
    usuario_id = request.cookies.get('merlo_uid')
    is_new_user = False

    if not usuario_id:
        usuario_id = str(uuid.uuid4())
        is_new_user = True

    # 3. Coleta de Dados
    dispositivo = f"{user_agent.os.family} {user_agent.os.version_string}"
    navegador = f"{user_agent.browser.family}"
    icone = "📱" if user_agent.is_mobile else "💻"

    data = request.get_json()

    # --- CORREÇÃO DE HORÁRIO (BRASIL UTC-3) ---
    # Pegamos o horário UTC do servidor e subtraímos 3 horas
    hora_atual = datetime.utcnow() - timedelta(hours=3)

    novo_clique = {
        "uid": usuario_id,
        "is_new_user": is_new_user,
        "botao": data.get('botao', 'Clique Genérico'),
        "pagina": data.get('pagina_origem', '/'),
        "destino": data.get('url_destino', '#'),
        "hora_fmt": hora_atual.strftime("%H:%M:%S"),  # Agora vai sair certo
        "ip": user_ip,
        "device_str": f"{icone} {navegador} no {dispositivo}"
    }

    BUFFER_CLIQUES.append(novo_clique)

    # 4. Resposta Ultra-Rápida
    response_json = {'status': 'acumulando', 'qtd': len(BUFFER_CLIQUES)}

    if len(BUFFER_CLIQUES) >= LIMITE_BUFFER_IMEDIATO:
        lote_atual = list(BUFFER_CLIQUES)
        BUFFER_CLIQUES.clear()

        t = threading.Thread(target=processar_envio_background, args=(lote_atual, "Buffer Cheio"))
        t.start()

        response_json = {'status': 'enviando_background'}

    resp = make_response(jsonify(response_json))
    if is_new_user:
        resp.set_cookie('merlo_uid', usuario_id, max_age=31536000, httponly=True, samesite='Lax')

    return resp


@app.route('/api/cron-job', methods=['GET'])
def cron_job():
    global BUFFER_CLIQUES

    # Horário Brasil para o log do terminal
    hora_br = datetime.utcnow() - timedelta(hours=3)
    print(f"⏰ Cron Job acionado em {hora_br.strftime('%H:%M:%S')}")

    if len(BUFFER_CLIQUES) > 0:
        lote_atual = list(BUFFER_CLIQUES)
        BUFFER_CLIQUES.clear()

        t = threading.Thread(target=processar_envio_background, args=(lote_atual, "Cron Job (Rotina)"))
        t.start()

        return jsonify({'status': 'ok', 'acao': 'thread_iniciada'}), 200
    else:
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


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)