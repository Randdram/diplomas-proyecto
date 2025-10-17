#!/usr/bin/env python3
"""
Módulo para la generación de diplomas.
- Genera PDFs en memoria.
- Sube directamente a Supabase sin guardar archivos locales.
- Evita la creación de diplomas duplicados para un mismo alumno y curso.
- Lógica simplificada para obtener profesor directamente del alumno.
"""
import os
import io
import hashlib
import uuid
import argparse
import datetime as dt
from dataclasses import dataclass
from typing import Optional, Tuple

from dotenv import load_dotenv
import mysql.connector as mysql
from PyPDF2 import PdfReader, PdfWriter
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
from reportlab.lib.pagesizes import letter
import qrcode
from storage_supabase import upload_pdf_from_bytes

load_dotenv()

# --- Configuración ---
DB_HOST = os.getenv("DB_HOST")
DB_PORT = int(os.getenv("DB_PORT", "3306"))
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_NAME = os.getenv("DB_NAME")
PLANTILLA_PDF = os.getenv("PLANTILLA_PDF", "reconocimientoo.pdf")
BASE_URL_VERIFICACION = os.getenv("BASE_URL_VERIFICACION")

@dataclass
class Posiciones:
    # Coordenadas ajustadas para alinear el texto SOBRE las líneas
    nombre_xy: Tuple[float, float] = (421, 322)
    qr_xy: Tuple[float, float] = (710, 60)
    coordinador_xy: Tuple[float, float] = (421, 120)
    fecha_xy: Tuple[float, float] = (421, 60)
    font_nombre: int = 28
    font_coordinador: int = 14
    font_fecha: int = 12

POS = Posiciones()

# --- Funciones de Utilidad ---
def conectar_db():
    return mysql.connect(host=DB_HOST, port=DB_PORT, user=DB_USER, password=DB_PASSWORD, database=DB_NAME)

def leer_tamano_pagina(pdf_path: str):
    try:
        with open(pdf_path, "rb") as f:
            reader = PdfReader(f)
            page = reader.pages[0]
            return float(page.mediabox.width), float(page.mediabox.height)
    except FileNotFoundError:
        print(f"ERROR: No se encontró el archivo de plantilla PDF en la ruta: {pdf_path}")
        # Intenta una ruta alternativa común en entornos de despliegue como Render
        alt_path = f"/var/task/{pdf_path}"
        if os.path.exists(alt_path):
             with open(alt_path, "rb") as f:
                reader = PdfReader(f)
                page = reader.pages[0]
                return float(page.mediabox.width), float(page.mediabox.height)
        raise

def crear_overlay(page_size, draw_fn):
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=page_size)
    draw_fn(c)
    c.save()
    return buf.getvalue()

def fusionar_con_plantilla(overlay_bytes: bytes, plantilla_path: str) -> io.BytesIO:
    try:
        with open(plantilla_path, "rb") as f:
            template_reader = PdfReader(f)
            page = template_reader.pages[0]
            overlay_reader = PdfReader(io.BytesIO(overlay_bytes))
            page.merge_page(overlay_reader.pages[0])
            writer = PdfWriter()
            writer.add_page(page)
            output_buffer = io.BytesIO()
            writer.write(output_buffer)
            output_buffer.seek(0)
            return output_buffer
    except FileNotFoundError:
        alt_path = f"/var/task/{plantilla_path}"
        with open(alt_path, "rb") as f:
            template_reader = PdfReader(f)
            page = template_reader.pages[0]
            overlay_reader = PdfReader(io.BytesIO(overlay_bytes))
            page.merge_page(overlay_reader.pages[0])
            writer = PdfWriter()
            writer.add_page(page)
            output_buffer = io.BytesIO()
            writer.write(output_buffer)
            output_buffer.seek(0)
            return output_buffer

def generar_qr_bytes(url: str):
    qr = qrcode.QRCode(version=1, box_size=8, border=2)
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    bio = io.BytesIO()
    img.save(bio, "PNG")
    bio.seek(0)
    return bio.getvalue()

def formato_fecha_es(fecha: dt.date):
    meses = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
    return f"Toluca, Estado de México, a {fecha.day} de {meses[fecha.month - 1]} de {fecha.year}"


# --- Lógica Principal de Generación ---
def generar_diploma_para_alumno(cursor, alumno_id: int, fecha_emision: dt.date, curso_id: Optional[int] = None):
    # 1. Obtener datos del alumno y su profesor_id
    cursor.execute("SELECT nombre, profesor_id FROM alumno WHERE alumno_id=%s", (alumno_id,))
    alumno_row = cursor.fetchone()
    if not alumno_row:
        raise ValueError(f"Alumno {alumno_id} no encontrado")
    alumno_nombre, profesor_id = alumno_row['nombre'], alumno_row['profesor_id']

    # 2. Obtener nombre del profesor
    nombre_profesor = "Coordinador de Aula"
    if profesor_id:
        cursor.execute("SELECT nombre FROM profesor WHERE profesor_id=%s", (profesor_id,))
        profesor_row = cursor.fetchone()
        if profesor_row:
            nombre_profesor = profesor_row['nombre']

    # 3. Generar folio, QR y overlay
    folio = str(uuid.uuid4())
    url_verificacion = f"{BASE_URL_VERIFICACION}/verificar/{folio}"
    qr_png = generar_qr_bytes(url_verificacion)
    W, H = leer_tamano_pagina(PLANTILLA_PDF)

    def draw(c):
        c.setFont("Helvetica-Bold", POS.font_nombre)
        c.drawCentredString(POS.nombre_xy[0], POS.nombre_xy[1], alumno_nombre)
        c.setFont("Helvetica", POS.font_coordinador)
        c.drawCentredString(POS.coordinador_xy[0], POS.coordinador_xy[1], nombre_profesor)
        c.setFont("Helvetica", POS.font_fecha)
        c.drawCentredString(POS.fecha_xy[0], POS.fecha_xy[1], formato_fecha_es(fecha_emision))
        c.drawImage(ImageReader(io.BytesIO(qr_png)), POS.qr_xy[0], POS.qr_xy[1], width=120, height=120, mask='auto')
        c.setFont("Helvetica", 8)
        c.drawRightString(W - 24, 18, f"Folio: {folio}")

    overlay_bytes = crear_overlay((W, H), draw)
    
    # 4. Fusionar en memoria y subir a Supabase
    pdf_buffer = fusionar_con_plantilla(overlay_bytes, PLANTILLA_PDF)
    pdf_bytes = pdf_buffer.getvalue()
    pdf_filename = f"DIPLOMA_{alumno_id}_{folio}.pdf"
    public_url = upload_pdf_from_bytes(pdf_bytes, dest_name=pdf_filename)
    print(f"  - [Supabase] Subido: {public_url}")

    # 5. Calcular hash y registrar en la BD
    sha = hashlib.sha256(pdf_bytes).hexdigest()
    # Usa profesor_id en la columna coordinador_id
    cursor.execute("""
      INSERT INTO diploma (alumno_id, curso_id, coordinador_id, folio, fecha_emision, hash_sha256, estado, pdf_path, pdf_url)
      VALUES (%s, %s, %s, %s, %s, %s, 'VALIDO', %s, %s)
    """, (alumno_id, curso_id, profesor_id, folio, fecha_emision, sha, pdf_filename, public_url))
    print(f"  - Diploma generado para Alumno {alumno_id}")

def generar_diplomas_para_curso(curso_id: int, fecha_emision: Optional[dt.date] = None):
    if not fecha_emision:
        fecha_emision = dt.date.today()

    conn = conectar_db()
    conn.autocommit = False
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT alumno_id FROM inscripcion WHERE curso_id=%s", (curso_id,))
        alumnos = cur.fetchall()

        print(f"Iniciando generación de diplomas para {len(alumnos)} alumno(s) del curso {curso_id}...")
        for alumno_data in alumnos:
            alumno_id = alumno_data['alumno_id']
            cur.execute("SELECT diploma_id FROM diploma WHERE alumno_id = %s AND curso_id = %s", (alumno_id, curso_id))
            if cur.fetchone():
                print(f"  - Alumno {alumno_id} ya tiene un diploma para este curso. Omitiendo.")
                continue
            generar_diploma_para_alumno(cur, alumno_id, fecha_emision, curso_id)
        
        conn.commit()
        print(f"[OK] Proceso para el curso {curso_id} finalizado.")
    except Exception as e:
        conn.rollback()
        print(f"[ERROR] Falló la generación para el curso {curso_id}: {e}")
        raise
    finally:
        if conn and conn.is_connected(): conn.close()

# --- Bloque para ejecución como script ---
def main():
    parser = argparse.ArgumentParser(description="Generador de Diplomas")
    parser.add_argument("--curso_id", type=int, help="ID del curso para generar para todos los alumnos inscritos")
    parser.add_argument("--alumno_id", type=int, help="ID del alumno para generar un solo diploma")
    parser.add_argument("--fecha", type=str, default=dt.date.today().isoformat(), help="Fecha de emisión YYYY-MM-DD")
    args = parser.parse_args()
    fecha_emision = dt.date.fromisoformat(args.fecha)

    if args.alumno_id:
        conn = conectar_db()
        try:
            cur = conn.cursor(dictionary=True)
            cur.execute("SELECT curso_id FROM inscripcion WHERE alumno_id = %s LIMIT 1", (args.alumno_id,))
            inscripcion = cur.fetchone()
            curso_id_alumno = inscripcion['curso_id'] if inscripcion else None
            generar_diploma_para_alumno(cur, args.alumno_id, fecha_emision, curso_id_alumno)
            conn.commit()
        finally:
            if conn and conn.is_connected(): conn.close()
    elif args.curso_id:
        generar_diplomas_para_curso(args.curso_id, fecha_emision)
    else:
        print("Error: Debes especificar --alumno_id o --curso_id.")

if __name__ == "__main__":
    main()

