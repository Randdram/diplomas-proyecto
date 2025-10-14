# forzar_urls_supabase.py
#!/usr/bin/env python3
"""
Fuerza todas las URLs a Supabase (útil para producción)
"""

import os
import mysql.connector
from dotenv import load_dotenv

load_dotenv()

def forzar_urls_supabase():
    print("🔧 FORZANDO URLs DE SUPABASE EN BD\n")
    
    SUPABASE_PUBLIC_BASE = os.getenv("SUPABASE_PUBLIC_BASE")
    
    if not SUPABASE_PUBLIC_BASE:
        print("❌ SUPABASE_PUBLIC_BASE no configurada")
        return
    
    try:
        conn = mysql.connector.connect(
            host=os.getenv("DB_HOST"),
            port=int(os.getenv("DB_PORT", "3306")),
            user=os.getenv("DB_USER"),
            password=os.getenv("DB_PASSWORD"),
            database=os.getenv("DB_NAME")
        )
        cur = conn.cursor(dictionary=True)
        
        # Obtener diplomas
        cur.execute("SELECT diploma_id, alumno_id, folio FROM diploma")
        diplomas = cur.fetchall()
        
        actualizados = 0
        
        for d in diplomas:
            # Generar URL de Supabase
            pdf_name = f"DIPLOMA_{d['alumno_id']}_{d['folio']}.pdf"
            url_supabase = f"{SUPABASE_PUBLIC_BASE}/{pdf_name}"
            
            # Actualizar BD
            cur.execute(
                "UPDATE diploma SET pdf_url = %s WHERE diploma_id = %s",
                (url_supabase, d["diploma_id"])
            )
            
            actualizados += 1
            print(f"✅ {d['diploma_id']} -> {url_supabase}")
        
        conn.commit()
        cur.close()
        conn.close()
        
        print(f"\n🎉 ACTUALIZACIÓN COMPLETADA: {actualizados} diplomas")
        
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    forzar_urls_supabase()