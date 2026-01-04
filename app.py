import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from flask import Flask, render_template, request, flash, redirect, url_for
from dotenv import load_dotenv

# Carrega as variáveis do arquivo .env
load_dotenv()

app = Flask(__name__)

app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'chave_dev_padrao')


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

        # --- LÓGICA DE ENVIO DE E-MAIL (HOSTINGER) ---
        try:
            # 1. Pegar credenciais do .env (Configuradas no Render)
            my_email = os.getenv('EMAIL_USER')
            my_password = os.getenv('EMAIL_PASS')
            email_destino = os.getenv('EMAIL_DESTINO')

            # 2. Configurar o e-mail
            msg = MIMEMultipart()
            msg['From'] = my_email
            msg['To'] = email_destino
            msg['Subject'] = f"Novo Lead MERLÔ: {nome} - {empresa}"

            # 3. Corpo do E-mail
            corpo_email = f"""
                    NOVA SOLICITAÇÃO DE CONTATO - MERLÔ DIGITAL
                    -------------------------------------------
                    Nome: {nome}
                    Empresa: {empresa}
                    E-mail do Cliente: {email_cliente}

                    Mensagem:
                    {mensagem_cliente}
                    -------------------------------------------
                    """
            msg.attach(MIMEText(corpo_email, 'plain'))

            # 4. Conectar ao servidor da HOSTINGER
            # Hostinger usa: smtp.hostinger.com | Porta: 465 (SSL)
            server = smtplib.SMTP_SSL('smtp.hostinger.com', 465)

            server.login(my_email, my_password)
            text = msg.as_string()
            server.sendmail(my_email, email_destino, text)
            server.quit()

            print(f"E-mail enviado com sucesso para {email_destino}")
            flash('Mensagem enviada com sucesso! Em breve entraremos em contato.', 'success')

        except Exception as e:
            print(f"Erro ao enviar e-mail: {e}")
            flash('Erro ao enviar mensagem. Tente novamente ou nos chame no WhatsApp.', 'danger')

        return redirect(url_for('contato'))

    return render_template('contato.html', title="Contato")


if __name__ == '__main__':
    # 'host=0.0.0.0' permite acesso externo se necessário em dev
    app.run(debug=True, host='0.0.0.0', port=5000)