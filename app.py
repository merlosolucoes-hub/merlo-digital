import os
import resend  # <--- Nova biblioteca
from flask import Flask, render_template, request, flash, redirect, url_for
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'chave_dev_padrao')

# Configura a chave do Resend
resend.api_key = os.getenv('RESEND_API_KEY')

@app.route('/')
def index():
    return render_template('index.html', title="Início")

@app.route('/servicos')
def servicos():
    return render_template('servicos.html', title="Serviços")

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

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)