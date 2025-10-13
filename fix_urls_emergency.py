# fix_urls_emergency.py
#!/usr/bin/env python3
"""
CORRECCIÓN URGENTE - Elimina 'out\' de las URLs en la base de datos
"""

import os
import logging
from pathlib import Path
from dotenv import load_dotenv
import mysql.connector

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()

def fix_urls_emergency():
    """Corrige URLs que contienen 'out\\' incorrectamente"""
    
    print("🚨 CORRECCIÓN URGENTE DE URLs CON 'out\\'\n")
    
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
        cur.execute("SELECT diploma_id, pdf_url FROM diploma")
        diplomas = cur.fetchall()
        
        actualizados = 0
        
        for d in diplomas:
            diploma_id = d["diploma_id"]
            url_actual = d["pdf_url"]
            
            if url_actual and "out\\" in url_actual:
                # ✅ CORREGIR: eliminar 'out\' de la URL
                nueva_url = url_actual.replace("out\\", "")
                logger.info(f"🔄 Corrigiendo URL: {url_actual} -> {nueva_url}")
                
                cur.execute("UPDATE diploma SET pdf_url = %s WHERE diploma_id = %s", 
                           (nueva_url, diploma_id))
                actualizados += 1
        
        conn.commit()
        
        # Verificar corrección
        cur.execute("SELECT diploma_id, pdf_url FROM diploma WHERE pdf_url LIKE '%out\\%'")
        todavia_mal = cur.fetchall()
        
        cur.close()
        conn.close()
        
        print(f"\n🎉 CORRECCIÓN COMPLETADA:")
        print(f"   📊 URLs corregidas: {actualizados}")
        print(f"   📊 URLs todavía incorrectas: {len(todavia_mal)}")
        
        if todavia_mal:
            print(f"\n⚠️  URLs que siguen mal:")
            for dm in todavia_mal:
                print(f"   - Diploma {dm['diploma_id']}: {dm['pdf_url']}")
        
    except Exception as e:
        logger.error(f"❌ Error en corrección: {e}")
        raise

if __name__ == "__main__":
    fix_urls_emergency()