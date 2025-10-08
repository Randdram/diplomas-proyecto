# rebuild_pdfs.py
import os, hashlib
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

NAME_Y  = 420
FECHA_Y = 140
FOLIO_Y = 120

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

def overlay_simple(datos) -> BytesIO:
    buf = BytesIO()
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

def merge(ov: BytesIO, out_path: Path):
    base = PdfReader(open(PLANTILLA_PDF, "rb")).pages[0]
    ovp  = PdfReader(ov).pages[0]
    writer = PdfWriter()
    pg = PageObject.create_blank_page(width=base.mediabox.width, height=base.mediabox.height)
    pg.merge_page(base); pg.merge_page(ovp)
    writer.add_page(pg)
    with open(out_path, "wb") as f:
        writer.write(f)

def rebuild_all():
    conn = conectar_db()
    cur = conn.cursor(dictionary=True)
    cur.execute("""
        SELECT d.diploma_id, d.folio, d.fecha_emision, d.pdf_path,
               a.nombre AS alumno
        FROM diploma d
        JOIN alumno a ON a.alumno_id = d.alumno_id
        ORDER BY d.diploma_id
    """)
    rows = cur.fetchall() or []
    print(f"Encontrados {len(rows)} diplomas para regenerar…")

    for r in rows:
        pdf_name = f"DIPLOMA_{r['diploma_id']}_{r['folio']}.pdf"
        out_path = Path(SALIDA_PDFS) / pdf_name
        fecha = r["fecha_emision"].isoformat() if r["fecha_emision"] else date.today().isoformat()
        ov = overlay_simple({"alumno": r["alumno"], "fecha_emision": fecha, "folio": r["folio"]})
        merge(ov, out_path)
        h = sha256_file(out_path)

        cur.execute("UPDATE diploma SET pdf_path=%s, hash_sha256=%s WHERE diploma_id=%s",
                    (out_path.as_posix(), h, r["diploma_id"]))
        conn.commit()
        print(f"✔ {r['diploma_id']} -> {out_path.name}")

    cur.close(); conn.close()
    print("🎉 Regeneración completada.")

if __name__ == "__main__":
    rebuild_all()
