#!/usr/bin/env python3
"""
Generador de diplomas (super principiante friendly)
- Toma tu PDF de diseño como fondo (PLANTILLA_PDF)
- Dibuja texto y un QR encima
- Guarda un PDF por alumno y registra todo en MySQL

Uso rápido:
  python generar_diplomas.py --calibrar
  python generar_diplomas.py --curso_id 1 --ciclo "2024-2025" --fecha "2025-09-02"

Requiere:
  - Python 3.10+
  - pip install -r requirements.txt
  - .env configurado (ver .env.example)
"""

import os, io, hashlib, uuid, argparse, datetime as dt
from dataclasses import dataclass
from typing import Optional, Tuple

from dotenv import load_dotenv
import mysql.connector as mysql
from PyPDF2 import PdfReader, PdfWriter
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter, A4
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

os.makedirs(SALIDA_PDFS, exist_ok=True)

@dataclass
class Posiciones:
    # Coordenadas en puntos (1 punto = 1/72 pulgadas).
    # Origen (0,0) es la ESQUINA INFERIOR IZQUIERDA de la página.
    nombre_xy: Tuple[float, float] = (300, 420)
    curso_xy: Tuple[float, float] = (300, 380)
    fecha_xy: Tuple[float, float] = (300, 120)
    coordinador_xy: Tuple[float, float] = (150, 170)
    qr_xy: Tuple[float, float] = (500, 90)  # esquina inferior derecha aprox.
    # Tamaños de fuente
    font_nombre: int = 26
    font_curso: int = 14
    font_fecha: int = 12
    font_coord: int = 12

POS = Posiciones()

def conectar_db():
    return mysql.connect(
        host=DB_HOST, port=DB_PORT, user=DB_USER, password=DB_PASSWORD, database=DB_NAME
    )

def leer_tamano_pagina(pdf_path):
    reader = PdfReader(pdf_path)
    page = reader.pages[0]
    # PyPDF2 coord units are in points
    width = float(page.mediabox.width)
    height = float(page.mediabox.height)
    return width, height

def crear_overlay(nombre_archivo, page_size, draw_fn):
    """
    Crea un PDF 'overlay' en memoria y ejecuta draw_fn(canvas) para dibujar encima.
    Devuelve bytes del overlay.
    """
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=page_size)
    draw_fn(c)
    c.showPage()
    c.save()
    return buf.getvalue()

def fusionar_con_plantilla(overlay_bytes, plantilla_path, salida_path):
    # Lee plantilla
    template_reader = PdfReader(plantilla_path)
    page = template_reader.pages[0]

    overlay_reader = PdfReader(io.BytesIO(overlay_bytes))
    overlay_page = overlay_reader.pages[0]

    page.merge_page(overlay_page)  # combina overlay y fondo
    writer = PdfWriter()
    writer.add_page(page)

    with open(salida_path, "wb") as f:
        writer.write(f)

def generar_qr_bytes(url: str, box_size: int = 8):
    qr = qrcode.QRCode(version=None, box_size=box_size, border=2)
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    bio = io.BytesIO()
    img.save(bio, format="PNG")
    bio.seek(0)
    return bio.getvalue()

def dibujar_calibracion(c, W, H):
    # Dibuja una cuadrícula cada 20 pt y marcas cada 100 pt para que ubiques coordenadas.
    c.setStrokeColorRGB(0.8,0.8,0.8)
    c.setLineWidth(0.2)
    step = 20
    for x in range(0, int(W)+1, step):
        c.line(x, 0, x, H)
    for y in range(0, int(H)+1, step):
        c.line(0, y, W, y)
    # Ejes y números cada 100 pt
    c.setStrokeColorRGB(0.2,0.2,0.2)
    c.setFillColorRGB(0.2,0.2,0.2)
    c.setLineWidth(0.8)
    for x in range(0, int(W)+1, 100):
        c.line(x, 0, x, H)
        c.drawString(x+2, 5, str(x))
    for y in range(0, int(H)+1, 100):
        c.line(0, y, W, y)
        c.drawString(5, y+2, str(y))
    c.setFillColorRGB(0,0,0)
    c.drawString(20, H-20, "Calibración de coordenadas (0,0 abajo-izquierda)")

def generar_diploma_para_alumno(cursor, alumno_id: int, ciclo: str, fecha_emision: dt.date, curso_id: Optional[int] = None):
    # Consulta datos mínimos
    cursor.execute("""
      SELECT a.nombre, a.curp, e.nombre AS escuela, g.nombre AS grado
      FROM alumno a
      JOIN escuela e ON e.escuela_id = a.escuela_id
      LEFT JOIN grado g ON g.grado_id = a.grado_id
      WHERE a.alumno_id=%s
    """, (alumno_id,))
    row = cursor.fetchone()
    if row is None:
        raise ValueError(f"Alumno {alumno_id} no encontrado")
    alumno_nombre, curp, escuela_nombre, grado_nombre = row

    curso_nombre = ""
    if curso_id:
        cursor.execute("SELECT nombre FROM curso WHERE curso_id=%s", (curso_id,))
        r = cursor.fetchone()
        if r: curso_nombre = r[0]

    # Puedes traer coordinador/firmante si tienes tabla; aquí lo dejaremos fijo/ejemplo:
    coordinador_nombre = "C. ALFONSO VALENTÍN MONDRAGÓN GARCÍA"
    lugar_fecha = f"Toluca, Estado de México, {fecha_emision.strftime('%d/%m/%Y')}"

    # FOLIO único y URL de verificación
    folio = str(uuid.uuid4())
    url_verificacion = f"{BASE_URL_VERIFICACION}/verificar/{folio}"

    # Prepara QR
    qr_png = generar_qr_bytes(url_verificacion)
    qr_img = ImageReader(io.BytesIO(qr_png))

    # Tamaño de la página según plantilla
    W, H = leer_tamano_pagina(PLANTILLA_PDF)

    def draw(c):
        # Nombre del alumno (centrado aproximado)
        c.setFont("Helvetica-Bold", POS.font_nombre)
        c.drawCentredString(POS.nombre_xy[0], POS.nombre_xy[1], alumno_nombre)

        # Texto del curso
        texto_curso = f"Por su esfuerzo y dedicación al concluir el curso de {curso_nombre or '_____'}."
        c.setFont("Helvetica", POS.font_curso)
        c.drawCentredString(POS.curso_xy[0], POS.curso_xy[1], texto_curso)

        # Fecha/lugar
        c.setFont("Helvetica", POS.font_fecha)
        c.drawCentredString(POS.fecha_xy[0], POS.fecha_xy[1], lugar_fecha)

        # Coordinador
        c.setFont("Helvetica", POS.font_coord)
        c.drawCentredString(POS.coordinador_xy[0], POS.coordinador_xy[1], f"COORDINADOR DE AULA:")
        c.drawCentredString(POS.coordinador_xy[0], POS.coordinador_xy[1]-16, coordinador_nombre)

        # QR (dibujamos a 100x100 pt)
        c.drawImage(qr_img, POS.qr_xy[0], POS.qr_xy[1], width=100, height=100, mask='auto')

        # Folio pequeño (abajo)
        c.setFont("Helvetica", 8)
        c.drawRightString(W-24, 18, f"Folio: {folio}")

    overlay = crear_overlay("overlay", (W, H), draw)

    # Fusionar con plantilla y guardar
    salida_path = os.path.join(SALIDA_PDFS, f"DIPLOMA_{alumno_id}_{folio}.pdf")
    fusionar_con_plantilla(overlay, PLANTILLA_PDF, salida_path)

    # Hash SHA-256 del PDF final
    with open(salida_path, "rb") as f:
        pdf_bytes = f.read()
    sha = hashlib.sha256(pdf_bytes).hexdigest()

    # Registrar en DB
    cursor.execute("""
      INSERT INTO diploma (alumno_id, curso_id, folio, ciclo, fecha_emision, hash_sha256, estado, pdf_path)
      VALUES (%s,%s,%s,%s,%s,%s,'VALIDO',%s)
    """, (alumno_id, curso_id, folio, ciclo, fecha_emision, sha, salida_path))

    return folio, salida_path, sha

def main():
    parser = argparse.ArgumentParser(description="Generador de Diplomas (overlay sobre PDF)")
    parser.add_argument("--calibrar", action="store_true",
                        help="Genera un PDF con cuadrícula para ubicar coordenadas en tu plantilla")
    parser.add_argument("--curso_id", type=int, help="ID de curso para generar (opcional)")
    parser.add_argument("--alumno_id", type=int, help="Generar solo para un alumno (opcional)")
    parser.add_argument("--ciclo", type=str, default="2024-2025", help="Ciclo escolar")
    parser.add_argument("--fecha", type=str, default=dt.date.today().isoformat(), help="Fecha de emisión YYYY-MM-DD")
    args = parser.parse_args()

    # Medidas reales de tu plantilla
    W, H = leer_tamano_pagina(PLANTILLA_PDF)

    if args.calibrar:
        # Crea un PDF con cuadrícula usando TU plantilla de fondo, para que veas coordenadas sobre el diseño real.
        def draw_grid(c):
            dibujar_calibracion(c, W, H)
        overlay = crear_overlay("grid", (W,H), draw_grid)
        salida = os.path.join(SALIDA_PDFS, "calibracion.pdf")
        fusionar_con_plantilla(overlay, PLANTILLA_PDF, salida)
        print(f"[OK] Generado {salida}. Abre el PDF y anota coordenadas X/Y para ajustar POSICIONES en el script.")
        return

    fecha_emision = dt.date.fromisoformat(args.fecha)

    conn = conectar_db()
    conn.autocommit = False
    try:
        cur = conn.cursor()

        alumnos = []
        if args.alumno_id:
            cur.execute("SELECT alumno_id FROM alumno WHERE alumno_id=%s", (args.alumno_id,))
            alumnos = [r[0] for r in cur.fetchall()]
        elif args.curso_id:
            # Todos los alumnos inscritos a ese curso
            cur.execute("""
                SELECT i.alumno_id
                FROM inscripcion i
                WHERE i.curso_id=%s
            """, (args.curso_id,))
            alumnos = [r[0] for r in cur.fetchall()]
        else:
            # Todos (no recomendado si hay miles)
            cur.execute("SELECT alumno_id FROM alumno")
            alumnos = [r[0] for r in cur.fetchall()]

        print(f"Generando diplomas para {len(alumnos)} alumno(s)...")
        for aid in alumnos:
            folio, path, sha = generar_diploma_para_alumno(cur, aid, args.ciclo, fecha_emision, args.curso_id)
            print(f"  - Alumno {aid} -> {path} | folio={folio} | sha256={sha[:12]}…")

        conn.commit()
        print("[OK] Listo. Revisa la carpeta de salida y la tabla 'diploma'.")
    except Exception as e:
        conn.rollback()
        raise
    finally:
        conn.close()

if __name__ == "__main__":
    main()
