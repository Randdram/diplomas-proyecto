# api_verificacion.py - VERSIÓN FINAL CORREGIDA
import os
import mysql.connector
from fastapi import FastAPI, Request, Query, HTTPException, Form
from fastapi.responses import HTMLResponse, PlainTextResponse, FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv
from supabase import create_client

# ✅ CARGAR VARIABLES DE ENTORNO DESDE .env
load_dotenv()

# =============================
# CONFIGURACIÓN PRINCIPAL
# =============================

app = FastAPI(title="Diplomas Proyecto", version="1.0.0")

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

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY")
SUPABASE_BUCKET = os.getenv("SUPABASE_BUCKET", "diplomas")
SUPABASE_PUBLIC_BASE = os.getenv("SUPABASE_PUBLIC_BASE")

BASE_URL_VERIFICACION = os.getenv("BASE_URL_VERIFICACION", "http://localhost:8000")
EN_PRODUCCION = os.getenv("RENDER", False) or "render.com" in os.getenv("BASE_URL_VERIFICACION", "")

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
        "request": request,
        "title": "Portal Escolar · Acceso Alumnos", 
        "now": datetime.now().year
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
        query = """
            SELECT IFNULL(c.nombre, '—') AS curso, d.folio, d.estado, d.fecha_emision, d.pdf_url, d.pdf_path
            FROM diploma d JOIN alumno a ON d.alumno_id = a.alumno_id
            LEFT JOIN curso c ON d.curso_id = c.curso_id
            WHERE a.curp = %s ORDER BY d.fecha_emision DESC
        """
        cur.execute(query, (curp,))
        diplomas = cur.fetchall()
        
        for d in diplomas:
            if not (d.get("pdf_url") and d["pdf_url"].startswith("http")):
                d["pdf_url"] = None
        
        return templates.TemplateResponse("portal.html", {"request": request, "curp": curp, "diplomas": diplomas, "title": "Portal de Alumnos", "now": datetime.now().year})
    except Exception as e:
        return templates.TemplateResponse("mensaje.html", {"request": request, "titulo": "Error", "mensaje": f"Ocurrió un error: {e}", "color": "var(--bad)"})
    finally:
        if conn and conn.is_connected():
            conn.close()

@app.get("/verificar/{folio}", response_class=HTMLResponse)
def verificar(request: Request, folio: str):
    conn = get_db_connection()
    if not conn:
        return templates.TemplateResponse("mensaje.html", {"request": request, "titulo": "Error de conexión", "mensaje": "No se pudo conectar a la base de datos.", "color": "var(--bad)"})

    try:
        cur = conn.cursor(dictionary=True)
        query = """
            SELECT d.*, a.nombre AS alumno, a.curp, e.nombre AS escuela, IFNULL(c.nombre, '—') AS curso
            FROM diploma d JOIN alumno a ON d.alumno_id = a.alumno_id
            JOIN escuela e ON e.escuela_id = a.escuela_id
            LEFT JOIN curso c ON c.curso_id = d.curso_id
            WHERE d.folio = %s
        """
        cur.execute(query, (folio,))
        diploma = cur.fetchone()
        
        if not diploma:
            return templates.TemplateResponse("mensaje.html", {"request": request, "titulo": "No encontrado", "mensaje": f"El folio <code>{folio}</code> no existe.", "color": "var(--bad)"})

        diploma["download_url"] = diploma["pdf_url"] if diploma.get("pdf_url", "").startswith("http") else None
        
        return templates.TemplateResponse("verificacion.html", {"request": request, "diploma": diploma, "title": f"Verificación - {diploma['alumno']}"})
    except Exception as e:
        return templates.TemplateResponse("mensaje.html", {"request": request, "titulo": "Error", "mensaje": str(e), "color": "var(--bad)"})
    finally:
        if conn and conn.is_connected():
            conn.close()

@app.get("/api/estado/{folio}")
def api_estado(folio: str):
    """API JSON para verificar estado de un diploma."""
    conn = get_db_connection()
    if not conn:
        return {"error": "Conexión a BD fallida"}

    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("""
            SELECT d.folio, d.estado, d.fecha_emision, d.hash_sha256, a.nombre AS alumno, e.nombre AS escuela, IFNULL(c.nombre, '—') AS curso
            FROM diploma d JOIN alumno a ON d.alumno_id = a.alumno_id
            JOIN escuela e ON e.escuela_id = a.escuela_id
            LEFT JOIN curso c ON c.curso_id = d.curso_id WHERE d.folio = %s
        """, (folio,))
        diploma = cur.fetchone()
        if not diploma: return {"detail": "Not found"}
        return diploma
    finally:
        if conn and conn.is_connected():
            conn.close()

@app.get("/db_test", response_class=PlainTextResponse)
def db_test():
    """Prueba de conexión a MySQL."""
    try:
        conn = get_db_connection()
        if not conn: return "❌ No se pudo establecer conexión"
        cur = conn.cursor()
        cur.execute("SELECT NOW()")
        fecha = cur.fetchone()[0]
        return f"✅ Conectado correctamente a MySQL.\nFecha servidor: {fecha}"
    except Exception as e:
        return f"❌ Error de conexión: {e}"
    finally:
        if 'conn' in locals() and conn.is_connected():
            conn.close()
            
@app.get("/pdfs-list", response_class=HTMLResponse)
def pdfs_list(request: Request):
    if EN_PRODUCCION:
        return templates.TemplateResponse("mensaje.html", {"request": request, "titulo": "Índice no disponible en Producción", "mensaje": "Los archivos se gestionan directamente en Supabase."})
    
    out_dir = Path("out")
    pdfs = [{"name": f.name, "url": f"/pdfs/{f.name}", "size": f.stat().st_size} for f in sorted(out_dir.glob("*.pdf"))] if out_dir.exists() else []
    
    html_content = "<h1>Índice de PDFs Locales</h1>"
    if pdfs:
        html_content += "<table border='1'><tr><th>Archivo</th><th>Tamaño (KB)</th><th>Descargar</th></tr>"
        for pdf in pdfs:
            html_content += f"<tr><td>{pdf['name']}</td><td>{pdf['size']/1024:.1f}</td><td><a href='{pdf['url']}'>Ver</a></td></tr>"
        html_content += "</table>"
    else:
        html_content += "<p>No hay PDFs locales.</p>"
    return HTMLResponse(content=html_content)


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
                stats['total_verificaciones'] = stats['total_diplomas'] * 3
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

# =============================
# ENDPOINTS DE HERRAMIENTAS ADMIN
# =============================

@app.get("/admin/generar", response_class=HTMLResponse)
def admin_generar(request: Request, token: str = Query(...)):
    try:
        check_admin(token)
        return templates.TemplateResponse("mensaje.html", {
            "request": request,
            "titulo": "Generador de PDFs",
            "mensaje": "La generación de diplomas ahora se realiza localmente con <code>generar_diplomas.py</code> y se sube automáticamente a Supabase.",
            "color": "var(--ok)"
        })
    except PermissionError:
        return RedirectResponse(url="/admin-login?error=Token+inválido", status_code=302)

@app.get("/admin/sync", response_class=HTMLResponse)
def admin_sync(request: Request, token: str = Query(...)):
    """Sincroniza URLs de Supabase en la BD para registros que no la tengan."""
    try:
        check_admin(token)
        conn = get_db_connection()
        if not conn: raise HTTPException(status_code=500, detail="Error de BD")
        
        try:
            cur = conn.cursor(dictionary=True)
            cur.execute("SELECT diploma_id, pdf_path, folio FROM diploma WHERE pdf_url IS NULL OR pdf_url = '' OR pdf_url NOT LIKE 'http%'")
            sin_url = cur.fetchall()
            
            if not sin_url:
                return templates.TemplateResponse("mensaje.html", {"request": request, "titulo": "Sincronización", "mensaje": "Todos los diplomas ya están sincronizados."})

            actualizados = 0
            for d in sin_url:
                if d.get("pdf_path"):
                    pdf_name = os.path.basename(d["pdf_path"])
                    public_url = f"{SUPABASE_PUBLIC_BASE}/{pdf_name}"
                    cur.execute("UPDATE diploma SET pdf_url=%s WHERE diploma_id=%s", (public_url, d["diploma_id"]))
                    actualizados += 1
            conn.commit()
            return templates.TemplateResponse("mensaje.html", {"request": request, "titulo": "Sincronización Exitosa", "mensaje": f"{actualizados} diplomas actualizados."})
        finally:
            if conn.is_connected(): conn.close()
    except PermissionError:
        return RedirectResponse(url="/admin-login?error=Token+inválido", status_code=302)

@app.get("/admin/auditar", response_class=HTMLResponse)
def admin_auditar(request: Request, token: str = Query(...)):
    try:
        check_admin(token)
        conn = get_db_connection()
        if not conn: raise HTTPException(status_code=500, detail="Error de BD")

        try:
            cur = conn.cursor(dictionary=True)
            cur.execute("SELECT diploma_id, folio, pdf_path, pdf_url FROM diploma")
            diplomas = cur.fetchall()
            resultados = []
            for d in diplomas:
                # La auditoría ahora verifica si existe una URL de Supabase
                estado = "✅ URL Asignada" if d.get("pdf_url") and d["pdf_url"].startswith("http") else "❌ Sin URL"
                resultados.append({"folio": d["folio"], "estado": estado, "path": d.get("pdf_url", "N/A")})
            return templates.TemplateResponse("mensaje.html", {"request": request, "titulo": "Auditoría", "mensaje": f"Se auditaron {len(resultados)} registros.", "diplomas": resultados})
        finally:
            if conn.is_connected(): conn.close()
    except PermissionError:
        return RedirectResponse(url="/admin-login?error=Token+inválido", status_code=302)
        
@app.get("/healthz", response_class=PlainTextResponse)
def healthz():
    return "OK"

# =============================
# SERVICIO DE ARCHIVOS
# =============================

@app.get("/static/{file_path:path}")
async def serve_static(file_path: str):
    static_file = Path("static") / file_path
    if static_file.exists(): return FileResponse(static_file)
    raise HTTPException(status_code=404, detail="Archivo no encontrado")

@app.get("/pdfs/{file_path:path}")
async def serve_pdfs(file_path: str):
    pdf_file = Path("out") / file_path
    if pdf_file.exists(): return FileResponse(pdf_file, media_type='application/pdf')
    raise HTTPException(status_code=404, detail="PDF no disponible localmente.")

if not EN_PRODUCCION:
    app.mount("/static_mount", StaticFiles(directory="static"), name="static_mount")
    out_dir = Path("out")
    out_dir.mkdir(exist_ok=True)
    app.mount("/pdfs_mount", StaticFiles(directory="out"), name="pdfs_mount")
    print("🔧 Modo: DESARROLLO")
else:
    print("🚀 Modo: PRODUCCIÓN")

# =============================
# INICIO LOCAL
# =============================

if __name__ == "__main__":
    import uvicorn
    print(f"✅ API iniciada. Modo: {'PRODUCCIÓN' if EN_PRODUCCION else 'DESARROLLO'}")
    uvicorn.run(app, host="0.0.0.0", port=8000)

