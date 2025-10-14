# sincronizar_supabase.py
#!/usr/bin/env python3
"""
Sincroniza todos los diplomas con Supabase
"""

import os
import mysql.connector
from dotenv import load_dotenv
from storage_supabase import upload_pdf

load_dotenv()

def sincronizar_todo():
    print("🚀 SINCRONIZANDO TODO CON SUPABASE\n")
    
    # 1. Conectar a BD
    try:
        conn = mysql.connector.connect(
            host=os.getenv("DB_HOST"),
            port=int(os.getenv("DB_PORT", "3306")),
            user=os.getenv("DB_USER"),
            password=os.getenv("DB_PASSWORD"),
            database=os.getenv("DB_NAME")
        )
        cur = conn.cursor(dictionary=True)
        print("✅ Conectado a base de datos")
    except Exception as e:
        print(f"❌ Error BD: {e}")
        return
    
    # 2. Obtener todos los diplomas
    cur.execute("""
        SELECT diploma_id, alumno_id, folio, pdf_path, pdf_url
        FROM diploma
    """)
    diplomas = cur.fetchall()
    
    print(f"📊 Encontrados {len(diplomas)} diplomas\n")
    
    # 3. Procesar cada diploma
    sincronizados = 0
    errores = 0
    
    for d in diplomas:
        diploma_id = d["diploma_id"]
        pdf_path = d["pdf_path"]
        folio = d["folio"]
        
        print(f"🔄 Procesando diploma {diploma_id}...")
        
        # Verificar si el archivo existe localmente
        if not pdf_path or not os.path.exists(pdf_path):
            print(f"   ❌ Archivo no existe: {pdf_path}")
            errores += 1
            continue
        
        # Verificar si ya tiene URL de Supabase
        if d["pdf_url"] and d["pdf_url"].startswith("http"):
            print(f"   ✅ Ya tiene URL Supabase: {d['pdf_url'][:50]}...")
            continue
        
        try:
            # Subir a Supabase
            pdf_name = f"DIPLOMA_{d['alumno_id']}_{folio}.pdf"
            destino = f"diplomas/{pdf_name}"
            
            print(f"   📤 Subiendo a Supabase: {pdf_name}")
            url_supabase = upload_pdf(pdf_path, destino)
            
            # Actualizar BD
            cur.execute(
                "UPDATE diploma SET pdf_url = %s WHERE diploma_id = %s",
                (url_supabase, diploma_id)
            )
            
            sincronizados += 1
            print(f"   ✅ Sincronizado: {url_supabase}")
            
        except Exception as e:
            errores += 1
            print(f"   ❌ Error: {e}")
    
    # 4. Confirmar cambios
    conn.commit()
    cur.close()
    conn.close()
    
    print(f"\n🎉 SINCRONIZACIÓN COMPLETADA:")
    print(f"   ✅ Sincronizados: {sincronizados}")
    print(f"   ❌ Errores: {errores}")
    print(f"   📊 Total: {len(diplomas)}")
    
    if sincronizados > 0:
        print("\n🔧 Ahora actualiza api_verificacion.py y redepoloy en Render")

if __name__ == "__main__":
    sincronizar_todo()