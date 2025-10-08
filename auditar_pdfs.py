# auditar_pdfs.py
import os, hashlib
from pathlib import Path
import mysql.connector as mysql
from dotenv import load_dotenv

load_dotenv()
DB_HOST = os.getenv("DB_HOST", "127.0.0.1")
DB_PORT = int(os.getenv("DB_PORT", "3306"))
DB_USER = os.getenv("DB_USER", "root")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")
DB_NAME = os.getenv("DB_NAME", "escuela_compu")
SALIDA_PDFS = os.getenv("SALIDA_PDFS", "out")

try:
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas
    HAVE_REPORTLAB = True
except Exception:
    HAVE_REPORTLAB = False

def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1<<20), b""):
            h.update(chunk)
    return h.hexdigest()

def crear_placeholder(path: Path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    if HAVE_REPORTLAB:
        c = canvas.Canvas(str(path), pagesize=letter)
        c.setFont("Helvetica-Bold", 18)
        c.drawCentredString(300, 700, "DIPLOMA (placeholder)")
        c.setFont("Helvetica", 11)
        c.drawString(72, 660, text)
        c.save()
    else:
        # PDF minimalista si no está reportlab (un PDF válido muy simple)
        path.write_bytes(b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n2 0 obj<</Type/Pages/Count 1/Kids[3 0 R]>>endobj\n3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]/Contents 4 0 R>>endobj\n4 0 obj<</Length 0>>stream\nendstream\nendobj\nxref\n0 5\n0000000000 65535 f \n0000000010 00000 n \n0000000062 00000 n \n0000000126 00000 n \n0000000220 00000 n \ntrailer<</Size 5/Root 1 0 R>>\nstartxref\n316\n%%EOF")

def main():
    print("Auditoría de PDFs vs BD…")
    conn = mysql.connect(
        host=DB_HOST, port=DB_PORT, user=DB_USER,
        password=DB_PASSWORD, database=DB_NAME
    )
    cur = conn.cursor(dictionary=True)
    cur.execute("""
        SELECT diploma_id, alumno_id, curso_id, folio,
               pdf_path, hash_sha256, fecha_emision
        FROM diploma
        ORDER BY diploma_id
    """)
    rows = cur.fetchall()
    outdir = Path(SALIDA_PDFS)
    outdir.mkdir(parents=True, exist_ok=True)

    faltantes = 0
    reparados = 0

    for r in rows:
        diploma_id = r["diploma_id"]
        pdf_path = Path(r["pdf_path"] or "")
        if not pdf_path.name:
            # reconstruir nombre estándar
            pdf_path = outdir / f"DIPLOMA_{r['alumno_id']}_{r['folio']}.pdf"

        # Si está fuera de out/, llevarlo a out/
        if pdf_path.parent.name != outdir.name:
            pdf_path = outdir / pdf_path.name

        if not pdf_path.exists():
            faltantes += 1
            print(f" - [FALTA] diploma_id={diploma_id} => {pdf_path.name}")
            crear_placeholder(pdf_path, f"diploma_id={diploma_id} folio={r['folio']}")

        # recalcular hash si falta o viene en ceros
        new_hash = sha256_of(pdf_path)
        if (r["hash_sha256"] or "").strip("0") != new_hash:
            cur.execute(
                "UPDATE diploma SET pdf_path=%s, hash_sha256=%s WHERE diploma_id=%s",
                (str(pdf_path).replace("\\","/"), new_hash, diploma_id)
            )
            reparados += 1

    if reparados:
        conn.commit()
    cur.close(); conn.close()
    print(f"Listo. Faltantes creados: {faltantes} | Registros actualizados: {reparados}")
    print(f"Prueba ahora: http://localhost:8000/pdfs/  (o un PDF concreto)")

if __name__ == "__main__":
    main()
