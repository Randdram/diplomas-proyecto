#!/usr/bin/env python3
"""
Actualiza todas las URLs de diplomas para que apunten a las rutas locales
en lugar de Supabase
"""

import os
from pathlib import Path
from dotenv import load_dotenv
import mysql.connector

load_dotenv()

DB_HOST = os.getenv("DB_HOST")
DB_PORT = int(os.getenv("DB_PORT", "3306"))
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_NAME = os.getenv("DB_NAME")

SALIDA_PDFS = os.getenv("SALIDA_PDFS", "out")


def conectar_db():
    return mysql.connector.connect(
        host=DB_HOST, port=DB_PORT, user=DB_USER,
        password=DB_PASSWORD, database=DB_NAME
    )


def main():
    print("🔄 Actualizando URLs de diplomas a rutas locales...\n")
    
    conn = conectar_db()
    cur = conn.cursor(dictionary=True)
    
    # Obtén todos los diplomas
    cur.execute("SELECT diploma_id, pdf_path FROM diploma")
    diplomas = cur.fetchall()
    
    if not diplomas:
        print("✅ No hay diplomas para actualizar.")
        conn.close()
        return
    
    actualizados = 0
    
    for d in diplomas:
        diploma_id = d["diploma_id"]
        pdf_path = d["pdf_path"]
        
        if not pdf_path:
            print(f"⚠️  diploma_id={diploma_id}: sin pdf_path")
            continue
        
        # Extrae solo el nombre del archivo
        pdf_name = os.path.basename(pdf_path)
        nueva_url = f"/pdfs/{pdf_name}"
        
        # Actualiza
        cur.execute(
            "UPDATE diploma SET pdf_url = %s WHERE diploma_id = %s",
            (nueva_url, diploma_id)
        )
        
        print(f"✅ diploma_id={diploma_id}: {nueva_url}")
        actualizados += 1
    
    conn.commit()
    cur.close()
    conn.close()
    
    print(f"\n🎉 Listo. {actualizados} diploma(s) actualizado(s).")
    print("Ahora reinicia el servidor y prueba: http://localhost:8000/ingresar?curp=TOAA040506MDFLRS08")


if __name__ == "__main__":
    main()