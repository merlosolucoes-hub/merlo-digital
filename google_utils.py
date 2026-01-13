import gspread
from oauth2client.service_account import ServiceAccountCredentials
import os
import json

# Escopos necessários para ler planilhas
SCOPE = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]


def get_client():
    """Autentica com o Google usando as credenciais do .env"""
    creds_json = os.getenv('GOOGLE_CREDENTIALS_JSON')

    if creds_json:
        # Carrega do JSON no .env (Produção/Render)
        creds_dict = json.loads(creds_json)
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, SCOPE)
    else:
        # Fallback para arquivo local (se existir)
        creds = ServiceAccountCredentials.from_json_keyfile_name('service_account.json', SCOPE)

    return gspread.authorize(creds)


def setup_master_sheet():
    """Conecta na Planilha Mestra definida no ID"""
    client = get_client()
    try:
        master_id = os.getenv('MASTER_SHEET_ID')
        return client.open_by_key(master_id)
    except Exception as e:
        print(f"Erro ao abrir Planilha Mestra: {e}")
        return None


def get_connections_sheet():
    """Pega a aba 'Conexoes' onde estão listados os IDs das tabelas"""
    sh = setup_master_sheet()
    if not sh: return None

    try:
        # Tenta pegar a aba de conexões
        return sh.worksheet("Conexoes")
    except:
        print("Erro: Aba 'Conexoes' não encontrada na planilha mestra.")
        return None


def get_sheet_data(tab_name):
    """
    Lê todo o conteúdo de uma aba específica (Tabela do Cliente/Portfólio)
    Retorna uma lista de dicionários.
    """
    sh = setup_master_sheet()
    if not sh: return []

    try:
        ws = sh.worksheet(tab_name)
        return ws.get_all_records()
    except Exception as e:
        print(f"Erro ao ler a aba '{tab_name}': {e}")
        return []