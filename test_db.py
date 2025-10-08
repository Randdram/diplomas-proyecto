# test_db.py
import os
import mysql.connector as mysql
from dotenv import load_dotenv

load_dotenv()
DB_HOST = os.getenv("DB_HOST", "127.0.0.1")
DB_PORT = int(os.getenv("DB_PORT", "3306"))
DB_USER = os.getenv("DB_USER", "root")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")
DB_NAME = os.getenv("DB_NAME", "escuela_compu")

print("Conectando a MySQL con:", DB_HOST, DB_PORT, DB_USER, DB_NAME)
conn = mysql.connect(
    host=DB_HOST, port=DB_PORT, user=DB_USER,
    password=DB_PASSWORD, database=DB_NAME
)
cur = conn.cursor(dictionary=True)

# 1) Ping rápido
cur.execute("SELECT DATABASE() AS db, VERSION() AS version")
print("OK >", cur.fetchone())

# 2) ¿Cuántas filas hay en cada tabla clave?
for t in ["escuela", "grado", "profesor", "curso", "alumno", "inscripcion", "diploma"]:
    try:
        cur.execute(f"SELECT COUNT(*) AS n FROM {t}")
        n = cur.fetchone()["n"]
        print(f"Filas en {t}: {n}")
    except Exception as e:
        print(f"(Aviso) No pude consultar {t}: {e}")

# 3) Alumno + diplomas (muestra uno si existe)
cur.execute("""
    SELECT a.alumno_id, a.nombre, a.curp,
           d.folio, d.pdf_path, d.hash_sha256, d.fecha_emision
    FROM alumno a
    LEFT JOIN diploma d ON d.alumno_id = a.alumno_id
    ORDER BY a.alumno_id, d.fecha_emision DESC
    LIMIT 5
""")
rows = cur.fetchall()
print("Muestra alumno/diploma:")
for r in rows:
    print("  -", r)

cur.close()
conn.close()
print("Conexión y consultas: OK")
