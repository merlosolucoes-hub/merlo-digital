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


def insert_tracking_event(data):
    """Salva o clique no banco"""
    conn = get_db_connection()
    if not conn: return

    try:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO tracking_events 
            (site_source, uid, botao, pagina_origem, url_destino, ip_address, localizacao, provedor, dispositivo, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            data.get('site_source', 'Merlô'),
            data['uid'],
            data['botao'],
            data['pagina_origem'],
            data['url_destino'],
            data['ip_address'],
            data['localizacao'],
            data['provedor'],
            data['dispositivo'],
            data['created_at']
        ))
        conn.commit()
    except Exception as e:
        print(f"❌ Erro ao salvar tracking: {e}")
    finally:
        if conn: conn.close()


# --- NOVA FUNÇÃO: Busca Configurações do My Ô ---
def get_tracking_settings(site_source):
    """
    Busca as configurações de tracking (Email, Balde, Intervalo)
    do usuário dono deste site na tabela 'users'.
    """
    conn = get_db_connection()
    if not conn: return None

    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        # Busca o usuário que tem este site_source
        cur.execute("SELECT tracking_config FROM users WHERE site_source = %s LIMIT 1", (site_source,))
        result = cur.fetchone()

        if result and result.get('tracking_config'):
            return result['tracking_config']

        # Padrão se não achar
        return {"email_enabled": True, "bucket_size": 10, "cron_interval": 15}

    except Exception as e:
        print(f"Erro ao buscar configs: {e}")
        return {"email_enabled": True, "bucket_size": 10, "cron_interval": 15}
    finally:
        if conn: conn.close()