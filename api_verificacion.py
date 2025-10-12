# -*- coding: utf-8 -*-
"""
Portal Escolar · Verificación de Diplomas
Versión corregida para Render y Clever Cloud (MySQL + Supabase)
"""

import os
import mysql.connector
from mysql.connector import Error
from fastapi import FastAPI, Request, Query, HTTPException, File, UploadFile
from fastapi.responses import HTMLResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime
from dotenv import load_dotenv
import importlib

# ============================
# Configuración base
# ============================
load_dotenv()

APP_NAME = "Portal Escolar · Diplomas"
BASE_DIR = os.path.dirname(__file__)
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")
STATIC_DIR = os.path.join(BASE_DIR, "static")
PDF_DIR = os.getenv("SALIDA_PDFS", os.path.join(BASE_DIR, "out"))

# Crear aplicación
app = FastAPI(title=APP_NAME)

# Middleware CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Montar carpetas
app.mount("/static", StaticFiles(directory=STATIC_DIR, check_dir=False), name="static")
app.mount("/pdfs", StaticFiles(directory=PDF_DIR, check_dir=False, html=True), name="pdfs")

templates = Jinja2Templates(directory=TEMPLATES_DIR)

# ============================
# Conexión a MySQL (Clever Cloud)
# ============================
def get_db_connection():
    try:
        conn = mysql.connector.connect(
            host=os.getenv("MYSQL_ADDON_HOST") or os.getenv("DB_HOST"),
            user=os.getenv("MYSQL_ADDON_USER") or os.getenv("DB_USER"),
            password=os.getenv("MYSQL_ADDON_PASSWORD") or os.getenv("DB_PASSWORD"),
            database=os.getenv("MYSQL_ADDON_DB") or os.getenv("DB_NAME"),
            port=int(os.getenv("MYSQL_ADDON_PORT") or os.getenv("DB_PORT", 3306))
        )
        return conn
    except Error as e:
        print(f"⚠️ Error de conexión MySQL: {e}")
        raise

# ============================
# Endpoints base
# ============================
@app.get("/healthz", response_class=PlainTextResponse)
def healthz():
    return "ok"

@app.get("/db_test", response_class=PlainTextResponse)
def db_test():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT NOW()")
        now = cursor.fetchone()[0]
        conn.close()
        return f"✅ Conectado correctamente a MySQL.\nFecha servidor: {now}"
    except Exception as e:
        return f"⚠️ Error MySQL: {e}"

# ============================
# Portal principal
# ============================
@app.get("/", response_class=HTMLResponse)
def home(request: Request, token: str | None = Query(None)):
    ctx = {
        "request": request,
        "token": token if token == os.getenv("ADMIN_TOKEN") else None,
        "now": datetime.now().year,
        "title": "Portal Escolar · Verificación de Diplomas"
    }
    return templates.TemplateResponse("index.html", ctx)

# ============================
# Verificar diploma por folio
# ============================
@app.get("/verificar", response_class=HTMLResponse)
def verificar(request: Request, folio: str | None = Query(None)):
    if not folio:
        return templates.TemplateResponse("mensaje.html", {
            "request": request,
            "titulo": "Verificación de diploma",
            "mensaje": "Debes ingresar un número de folio.",
            "color": "var(--bad)"
        })
    try:
        conn = get_db_connection()
        cur = conn.cursor(dictionary=True)
        cur.execute("""
            SELECT d.folio, d.estado, d.fecha_emision, d.pdf_url, 
                   a.nombre AS alumno, c.nombre AS curso
            FROM diploma d
            JOIN alumno a ON d.alumno_id = a.alumno_id
            JOIN curso c ON d.curso_id = c.curso_id
            WHERE d.folio = %s
        """, (folio,))
        row = cur.fetchone()
        conn.close()

        if not row:
            return templates.TemplateResponse("mensaje.html", {
                "request": request,
                "titulo": "Folio no encontrado",
                "mensaje": f"No se encontró el diploma con folio: {folio}",
                "color": "var(--bad)"
            })

        return templates.TemplateResponse("mensaje.html", {
            "request": request,
            "titulo": "Diploma encontrado",
            "mensaje": f"Diploma válido para {row['alumno']} ({row['curso']})",
            "color": "var(--ok)",
            "diplomas": [row]
        })
    except Exception as e:
        return templates.TemplateResponse("mensaje.html", {
            "request": request,
            "titulo": "Error en la verificación",
            "mensaje": str(e),
            "color": "var(--bad)"
        })

# ============================
# Portal de alumnos
# ============================
@app.get("/ingresar", response_class=HTMLResponse)
def ingresar(request: Request, curp: str | None = Query(None)):
    diplomas = []
    if curp:
        try:
            conn = get_db_connection()
            cur = conn.cursor(dictionary=True)
            cur.execute("""
                SELECT d.folio, d.estado, d.fecha_emision, d.pdf_url, c.nombre AS curso
                FROM diploma d
                JOIN alumno a ON d.alumno_id = a.alumno_id
                JOIN curso c ON d.curso_id = c.curso_id
                WHERE a.curp = %s
            """, (curp,))
            diplomas = cur.fetchall()
            conn.close()
        except Exception as e:
            return templates.TemplateResponse("mensaje.html", {
                "request": request,
                "titulo": "Error",
                "mensaje": str(e),
                "color": "var(--bad)"
            })
    return templates.TemplateResponse("portal.html", {
        "request": request,
        "curp": curp,
        "diplomas": diplomas,
        "now": datetime.now().year
    })

# ============================
# Admin endpoints
# ============================
def check_admin(token: str):
    if token != os.getenv("ADMIN_TOKEN"):
        raise HTTPException(status_code=401, detail="No autorizado")

@app.get("/admin/sync", response_class=HTMLResponse)
def admin_sync(request: Request, token: str = Query(...)):
    check_admin(token)
    try:
        conn = get_db_connection()
        cur = conn.cursor(dictionary=True)
        cur.execute("""
            SELECT a.nombre AS alumno, d.folio, d.pdf_url
            FROM diploma d
            JOIN alumno a ON d.alumno_id = a.alumno_id
            WHERE d.pdf_url IS NOT NULL
        """)
        diplomas = cur.fetchall()
        conn.close()
        return templates.TemplateResponse("mensaje.html", {
            "request": request,
            "titulo": "Sincronización completada",
            "mensaje": f"{len(diplomas)} diplomas verificados.",
            "color": "var(--ok)",
            "diplomas": diplomas
        })
    except Exception as e:
        return templates.TemplateResponse("mensaje.html", {
            "request": request,
            "titulo": "Error en sincronización",
            "mensaje": str(e),
            "color": "var(--bad)"
        })

@app.get("/admin/generar", response_class=HTMLResponse)
def admin_generar(request: Request, token: str = Query(...)):
    check_admin(token)
    try:
        mod = importlib.import_module("auto_diplomas")
        if hasattr(mod, "generar_diplomas_automatica"):
            mod.generar_diplomas_automatica()
        msg = "Diplomas generados correctamente."
        color = "var(--ok)"
    except Exception as e:
        msg = f"Error al generar: {e}"
        color = "var(--bad)"
    return templates.TemplateResponse("mensaje.html", {
        "request": request,
        "titulo": "Generación de diplomas",
        "mensaje": msg,
        "color": color
    })
