import mysql.connector
from dotenv import load_dotenv
import os
from datetime import datetime

# Cargar variables del archivo .env
load_dotenv()

conn = mysql.connector.connect(
    host=os.getenv("DB_HOST"),
    user=os.getenv("DB_USER"),
    password=os.getenv("DB_PASSWORD"),
    database=os.getenv("DB_NAME"),
    port=os.getenv("DB_PORT")
)
cur = conn.cursor()

print("🛠 Creando estructura de base de datos...")

schema_sql = """
CREATE TABLE IF NOT EXISTS escuela (
    escuela_id BIGINT AUTO_INCREMENT PRIMARY KEY,
    nombre VARCHAR(100) NOT NULL
);

CREATE TABLE IF NOT EXISTS grado (
    grado_id BIGINT AUTO_INCREMENT PRIMARY KEY,
    nombre VARCHAR(100) NOT NULL
);

CREATE TABLE IF NOT EXISTS profesor (
    profesor_id BIGINT AUTO_INCREMENT PRIMARY KEY,
    nombre VARCHAR(100) NOT NULL,
    correo VARCHAR(100)
);

CREATE TABLE IF NOT EXISTS curso (
    curso_id BIGINT AUTO_INCREMENT PRIMARY KEY,
    nombre VARCHAR(100) NOT NULL,
    profesor_id BIGINT,
    FOREIGN KEY (profesor_id) REFERENCES profesor(profesor_id)
);

CREATE TABLE IF NOT EXISTS alumno (
    alumno_id BIGINT AUTO_INCREMENT PRIMARY KEY,
    nombre VARCHAR(100) NOT NULL,
    curp VARCHAR(18) UNIQUE,
    escuela_id BIGINT,
    grado_id BIGINT,
    fecha_reg DATETIME,
    FOREIGN KEY (escuela_id) REFERENCES escuela(escuela_id),
    FOREIGN KEY (grado_id) REFERENCES grado(grado_id)
);

CREATE TABLE IF NOT EXISTS inscripcion (
    inscripcion_id BIGINT AUTO_INCREMENT PRIMARY KEY,
    alumno_id BIGINT,
    curso_id BIGINT,
    fecha DATETIME,
    FOREIGN KEY (alumno_id) REFERENCES alumno(alumno_id),
    FOREIGN KEY (curso_id) REFERENCES curso(curso_id)
);

CREATE TABLE IF NOT EXISTS diploma (
    diploma_id BIGINT AUTO_INCREMENT PRIMARY KEY,
    alumno_id BIGINT,
    curso_id BIGINT,
    coordinador_id BIGINT,
    folio VARCHAR(255),
    estado VARCHAR(20),
    fecha_emision DATE,
    pdf_path VARCHAR(255),
    hash_sha256 VARCHAR(255),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    pdf_url VARCHAR(255),
    FOREIGN KEY (alumno_id) REFERENCES alumno(alumno_id),
    FOREIGN KEY (curso_id) REFERENCES curso(curso_id)
);
"""

cur.execute("SET FOREIGN_KEY_CHECKS = 0;")
for result in cur.execute(schema_sql, multi=True):
    pass
cur.execute("SET FOREIGN_KEY_CHECKS = 1;")

print("✅ Tablas creadas correctamente.")

# ===============================================
# Insertar datos de ejemplo si están vacías
# ===============================================

def table_empty(table):
    cur.execute(f"SELECT COUNT(*) FROM {table}")
    return cur.fetchone()[0] == 0

if table_empty("escuela"):
    cur.execute("INSERT INTO escuela (nombre) VALUES ('Escuela de Sistemas UNITEC Toluca')")
    print("🏫 Escuela agregada.")

if table_empty("grado"):
    cur.execute("INSERT INTO grado (nombre) VALUES ('Ingeniería en Sistemas Computacionales')")
    print("🎓 Grado agregado.")

if table_empty("profesor"):
    cur.execute("INSERT INTO profesor (nombre, correo) VALUES ('Hortensia Depine Corral', 'hortensia@unitec.mx')")
    print("👩‍🏫 Profesor agregado.")

if table_empty("curso"):
    cur.execute("INSERT INTO curso (nombre, profesor_id) VALUES ('Análisis de Sistemas de Información', 1)")
    print("📘 Curso agregado.")

if table_empty("alumno"):
    alumnos = [
        ("Kevin Santillán", "SASK010203HDFRNV09", 1, 1, datetime(2025, 10, 3, 13, 25)),
        ("Ana Torres", "TOAA040506MDFLRS08", 1, 1, datetime(2025, 10, 2, 13, 40)),
        ("Juan Pérez", "PEPJ010203HDFRNV09", 1, 1, datetime(2025, 10, 3, 13, 10))
    ]
    cur.executemany("""
        INSERT INTO alumno (nombre, curp, escuela_id, grado_id, fecha_reg)
        VALUES (%s, %s, %s, %s, %s)
    """, alumnos)
    print("👨‍🎓 Alumnos de ejemplo agregados.")

if table_empty("inscripcion"):
    cur.execute("INSERT INTO inscripcion (alumno_id, curso_id, fecha) VALUES (1, 1, NOW())")
    cur.execute("INSERT INTO inscripcion (alumno_id, curso_id, fecha) VALUES (2, 1, NOW())")
    cur.execute("INSERT INTO inscripcion (alumno_id, curso_id, fecha) VALUES (3, 1, NOW())")
    print("📝 Inscripciones agregadas.")

if table_empty("diploma"):
    cur.execute("""
        INSERT INTO diploma (alumno_id, curso_id, coordinador_id, folio, estado, fecha_emision, pdf_path, hash_sha256)
        VALUES (1, 1, 1, 'FOLIO-TEST-001', 'VALIDO', CURDATE(), 'out/DIPLOMA_1.pdf', 'abc123hashdemo')
    """)
    print("📜 Diploma de ejemplo agregado.")

conn.commit()
conn.close()

print("\n🎉 Base de datos inicializada correctamente en Clever Cloud.")
