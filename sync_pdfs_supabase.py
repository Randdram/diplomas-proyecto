import os
import mysql.connector
from dotenv import load_dotenv
from storage_supabase import upload_pdf

# === Cargar variables del entorno ===
load_dotenv()

DB_HOST = os.getenv("DB_HOST")
DB_PORT = os.getenv("DB_PORT")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_NAME = os.getenv("DB_NAME")
SALIDA_PDFS = os.getenv("SALIDA_PDFS", "out")

# === Conexión MySQL ===
def conectar_db():
    try:
        conn = mysql.connector.connect(
            host=DB_HOST,
            port=DB_PORT,
            user=DB_USER,
            password=DB_PASSWORD,
            database=DB_NAME
        )
        return conn
    except mysql.connector.Error as err:
        print(f"❌ Error de conexión MySQL: {err}")
        exit(1)

# === Sincronizar PDFs locales con Supabase ===
def sync_pdfs():
    conn = conectar_db()
    cur = conn.cursor(dictionary=True)

    print("🚀 Sincronizando diplomas locales con Supabase…")

    cur.execute("""
        SELECT diploma_id, folio, pdf_path
        FROM diploma
        WHERE pdf_url IS NULL OR pdf_url = ''
    """)
    registros = cur.fetchall()

    if not registros:
        print("✅ Todos los diplomas ya tienen URL en Supabase.")
        return

    for r in registros:
        pdf_local = r["pdf_path"]

        if not os.path.exists(pdf_local):
            print(f"⚠️ No se encontró el archivo: {pdf_local}")
            continue

        try:
            nombre_pdf = os.path.basename(pdf_local)
            destino = f"diplomas/{nombre_pdf}"

            url = upload_pdf(pdf_local, destino)
            print(f"✅ Subido: {nombre_pdf} → {url}")

            cur.execute("""
                UPDATE diploma SET pdf_url = %s WHERE diploma_id = %s
            """, (url, r["diploma_id"]))
            conn.commit()

        except Exception as e:
            print(f"❌ Error al subir {pdf_local}: {e}")

    cur.close()
    conn.close()
    print("🎉 Sincronización completada.")

# === Ejecución principal ===
if __name__ == "__main__":
    sync_pdfs()
