import os
import json
import psycopg2
from psycopg2.extras import RealDictCursor

def get_db_connection():
    """Conecta ao banco de dados Neon"""
    try:
        conn = psycopg2.connect(os.getenv('DATABASE_URL'))
        return conn
    except Exception as e:
        print(f"❌ Erro ao conectar no Banco: {e}")
        return None

def get_table_id_by_name(keyword):
    """Procura ID da tabela pelo nome"""
    conn = get_db_connection()
    if not conn: return None
    try:
        cur = conn.cursor()
        query = "SELECT id FROM user_tables WHERE LOWER(display_name) LIKE LOWER(%s) LIMIT 1"
        cur.execute(query, (f"%{keyword}%",))
        result = cur.fetchone()
        return result[0] if result else None
    except Exception as e:
        print(f"Erro ao buscar ID da tabela: {e}")
        return None
    finally:
        if conn: conn.close()

def get_sheet_data(tab_id):
    """Busca os dados JSON da tabela"""
    conn = get_db_connection()
    if not conn: return []
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT data FROM table_records WHERE table_id = %s ORDER BY id ASC", (tab_id,))
        rows = cur.fetchall()
        return [r['data'] for r in rows]
    except Exception as e:
        print(f"Erro ao ler dados da tabela {tab_id}: {e}")
        return []
    finally:
        if conn: conn.close()

# --- ALTERAÇÃO AQUI: Recebe e grava a data correta ---
def insert_tracking_event(data):
    """
    Salva um evento de clique na tabela tracking_events.
    """
    conn = get_db_connection()
    if not conn: return

    try:
        cur = conn.cursor()
        # Adicionei 'created_at' no INSERT
        cur.execute("""
            INSERT INTO tracking_events 
            (site_source, uid, botao, pagina_origem, url_destino, ip_address, localizacao, provedor, dispositivo, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            data['site_source'],
            data['uid'],
            data['botao'],
            data['pagina_origem'],
            data['url_destino'],
            data['ip_address'],
            data['localizacao'],
            data['provedor'],
            data['dispositivo'],
            data['created_at']  # <--- DATA BRASILEIRA VINDA DO PYTHON
        ))
        conn.commit()
    except Exception as e:
        print(f"❌ Erro ao salvar tracking no BD: {e}")
    finally:
        if conn: conn.close()