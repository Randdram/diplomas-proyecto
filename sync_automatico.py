#!/usr/bin/env python3
"""
Sincronización automática con Supabase - Mejorado
"""

import os
import mysql.connector
from dotenv import load_dotenv
from storage_supabase import upload_pdf
from datetime import datetime

load_dotenv()

def sync_automatico():
    """Sincronización automática mejorada"""
    print(f"🔄 INICIANDO SINCRONIZACIÓN AUTOMÁTICA - {datetime.now()}")
    
    try:
        # Conectar a BD
        conn = mysql.connector.connect(
            host=os.getenv("DB_HOST"),
            port=int(os.getenv("DB_PORT", "3306")),
            user=os.getenv("DB_USER"),
            password=os.getenv("DB_PASSWORD"),
            database=os.getenv("DB_NAME")
        )
        cur = conn.cursor(dictionary=True)
        
        # 1. Verificar nuevos alumnos sin diplomas
        print("1. 🔍 Buscando nuevos alumnos sin diplomas...")
        cur.execute("""
            SELECT a.alumno_id, a.nombre, a.curp, c.curso_id, c.nombre as curso_nombre
            FROM alumno a
            JOIN inscripcion i ON a.alumno_id = i.alumno_id
            JOIN curso c ON i.curso_id = c.curso_id
            WHERE a.alumno_id NOT IN (SELECT alumno_id FROM diploma)
        """)
        nuevos_alumnos = cur.fetchall()
        
        if nuevos_alumnos:
            print(f"   📝 Encontrados {len(nuevos_alumnos)} nuevos alumnos")
            for alumno in nuevos_alumnos:
                print(f"      - {alumno['nombre']} (ID: {alumno['alumno_id']})")
        else:
            print("   ✅ No hay nuevos alumnos sin diplomas")
        
        # 2. Sincronizar PDFs con Supabase
        print("2. 📤 Sincronizando PDFs con Supabase...")
        cur.execute("""
            SELECT diploma_id, alumno_id, folio, pdf_path, pdf_url
            FROM diploma 
            WHERE pdf_url IS NULL OR pdf_url = '' OR pdf_url NOT LIKE 'http%'
        """)
        diplomas_sin_url = cur.fetchall()
        
        sincronizados = 0
        errores = 0
        
        for d in diplomas_sin_url:
            try:
                pdf_path = d["pdf_path"]
                
                if not pdf_path or not os.path.exists(pdf_path):
                    print(f"   ⚠️  PDF no encontrado: {pdf_path}")
                    errores += 1
                    continue
                
                # Subir a Supabase
                pdf_name = f"DIPLOMA_{d['alumno_id']}_{d['folio']}.pdf"
                url_supabase = upload_pdf(pdf_path, f"diplomas/{pdf_name}")
                
                # Actualizar BD
                cur.execute(
                    "UPDATE diploma SET pdf_url = %s WHERE diploma_id = %s",
                    (url_supabase, d["diploma_id"])
                )
                
                sincronizados += 1
                print(f"   ✅ Sincronizado: {d['folio']}")
                
            except Exception as e:
                errores += 1
                print(f"   ❌ Error con {d['folio']}: {e}")
        
        conn.commit()
        cur.close()
        conn.close()
        
        print(f"\n🎉 SINCRONIZACIÓN COMPLETADA:")
        print(f"   ✅ Diplomas sincronizados: {sincronizados}")
        print(f"   ❌ Errores: {errores}")
        print(f"   👥 Nuevos alumnos: {len(nuevos_alumnos)}")
        
        return {
            "sincronizados": sincronizados,
            "errores": errores,
            "nuevos_alumnos": len(nuevos_alumnos)
        }
        
    except Exception as e:
        print(f"❌ Error general en sincronización: {e}")
        return {"error": str(e)}

if __name__ == "__main__":
    sync_automatico()