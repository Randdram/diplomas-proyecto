#!/usr/bin/env python3
"""
Generador simple de diplomas sin dependencia de tabla 'coordinador'
Uso: python generar_diplomas_simple.py
"""

import os, io, hashlib, uuid
from datetime import date
from pathlib import Path

from dotenv import load_dotenv
import mysql.connector as mysql
from PyPDF2 import PdfReader, PdfWriter
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
import qrcode

load_dotenv()

DB_HOST = os.getenv("DB_HOST", "127.0.0.1")
DB_PORT = int(os.getenv("DB_PORT", "3306"))
DB_USER = os.getenv("DB_USER", "root")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")
DB_NAME = os.getenv("DB_NAME", "escuela_compu")

PLANTILLA_PDF = os.getenv("PLANTILLA_PDF", "RECONOCIMIENTOv2.pdf")
SALIDA_PDFS = os.getenv("SALIDA_PDFS", "out")
BASE_URL_VERIFICACION = os.getenv("BASE_URL_VERIFICACION", "http://localhost:8000")

Path(SALIDA_PDFS).mkdir(parents=True, exist_ok=True)

POS_NOMBRE_X = 421
POS_NOMBRE_Y = 315
POS_QR_X = 710
POS_QR_Y = 60


def conectar_db():
    return mysql.connect(
        host=DB_HOST, port=DB_PORT, user=DB_USER,
        password=DB_PASSWORD, database=DB_NAME
    )


def leer_tamano_pagina(pdf_path: str):
    reader = PdfReader(pdf_path)
    page = reader.pages[0]
    return float(page.mediabox.width), float(page.mediabox.height)


def generar_qr_bytes(url: str):
    qr = qrcode.QRCode(version=None, box_size=8, border=2)
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    bio = io.BytesIO()
    img.save(bio, format="PNG")
    bio.seek(0)
    return bio.getvalue()


def crear_overlay(page_size, alumno_nombre: str, folio: str):
    W, H = page_size
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=page_size)
    
    # Tapa el nombre anterior
    c.saveState()
    c.setFillColorRGB(1, 1, 1)
    c.rect(110, 302, 620, 34, fill=1, stroke=0)
    c.restoreState()
    
    # Dibuja nombre centrado
    c.setFont("Helvetica-Bold", 34)
    c.drawCentredString(POS_NOMBRE_X, POS_NOMBRE_Y, alumno_nombre)
    
    # Dibuja QR
    qr_png = generar_qr_bytes(f"{BASE_URL_VERIFICACION}/verificar/{folio}")
    qr_img = ImageReader(io.BytesIO(qr_png))
    c.drawImage(qr_img, POS_QR_X, POS_QR_Y, width=120, height=120, mask='auto')
    
    # Folio pequeño abajo-derecha
    c.setFont("Helvetica", 8)
    c.drawRightString(W - 24, 18, f"Folio: {folio}")
    
    c.showPage()
    c.save()
    return buf.getvalue()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def generar_diploma_para_alumno(cur, alumno_id: int):
    """Genera un diploma para un alumno específico."""
    
    # Obtén datos del alumno
    cur.execute("""
        SELECT a.nombre, a.curp, e.nombre AS escuela
        FROM alumno a
        JOIN escuela e ON e.escuela_id = a.escuela_id
        WHERE a.alumno_id = %s
    """, (alumno_id,))
    row = cur.fetchone()
    
    if not row:
        print(f"⚠️ Alumno {alumno_id} no encontrado")
        return False
    
    alumno_nombre, curp, escuela_nombre = row
    
    # Genera folio y URL
    folio = str(uuid.uuid4())
    fecha_emision = date.today().isoformat()
    
    # Obtén tamaño real de plantilla
    W, H = leer_tamano_pagina(PLANTILLA_PDF)
    
    # Crea overlay
    overlay_bytes = crear_overlay((W, H), alumno_nombre, folio)
    
    # Fusiona con plantilla
    template_reader = PdfReader(PLANTILLA_PDF)
    page = template_reader.pages[0]
    
    overlay_reader = PdfReader(io.BytesIO(overlay_bytes))
    overlay_page = overlay_reader.pages[0]
    
    page.merge_page(overlay_page)
    writer = PdfWriter()
    writer.add_page(page)
    
    # Guarda PDF
    salida_path = Path(SALIDA_PDFS) / f"DIPLOMA_{alumno_id}_{folio}.pdf"
    with open(salida_path, "wb") as f:
        writer.write(f)
    
    # Calcula hash
    sha = sha256_file(salida_path)
    
    # Inserta en BD (sin coordinador_id)
    cur.execute("""
        INSERT INTO diploma 
        (alumno_id, folio, fecha_emision, hash_sha256, estado, pdf_path)
        VALUES (%s, %s, %s, %s, 'VALIDO', %s)
    """, (alumno_id, folio, fecha_emision, sha, str(salida_path)))
    
    print(f"✅ {alumno_nombre} ({curp}) -> {salida_path.name}")
    return True


def main():
    conn = conectar_db()
    conn.autocommit = False
    
    try:
        cur = conn.cursor(dictionary=True)
        
        # Obtén alumnos sin diploma
        cur.execute("""
            SELECT a.alumno_id FROM alumno a
            WHERE NOT EXISTS (
                SELECT 1 FROM diploma d WHERE d.alumno_id = a.alumno_id
            )
        """)
        alumnos = [r["alumno_id"] for r in cur.fetchall()]
        
        if not alumnos:
            print("✅ No hay alumnos pendientes de diploma")
            conn.close()
            return
        
        print(f"🚀 Generando {len(alumnos)} diploma(s)...\n")
        
        for aid in alumnos:
            if generar_diploma_para_alumno(cur, aid):
                conn.commit()
        
        print(f"\n🎉 Listo. {len(alumnos)} diploma(s) generado(s)")
        
    except Exception as e:
        conn.rollback()
        print(f"❌ Error: {e}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()