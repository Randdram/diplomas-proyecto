import os
import mysql.connector
from fastapi import FastAPI, Request, Query
from fastapi.responses import HTMLResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from datetime import datetime
from supabase import create_client


# =============================
# CONFIGURACIÓN PRINCIPAL
# =============================

app = FastAPI(title="Diplomas Proyecto", version="1.0.0")

# Archivos estáticos y templates
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# Variables de entorno
DB_HOST = os.getenv("DB_HOST")
DB_PORT = os.getenv("DB_PORT")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_NAME = os.getenv("DB_NAME")

ADMIN_TOKEN = os.getenv("ADMIN_TOKEN")

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY")
SUPABASE_BUCKET = os.getenv("SUPABASE_BUCKET")
SUPABASE_PUBLIC_BASE = os.getenv("SUPABASE_PUBLIC_BASE")


# =============================
# FUNCIONES AUXILIARES
# =============================

def get_db_connection():
    """Conecta a la base de datos MySQL (Clever Cloud)."""
    conn = mysql.connector.connect(
        host=DB_HOST,
        port=DB_PORT,
        user=DB_USER,
        password=DB_PASSWORD,
        database=DB_NAME
    )
    return conn


def check_admin(token: str):
    """Valida token de administrador."""
    if token != ADMIN_TOKEN:
        raise PermissionError("Token inválido o no autorizado.")


# =============================
# ENDPOINTS DEL PORTAL
# =============================

@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    """Página principal."""
    return templates.TemplateResponse("portal.html", {"request": request})


@app.get("/ingresar", response_class=HTMLResponse)
def ingresar(request: Request, curp: str = Query(None)):
    """Consulta diplomas por CURP."""
    if not curp:
        return templates.TemplateResponse("index.html", {"request": request})

    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)

    query = """
        SELECT c.nombre AS curso, d.folio, d.estado, d.fecha_emision, d.pdf_url
        FROM diploma d
        JOIN alumno a ON d.alumno_id = a.alumno_id
        JOIN curso c ON d.curso_id = c.curso_id
        WHERE a.curp = %s
        ORDER BY d.fecha_emision DESC
    """
    cur.execute(query, (curp,))
    diplomas = cur.fetchall()
    conn.close()

    if not diplomas:
        return templates.TemplateResponse("mensaje.html", {
            "request": request,
            "titulo": "Sin resultados",
            "mensaje": f"No se encontraron diplomas para el CURP {curp}.",
            "color": "var(--bad)"
        })

    return templates.TemplateResponse("index.html", {
        "request": request,
        "curp": curp,
        "diplomas": diplomas
    })


@app.get("/db_test", response_class=PlainTextResponse)
def db_test():
    """Prueba de conexión a MySQL."""
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT NOW()")
        fecha = cur.fetchone()[0]
        conn.close()
        return f"✅ Conectado correctamente a MySQL.\nFecha servidor: {fecha}"
    except Exception as e:
        return f"❌ Error de conexión: {e}"


# =============================
# ADMINISTRACIÓN: SINCRONIZACIÓN SUPABASE
# =============================

@app.get("/admin/sync", response_class=HTMLResponse)
def admin_sync(request: Request, token: str = Query(...)):
    """Sincroniza rutas PDF desde Supabase y actualiza la base de datos."""
    try:
        check_admin(token)

        supabase = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
        conn = get_db_connection()
        cur = conn.cursor(dictionary=True)

        # Buscar diplomas sin URL asignada
        cur.execute("SELECT diploma_id, pdf_path, folio FROM diploma WHERE pdf_url IS NULL OR pdf_url = ''")
        sin_url = cur.fetchall()

        if not sin_url:
            conn.close()
            return templates.TemplateResponse("mensaje.html", {
                "request": request,
                "titulo": "Sincronización completada",
                "mensaje": "Todos los diplomas ya tienen URL asignada.",
                "color": "var(--ok)"
            })

        actualizados = []
        for d in sin_url:
            nombre_pdf = os.path.basename(d["pdf_path"])
            public_url = f"{SUPABASE_PUBLIC_BASE}/{nombre_pdf}"

            try:
                # Validar existencia en Supabase
                response = supabase.storage.from_(SUPABASE_BUCKET).get_public_url(nombre_pdf)
                if response:
                    cur.execute(
                        "UPDATE diploma SET pdf_url=%s WHERE diploma_id=%s",
                        (public_url, d["diploma_id"])
                    )
                    actualizados.append({
                        "folio": d["folio"],
                        "pdf_url": public_url
                    })
            except Exception as e:
                print(f"⚠️ No encontrado en Supabase: {nombre_pdf} ({e})")

        conn.commit()
        conn.close()

        return templates.TemplateResponse("mensaje.html", {
            "request": request,
            "titulo": "Sincronización completada",
            "mensaje": f"{len(actualizados)} diplomas sincronizados correctamente.",
            "color": "var(--ok)",
            "diplomas": actualizados
        })

    except PermissionError as e:
        return templates.TemplateResponse("mensaje.html", {
            "request": request,
            "titulo": "Acceso denegado",
            "mensaje": str(e),
            "color": "var(--bad)"
        })
    except Exception as e:
        return templates.TemplateResponse("mensaje.html", {
            "request": request,
            "titulo": "Error de sincronización",
            "mensaje": str(e),
            "color": "var(--bad)"
        })


# =============================
# DEBUG OPCIONAL
# =============================

@app.get("/debug/supabase", response_class=PlainTextResponse)
def debug_supabase():
    """Lista los archivos en el bucket de Supabase (solo para debug)."""
    try:
        supabase = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
        archivos = supabase.storage.from_(SUPABASE_BUCKET).list()
        salida = "\n".join([f"- {f['name']}" for f in archivos])
        return f"✅ Conectado a Supabase.\nArchivos encontrados:\n{salida}"
    except Exception as e:
        return f"❌ Error al conectar con Supabase: {e}"


# =============================
# INICIO LOCAL (solo debug)
# =============================

if __name__ == "__main__":
    import uvicorn
    print("✅ Templates encontrados correctamente")
    uvicorn.run(app, host="0.0.0.0", port=8000)
