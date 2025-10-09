#!/usr/bin/env python3
"""
Generador de diplomas (overlay sobre tu PDF de diseño)
- Dibuja SOLAMENTE: Nombre, QR y Folio
- Cubre (tapa) el nombre de ejemplo que trae la plantilla
- Guarda un PDF por alumno y registra todo en MySQL

Uso rápido:
  python generar_diplomas.py --calibrar
  python generar_diplomas.py --alumno_id 1 --ciclo "2024-2025" --fecha "2025-09-30"
  python generar_diplomas.py --curso_id 1 --ciclo "2024-2025" --fecha "2025-09-30"

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
import qrcode
from fastapi.encoders import jsonable_encoder

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
    """
    Coordenadas en puntos (1 pt = 1/72 in).
    Origen (0,0) = ESQUINA INFERIOR IZQUIERDA de la página.

    Estos valores están calibrados para A4 horizontal (~842 x 595).
    Si tu PDF usa otro tamaño, ejecuta: python generar_diplomas.py --calibrar
    y ajusta aquí en base a la cuadrícula.
    """
    # Textos centrados: X = centro de la página (~842/2 = 421)
    nombre_xy: Tuple[float, float]      = (421, 315)  # Nombre centrado
    qr_xy: Tuple[float, float]          = (710,  60)  # QR abajo-derecha (120x120)
    # No se usan en esta plantilla (los dejo por si los ocupas luego)
    curso_xy: Tuple[float, float]       = (421, 270)
    fecha_xy: Tuple[float, float]       = (421,  75)
    coordinador_xy: Tuple[float, float] = (421, 180)
    # Tamaños de fuente
    font_nombre: int = 34
    font_curso: int  = 14
    font_fecha: int  = 12
    font_coord: int  = 12


POS = Posiciones()


# =========================
#  UTILIDADES
# =========================
def conectar_db():
    """Conecta a MySQL usando datos del .env"""
    return mysql.connect(
        host=DB_HOST, port=DB_PORT, user=DB_USER, password=DB_PASSWORD, database=DB_NAME
    )


def leer_tamano_pagina(pdf_path: str) -> Tuple[float, float]:
    """Lee el tamaño de la primera página de tu PDF (en puntos)."""
    reader = PdfReader(pdf_path)
    page = reader.pages[0]
    width = float(page.mediabox.width)
    height = float(page.mediabox.height)
    return width, height


def crear_overlay(page_size: Tuple[float, float], draw_fn):
    """
    Crea un PDF en memoria (overlay) y ejecuta draw_fn(canvas) para dibujar encima.
    Devuelve los bytes del PDF de overlay.
    """
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=page_size)
    draw_fn(c)
    c.showPage()
    c.save()
    return buf.getvalue()


def fusionar_con_plantilla(overlay_bytes: bytes, plantilla_path: str, salida_path: str):
    """
    Combina la página del overlay con la página de tu plantilla y guarda el PDF final.
    """
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
    """Genera un QR (PNG en bytes) con la URL dada."""
    qr = qrcode.QRCode(version=None, box_size=box_size, border=2)
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    bio = io.BytesIO()
    img.save(bio, format="PNG")
    bio.seek(0)
    return bio.getvalue()


def dibujar_calibracion(c, W: float, H: float):
    """
    Dibuja una cuadrícula sobre tu plantilla para encontrar coordenadas.
    - Líneas claras cada 20 pt
    - Líneas marcadas y números cada 100 pt
    """
    # Cuadrícula fina
    c.setStrokeColorRGB(0.85, 0.85, 0.85)
    c.setLineWidth(0.2)
    step = 20
    for x in range(0, int(W) + 1, step):
        c.line(x, 0, x, H)
    for y in range(0, int(H) + 1, step):
        c.line(0, y, W, y)

    # Ejes marcados cada 100 pt
    c.setStrokeColorRGB(0.2, 0.2, 0.2)
    c.setFillColorRGB(0.2, 0.2, 0.2)
    c.setLineWidth(0.8)
    for x in range(0, int(W) + 1, 100):
        c.line(x, 0, x, H)
        c.drawString(x + 2, 5, str(x))
    for y in range(0, int(H) + 1, 100):
        c.line(0, y, W, y)
        c.drawString(5, y + 2, str(y))

    c.setFillColorRGB(0, 0, 0)
    c.drawString(16, H - 16, "Calibración de coordenadas (0,0 abajo-izquierda)")


# =========================
#  LÓGICA PRINCIPAL
# =========================
def generar_diploma_para_alumno(cursor, alumno_id: int, ciclo: str, fecha_emision: dt.date, curso_id: Optional[int] = None):
    """
    Genera el PDF de diploma para un alumno, crea QR/folio, calcula hash y guarda registro en DB.
    SOLO dibuja: Nombre, QR y Folio (todo lo demás queda tal cual en la plantilla).
    """
    # 1) Trae datos del alumno (ajusta los JOIN/columnas si tu base cambia)
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

    # Curso (opcional)
    curso_nombre = ""
    if curso_id:
        cursor.execute("SELECT nombre FROM curso WHERE curso_id=%s", (curso_id,))
        r = cursor.fetchone()
        if r:
            curso_nombre = r[0]

    # 2) Genera folio y URL de verificación
    folio = str(uuid.uuid4())
    url_verificacion = f"{BASE_URL_VERIFICACION}/verificar/{folio}"

    # 3) Prepara QR como ImageReader para reportlab
    qr_png = generar_qr_bytes(url_verificacion)
    qr_img = ImageReader(io.BytesIO(qr_png))

    # 4) Tamaño real de tu plantilla
    W, H = leer_tamano_pagina(PLANTILLA_PDF)

    # 5) Dibujo del overlay
    def draw(c):
        # (A) TAPA el nombre impreso en la plantilla para que no se vea dos veces.
        #     Ajusta x/y/w/h si ves restos de texto o si se tapa el subrayado.
        #     Sube o baja 2-6 pt y prueba otra vez.
        c.saveState()
        c.setFillColorRGB(1, 1, 1)      # blanco
        # x=110, y=302, w=620, h=34 -> pensado para tu captura de pantalla
        c.rect(110, 302, 620, 34, fill=1, stroke=0)
        c.restoreState()

        # (B) NOMBRE (centrado)
        c.setFont("Helvetica-Bold", POS.font_nombre)
        # TIP: si quieres centrar “siempre” sin pensar, usa W/2 en lugar de POS.nombre_xy[0]
        c.drawCentredString(POS.nombre_xy[0], POS.nombre_xy[1], alumno_nombre)

        # (C) QR (120x120 px aprox.)
        c.drawImage(qr_img, POS.qr_xy[0], POS.qr_xy[1], width=120, height=120, mask='auto')

        # (D) Folio (texto pequeño abajo-derecha)
        c.setFont("Helvetica", 8)
        c.drawRightString(W - 24, 18, f"Folio: {folio}")

        # NOTA: No volvemos a dibujar curso/fecha/coordinador para evitar duplicados,
        #       porque ya vienen impresos en la plantilla.

    overlay = crear_overlay((W, H), draw)

    # 6) Fusiona overlay + plantilla y guarda
    salida_path = os.path.join(SALIDA_PDFS, f"DIPLOMA_{alumno_id}_{folio}.pdf")
    fusionar_con_plantilla(overlay, PLANTILLA_PDF, salida_path)

    # 7) Calcula hash de integridad
    with open(salida_path, "rb") as f:
        pdf_bytes = f.read()
    sha = hashlib.sha256(pdf_bytes).hexdigest()

    # 8) Inserta registro
    cursor.execute("""
      INSERT INTO diploma (alumno_id, curso_id, folio, ciclo, fecha_emision, hash_sha256, estado, pdf_path)
      VALUES (%s,%s,%s,%s,%s,%s,'VALIDO',%s)
    """, (alumno_id, curso_id, folio, ciclo, fecha_emision, sha, salida_path))

    return folio, salida_path, sha


def main():
    parser = argparse.ArgumentParser(description="Generador de Diplomas (overlay sobre PDF de diseño)")
    parser.add_argument("--calibrar", action="store_true",
                        help="Genera un PDF con cuadrícula sobre TU plantilla para ubicar coordenadas")
    parser.add_argument("--curso_id", type=int, help="Generar para todos los alumnos de este curso (opcional)")
    parser.add_argument("--alumno_id", type=int, help="Generar solo para un alumno (opcional)")
    parser.add_argument("--ciclo", type=str, default="2024-2025", help="Ciclo escolar a imprimir")
    parser.add_argument("--fecha", type=str, default=dt.date.today().isoformat(), help="Fecha de emisión YYYY-MM-DD")
    args = parser.parse_args()

    # Tamaño real de tu plantilla (así sabemos el ancho/alto para la cuadrícula y el overlay)
    W, H = leer_tamano_pagina(PLANTILLA_PDF)

    if args.calibrar:
        # Crea un overlay con cuadrícula y fusiónalo con tu plantilla para ver coordenadas
        def draw_grid(c):
            dibujar_calibracion(c, W, H)
        overlay = crear_overlay((W, H), draw_grid)
        salida = os.path.join(SALIDA_PDFS, "calibracion.pdf")
        fusionar_con_plantilla(overlay, PLANTILLA_PDF, salida)
        print(f"[OK] Generado {salida}. Abre el PDF y ajusta POSICIONES si hace falta.")
        return

    fecha_emision = dt.date.fromisoformat(args.fecha)

    conn = conectar_db()
    conn.autocommit = False
    try:
        cur = conn.cursor()

        # Lógica para decidir la lista de alumnos
        if args.alumno_id:
            cur.execute("SELECT alumno_id FROM alumno WHERE alumno_id=%s", (args.alumno_id,))
            alumnos = [r[0] for r in cur.fetchall()]
        elif args.curso_id:
            cur.execute("SELECT alumno_id FROM inscripcion WHERE curso_id=%s", (args.curso_id,))
            alumnos = [r[0] for r in cur.fetchall()]
        else:
            # Todos (si tienes muchos, mejor usa --curso_id o --alumno_id)
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
