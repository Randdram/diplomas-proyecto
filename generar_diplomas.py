# =========================
#!/usr/bin/env python3
"""
Generador de diplomas (overlay sobre tu PDF de diseño)
- Dibuja SOLAMENTE: Nombre, QR y Folio
- Guarda un PDF por alumno, lo sube a Supabase y registra todo en MySQL

Uso rápido:
  python generar_diplomas.py --alumno_id 1
"""

import os, io, hashlib, uuid, argparse, datetime as dt
from dataclasses import dataclass
from typing import Optional, Tuple

from dotenv import load_dotenv
import mysql.connector as mysql
from PyPDF2 import PdfReader, PdfWriter
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
import qrcode

# ===================== INICIA CAMBIO #1 =====================
# Importamos la función para subir archivos a Supabase
from storage_supabase import upload_pdf
# ===================== TERMINA CAMBIO #1 =====================

# Carga variables de entorno (host, usuario, contraseña, etc.)
load_dotenv()

DB_HOST = os.getenv("DB_HOST", "127.0.0.1")
DB_PORT = int(os.getenv("DB_PORT", "3306"))
DB_USER = os.getenv("DB_USER", "root")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")
DB_NAME = os.getenv("DB_NAME", "escuela_compu")

PLANTILLA_PDF = os.getenv("PLANTILLA_PDF", "RECONOCIMIENTOv2.pdf")
SALIDA_PDFS = os.getenv("SALIDA_PDFS", "out")
BASE_URL_VERIFICACION = os.getenv("BASE_URL_VERIFICACION", "http://localhost:8000")

os.makedirs(SALIDA_PDFS, exist_ok=True)


# =========================
#  COORDENADAS Y TAMAÑOS
# =========================
@dataclass
class Posiciones:
    nombre_xy: Tuple[float, float]      = (421, 315)
    qr_xy: Tuple[float, float]          = (710,  60)
    font_nombre: int = 34

POS = Posiciones()

# =========================
#  UTILIDADES
# =========================
def conectar_db():
    return mysql.connect(
        host=DB_HOST, port=DB_PORT, user=DB_USER, password=DB_PASSWORD, database=DB_NAME
    )

def leer_tamano_pagina(pdf_path: str) -> Tuple[float, float]:
    reader = PdfReader(pdf_path)
    page = reader.pages[0]
    return float(page.mediabox.width), float(page.mediabox.height)

def crear_overlay(page_size: Tuple[float, float], draw_fn):
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=page_size)
    draw_fn(c)
    c.save()
    buf.seek(0)
    return buf

def fusionar_con_plantilla(overlay_buf: io.BytesIO, plantilla_path: str, salida_path: str):
    template_reader = PdfReader(plantilla_path)
    page = template_reader.pages[0]

    overlay_reader = PdfReader(overlay_buf)
    overlay_page = overlay_reader.pages[0]

    page.merge_page(overlay_page)
    writer = PdfWriter()
    writer.add_page(page)

    with open(salida_path, "wb") as f:
        writer.write(f)

def generar_qr_bytes(url: str, box_size: int = 8) -> bytes:
    qr = qrcode.QRCode(version=None, box_size=box_size, border=2)
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    bio = io.BytesIO()
    img.save(bio, format="PNG")
    bio.seek(0)
    return bio.getvalue()

# =========================
#  LÓGICA PRINCIPAL
# =========================
def generar_diploma_para_alumno(cursor, alumno_id: int, ciclo: str, fecha_emision: dt.date, curso_id: Optional[int] = None):
    cursor.execute("""
      SELECT a.nombre FROM alumno a WHERE a.alumno_id=%s
    """, (alumno_id,))
    row = cursor.fetchone()
    if row is None:
        raise ValueError(f"Alumno {alumno_id} no encontrado")
    alumno_nombre = row[0]

    folio = str(uuid.uuid4())
    url_verificacion = f"{BASE_URL_VERIFICACION}/verificar/{folio}"
    qr_png = generar_qr_bytes(url_verificacion)
    qr_img = ImageReader(io.BytesIO(qr_png))

    W, H = leer_tamano_pagina(PLANTILLA_PDF)

    def draw(c):
        c.saveState()
        c.setFillColorRGB(1, 1, 1)
        c.rect(110, 302, 620, 34, fill=1, stroke=0)
        c.restoreState()
        c.setFont("Helvetica-Bold", POS.font_nombre)
        c.drawCentredString(POS.nombre_xy[0], POS.nombre_xy[1], alumno_nombre)
        c.drawImage(qr_img, POS.qr_xy[0], POS.qr_xy[1], width=120, height=120, mask='auto')
        c.setFont("Helvetica", 8)
        c.drawRightString(W - 24, 18, f"Folio: {folio}")

    overlay_buf = crear_overlay((W, H), draw)
    
    salida_path = os.path.join(SALIDA_PDFS, f"DIPLOMA_{alumno_id}_{folio}.pdf")
    fusionar_con_plantilla(overlay_buf, PLANTILLA_PDF, salida_path)

    with open(salida_path, "rb") as f:
        pdf_bytes = f.read()
    sha = hashlib.sha256(pdf_bytes).hexdigest()

    # ===================== INICIA CAMBIO #2 =====================
    # Subir a Supabase inmediatamente después de crear el PDF
    public_url = None
    try:
        pdf_name = os.path.basename(salida_path)
        # El `dest_name` en Supabase no necesita la carpeta 'diplomas/' si tu función `upload_pdf` ya la gestiona
        public_url = upload_pdf(salida_path, dest_name=pdf_name)
        print(f"  - [Supabase] ✅ Subido exitosamente a: {public_url}")
    except Exception as e:
        print(f"  - [Supabase] ❌ ERROR al subir '{pdf_name}': {e}")
    # ===================== TERMINA CAMBIO #2 =====================


    # ===================== INICIA CAMBIO #3 =====================
    # Modificar la inserción en la BD para incluir la pdf_url
    cursor.execute("""
      INSERT INTO diploma (alumno_id, curso_id, folio, ciclo, fecha_emision, hash_sha256, estado, pdf_path, pdf_url)
      VALUES (%s, %s, %s, %s, %s, %s, 'VALIDO', %s, %s)
    """, (alumno_id, curso_id, folio, ciclo, fecha_emision, sha, salida_path, public_url))
    # ===================== TERMINA CAMBIO #3 =====================

    return folio, salida_path, sha, public_url


def main():
    parser = argparse.ArgumentParser(description="Generador de Diplomas con subida automática a Supabase")
    parser.add_argument("--curso_id", type=int, help="Generar para todos los alumnos de este curso")
    parser.add_argument("--alumno_id", type=int, help="Generar solo para un alumno")
    parser.add_argument("--ciclo", type=str, default="2024-2025", help="Ciclo escolar")
    parser.add_argument("--fecha", type=str, default=dt.date.today().isoformat(), help="Fecha de emisión YYYY-MM-DD")
    args = parser.parse_args()

    fecha_emision = dt.date.fromisoformat(args.fecha)

    conn = conectar_db()
    conn.autocommit = False
    try:
        cur = conn.cursor()
        if args.alumno_id:
            alumnos = [args.alumno_id]
        elif args.curso_id:
            cur.execute("SELECT alumno_id FROM inscripcion WHERE curso_id=%s", (args.curso_id,))
            alumnos = [r[0] for r in cur.fetchall()]
        else:
            print("❌ Error: Debes especificar --alumno_id o --curso_id.")
            return

        print(f"Generando diplomas para {len(alumnos)} alumno(s)...")
        for aid in alumnos:
            folio, path, sha, url = generar_diploma_para_alumno(cur, aid, args.ciclo, fecha_emision, args.curso_id)
            print(f"  - Alumno {aid} -> {path} | sha256={sha[:12]}…")

        conn.commit()
        print("\n[OK] 🎉 Proceso completado. Revisa la base de datos y tu bucket de Supabase.")
    except Exception as e:
        conn.rollback()
        print(f"\n[ERROR] ❌ Ocurrió un error: {e}")
    finally:
        if conn and conn.is_connected():
            conn.close()

if __name__ == "__main__":
    main()
