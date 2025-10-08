# auto_diplomas.py
import os, uuid, hashlib
from io import BytesIO
from pathlib import Path
from datetime import date

from dotenv import load_dotenv
import mysql.connector as mysql
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from PyPDF2 import PdfReader, PdfWriter, PageObject

load_dotenv()

DB_HOST = os.getenv("DB_HOST", "127.0.0.1")
DB_PORT = int(os.getenv("DB_PORT", "3306"))
DB_USER = os.getenv("DB_USER", "root")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")
DB_NAME = os.getenv("DB_NAME", "escuela_compu")

PLANTILLA_PDF = os.getenv("PLANTILLA_PDF", "RECONOCIMIENTOv2.pdf")
SALIDA_PDFS = os.getenv("SALIDA_PDFS", "out")
Path(SALIDA_PDFS).mkdir(parents=True, exist_ok=True)

def conectar_db():
    return mysql.connect(
        host=DB_HOST, port=DB_PORT, user=DB_USER,
        password=DB_PASSWORD, database=DB_NAME
    )

def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

# ===== Overlay: solo nombre + fecha + folio (no pisa el diseño) =====
NAME_Y  = 420
FECHA_Y = 140
FOLIO_Y = 120

def draw_overlay(datos: dict) -> BytesIO:
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    w, h = letter
    c.setFont("Helvetica-Bold", 42)
    c.drawCentredString(w/2, NAME_Y, datos.get("alumno","-"))
    c.setFont("Helvetica", 12)
    c.drawString(70, FECHA_Y, f"Fecha de emisión: {datos.get('fecha_emision')}")
    c.drawString(70, FOLIO_Y, f"Folio: {datos.get('folio')}")
    c.save()
    buf.seek(0)
    return buf

def merge_with_template(overlay_buf: BytesIO, out_path: Path):
    base = PdfReader(open(PLANTILLA_PDF, "rb")).pages[0]
    ov   = PdfReader(overlay_buf).pages[0]
    writer = PdfWriter()
    page = PageObject.create_blank_page(width=base.mediabox.width, height=base.mediabox.height)
    page.merge_page(base)
    page.merge_page(ov)
    writer.add_page(page)
    with open(out_path, "wb") as f:
        writer.write(f)

def generar_diplomas_automatica():
    conn = conectar_db()
    cur  = conn.cursor(dictionary=True)

    # >>> SIN GROUP BY, compatible con ONLY_FULL_GROUP_BY <<<
    cur.execute("""
        SELECT a.alumno_id, a.nombre AS alumno, a.curp,
               IFNULL(g.nombre,'-') AS grado,
               e.nombre AS escuela,
               (
                 SELECT cu2.curso_id
                 FROM inscripcion i2
                 JOIN curso cu2 ON cu2.curso_id = i2.curso_id
                 WHERE i2.alumno_id = a.alumno_id
                 ORDER BY cu2.curso_id ASC
                 LIMIT 1
               ) AS curso_id,
               (
                 SELECT cu3.nombre
                 FROM inscripcion i3
                 JOIN curso cu3 ON cu3.curso_id = i3.curso_id
                 WHERE i3.alumno_id = a.alumno_id
                 ORDER BY cu3.curso_id ASC
                 LIMIT 1
               ) AS curso,
               (
                 SELECT co.coordinador_id
                 FROM coordinador co
                 WHERE co.escuela_id = e.escuela_id
                 ORDER BY co.coordinador_id ASC
                 LIMIT 1
               ) AS coordinador_id
        FROM alumno a
        JOIN escuela e ON e.escuela_id = a.escuela_id
        LEFT JOIN grado g ON g.grado_id = a.grado_id
        WHERE NOT EXISTS (
            SELECT 1 FROM diploma d WHERE d.alumno_id = a.alumno_id
        )
    """)
    alumnos = cur.fetchall() or []
    print(f"🔍 Alumnos sin diploma: {len(alumnos)}")

    for a in alumnos:
        folio = str(uuid.uuid4())
        fecha = date.today().isoformat()
        pdf_name = f"DIPLOMA_{a['alumno_id']}_{folio}.pdf"
        pdf_path = Path(SALIDA_PDFS) / pdf_name

        overlay = draw_overlay({"alumno": a["alumno"], "fecha_emision": fecha, "folio": folio})
        merge_with_template(overlay, pdf_path)
        h = sha256_file(pdf_path)

        cur.execute("""
            INSERT INTO diploma
              (alumno_id, curso_id, coordinador_id, folio, estado,
               fecha_emision, pdf_path, hash_sha256)
            VALUES (%s, %s, %s, %s, 'VALIDO', %s, %s, %s)
        """, (
            a["alumno_id"], a["curso_id"], a["coordinador_id"],
            folio, fecha, pdf_path.as_posix(), h
        ))
        conn.commit()
        print(f"✅ Generado: {a['alumno']} -> {pdf_path.name}")

    cur.close(); conn.close()
    if not alumnos:
        print("✅ No hay nada que generar.")
    else:
        print("🎉 Listo.")

if __name__ == "__main__":
    print("🚀 Generando diplomas pendientes con plantilla…")
    generar_diplomas_automatica()
