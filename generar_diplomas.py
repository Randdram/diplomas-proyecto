#!/usr/bin/env python3
"""
Generador de diplomas (overlay sobre tu PDF de diseño)
- Dibuja SOLAMENTE: Nombre, QR y Folio
- Guarda un PDF por alumno y registra todo en MySQL

Uso rápido:
  python generar_diplomas.py --calibrar
  python generar_diplomas.py --alumno_id 1
  python generar_diplomas.py --curso_id 1 --fecha "2025-09-30"

Requiere:
  - Python 3.10+
  - pip install -r requirements.txt
  - .env con tus credenciales (ver .env.example)
"""
import os, io, hashlib, uuid, argparse, datetime as dt
from dataclasses import dataclass
from typing import Optional, Tuple

from dotenv import load_dotenv
import mysql.connector as mysql
from PyPDF2 import PdfReader, PdfWriter
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
from reportlab.lib.pagesizes import letter
import qrcode
from storage_supabase import upload_pdf # Importa la función de subida

# Carga variables de entorno (host, usuario, contraseña, etc.)
load_dotenv()

DB_HOST = os.getenv("DB_HOST", "127.0.0.1")
DB_PORT = int(os.getenv("DB_PORT", "3306"))
DB_USER = os.getenv("DB_USER", "root")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")
DB_NAME = os.getenv("DB_NAME", "escuela_compu")

PLANTILLA_PDF = os.getenv("PLANTILLA_PDF", "reconocimientoo.pdf") # Actualizado por si acaso
SALIDA_PDFS = os.getenv("SALIDA_PDFS", "out")
BASE_URL_VERIFICACION = os.getenv("BASE_URL_VERIFICACION", "http://localhost:8000")

os.makedirs(SALIDA_PDFS, exist_ok=True)


# =========================
#  COORDENADAS Y TAMAÑOS
# =========================
@dataclass
class Posiciones:
    """
    Coordenadas en puntos (1 pt = 1/72 in).
    Origen (0,0) = ESQUINA INFERIOR IZQUIERDA de la página.

    Ajusta estos valores para calibrar la posición del texto.
    Disminuir 'Y' mueve el texto hacia ABAJO.
    """
    # Aumentamos el valor de Y para subir el texto y que quede sobre la línea
    nombre_xy: Tuple[float, float]      = (421, 322)
    qr_xy: Tuple[float, float]          = (710,  60)
    coordinador_xy: Tuple[float, float] = (421, 120)
    fecha_xy: Tuple[float, float]       = (421, 60)

    # Tamaños de fuente
    font_nombre: int = 34
    font_coordinador: int = 16
    font_fecha: int  = 14


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
    width = float(page.mediabox.width)
    height = float(page.mediabox.height)
    return width, height

def crear_overlay(page_size: Tuple[float, float], draw_fn):
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=page_size)
    draw_fn(c)
    c.showPage()
    c.save()
    return buf.getvalue()

def fusionar_con_plantilla(overlay_bytes: bytes, plantilla_path: str, salida_path: str):
    template_reader = PdfReader(plantilla_path)
    page = template_reader.pages[0]
    overlay_reader = PdfReader(io.BytesIO(overlay_bytes))
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

def formato_fecha_es(fecha: dt.date) -> str:
    """Formatea la fecha a 'Toluca, Estado de México, a DD de MES de AAAA'"""
    meses = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
    return f"Toluca, Estado de México, a {fecha.day} de {meses[fecha.month - 1]} de {fecha.year}"


# =========================
#  LÓGICA PRINCIPAL
# =========================
def generar_diploma_para_alumno(cursor, alumno_id: int, fecha_emision: dt.date, curso_id: Optional[int] = None):
    # 1) Trae datos del alumno
    cursor.execute("SELECT nombre, escuela_id FROM alumno WHERE alumno_id=%s", (alumno_id,))
    alumno_row = cursor.fetchone()
    if alumno_row is None:
        raise ValueError(f"Alumno {alumno_id} no encontrado")
    alumno_nombre = alumno_row['nombre']
    escuela_id = alumno_row['escuela_id']

    # Lógica robusta para obtener el coordinador/profesor
    nombre_profesor = "Coordinador de Aula" # Valor por defecto
    profesor_id_para_diploma = None # Valor por defecto

    if curso_id:
        try:
            # Intenta buscar al profesor asociado al curso
            cursor.execute("SELECT p.profesor_id, p.nombre FROM profesor p JOIN curso c ON p.profesor_id = c.profesor_id WHERE c.curso_id=%s", (curso_id,))
            profesor_row = cursor.fetchone()
            if profesor_row:
                profesor_id_para_diploma = profesor_row['profesor_id']
                nombre_profesor = profesor_row['nombre']
        except mysql.errors.ProgrammingError as e:
            # Si hay un error de SQL (como una tabla que no existe), lo ignora y usa los valores por defecto
            print(f"Aviso de base de datos: {e}. Se usará un nombre genérico.")
            pass


    # 3) Genera folio y URL de verificación
    folio = str(uuid.uuid4())
    url_verificacion = f"{BASE_URL_VERIFICACION}/verificar/{folio}"

    # 4) Prepara QR
    qr_png = generar_qr_bytes(url_verificacion)
    qr_img = ImageReader(io.BytesIO(qr_png))

    # 5) Tamaño de la plantilla
    W, H = leer_tamano_pagina(PLANTILLA_PDF)

    # 6) Dibujo del overlay
    def draw(c):
        # (A) NOMBRE DEL ALUMNO
        c.setFont("Helvetica-Bold", POS.font_nombre)
        c.drawCentredString(POS.nombre_xy[0], POS.nombre_xy[1], alumno_nombre)

        # (B) NOMBRE DEL PROFESOR (ahora dinámico)
        c.setFont("Helvetica", POS.font_coordinador)
        c.drawCentredString(POS.coordinador_xy[0], POS.coordinador_xy[1], nombre_profesor)

        # (C) FECHA EN ESPAÑOL
        fecha_texto = formato_fecha_es(fecha_emision)
        c.setFont("Helvetica", POS.font_fecha)
        c.drawCentredString(POS.fecha_xy[0], POS.fecha_xy[1], fecha_texto)

        # (D) QR (120x120 px)
        c.drawImage(qr_img, POS.qr_xy[0], POS.qr_xy[1], width=120, height=120, mask='auto')

        # (E) Folio
        c.setFont("Helvetica", 8)
        c.drawRightString(W - 24, 18, f"Folio: {folio}")

    overlay = crear_overlay((W, H), draw)

    # 7) Fusiona y guarda
    salida_path = os.path.join(SALIDA_PDFS, f"DIPLOMA_{alumno_id}_{folio}.pdf")
    fusionar_con_plantilla(overlay, PLANTILLA_PDF, salida_path)

    # 7.1) SUBIR A SUPABASE
    public_url = None
    try:
        pdf_name = os.path.basename(salida_path)
        public_url = upload_pdf(salida_path, dest_name=pdf_name)
        print(f"  - [Supabase] Subido exitosamente a: {public_url}")
    except Exception as e:
        print(f"  - [ERROR SUPABASE] No se pudo subir el archivo '{pdf_name}': {e}")

    # 8) Calcula hash
    with open(salida_path, "rb") as f:
        pdf_bytes = f.read()
    sha = hashlib.sha256(pdf_bytes).hexdigest()

    # 9) Inserta registro en la BD
    # Nota: Se usa 'profesor_id_para_diploma' en la columna 'coordinador_id'
    cursor.execute("""
      INSERT INTO diploma (alumno_id, curso_id, coordinador_id, folio, fecha_emision, hash_sha256, estado, pdf_path, pdf_url)
      VALUES (%s, %s, %s, %s, %s, %s, 'VALIDO', %s, %s)
    """, (alumno_id, curso_id, profesor_id_para_diploma, folio, fecha_emision, sha, salida_path, public_url))

    return folio, salida_path, sha

def main():
    parser = argparse.ArgumentParser(description="Generador de Diplomas")
    parser.add_argument("--calibrar", action="store_true", help="Genera PDF con cuadrícula para calibrar")
    parser.add_argument("--curso_id", type=int, help="Generar para todos los alumnos de este curso")
    parser.add_argument("--alumno_id", type=int, help="Generar solo para un alumno")
    # Si no se provee la fecha, se usa la del día de hoy
    parser.add_argument("--fecha", type=str, default=dt.date.today().isoformat(), help="Fecha de emisión YYYY-MM-DD")
    args = parser.parse_args()

    fecha_emision = dt.date.fromisoformat(args.fecha)

    conn = conectar_db()
    conn.autocommit = False
    try:
        cur = conn.cursor(dictionary=True)

        if args.alumno_id:
            alumnos = [{'alumno_id': args.alumno_id}]
        elif args.curso_id:
            cur.execute("SELECT alumno_id FROM inscripcion WHERE curso_id=%s", (args.curso_id,))
            alumnos = cur.fetchall()
        else:
            cur.execute("SELECT alumno_id FROM alumno")
            alumnos = cur.fetchall()

        print(f"Generando diplomas para {len(alumnos)} alumno(s)...")
        for alumno_data in alumnos:
            aid = alumno_data['alumno_id']
            # Para la lógica del profesor, es crucial pasar el curso_id si está disponible.
            # Si se ejecuta para todos, el curso_id será None y se usará el nombre por defecto.
            current_curso_id = args.curso_id
            if not current_curso_id:
                # Si no se especifica un curso, intentamos buscar uno para el alumno
                cur.execute("SELECT curso_id FROM inscripcion WHERE alumno_id=%s LIMIT 1", (aid,))
                inscripcion_row = cur.fetchone()
                if inscripcion_row:
                    current_curso_id = inscripcion_row['curso_id']

            folio, path, sha = generar_diploma_para_alumno(cur, aid, fecha_emision, current_curso_id)
            print(f"  - Alumno {aid} -> {path} | folio={folio[:8]}…")

        conn.commit()
        print("[OK] Listo. Revisa la carpeta de salida y la tabla 'diploma'.")
    except Exception as e:
        conn.rollback()
        raise
    finally:
        conn.close()

if __name__ == "__main__":
    main()

