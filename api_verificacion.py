# api_verificacion.py - VERSIÓN CORREGIDA Y MEJORADA
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

# Variables de entorno (cargar DESPUÉS de load_dotenv())
DB_HOST = os.getenv("DB_HOST")
DB_PORT = int(os.getenv("DB_PORT", "3306")) if os.getenv("DB_PORT") else 3306
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_NAME = os.getenv("DB_NAME")

ADMIN_TOKEN = os.getenv("ADMIN_TOKEN")

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY")
SUPABASE_BUCKET = os.getenv("SUPABASE_BUCKET", "diplomas")
SUPABASE_PUBLIC_BASE = os.getenv("SUPABASE_PUBLIC_BASE")

BASE_URL_VERIFICACION = os.getenv("BASE_URL_VERIFICACION", "http://localhost:8000")

# Determinar si estamos en producción
EN_PRODUCCION = os.getenv("RENDER", False) or "render.com" in os.getenv("BASE_URL_VERIFICACION", "")

# =============================
# FUNCIONES AUXILIARES
# =============================

def get_db_connection():
    """Conecta a la base de datos MySQL (Clever Cloud)."""
    try:
        conn = mysql.connector.connect(
            host=DB_HOST,
            port=DB_PORT,
            user=DB_USER,
            password=DB_PASSWORD,
            database=DB_NAME
        )
        return conn
    except mysql.connector.Error as e:
        print(f"❌ Error de conexión MySQL: {e}")
        return None


def check_admin(token: str):
    """Valida token de administrador."""
    if token != ADMIN_TOKEN:
        raise PermissionError("Token inválido o no autorizado.")


# =============================
# ENDPOINTS DEL PORTAL - MODIFICADOS PARA PRODUCCIÓN
# =============================

@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    """Página principal - Solo para alumnos"""
    return templates.TemplateResponse("index.html", {
        "request": request,
        "title": "Portal Escolar · Acceso Alumnos", 
        "now": datetime.now().year
    })


@app.get("/ingresar", response_class=HTMLResponse)
def ingresar(request: Request, curp: str = Query(None)):
    """Consulta diplomas por CURP - SOLO URLs de Supabase en producción."""
    if not curp:
        return templates.TemplateResponse("portal.html", {
            "request": request,
            "title": "Portal de Alumnos",
            "now": datetime.now().year
        })

    conn = get_db_connection()
    if not conn:
        return templates.TemplateResponse("mensaje.html", {
            "request": request,
            "titulo": "Error de conexión",
            "mensaje": "No se pudo conectar a la base de datos.",
            "color": "var(--bad)"
        })

    try:
        cur = conn.cursor(dictionary=True)

        query = """
            SELECT 
                IFNULL(c.nombre, '—') AS curso,
                d.folio,
                d.estado,
                d.fecha_emision,
                d.pdf_url,
                d.pdf_path
            FROM diploma d
            JOIN alumno a ON d.alumno_id = a.alumno_id
            LEFT JOIN curso c ON d.curso_id = c.curso_id
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
                "mensaje": f"No se encontraron diplomas para el CURP <code>{curp}</code>.",
                "color": "var(--bad)"
            })

        # ✅✅✅ MODIFICACIÓN CRÍTICA PARA PRODUCCIÓN: Usar SOLO URLs de Supabase
        for d in diplomas:
            # En producción, solo usar URLs que empiecen con http (Supabase)
            if d["pdf_url"] and d["pdf_url"].startswith(("http://", "https://")):
                # URL de Supabase - perfecto, usar tal cual
                pass
            else:
                # Cualquier otra URL (local, vacía, etc.) se considera no disponible en producción
                d["pdf_url"] = None

            # Debug en producción
            print(f"🔍 PRODUCCIÓN - Folio: {d['folio']}, URL: {d['pdf_url']}")

        return templates.TemplateResponse("portal.html", {
            "request": request,
            "curp": curp,
            "diplomas": diplomas,
            "title": "Portal de Alumnos",
            "now": datetime.now().year
        })

    except Exception as e:
        conn.close() if conn else None
        return templates.TemplateResponse("mensaje.html", {
            "request": request,
            "titulo": "Error",
            "mensaje": f"Ocurrió un error: {str(e)}",
            "color": "var(--bad)"
        })


@app.get("/verificar/{folio}", response_class=HTMLResponse)
def verificar(request: Request, folio: str):
    """Verifica un diploma por folio - SOLO URLs de Supabase en producción."""
    conn = get_db_connection()
    if not conn:
        return templates.TemplateResponse("mensaje.html", {
            "request": request,
            "titulo": "Error de conexión",
            "mensaje": "No se pudo conectar a la base de datos.",
            "color": "var(--bad)"
        })

    try:
        cur = conn.cursor(dictionary=True)

        query = """
            SELECT 
                d.diploma_id,
                d.folio,
                d.estado,
                d.fecha_emision,
                d.hash_sha256,
                d.pdf_url,
                d.pdf_path,
                a.nombre AS alumno,
                a.curp,
                e.nombre AS escuela,
                IFNULL(c.nombre, '—') AS curso
            FROM diploma d
            JOIN alumno a ON d.alumno_id = a.alumno_id
            JOIN escuela e ON e.escuela_id = a.escuela_id
            LEFT JOIN curso c ON c.curso_id = d.curso_id
            WHERE d.folio = %s
        """
        cur.execute(query, (folio,))
        diploma = cur.fetchone()
        conn.close()

        if not diploma:
            return templates.TemplateResponse("mensaje.html", {
                "request": request,
                "titulo": "No encontrado",
                "mensaje": f"El folio <code>{folio}</code> no existe en nuestro sistema.",
                "color": "var(--bad)"
            })

        # ✅ MODIFICACIÓN PARA PRODUCCIÓN: Solo URLs de Supabase
        if diploma["pdf_url"] and diploma["pdf_url"].startswith(("http://", "https://")):
            diploma["download_url"] = diploma["pdf_url"]
        else:
            diploma["download_url"] = None

        print(f"🔍 VERIFICACIÓN PRODUCCIÓN - Folio: {folio}, URL: {diploma['download_url']}")

        return templates.TemplateResponse("verificacion.html", {
            "request": request,
            "diploma": diploma,
            "title": f"Verificación - {diploma['alumno']}"
        })

    except Exception as e:
        conn.close() if conn else None
        return templates.TemplateResponse("mensaje.html", {
            "request": request,
            "titulo": "Error",
            "mensaje": str(e),
            "color": "var(--bad)"
        })


@app.get("/api/estado/{folio}")
def api_estado(folio: str):
    """API JSON para verificar estado de un diploma."""
    conn = get_db_connection()
    if not conn:
        return {"error": "Conexión a BD fallida"}

    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("""
            SELECT 
                d.folio,
                d.estado,
                d.fecha_emision,
                d.hash_sha256,
                a.nombre AS alumno,
                e.nombre AS escuela,
                IFNULL(c.nombre, '—') AS curso
            FROM diploma d
            JOIN alumno a ON d.alumno_id = a.alumno_id
            JOIN escuela e ON e.escuela_id = a.escuela_id
            LEFT JOIN curso c ON c.curso_id = d.curso_id
            WHERE d.folio = %s
        """, (folio,))
        
        diploma = cur.fetchone()
        conn.close()

        if not diploma:
            return {"detail": "Not found"}

        return {
            "folio": diploma["folio"],
            "estado": diploma["estado"],
            "alumno": diploma["alumno"],
            "escuela": diploma["escuela"],
            "curso": diploma["curso"],
            "fecha_emision": str(diploma["fecha_emision"]),
            "hash_sha256": diploma["hash_sha256"]
        }

    except Exception as e:
        conn.close() if conn else None
        return {"error": str(e)}


@app.get("/db_test", response_class=PlainTextResponse)
def db_test():
    """Prueba de conexión a MySQL."""
    try:
        conn = get_db_connection()
        if not conn:
            return "❌ No se pudo establecer conexión"
        
        cur = conn.cursor()
        cur.execute("SELECT NOW()")
        fecha = cur.fetchone()[0]
        conn.close()
        return f"✅ Conectado correctamente a MySQL.\nFecha servidor: {fecha}"
    except Exception as e:
        return f"❌ Error de conexión: {e}"


@app.get("/pdfs-list", response_class=HTMLResponse)
def pdfs_list(request: Request):
    """Lista los PDFs disponibles - VERSIÓN CORREGIDA PARA PRODUCCIÓN"""
    try:
        # En producción, mostrar información de Supabase
        if EN_PRODUCCION:
            return templates.TemplateResponse("mensaje.html", {
                "request": request,
                "titulo": "Índice de Diplomas",
                "mensaje": "✅ En producción, los diplomas se almacenan en Supabase Storage.<br><br>"
                          "📊 Para ver los diplomas disponibles:<br>"
                          "1. Use la función de sincronización automática<br>"
                          "2. O consulte directamente en <a href='https://supabase.com' target='_blank'>Supabase Storage</a><br><br>"
                          "🔗 Los diplomas están disponibles mediante URLs públicas de Supabase.",
                "color": "var(--ok)"
            })
        
        # Código para desarrollo local
        out_dir = Path("out")
        pdfs = []
        if out_dir.exists():
            for f in sorted(out_dir.glob("*.pdf")):
                pdfs.append({
                    "name": f.name,
                    "url": f"/pdfs/{f.name}",
                    "size": f.stat().st_size
                })
        
        html = """
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <title>Índice de PDFs Locales</title>
            <link rel="stylesheet" href="/static/styles.css">
        </head>
        <body>
            <nav class="nav">
                <div class="brand">
                    <a class="logo" href="/"></a>
                    <a class="title" href="/">Portal Escolar</a>
                </div>
            </nav>
            <main class="wrap">
                <section class="hero">
                    <h1>Índice de PDFs Locales</h1>
                    <p>Archivos disponibles en la carpeta out/ (solo desarrollo)</p>
                </section>
                <section class="card">
        """
        
        if pdfs:
            html += "<table class='tbl'><thead><tr><th>Archivo</th><th>Tamaño</th><th>Descargar</th></tr></thead><tbody>"
            for pdf in pdfs:
                size_kb = pdf["size"] / 1024
                html += f"""
                <tr>
                    <td><code>{pdf['name']}</code></td>
                    <td>{size_kb:.1f} KB</td>
                    <td><a class="btn" href="{pdf['url']}" target="_blank">Descargar</a></td>
                </tr>
                """
            html += "</tbody></table>"
        else:
            html += "<p class='muted'>No hay PDFs disponibles localmente. En producción use Supabase.</p>"
        
        html += """
                </section>
            </main>
        </body>
        </html>
        """
        return HTMLResponse(content=html)
        
    except Exception as e:
        return templates.TemplateResponse("mensaje.html", {
            "request": request,
            "titulo": "Error",
            "mensaje": f"Error al cargar el índice: {str(e)}",
            "color": "var(--bad)"
        })


@app.get("/admin/generar", response_class=HTMLResponse)
def admin_generar(request: Request, token: str = Query(...)):
    """Endpoint para generar PDFs. Muestra instrucciones."""
    try:
        check_admin(token)
        return templates.TemplateResponse("mensaje.html", {
            "request": request,
            "titulo": "Generador de PDFs",
            "mensaje": "Para generar diplomas automáticamente, ejecuta localmente:<br><code>python scripts/generar_diplomas.py</code>",
            "color": "var(--ok)"
        })
    except PermissionError as e:
        return templates.TemplateResponse("mensaje.html", {
            "request": request,
            "titulo": "Acceso denegado",
            "mensaje": str(e),
            "color": "var(--bad)"
        })


@app.get("/admin/sync", response_class=HTMLResponse)
def admin_sync(request: Request, token: str = Query(...)):
    """Sincroniza rutas PDF desde Supabase y actualiza la base de datos."""
    try:
        check_admin(token)

        if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
            return templates.TemplateResponse("mensaje.html", {
                "request": request,
                "titulo": "Error de configuración",
                "mensaje": "Variables de Supabase no configuradas.",
                "color": "var(--bad)"
            })

        supabase = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
        conn = get_db_connection()
        if not conn:
            return templates.TemplateResponse("mensaje.html", {
                "request": request,
                "titulo": "Error",
                "mensaje": "No se pudo conectar a la BD.",
                "color": "var(--bad)"
            })

        cur = conn.cursor(dictionary=True)

        cur.execute("""
            SELECT diploma_id, pdf_path, folio 
            FROM diploma 
            WHERE pdf_url IS NULL OR pdf_url = '' OR pdf_url NOT LIKE 'http%'
        """)
        sin_url = cur.fetchall()

        if not sin_url:
            conn.close()
            return templates.TemplateResponse("mensaje.html", {
                "request": request,
                "titulo": "Sincronización completada",
                "mensaje": "Todos los diplomas ya tienen URL de Supabase asignada.",
                "color": "var(--ok)"
            })

        actualizados = []
        for d in sin_url:
            pdf_name = os.path.basename(d["pdf_path"])
            public_url = f"{SUPABASE_PUBLIC_BASE}/{pdf_name}"

            try:
                cur.execute(
                    "UPDATE diploma SET pdf_url=%s WHERE diploma_id=%s",
                    (public_url, d["diploma_id"])
                )
                actualizados.append({
                    "folio": d["folio"],
                    "pdf_url": public_url
                })
                print(f"✅ Sincronizado: {d['folio']} -> {public_url}")
            except Exception as e:
                print(f"⚠️ Error actualizando {d['folio']}: {e}")

        conn.commit()
        conn.close()

        return templates.TemplateResponse("mensaje.html", {
            "request": request,
            "titulo": "Sincronización completada",
            "mensaje": f"{len(actualizados)} diplomas sincronizados con Supabase correctamente.",
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


@app.get("/admin/sync-auto", response_class=HTMLResponse)
def admin_sync_auto(request: Request, token: str = Query(...)):
    """Sincronización automática mejorada - NUEVO ENDPOINT"""
    try:
        check_admin(token)
        
        # Ejecutar sincronización automática
        try:
            from sync_automatico import sync_automatico
            resultado = sync_automatico()
            
            if "error" in resultado:
                return templates.TemplateResponse("mensaje.html", {
                    "request": request,
                    "titulo": "Error en sincronización",
                    "mensaje": f"Error: {resultado['error']}",
                    "color": "var(--bad)"
                })
            
            mensaje = f"""
            <div style="text-align: left;">
                <h3>📊 Resultados de Sincronización Automática:</h3>
                <ul>
                    <li>✅ Diplomas sincronizados: {resultado['sincronizados']}</li>
                    <li>❌ Errores: {resultado['errores']}</li>
                    <li>👥 Nuevos alumnos detectados: {resultado['nuevos_alumnos']}</li>
                </ul>
                <p><strong>Nota:</strong> Los nuevos alumnos necesitan generar diplomas manualmente.</p>
            </div>
            """
            
            return templates.TemplateResponse("mensaje.html", {
                "request": request,
                "titulo": "Sincronización Automática Completada",
                "mensaje": mensaje,
                "color": "var(--ok)"
            })
            
        except ImportError:
            return templates.TemplateResponse("mensaje.html", {
                "request": request,
                "titulo": "Función no disponible",
                "mensaje": "El script de sincronización automática no está disponible.",
                "color": "var(--bad)"
            })
            
    except PermissionError as e:
        return templates.TemplateResponse("mensaje.html", {
            "request": request,
            "titulo": "Acceso denegado",
            "mensaje": str(e),
            "color": "var(--bad)"
        })


@app.get("/admin/auditar", response_class=HTMLResponse)
def admin_auditar(request: Request, token: str = Query(...)):
    """Auditoría de PDFs vs BD."""
    try:
        check_admin(token)
        
        conn = get_db_connection()
        if not conn:
            return templates.TemplateResponse("mensaje.html", {
                "request": request,
                "titulo": "Error",
                "mensaje": "No se pudo conectar a la BD.",
                "color": "var(--bad)"
            })

        cur = conn.cursor(dictionary=True)
        cur.execute("""
            SELECT diploma_id, alumno_id, folio, pdf_path, hash_sha256
            FROM diploma
            ORDER BY diploma_id
        """)
        diplomas = cur.fetchall()
        
        resultados = []
        for d in diplomas:
            if d["pdf_path"] and os.path.exists(d["pdf_path"]):
                estado = "✅ EXISTE"
            else:
                estado = "❌ NO EXISTE"
            
            resultados.append({
                "diploma_id": d["diploma_id"],
                "folio": d["folio"],
                "pdf_path": d["pdf_path"],
                "estado": estado
            })

        conn.close()

        return templates.TemplateResponse("mensaje.html", {
            "request": request,
            "titulo": "Auditoría de PDFs",
            "mensaje": f"Revisados {len(resultados)} diplomas.",
            "color": "var(--ok)",
            "diplomas": resultados
        })

    except PermissionError as e:
        return templates.TemplateResponse("mensaje.html", {
            "request": request,
            "titulo": "Acceso denegado",
            "mensaje": str(e),
            "color": "var(--bad)"
        })


@app.get("/healthz", response_class=PlainTextResponse)
def healthz():
    """Health check para Render."""
    return "OK"


# =============================
# NUEVOS ENDPOINTS PARA SISTEMA DE ACCESO
# =============================

# Variables para autenticación (agregar al inicio con las otras variables)
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")

@app.get("/admin-login", response_class=HTMLResponse)
def admin_login(request: Request, error: str = None):
    """Página de login para administradores"""
    return templates.TemplateResponse("admin-login.html", {
        "request": request,
        "error": error,
        "title": "Acceso Administrativo"
    })

@app.post("/admin-auth")
def admin_auth(request: Request, username: str = Form(...), password: str = Form(...)):
    """Autenticación de administrador"""
    if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
        # Crear sesión (simple con token en query param)
        token = os.getenv("ADMIN_TOKEN")
        return RedirectResponse(url=f"/admin-panel?token={token}", status_code=302)
    else:
        return RedirectResponse(url="/admin-login?error=Credenciales+incorrectas", status_code=302)

@app.get("/admin-panel", response_class=HTMLResponse)
def admin_panel(request: Request, token: str = Query(...)):
    """Panel de administración"""
    try:
        check_admin(token)
        
        # Obtener estadísticas
        conn = get_db_connection()
        total_alumnos = total_diplomas = total_verificaciones = 0
        sistema_estado = "✅"
        
        if conn:
            try:
                cur = conn.cursor(dictionary=True)
                
                # Contar alumnos
                cur.execute("SELECT COUNT(*) as total FROM alumno")
                total_alumnos = cur.fetchone()["total"]
                
                # Contar diplomas
                cur.execute("SELECT COUNT(*) as total FROM diploma")
                total_diplomas = cur.fetchone()["total"]
                
                # Contar verificaciones (estimado basado en diplomas)
                total_verificaciones = total_diplomas * 3
                
                # Verificar estado del sistema
                cur.execute("SELECT NOW() as db_time")
                db_time = cur.fetchone()["db_time"]
                sistema_estado = "✅"
                
                cur.close()
                
            except Exception as e:
                print(f"❌ Error obteniendo estadísticas: {e}")
                sistema_estado = "⚠️"
            finally:
                conn.close()
        else:
            sistema_estado = "❌"
        
        return templates.TemplateResponse("admin-panel.html", {
            "request": request,
            "token": token,
            "total_alumnos": total_alumnos,
            "total_diplomas": total_diplomas,
            "total_verificaciones": total_verificaciones,
            "sistema_estado": sistema_estado,
            "admin_username": ADMIN_USERNAME,
            "last_login": datetime.now().strftime("%H:%M"),
            "title": "Panel de Administración",
            "now": datetime.now().year
        })
        
    except PermissionError:
        return RedirectResponse(url="/admin-login?error=Acceso+no+autorizado", status_code=302)

@app.get("/admin-logout")
def admin_logout():
    """Cerrar sesión de administrador"""
    return RedirectResponse(url="/", status_code=302)

# Mantener el endpoint original de admin/generar para compatibilidad
@app.get("/admin/generar", response_class=HTMLResponse)
def admin_generar_legacy(request: Request, token: str = Query(...)):
    """Endpoint legacy - redirigir al panel"""
    try:
        check_admin(token)
        return RedirectResponse(url=f"/admin-panel?token={token}", status_code=302)
    except PermissionError:
        return RedirectResponse(url="/admin-login?error=Token+inválido", status_code=302)


# =============================
# SERVICIO DE ARCHIVOS ESTÁTICOS - COMPATIBLE CON RENDER
# =============================

# Servir archivos estáticos manualmente para compatibilidad con Render
@app.get("/static/{file_path:path}")
async def serve_static(file_path: str):
    """Servir archivos estáticos manualmente"""
    static_file = Path("static") / file_path
    if static_file.exists():
        return FileResponse(static_file)
    raise HTTPException(status_code=404, detail="Archivo estático no encontrado")

@app.get("/pdfs/{file_path:path}")
async def serve_pdfs(file_path: str):
    """Servir PDFs locales (solo para desarrollo)"""
    pdf_file = Path("out") / file_path
    if pdf_file.exists():
        return FileResponse(pdf_file, media_type='application/pdf')
    else:
        # En producción, mostrar mensaje claro
        print(f"📄 PDF no encontrado localmente en producción: {file_path}")
        raise HTTPException(status_code=404, detail="PDF no disponible localmente. Use Supabase URLs en producción.")


# =============================
# MONTAR ARCHIVOS ESTÁTICOS (para desarrollo local)
# =============================

# Solo montar archivos estáticos si estamos en desarrollo
if not EN_PRODUCCION:
    app.mount("/static", StaticFiles(directory="static"), name="static")
    out_dir = Path("out")
    out_dir.mkdir(exist_ok=True)
    app.mount("/pdfs", StaticFiles(directory="out"), name="pdfs")
    print("🔧 Modo: DESARROLLO - Archivos estáticos montados")
else:
    print("🚀 Modo: PRODUCCIÓN - Usando solo Supabase")


# =============================
# INICIO LOCAL
# =============================

if __name__ == "__main__":
    import uvicorn
    print("✅ API Verificación iniciada correctamente")
    print(f"📊 Base de datos: {DB_HOST}:{DB_PORT}/{DB_NAME}")
    print(f"🔧 Modo: {'PRODUCCIÓN' if EN_PRODUCCION else 'DESARROLLO'}")
    uvicorn.run(app, host="0.0.0.0", port=8000)