# api_verificacion.py - VERSIÓN CON CARGA DE CSV Y GENERACIÓN WEB
import os
import mysql.connector
import csv
import io
from fastapi import FastAPI, Request, Query, HTTPException, Form, UploadFile, File, BackgroundTasks
from fastapi.responses import HTMLResponse, PlainTextResponse, FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

# Importamos la lógica de generación de diplomas como un módulo
import generar_diplomas as gen

# ✅ CARGAR VARIABLES DE ENTORNO DESDE .env
load_dotenv()

# =============================
# CONFIGURACIÓN PRINCIPAL
# =============================

app = FastAPI(title="Diplomas Proyecto", version="2.0.0")

templates = Jinja2Templates(directory="templates")

# Variables de entorno
DB_HOST = os.getenv("DB_HOST")
DB_PORT = int(os.getenv("DB_PORT", "3306")) if os.getenv("DB_PORT") else 3306
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_NAME = os.getenv("DB_NAME")

ADMIN_TOKEN = os.getenv("ADMIN_TOKEN")
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")

# =============================
# FUNCIONES AUXILIARES
# =============================

def get_db_connection():
    try:
        return mysql.connector.connect(
            host=DB_HOST, port=DB_PORT, user=DB_USER,
            password=DB_PASSWORD, database=DB_NAME
        )
    except mysql.connector.Error as e:
        print(f"❌ Error de conexión MySQL: {e}")
        return None

def check_admin(token: str):
    if token != ADMIN_TOKEN:
        raise PermissionError("Token inválido o no autorizado.")

# =============================
# ENDPOINTS DEL PORTAL 
# =============================

@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse("index.html", {
        "request": request, "title": "Portal Escolar · Acceso Alumnos", "now": datetime.now().year
    })

@app.get("/ingresar", response_class=HTMLResponse)
def ingresar(request: Request, curp: str = Query(None)):
    if not curp:
        return templates.TemplateResponse("portal.html", {"request": request, "title": "Portal de Alumnos", "now": datetime.now().year})
    conn = get_db_connection()
    if not conn:
        return templates.TemplateResponse("mensaje.html", {"request": request, "titulo": "Error de conexión", "mensaje": "No se pudo conectar a la base de datos.", "color": "var(--bad)"})
    try:
        cur = conn.cursor(dictionary=True)
        query = "SELECT IFNULL(c.nombre, '—') AS curso, d.folio, d.estado, d.fecha_emision, d.pdf_url FROM diploma d JOIN alumno a ON d.alumno_id = a.alumno_id LEFT JOIN curso c ON d.curso_id = c.curso_id WHERE a.curp = %s ORDER BY d.fecha_emision DESC"
        cur.execute(query, (curp,))
        diplomas = cur.fetchall()
        for d in diplomas:
            if not (d.get("pdf_url") and d["pdf_url"].startswith("http")):
                d["pdf_url"] = None
        return templates.TemplateResponse("portal.html", {"request": request, "curp": curp, "diplomas": diplomas, "title": "Portal de Alumnos", "now": datetime.now().year})
    finally:
        if conn and conn.is_connected(): conn.close()


@app.get("/verificar/{folio}", response_class=HTMLResponse)
def verificar(request: Request, folio: str):
    conn = get_db_connection()
    if not conn:
        return templates.TemplateResponse("mensaje.html", {"request": request, "titulo": "Error de conexión", "mensaje": "No se pudo conectar a la base de datos.", "color": "var(--bad)"})
    try:
        cur = conn.cursor(dictionary=True)
        query = "SELECT d.*, a.nombre AS alumno, a.curp, e.nombre AS escuela, IFNULL(c.nombre, '—') AS curso FROM diploma d JOIN alumno a ON d.alumno_id = a.alumno_id LEFT JOIN curso c ON d.curso_id = c.curso_id LEFT JOIN escuela e ON a.escuela_id = e.escuela_id WHERE d.folio = %s"
        cur.execute(query, (folio,))
        diploma = cur.fetchone()
        if not diploma:
            return templates.TemplateResponse("mensaje.html", {"request": request, "titulo": "No encontrado", "mensaje": f"El folio <code>{folio}</code> no existe.", "color": "var(--bad)"})
        diploma["download_url"] = diploma["pdf_url"] if diploma.get("pdf_url", "").startswith("http") else None
        return templates.TemplateResponse("verificacion.html", {"request": request, "diploma": diploma, "title": f"Verificación - {diploma['alumno']}"})
    finally:
        if conn and conn.is_connected(): conn.close()

# =============================
# SISTEMA DE ACCESO ADMIN
# =============================

@app.get("/admin-login", response_class=HTMLResponse)
def admin_login(request: Request, error: str = None):
    return templates.TemplateResponse("admin-login.html", {"request": request, "error": error, "title": "Acceso Administrativo"})

@app.post("/admin-auth")
def admin_auth(username: str = Form(...), password: str = Form(...)):
    if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
        return RedirectResponse(url=f"/admin-panel?token={ADMIN_TOKEN}", status_code=302)
    else:
        return RedirectResponse(url="/admin-login?error=Credenciales+incorrectas", status_code=302)

@app.get("/admin-panel", response_class=HTMLResponse)
def admin_panel(request: Request, token: str = Query(...)):
    try:
        check_admin(token)
        conn = get_db_connection()
        stats = {}
        if conn:
            try:
                cur = conn.cursor(dictionary=True)
                cur.execute("SELECT COUNT(*) as total FROM alumno")
                stats['total_alumnos'] = cur.fetchone()['total']
                cur.execute("SELECT COUNT(*) as total FROM diploma")
                stats['total_diplomas'] = cur.fetchone()['total']
                cur.execute("SELECT COUNT(*) as total FROM curso")
                stats['total_cursos'] = cur.fetchone()['total']
                stats['sistema_estado'] = "✅"
            finally:
                if conn.is_connected(): conn.close()
        else:
            stats['sistema_estado'] = "❌"
        return templates.TemplateResponse("admin-panel.html", {"request": request, "token": token, **stats, "admin_username": ADMIN_USERNAME, "now": datetime.now().year})
    except PermissionError:
        return RedirectResponse(url="/admin-login?error=Acceso+no+autorizado", status_code=302)

@app.get("/admin-logout")
def admin_logout():
    return RedirectResponse(url="/", status_code=302)


# =======================================================
# NUEVOS ENDPOINTS PARA CARGA DE CSV Y GENERACIÓN WEB
# =======================================================

@app.post("/admin/upload-alumnos", response_class=HTMLResponse)
async def upload_alumnos_csv(request: Request, token: str = Query(...), file: UploadFile = File(...)):
    try:
        check_admin(token)
    except PermissionError:
        return RedirectResponse(url="/admin-login?error=Token+inválido", status_code=302)

    if not file.filename.endswith('.csv'):
        return templates.TemplateResponse("mensaje.html", {"request": request, "titulo": "Error de Archivo", "mensaje": "El archivo debe ser de tipo CSV."})

    content = await file.read()
    stream = io.StringIO(content.decode("utf-8"))
    reader = csv.DictReader(stream)

    alumnos_nuevos = 0
    alumnos_actualizados = 0
    errores = []

    conn = get_db_connection()
    try:
        cur = conn.cursor(dictionary=True)
        for i, row in enumerate(reader):
            try:
                # El CSV debe tener: nombre, curp, escuela_id, grado_id, profesor_id
                cur.execute("SELECT alumno_id FROM alumno WHERE curp = %s", (row['curp'],))
                existe = cur.fetchone()
                if existe:
                    cur.execute("UPDATE alumno SET nombre=%s, escuela_id=%s, grado_id=%s, profesor_id=%s WHERE curp=%s",
                                (row['nombre'], row['escuela_id'], row['grado_id'], row['profesor_id'], row['curp']))
                    alumnos_actualizados += 1
                else:
                    cur.execute("INSERT INTO alumno (nombre, curp, escuela_id, grado_id, profesor_id, fecha_reg) VALUES (%s, %s, %s, %s, %s, NOW())",
                                (row['nombre'], row['curp'], row['escuela_id'], row['grado_id'], row['profesor_id']))
                    alumnos_nuevos += 1
            except Exception as e:
                errores.append(f"Error en fila {i+2}: {e}")
        conn.commit()
    finally:
        if conn and conn.is_connected(): conn.close()

    mensaje = f"Carga completada.<br>Alumnos nuevos: {alumnos_nuevos}<br>Alumnos actualizados: {alumnos_actualizados}"
    if errores:
        mensaje += "<br><br><strong>Errores:</strong><br>" + "<br>".join(errores)

    return templates.TemplateResponse("mensaje.html", {"request": request, "titulo": "Resultado de Carga", "mensaje": mensaje})


def task_generar_diplomas_wrapper(curso_id: int):
    """ Función que envuelve la lógica de generación para ser llamada en segundo plano. """
    print(f"INICIANDO TAREA: Generación de diplomas para el curso {curso_id}")
    try:
        gen.generar_diplomas_para_curso(curso_id)
        print(f"TAREA COMPLETADA: Diplomas para el curso {curso_id} generados.")
    except Exception as e:
        print(f"TAREA FALLIDA: Error al generar diplomas para el curso {curso_id}: {e}")

# ===================== INICIA CORRECCIÓN =====================
@app.post("/admin/generar-diplomas-action", response_class=HTMLResponse)
async def generar_diplomas_action(request: Request, background_tasks: BackgroundTasks, token: str = Query(...), curso_id: int = Form(...)):
# ===================== TERMINA CORRECCIÓN ====================
    """ Inicia la generación de diplomas para un curso en segundo plano. """
    try:
        check_admin(token)
    except PermissionError:
        return RedirectResponse(url="/admin-login?error=Token+inválido", status_code=302)

    background_tasks.add_task(task_generar_diplomas_wrapper, curso_id)

    mensaje = f"La generación de diplomas para el curso <strong>{curso_id}</strong> ha comenzado en segundo plano.<br>El proceso puede tardar varios minutos. Revisa los logs de Render para ver el progreso."
    return templates.TemplateResponse("mensaje.html", {"request": request, "titulo": "Proceso Iniciado", "mensaje": mensaje})


# =============================
# OTROS ENDPOINTS Y SERVICIO DE ARCHIVOS
# =============================
@app.get("/healthz", response_class=PlainTextResponse)
def healthz():
    return "OK"

@app.get("/static/{file_path:path}")
async def serve_static(file_path: str):
    static_file = Path("static") / file_path
    if static_file.exists(): return FileResponse(static_file)
    raise HTTPException(status_code=404)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)