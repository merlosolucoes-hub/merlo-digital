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
    """
    Procura na tabela 'user_tables' se existe alguma tabela
    que tenha o nome (display_name) parecido com a keyword (ex: 'Portfolio').
    Retorna o ID da tabela (ex: DB_Portfolio_1234).
    """
    conn = get_db_connection()
    if not conn: return None

    try:
        cur = conn.cursor()
        # Busca insensível a maiúsculas/minúsculas
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
    """
    Busca os dados (JSON) dentro da tabela 'table_records'.
    Retorna uma lista de dicionários, igual o Google Sheets fazia.
    """
    conn = get_db_connection()
    if not conn: return []

    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        # Pega o campo 'data' (que é o JSON com as colunas)
        cur.execute("SELECT data FROM table_records WHERE table_id = %s ORDER BY id ASC", (tab_id,))
        rows = cur.fetchall()

        # Extrai apenas o dicionário de dados de cada linha
        return [r['data'] for r in rows]
    except Exception as e:
        print(f"Erro ao ler dados da tabela {tab_id}: {e}")
        return []
    finally:
        if conn: conn.close()