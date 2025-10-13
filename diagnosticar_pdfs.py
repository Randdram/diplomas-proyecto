# diagnosticar_pdfs.py
#!/usr/bin/env python3
"""
Script para diagnosticar problemas con PDFs
"""

import os
import logging
from pathlib import Path
from dotenv import load_dotenv
import mysql.connector

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()

def diagnosticar_pdfs():
    """Diagnostica problemas con PDFs en el sistema"""
    
    print("🔍 INICIANDO DIAGNÓSTICO DE PDFs\n")
    
    # 1. Verificar carpeta de PDFs
    pdf_dir = Path(os.getenv("SALIDA_PDFS", "out"))
    print("1. 📁 Verificando carpeta de PDFs...")
    if pdf_dir.exists():
        pdf_files = list(pdf_dir.glob("*.pdf"))
        print(f"   ✅ Carpeta existe: {pdf_dir}")
        print(f"   📊 Archivos PDF encontrados: {len(pdf_files)}")
        
        for pdf in pdf_files[:5]:  # Mostrar primeros 5
            print(f"      - {pdf.name} ({pdf.stat().st_size} bytes)")
    else:
        print(f"   ❌ Carpeta NO existe: {pdf_dir}")
    
    # 2. Verificar base de datos
    print("\n2. 🗄️ Verificando base de datos...")
    try:
        conn = mysql.connector.connect(
            host=os.getenv("DB_HOST"),
            port=int(os.getenv("DB_PORT", "3306")),
            user=os.getenv("DB_USER"),
            password=os.getenv("DB_PASSWORD"),
            database=os.getenv("DB_NAME")
        )
        cur = conn.cursor(dictionary=True)
        
        # Contar diplomas
        cur.execute("SELECT COUNT(*) as total FROM diploma")
        total = cur.fetchone()["total"]
        print(f"   ✅ Conexión BD: OK")
        print(f"   📊 Total diplomas en BD: {total}")
        
        # Verificar diplomas sin PDF
        cur.execute("""
            SELECT COUNT(*) as sin_pdf 
            FROM diploma 
            WHERE pdf_path IS NULL OR pdf_path = ''
        """)
        sin_pdf = cur.fetchone()["sin_pdf"]
        print(f"   📋 Diplomas sin ruta PDF: {sin_pdf}")
        
        # Verificar URLs
        cur.execute("""
            SELECT COUNT(*) as sin_url 
            FROM diploma 
            WHERE pdf_url IS NULL OR pdf_url = ''
        """)
        sin_url = cur.fetchone()["sin_url"]
        print(f"   🔗 Diplomas sin URL: {sin_url}")
        
        # Ejemplos de diplomas
        print(f"\n3. 📝 Ejemplos de diplomas en BD:")
        cur.execute("""
            SELECT d.diploma_id, d.alumno_id, d.folio, d.pdf_path, d.pdf_url,
                   a.nombre as alumno, a.curp
            FROM diploma d
            JOIN alumno a ON a.alumno_id = d.alumno_id
            ORDER BY d.diploma_id
            LIMIT 5
        """)
        ejemplos = cur.fetchall()
        
        for ej in ejemplos:
            print(f"\n   ┌─ Diploma ID: {ej['diploma_id']}")
            print(f"   ├─ Alumno: {ej['alumno']} ({ej['curp']})")
            print(f"   ├─ Folio: {ej['folio']}")
            print(f"   ├─ Ruta PDF: {ej['pdf_path'] or '❌ NO'}")
            print(f"   └─ URL PDF: {ej['pdf_url'] or '❌ NO'}")
            
            # Verificar si el archivo existe
            if ej['pdf_path']:
                archivo = Path(ej['pdf_path'])
                if archivo.exists():
                    print(f"      📄 Archivo existe: ✅ ({archivo.stat().st_size} bytes)")
                else:
                    print(f"      📄 Archivo existe: ❌ NO ENCONTRADO")
        
        cur.close()
        conn.close()
        
    except Exception as e:
        print(f"   ❌ Error BD: {e}")
    
    # 3. Verificar estructura de nombres
    print(f"\n4. 🔤 Verificando estructura de nombres...")
    if pdf_dir.exists():
        for pdf in pdf_dir.glob("DIPLOMA_*.pdf"):
            nombre = pdf.name
            partes = nombre.replace("DIPLOMA_", "").replace(".pdf", "").split("_")
            
            if len(partes) == 2:
                alumno_id, folio = partes
                print(f"   ✅ {nombre} - AlumnoID: {alumno_id}, Folio: {folio[:8]}...")
            else:
                print(f"   ⚠️  {nombre} - Formato inesperado: {partes}")
    
    print(f"\n🎯 RECOMENDACIONES:")
    print(f"   1. Ejecutar: python rebuild_pdfs_fixed.py (para regenerar PDFs)")
    print(f"   2. Ejecutar: python sync_urls_fix.py (para corregir URLs)")
    print(f"   3. Verificar: http://localhost:8000/ingresar?curp=TOAA040506MDFLRS08")

if __name__ == "__main__":
    diagnosticar_pdfs()