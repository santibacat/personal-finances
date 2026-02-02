import sqlite3
import hashlib
import pandas as pd
from datetime import datetime

DB_PATH = "finance.db"

def get_connection():
    """Connects to the SQLite database."""
    conn = sqlite3.connect(DB_PATH)
    return conn

def init_db():
    """Initializes the database tables if they don't exist."""
    conn = get_connection()
    c = conn.cursor()
    
    # Tabla de transacciones
    c.execute('''
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date DATE,
            amount REAL,
            concept TEXT,
            bank_source TEXT,
            import_date DATETIME,
            hash TEXT UNIQUE
        )
    ''')
    
    # Tabla de etiquetas
    c.execute('''
        CREATE TABLE IF NOT EXISTS tags (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE,
            color TEXT
        )
    ''')
    
    # Tabla de relación transacciones-etiquetas
    c.execute('''
        CREATE TABLE IF NOT EXISTS transaction_tags (
            transaction_id INTEGER,
            tag_id INTEGER,
            PRIMARY KEY (transaction_id, tag_id),
            FOREIGN KEY (transaction_id) REFERENCES transactions(id),
            FOREIGN KEY (tag_id) REFERENCES tags(id)
        )
    ''')
    
    conn.commit()
    conn.close()

def generate_hash(row):
    """Generates a unique hash for a transaction to prevent duplicates."""
    # Concatenar fecha, monto y concepto para crear una firma única
    s = f"{row['date']}{row['amount']}{row['concept']}"
    return hashlib.md5(s.encode('utf-8')).hexdigest()

def insert_transactions(df, bank_name):
    """Inserts transactions from a dataframe into the database."""
    conn = get_connection()
    c = conn.cursor()
    
    inserted_count = 0
    duplicate_count = 0
    
    import_date = datetime.now()
    
    for _, row in df.iterrows():
        # Asumimos que el DF ya viene con columnas normalizadas: date, amount, concept, balance
        tx_hash = generate_hash(row)
        
        try:
            c.execute('''
                INSERT INTO transactions (date, amount, concept, bank_source, import_date, hash)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (
                row['date'], 
                row['amount'], 
                row['concept'], 
                bank_name, 
                import_date, 
                tx_hash
            ))
            inserted_count += 1
        except sqlite3.IntegrityError:
            duplicate_count += 1
            
    conn.commit()
    conn.close()
    return inserted_count, duplicate_count

def get_all_transactions():
    """Retrieves all transactions with their tags."""
    conn = get_connection()
    query = '''
        SELECT t.*, GROUP_CONCAT(tg.name) as tags_list
        FROM transactions t
        LEFT JOIN transaction_tags tt ON t.id = tt.transaction_id
        LEFT JOIN tags tg ON tt.tag_id = tg.id
        GROUP BY t.id
        ORDER BY t.date DESC
    '''
    df = pd.read_sql_query(query, conn)
    conn.close()
    return df

def get_all_tags():
    """Retrieves all available tags."""
    conn = get_connection()
    df = pd.read_sql_query("SELECT * FROM tags ORDER BY name", conn)
    conn.close()
    return df

def add_tag(tag_name):
    """Adds a new tag."""
    conn = get_connection()
    c = conn.cursor()
    try:
        c.execute("INSERT INTO tags (name, color) VALUES (?, ?)", (tag_name, "#808080"))
        conn.commit()
        success = True
    except sqlite3.IntegrityError:
        success = False
    conn.close()
    return success

def link_transaction_tag(transaction_id, tag_name):
    """Links a transaction to a tag (creating the tag if it doesn't exist)."""
    conn = get_connection()
    c = conn.cursor()
    
    # Asegurar que el tag existe
    c.execute("INSERT OR IGNORE INTO tags (name, color) VALUES (?, ?)", (tag_name, "#808080"))
    
    # Obtener ID del tag
    c.execute("SELECT id FROM tags WHERE name = ?", (tag_name,))
    tag_id = c.fetchone()[0]
    
    # Crear vínculo
    try:
        c.execute("INSERT INTO transaction_tags (transaction_id, tag_id) VALUES (?, ?)", (transaction_id, tag_id))
        conn.commit()
    except sqlite3.IntegrityError:
        pass # Ya existía
        
    conn.close()

def remove_transaction_tag(transaction_id, tag_name):
    """Removes a tag from a transaction."""
    conn = get_connection()
    c = conn.cursor()
    
    c.execute("SELECT id FROM tags WHERE name = ?", (tag_name,))
    result = c.fetchone()
    if result:
        tag_id = result[0]
        c.execute("DELETE FROM transaction_tags WHERE transaction_id = ? AND tag_id = ?", (transaction_id, tag_id))
        conn.commit()
    
    conn.close()

def sync_transaction_tags(transaction_id, tags_list):
    """Updates the tags for a transaction to match the provided list."""
    conn = get_connection()
    c = conn.cursor()
    
    # 1. Eliminar vínculos actuales
    c.execute("DELETE FROM transaction_tags WHERE transaction_id = ?", (transaction_id,))
    
    # 2. Añadir nuevos vínculos
    for tag_name in tags_list:
        tag_name = tag_name.strip()
        if not tag_name: continue
        
        # Asegurar que el tag existe
        c.execute("INSERT OR IGNORE INTO tags (name, color) VALUES (?, ?)", (tag_name, "#808080"))
        c.execute("SELECT id FROM tags WHERE name = ?", (tag_name,))
        tag_id = c.fetchone()[0]
        
        # Crear vínculo
        c.execute("INSERT OR IGNORE INTO transaction_tags (transaction_id, tag_id) VALUES (?, ?)", (transaction_id, tag_id))
    
    conn.commit()
    conn.close()
