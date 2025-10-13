#!/usr/bin/env python3
"""
Sincroniza PDFs locales a Supabase y actualiza la BD
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv
import mysql.connector
from storage_supabase import upload_pdf

load_dotenv()

DB_HOST = os.getenv("DB_HOST")
DB_PORT = int(os.getenv("DB_PORT", "3306"))
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_NAME = os.getenv("DB_NAME")

SALIDA_PDFS = os.getenv("SALIDA_PDFS", "out")
SUPABASE_PUBLIC_BASE = os.getenv("SUPABASE_PUBLIC_BASE")


def conectar_db():
    return mysql.connector.connect(
        host=DB_HOST, port=DB_PORT, user=DB_USER,
        password=DB_PASSWORD, database=DB_NAME
    )


def sync():
    print("🚀 Sincronizando PDFs con Supabase...\n")
    
    conn = conectar_db()
    cur = conn.cursor(dictionary=True)
    
    # Obtén diplomas sin URL
    cur.execute("""
        SELECT diploma_id, folio, pdf_path
        FROM diploma
        WHERE pdf_url IS NULL OR pdf_url = ''
    """)
    registros = cur.fetchall()
    
    if not registros:
        print("✅ Todos los diplomas ya tienen URL en Supabase.")
        conn.close()
        return
    
    print(f"Encontrados {len(registros)} diploma(s) sin URL.\n")
    
    subidos = 0
    for r in registros:
        pdf_path = r["pdf_path"]
        folio = r["folio"]
        diploma_id = r["diploma_id"]
        
        if not os.path.exists(pdf_path):
            print(f"⚠️  No existe: {pdf_path}")
            continue
        
        try:
            nombre_pdf = os.path.basename(pdf_path)
            dest_name = f"diplomas/{nombre_pdf}"
            
            # Subir a Supabase
            url = upload_pdf(pdf_path, dest_name)
            print(f"✅ Subido: {nombre_pdf}")
            print(f"   URL: {url}\n")
            
            # Actualizar BD
            cur.execute(
                "UPDATE diploma SET pdf_url = %s WHERE diploma_id = %s",
                (url, diploma_id)
            )
            conn.commit()
            subidos += 1
            
        except Exception as e:
            print(f"❌ Error con {folio}: {e}\n")
    
    cur.close()
    conn.close()
    
    print(f"🎉 Sincronización completada. {subidos}/{len(registros)} subidos correctamente.")


if __name__ == "__main__":
    sync()