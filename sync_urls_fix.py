# sync_urls_fix.py
#!/usr/bin/env python3
"""
Corrige automáticamente las URLs de PDFs en la base de datos
"""

import os
import logging
from pathlib import Path
from dotenv import load_dotenv
import mysql.connector

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()

def fix_pdf_urls():
    """Corrige todas las URLs de PDFs en la base de datos"""
    
    print("🔧 CORRIGIENDO URLs DE PDFs...\n")
    
    try:
        conn = mysql.connector.connect(
            host=os.getenv("DB_HOST"),
            port=int(os.getenv("DB_PORT", "3306")),
            user=os.getenv("DB_USER"),
            password=os.getenv("DB_PASSWORD"),
            database=os.getenv("DB_NAME")
        )
        cur = conn.cursor(dictionary=True)
        
        # Obtener todos los diplomas
        cur.execute("""
            SELECT diploma_id, alumno_id, folio, pdf_path, pdf_url
            FROM diploma
        """)
        diplomas = cur.fetchall()
        
        actualizados = 0
        
        for d in diplomas:
            diploma_id = d["diploma_id"]
            alumno_id = d["alumno_id"]
            folio = d["folio"]
            
            # Generar nombre de archivo esperado
            pdf_nombre_esperado = f"DIPLOMA_{alumno_id}_{folio}.pdf"
            pdf_url_local = f"/pdfs/{pdf_nombre_esperado}"
            
            # Verificar si necesita actualización
            necesita_actualizar = False
            
            if not d["pdf_url"] or d["pdf_url"] == "":
                necesita_actualizar = True
                logger.info(f"📝 Actualizando URL vacía: {diploma_id}")
            elif "diploma_id" in d["pdf_url"]:
                # URL contiene diploma_id (incorrecto), debe contener alumno_id
                necesita_actualizar = True
                logger.info(f"🔄 Corrigiendo URL con ID incorrecto: {diploma_id}")
            
            if necesita_actualizar:
                # También actualizar pdf_path si es necesario
                nuevo_pdf_path = str(Path(os.getenv("SALIDA_PDFS", "out")) / pdf_nombre_esperado)
                
                cur.execute("""
                    UPDATE diploma 
                    SET pdf_url = %s, pdf_path = %s
                    WHERE diploma_id = %s
                """, (pdf_url_local, nuevo_pdf_path, diploma_id))
                
                actualizados += 1
                logger.info(f"✅ Diploma {diploma_id}: {pdf_url_local}")
        
        conn.commit()
        cur.close()
        conn.close()
        
        print(f"\n🎉 CORRECCIÓN COMPLETADA:")
        print(f"   📊 Diplomas actualizados: {actualizados}")
        print(f"   📊 Total diplomas: {len(diplomas)}")
        
    except Exception as e:
        logger.error(f"❌ Error en corrección: {e}")
        raise

if __name__ == "__main__":
    fix_pdf_urls()