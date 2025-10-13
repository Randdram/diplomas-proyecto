# rebuild_pdfs.py - VERSIÓN CORREGIDA
import os
import hashlib
import logging
from io import BytesIO
from pathlib import Path
from datetime import date
from contextlib import contextmanager

from dotenv import load_dotenv
import mysql.connector as mysql
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from PyPDF2 import PdfReader, PdfWriter, PageObject

# ✅ Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()

DB_HOST = os.getenv("DB_HOST", "127.0.0.1")
DB_PORT = int(os.getenv("DB_PORT", "3306"))
DB_USER = os.getenv("DB_USER", "root")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")
DB_NAME = os.getenv("DB_NAME", "escuela_compu")

PLANTILLA_PDF = os.getenv("PLANTILLA_PDF", "RECONOCIMIENTOv2.pdf")
SALIDA_PDFS = os.getenv("SALIDA_PDFS", "out")
Path(SALIDA_PDFS).mkdir(parents=True, exist_ok=True)

NAME_Y  = 420
FECHA_Y = 140
FOLIO_Y = 120

@contextmanager
def get_db_connection():
    """Context manager seguro para conexiones BD"""
    conn = None
    try:
        conn = mysql.connect(
            host=DB_HOST, port=DB_PORT, user=DB_USER,
            password=DB_PASSWORD, database=DB_NAME
        )
        yield conn
    except Exception as e:
        logger.error(f"❌ Error de conexión: {e}")
        raise
    finally:
        if conn and conn.is_connected():
            conn.close()

def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                h.update(chunk)
        return h.hexdigest()
    except Exception as e:
        logger.error(f"❌ Error calculando hash: {e}")
        raise

def overlay_simple(datos) -> BytesIO:
    """Crea overlay con nombre, fecha y folio"""
    buf = BytesIO()
    try:
        c = canvas.Canvas(buf, pagesize=letter)
        w, h = letter
        c.setFont("Helvetica-Bold", 42)
        c.drawCentredString(w/2, NAME_Y, datos["alumno"])
        c.setFont("Helvetica", 12)
        c.drawString(70, FECHA_Y, f"Fecha de emisión: {datos['fecha_emision']}")
        c.drawString(70, FOLIO_Y, f"Folio: {datos['folio']}")
        c.save()
        buf.seek(0)
        return buf
    except Exception as e:
        logger.error(f"❌ Error creando overlay: {e}")
        raise

def merge_pdfs(overlay_buf: BytesIO, out_path: Path):
    """Fusiona plantilla con overlay"""
    try:
        base = PdfReader(open(PLANTILLA_PDF, "rb")).pages[0]
        overlay_page = PdfReader(overlay_buf).pages[0]
        
        writer = PdfWriter()
        page = PageObject.create_blank_page(
            width=base.mediabox.width, 
            height=base.mediabox.height
        )
        page.merge_page(base)
        page.merge_page(overlay_page)
        writer.add_page(page)
        
        with open(out_path, "wb") as f:
            writer.write(f)
            
        logger.info(f"✅ PDF generado: {out_path.name}")
    except Exception as e:
        logger.error(f"❌ Error fusionando PDFs: {e}")
        raise

def rebuild_all():
    """Regenera todos los PDFs con nombres CORRECTOS"""
    try:
        with get_db_connection() as conn:
            with conn.cursor(dictionary=True) as cur:
                # ✅ CORREGIDO: Incluir alumno_id en la consulta
                cur.execute("""
                    SELECT d.diploma_id, d.alumno_id, d.folio, d.fecha_emision, d.pdf_path,
                           a.nombre AS alumno
                    FROM diploma d
                    JOIN alumno a ON a.alumno_id = d.alumno_id
                    ORDER BY d.diploma_id
                """)
                rows = cur.fetchall() or []
                
                logger.info(f"Encontrados {len(rows)} diplomas para regenerar…")

                for r in rows:
                    # ✅ CORREGIDO: Usar alumno_id en lugar de diploma_id
                    pdf_name = f"DIPLOMA_{r['alumno_id']}_{r['folio']}.pdf"
                    out_path = Path(SALIDA_PDFS) / pdf_name
                    
                    fecha = r["fecha_emision"].isoformat() if r["fecha_emision"] else date.today().isoformat()
                    
                    # Generar overlay y fusionar
                    ov = overlay_simple({
                        "alumno": r["alumno"], 
                        "fecha_emision": fecha, 
                        "folio": r["folio"]
                    })
                    merge_pdfs(ov, out_path)
                    
                    # Calcular hash
                    h = sha256_file(out_path)
                    
                    # ✅ CORREGIDO: Actualizar también la URL local
                    pdf_url_local = f"/pdfs/{pdf_name}"
                    
                    cur.execute("""
                        UPDATE diploma 
                        SET pdf_path = %s, hash_sha256 = %s, pdf_url = %s
                        WHERE diploma_id = %s
                    """, (str(out_path), h, pdf_url_local, r["diploma_id"]))
                    
                    conn.commit()
                    logger.info(f"✅ {r['diploma_id']} -> {out_path.name}")

        logger.info("🎉 Regeneración completada correctamente.")
        
    except Exception as e:
        logger.error(f"❌ Error en regeneración: {e}")
        raise

if __name__ == "__main__":
    rebuild_all()