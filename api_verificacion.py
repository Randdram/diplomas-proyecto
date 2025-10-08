# api_verificacion.py
import os
import re
import csv, io
from pathlib import Path
from datetime import date, datetime
from auto_diplomas import generar_diplomas_automatica
import subprocess
import csv
import mysql.connector as mysql
from dotenv import load_dotenv

from fastapi import FastAPI, HTTPException, Form
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.middleware.cors import CORSMiddleware
from fastapi import UploadFile, File, Form
# ⬇️ NUEVO: importamos la generación automática
from auto_diplomas import generar_diplomas_automatica

# ========= Carga de variables de entorno (.env) =========
load_dotenv()
DB_HOST = os.getenv("DB_HOST", "127.0.0.1")
DB_PORT = int(os.getenv("DB_PORT", "3306"))
DB_USER = os.getenv("DB_USER", "root")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")
DB_NAME = os.getenv("DB_NAME", "escuela_compu")

BASE_URL_VERIFICACION = os.getenv("BASE_URL_VERIFICACION", "http://localhost:8000")
SALIDA_PDFS = os.getenv("SALIDA_PDFS", "out")
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "cambia-esto")  # <-- cámbialo en tu .env

# ========= App FastAPI =========
app = FastAPI(title="Diplomas API", version="1.0.0")

# CORS (ajústalo en producción)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Servir PDFs estáticamente desde /pdfs  (carpeta local SALIDA_PDFS)
from fastapi.staticfiles import StaticFiles
from pathlib import Path

# Crear la carpeta de salida si no existe
Path(SALIDA_PDFS).mkdir(parents=True, exist_ok=True)

# Montar la carpeta estática para servir los PDF
app.mount("/pdfs", StaticFiles(directory=SALIDA_PDFS), name="pdfs")

# Servir archivos estáticos (CSS, imágenes, etc.)
app.mount("/static", StaticFiles(directory="static"), name="static")


# ========= Utilidades comunes =========
def conectar_db():
    return mysql.connect(
        host=DB_HOST, port=DB_PORT, user=DB_USER, password=DB_PASSWORD, database=DB_NAME
    )

def _serialize(v):
    if isinstance(v, (date, datetime)):
        return v.isoformat()
    return v

def _jsonify_row(row: dict) -> dict:
    return {k: _serialize(v) for k, v in row.items() if v is not None}

def _estado_badge_html(estado: str) -> str:
    if estado == "VALIDO":
        return '<span class="badge ok">VÁLIDO</span>'
    if estado == "ANULADO":
        return '<span class="badge bad">ANULADO</span>'
    return '<span class="badge muted">DESCONOCIDO</span>'

def _html_layout(inner: str) -> str:
    return f"""<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Diplomas</title>
  <link rel="stylesheet" href="/static/styles.css">
</head>
<body>
  <nav class="nav">
    <a class="brand" href="/ingresar">
      <span class="logo"></span>
      <span class="title">Portal Escolar</span>
    </a>
    <div class="links">
      <a href="/ingresar">Alumnos</a>
      <a href="/docs" target="_blank" rel="noopener">API</a>
    </div>
  </nav>

  <section class="hero">
    <div class="wrap">
      <h1>Verificación de Diplomas</h1>
      <p>Consulta, valida y descarga tus reconocimientos.</p>
    </div>
  </section>

  <main style="max-width:980px;margin:26px auto 30px;">
    {inner}
  </main>

  <footer class="footer">
    <div class="wrap">
      <small>© {datetime.now().year} Portal Escolar · Verificación de Diplomas</small>
    </div>
  </footer>
</body>
</html>"""


# ========= Validador de CURP =========
_CURP_ESTADOS = "(?:AS|BC|BS|CC|CL|CM|CS|CH|DF|DG|GT|GR|HG|JC|MC|MN|MS|NT|NL|OC|PL|QT|QR|SP|SL|SR|TC|TS|TL|VZ|YN|ZS|NE)"
_CURP_REGEX = re.compile(
    r"^[A-Z][AEIOUX][A-Z]{2}\d{2}"
    r"(?:0[1-9]|1[0-2])"               # mes
    r"(?:0[1-9]|[12]\d|3[01])"         # día
    r"[HM]"                            # sexo
    + _CURP_ESTADOS +                  # estado
    r"[B-DF-HJ-NP-TV-Z]{3}"            # consonantes internas
    r"[0-9A-Z]\d$"                     # homoclave + dígito verificador
)
def validar_curp(curp: str) -> bool:
    if not curp:
        return False
    curp = curp.strip().upper()
    return bool(_CURP_REGEX.fullmatch(curp))


# ========= API ESTADO (JSON) =========
@app.get("/api/estado/{folio}")
def api_estado(folio: str):
    conn = conectar_db()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute(
            """
            SELECT d.estado, d.folio, d.pdf_path, d.hash_sha256, d.fecha_emision,
                   a.nombre AS alumno, e.nombre AS escuela, g.nombre AS grado, c.nombre AS curso
            FROM diploma d
            JOIN alumno a   ON a.alumno_id = d.alumno_id
            LEFT JOIN escuela e ON e.escuela_id = a.escuela_id
            LEFT JOIN grado g   ON g.grado_id = a.grado_id
            LEFT JOIN curso c   ON c.curso_id = d.curso_id
            WHERE d.folio=%s
            """,
            (folio,),
        )
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Folio no encontrado")

        pdf_name = Path(row["pdf_path"]).name if row.get("pdf_path") else ""
        row["pdf_url"] = f"/pdfs/{pdf_name}" if pdf_name else None
        return JSONResponse(_jsonify_row(row))
    finally:
        conn.close()


# ========= PÁGINA DE VERIFICACIÓN POR FOLIO =========
@app.get("/verificar/{folio}", response_class=HTMLResponse)
def verificar(folio: str):
    conn = conectar_db()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute(
            """
            SELECT d.estado, d.folio, d.pdf_path, d.hash_sha256, d.fecha_emision,
                   a.nombre AS alumno, e.nombre AS escuela, g.nombre AS grado, c.nombre AS curso
            FROM diploma d
            JOIN alumno a   ON a.alumno_id = d.alumno_id
            LEFT JOIN escuela e ON e.escuela_id = a.escuela_id
            LEFT JOIN grado g   ON g.grado_id = a.grado_id
            LEFT JOIN curso c   ON c.curso_id = d.curso_id
            WHERE d.folio=%s
            """,
            (folio,),
        )
        row = cur.fetchone()
        if not row:
            return HTMLResponse(_html_layout(
                "<h1>Verificación de Diploma</h1>"
                '<div class="card"><span class="badge bad">NO ENCONTRADO</span>'
                f"<p>El folio <b>{folio}</b> no existe o fue eliminado.</p>"
                f'<a class="btn" href="{BASE_URL_VERIFICACION}/docs" target="_blank">Ver documentación</a>'
                "</div>"
            ), status_code=404)

        pdf_name = Path(row["pdf_path"]).name if row.get("pdf_path") else ""
        pdf_url = f"/pdfs/{pdf_name}" if pdf_name else "#"
        pdf_btn = ""  # por defecto, nada
        if row['estado'] == "VALIDO" and pdf_url != "#":
            pdf_btn = f'<a class="btn" href="{pdf_url}" target="_blank" rel="noopener">Ver/Descargar PDF</a>'

        body = f"""
        <h1>Verificación de Diploma</h1>
        <div class="card">
          <div class="row" style="justify-content:space-between;align-items:center;">
            <div></div>{_estado_badge_html(row['estado'])}
          </div>
          <div class="grid">
            <div><b>Alumno:</b> {row.get('alumno','-')}</div>
            <div><b>Grado:</b> {row.get('grado','-')}</div>
            <div><b>Escuela:</b> {row.get('escuela','-')}</div>
            <div><b>Curso:</b> {row.get('curso','-')}</div>
            <div><b>Folio:</b> <small>{row.get('folio')}</small></div>
            <div><b>Fecha de emisión:</b> { _serialize(row.get('fecha_emision')) or '-' }</div>
          </div>
          <div class="row"><b>SHA-256:</b> <small>{row.get('hash_sha256','')}</small></div>
          <div class="row" style="margin-top:14px;">
            {pdf_btn}
          </div>
          <p class="muted" style="margin-top:16px;">Para validar, compare el hash SHA-256 del archivo descargado con el mostrado arriba.</p>
        </div>
        """
        return HTMLResponse(_html_layout(body))
    finally:
        conn.close()


# ========= PORTAL: FORMULARIO DE CURP (GET/POST) =========
@app.get("/ingresar", response_class=HTMLResponse)
def ingresar_form(error: str | None = None):
    err_html = f"<div class='row'><span class='badge bad'>{error}</span></div>" if error else ""
    body = f"""
    <h1>Portal de Alumnos</h1>
    <div class="card">
      {err_html}
      <form method="post" action="/ingresar" class="stack" autocomplete="off" novalidate>
        <label>CURP</label>
        <input name="curp"
               placeholder="Escribe tu CURP"
               maxlength="18"
               minlength="18"
               pattern="[A-Za-z0-9]{{18}}"
               title="El CURP debe tener 18 caracteres (letras y números)."
               style="text-transform:uppercase"
               required>
        <button class="btn" type="submit">Entrar</button>
      </form>
      <small class="muted">Solo se usa para buscar tus diplomas. No se guarda contraseña.</small>
    </div>
    """
    return HTMLResponse(_html_layout(body))

@app.post("/ingresar")
def ingresar_post(curp: str = Form(...)):
    curp = (curp or "").strip().upper()
    if not validar_curp(curp):
        body = f"""
        <h1>Portal de Alumnos</h1>
        <div class="card">
          <span class="badge bad">CURP inválido</span>
          <p>Revisa que tenga <b>18 caracteres</b> en mayúsculas y formato válido.</p>
          <a class="btn" href="/ingresar">Volver</a>
        </div>
        """
        return HTMLResponse(_html_layout(body), status_code=400)

    return RedirectResponse(f"/alumno/{curp}", status_code=303)


# ========= PORTAL: PÁGINA DE ALUMNO POR CURP =========
@app.get("/alumno/{curp}", response_class=HTMLResponse)
def alumno_por_curp(curp: str):
    curp = (curp or "").strip().upper()
    conn = conectar_db()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute(
            """
            SELECT a.alumno_id, a.nombre AS alumno, e.nombre AS escuela, g.nombre AS grado
            FROM alumno a
            LEFT JOIN escuela e ON e.escuela_id = a.escuela_id
            LEFT JOIN grado g   ON g.grado_id = a.grado_id
            WHERE a.curp=%s
            """,
            (curp,),
        )
        alum = cur.fetchone()
        if not alum:
            return HTMLResponse(_html_layout(
                f"<h1>Portal de Alumnos</h1>"
                f"<div class='card'><span class='badge bad'>No encontrado</span>"
                f"<p>No encontramos el CURP <b>{curp}</b>.</p>"
                f"<a class='btn' href='/ingresar'>Intentar de nuevo</a></div>"
            ), status_code=404)

        cur.execute(
            """
            SELECT d.folio, d.estado, d.fecha_emision, d.pdf_path, d.hash_sha256,
                   c.nombre AS curso
            FROM diploma d
            LEFT JOIN curso c ON c.curso_id = d.curso_id
            WHERE d.alumno_id=%s
            ORDER BY d.fecha_emision DESC, d.diploma_id DESC
            """,
            (alum["alumno_id"],),
        )
        diplomas = cur.fetchall() or []

        if diplomas:
            rows_html = ""
            for d in diplomas:
                pdf_name = Path(d["pdf_path"]).name if d.get("pdf_path") else ""
                pdf_url  = f"/pdfs/{pdf_name}" if pdf_name else "#"
                ver_url  = f"/verificar/{d['folio']}"
                acciones = []
                if d.get("estado") == "VALIDO" and pdf_url != "#":
                    acciones.append(f'<a class="btn" href="{pdf_url}" target="_blank">PDF</a>')
                acciones.append(f'<a class="btn" href="{ver_url}" target="_blank">Verificación</a>')
                acciones_html = " ".join(acciones)
                rows_html += f"""
                <tr>
                  <td>{_serialize(d.get('fecha_emision')) or '-'}</td>
                  <td>{d.get('curso','-')}</td>
                  <td>{d.get('folio')}</td>
                  <td>{d.get('estado')}</td>
                  <td style="white-space:nowrap">
                    {acciones_html}
                  </td>
                </tr>
                """
            tabla = f"""
            <table class="tbl">
              <thead><tr><th>Fecha</th><th>Curso</th><th>Folio</th><th>Estado</th><th>Acciones</th></tr></thead>
              <tbody>{rows_html}</tbody>
            </table>
            """
        else:
            tabla = "<p class='muted'>No tienes diplomas registrados todavía.</p>"

        body = f"""
        <h1>Mis Diplomas</h1>
        <div class="card">
          <div class="row"><b>Alumno:</b> {alum.get('alumno','-')}</div>
          <div class="grid">
            <div><b>Escuela:</b> {alum.get('escuela','-')}</div>
            <div><b>Grado:</b> {alum.get('grado','-')}</div>
          </div>
          <hr/>
          {tabla}
          <div class="row" style="margin-top:8px;">
            <a class="btn" href="/ingresar">Salir</a>
          </div>
        </div>
        """
        return HTMLResponse(_html_layout(body))
    finally:
        conn.close()


# ========= API: LISTA JSON DE DIPLOMAS POR CURP =========
@app.get("/api/alumno/{curp}/diplomas")
def api_diplomas_por_curp(curp: str):
    curp = (curp or "").strip().upper()
    conn = conectar_db()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT alumno_id, nombre FROM alumno WHERE curp=%s", (curp,))
        alum = cur.fetchone()
        if not alum:
            raise HTTPException(status_code=404, detail="Alumno no encontrado")

        cur.execute(
            """
            SELECT d.folio, d.estado, d.fecha_emision, d.pdf_path, d.hash_sha256,
                   c.nombre AS curso
            FROM diploma d
            LEFT JOIN curso c ON c.curso_id = d.curso_id
            WHERE d.alumno_id=%s
            ORDER BY d.fecha_emision DESC, d.diploma_id DESC
            """,
            (alum["alumno_id"],),
        )
        data = []
        for r in cur.fetchall() or []:
            item = _jsonify_row(r)
            pdf_name = Path(r["pdf_path"]).name if r.get("pdf_path") else ""
            item["pdf_url"] = f"/pdfs/{pdf_name}" if pdf_name else None
            item["verificacion_url"] = f"/verificar/{r['folio']}"
            data.append(item)

        return {"alumno": alum["nombre"], "curp": curp, "diplomas": data}
    finally:
        conn.close()


# ========= ADMIN: Exportar enlaces como CSV =========
@app.get("/admin/links")
def admin_links(token: str, curso: str | None = None, escuela: str | None = None):
    """
    Exporta CSV con: alumno, curso, escuela, folio, verificacion, pdf.
    Uso:
      /admin/links?token=TU_TOKEN
      /admin/links?token=TU_TOKEN&curso=Computación%20Básica
      /admin/links?token=TU_TOKEN&escuela=Sec.%20Técnica%2012
    """
    if token != ADMIN_TOKEN:
        raise HTTPException(status_code=401, detail="No autorizado")

    conn = conectar_db()
    try:
        cur = conn.cursor(dictionary=True)

        base_sql = """
            SELECT a.nombre AS alumno,
                   IFNULL(cu.nombre,'-') AS curso,
                   e.nombre AS escuela,
                   d.folio,
                   d.pdf_path
            FROM diploma d
            JOIN alumno a   ON a.alumno_id = d.alumno_id
            JOIN escuela e  ON e.escuela_id = a.escuela_id
            LEFT JOIN curso cu ON cu.curso_id = d.curso_id
        """
        where = []
        params = []

        if curso:
            where.append("cu.nombre = %s")
            params.append(curso)
        if escuela:
            where.append("e.nombre = %s")
            params.append(escuela)

        if where:
            base_sql += " WHERE " + " AND ".join(where)
        base_sql += " ORDER BY a.nombre"

        cur.execute(base_sql, params)
        rows = cur.fetchall() or []

        # Arma CSV en memoria
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["alumno", "curso", "escuela", "folio", "verificacion", "pdf"])

        for r in rows:
            pdf_name = Path(r["pdf_path"]).name if r.get("pdf_path") else ""
            ver_url = f"{BASE_URL_VERIFICACION}/verificar/{r['folio']}"
            pdf_url = f"{BASE_URL_VERIFICACION}/pdfs/{pdf_name}" if pdf_name else ""
            w.writerow([r["alumno"], r["curso"], r["escuela"], r["folio"], ver_url, pdf_url])

        csv_text = buf.getvalue()
        return Response(
            content=csv_text,
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": "attachment; filename=links.csv"},
        )
    finally:
        conn.close()


# ========= ADMIN: Generar diplomas pendientes (manual) =========
@app.get("/admin/generar")
def admin_generar(token: str):
    if token != ADMIN_TOKEN:
        raise HTTPException(status_code=401, detail="No autorizado")

    resumen = _generar_y_rebuild()

    msg = resumen.replace("\r", " ").replace("\n", " ")
    url = f"/admin/pdfs?token={token}&msg={msg}"
    return RedirectResponse(url, status_code=303)


def _generar_y_rebuild() -> str:
    """
    1) Genera diplomas faltantes (en el mismo proceso).
    2) Reconstruye TODOS los PDFs con la plantilla (llamando rebuild_pdfs.py).
    Devuelve un resumen para mostrar en el panel admin.
    """
    pasos = []

    # Paso 1: auto-generación (si no hay pendientes, solo dirá OK)
    try:
        generar_diplomas_automatica()
        pasos.append("Auto-generación: OK (revisó y creó si faltaban)")
    except Exception as e:
        pasos.append(f"Auto-generación: ERROR: {e!r}")

    # Paso 2: rebuild de todos los PDFs
    try:
        import subprocess
        completed = subprocess.run(
            ["python", "rebuild_pdfs.py"],
            capture_output=True,
            text=True,
            check=False,
        )
        out = (completed.stdout or "").strip()
        err = (completed.stderr or "").strip()
        if completed.returncode == 0:
            pasos.append("Rebuild PDFs: OK" + (f" | {out}" if out else ""))
        else:
            pasos.append(f"Rebuild PDFs: ERROR code {completed.returncode} | {out} | {err}")
    except Exception as e:
        pasos.append(f"Rebuild PDFs: ERROR: {e!r}")

    return "  •  ".join(pasos)[:600]


# ====== UTILIDADES PARA ADMIN/DIAGNÓSTICO ======
import os
from datetime import datetime

def _fmt_size(nbytes: int) -> str:
    # formatea tamaños bonitos sin dependencias externas
    for unit in ("B","KB","MB","GB","TB"):
        if nbytes < 1024.0:
            return f"{nbytes:.1f} {unit}"
        nbytes /= 1024.0
    return f"{nbytes:.1f} PB"

@app.get("/api/health")
def api_health():
    """
    Healthcheck sencillo: conecta a la BD y regresa conteos básicos.
    """
    try:
        conn = conectar_db()
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT COUNT(*) AS n FROM alumno");   n_alum = cur.fetchone()["n"]
        cur.execute("SELECT COUNT(*) AS n FROM diploma");   n_dip  = cur.fetchone()["n"]
        cur.close(); conn.close()
        return {"ok": True, "db": DB_NAME, "alumnos": n_alum, "diplomas": n_dip}
    except Exception as e:
        return {"ok": False, "error": str(e)}

@app.get("/admin/pdfs", response_class=HTMLResponse)
def admin_pdfs(token: str, msg: str | None = None):
    if token != ADMIN_TOKEN:
        return HTMLResponse(_html_layout("""
        <h1>Índice de PDFs</h1>
        <div class="card"><span class="badge bad">No autorizado</span></div>
        """), status_code=401)

    conn = conectar_db()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("""
            SELECT d.diploma_id, d.folio, d.pdf_path, d.fecha_emision, d.estado,
                   a.nombre AS alumno, e.nombre AS escuela, IFNULL(c.nombre,'-') AS curso
            FROM diploma d
            JOIN alumno a ON a.alumno_id = d.alumno_id
            JOIN escuela e ON e.escuela_id = a.escuela_id
            LEFT JOIN curso c ON c.curso_id = d.curso_id
            ORDER BY d.diploma_id DESC
        """)
        rows = cur.fetchall() or []
    finally:
        conn.close()

    def _acciones(r):
        pdf_name = Path(r["pdf_path"]).name if r.get("pdf_path") else ""
        pdf_url  = f"/pdfs/{pdf_name}" if pdf_name else "#"
        ver_url  = f"/verificar/{r['folio']}"
        botones = []

        # Mostrar PDF/Verif. solo si no está anulado (Modo 1: ocultar enlaces)
        if r.get("estado") == "VALIDO":
            botones.append(f'<a class="btn" href="{pdf_url}" target="_blank">PDF</a>')
            botones.append(f'<a class="btn" href="{ver_url}" target="_blank">Verif.</a>')
            botones.append(f'<a class="btn" href="/admin/anular?token={token}&folio={r["folio"]}">Anular</a>')
        else:
            # ANULADO: mostrar opción para restaurar
            botones.append(f'<a class="btn" href="/admin/restaurar?token={token}&folio={r["folio"]}">Restaurar</a>')
        return " ".join(botones)

    body_rows = "".join(
        f"""
        <tr>
          <td>{r['diploma_id']}</td>
          <td>{r['alumno']}</td>
          <td>{r['escuela']}</td>
          <td>{r['curso']}</td>
          <td style="white-space:nowrap"><small>{r['folio']}</small></td>
          <td>{_estado_badge_html(r.get('estado') or '-')}</td>
          <td>{_serialize(r['fecha_emision']) or '-'}</td>
          <td style="white-space:nowrap">{_acciones(r)}</td>
        </tr>
        """
        for r in rows
    )

    alert = f"<div class='row'><span class='badge ok'>{msg}</span></div>" if msg else ""

    html = f"""
    <h1>Índice de PDFs</h1>
    <div class="card">
      {alert}
      <div class="row" style="display:flex;gap:10px;align-items:center;margin-bottom:10px;">
        <a class="btn" href="/admin/generar?token={token}">⚙️ Crear y regenerar</a>
        <a class="btn" href="/admin/auditar?token={token}" target="_blank">🧰 Auditar</a>
        <a class="btn" href="/admin/links?token={token}" target="_blank">🔗 Exportar links (CSV)</a>
        <a class="btn" href="/admin/carga?token={token}">📥 Cargar CSV</a>
      </div>

      <table class="tbl">
        <thead>
          <tr>
            <th>ID</th><th>Alumno</th><th>Escuela</th><th>Curso</th>
            <th>Folio</th><th>Estado</th><th>Fecha</th><th>Acciones</th>
          </tr>
        </thead>
        <tbody>
          {body_rows}
        </tbody>
      </table>
    </div>
    """
    return HTMLResponse(_html_layout(html))


# ========= ADMIN: Auditar PDFs (discrepancias BD vs disco) =========
@app.get("/admin/auditar", response_class=HTMLResponse)
def admin_auditar(token: str):
    """
    Compara BD vs archivos:
      - PDFs que existen en disco pero no están referenciados
      - Diplomas en BD con pdf_path faltante en disco
    Requiere ?token=ADMIN_TOKEN
    """
    if token != ADMIN_TOKEN:
        return HTMLResponse(_html_layout(
            "<h1>Auditoría</h1><div class='card'><span class='badge bad'>No autorizado</span></div>"
        ), status_code=401)

    # Archivos reales en carpeta
    try:
        disk_pdfs = {name for name in os.listdir(SALIDA_PDFS)
                     if os.path.isfile(os.path.join(SALIDA_PDFS, name)) and name.lower().endswith(".pdf")}
    except FileNotFoundError:
        disk_pdfs = set()

    # Referencias en BD
    conn = conectar_db()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT diploma_id, folio, pdf_path FROM diploma")
        rows = cur.fetchall() or []
    finally:
        conn.close()

    ref_pdfs = set()
    faltan_en_disco = []
    for r in rows:
        name = ""
        if r.get("pdf_path"):
            name = os.path.basename(r["pdf_path"])
            ref_pdfs.add(name)
            if name not in disk_pdfs:
                faltan_en_disco.append(r)

    sobran_en_disco = sorted(disk_pdfs - ref_pdfs)

    def _li(items):
        if not items:
            return "<li class='muted'>Nada</li>"
        if isinstance(items[0], dict):
            return "".join(
                f"<li><code>{i.get('pdf_path','')}</code> (folio {i.get('folio')})</li>" for i in items
            )
        return "".join(f"<li><code>{x}</code></li>" for x in items)

    body = f"""
    <h1>Auditoría de PDFs</h1>
    <div class="card">
      <div class="row"><b>Carpeta:</b> {SALIDA_PDFS}</div>
      <div class="row"><b>Diplomas en BD:</b> {len(rows)}</div>
      <div class="row"><b>Archivos PDF en disco:</b> {len(disk_pdfs)}</div>
      <hr/>
      <div class="row"><b>Faltan en disco (referenciados en BD, archivo no existe):</b>
        <ul>{_li(faltan_en_disco)}</ul>
      </div>
      <div class="row"><b>Sobran en disco (existen en carpeta pero no están referenciados en BD):</b>
        <ul>{_li(sobran_en_disco)}</ul>
      </div>
      <div class="row" style="margin-top:10px">
        <a class="btn" href="/admin/pdfs?token={ADMIN_TOKEN}">Ver índice de PDFs</a>
      </div>
    </div>
    """
    return HTMLResponse(_html_layout(body))


# =================== ADMIN: Anular folio ===================

@app.get("/admin/anular", response_class=HTMLResponse)
def admin_anular_form(token: str, folio: str):
    """
    Muestra una confirmación para anular un folio.
    """
    if token != ADMIN_TOKEN:
        return HTMLResponse(_html_layout("""
        <h1>Anular diploma</h1>
        <div class="card"><span class="badge bad">No autorizado</span></div>
        """), status_code=401)

    conn = conectar_db()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("""
            SELECT d.folio, d.estado, d.fecha_emision, d.pdf_path,
                   a.nombre AS alumno, e.nombre AS escuela, IFNULL(c.nombre,'-') AS curso
            FROM diploma d
            JOIN alumno a ON a.alumno_id = d.alumno_id
            JOIN escuela e ON e.escuela_id = a.escuela_id
            LEFT JOIN curso c ON c.curso_id = d.curso_id
            WHERE d.folio=%s
        """, (folio,))
        row = cur.fetchone()
    finally:
        conn.close()

    if not row:
        return HTMLResponse(_html_layout(f"""
        <h1>Anular diploma</h1>
        <div class="card">
          <span class="badge bad">Folio no encontrado</span>
          <p>El folio <code>{folio}</code> no existe.</p>
          <div class="row"><a class="btn" href="/admin/pdfs?token={token}">Volver</a></div>
        </div>
        """), status_code=404)

    estado_badge = _estado_badge_html(row["estado"])
    pdf_name = Path(row["pdf_path"]).name if row.get("pdf_path") else ""
    pdf_url  = f"/pdfs/{pdf_name}" if pdf_name else "#"

    body = f"""
    <h1>Anular diploma</h1>
    <div class="card">
      <div class="row" style="display:flex;justify-content:space-between;align-items:center;">
        <div><b>Alumno:</b> {row['alumno']} &nbsp;|&nbsp; <b>Escuela:</b> {row['escuela']} &nbsp;|&nbsp; <b>Curso:</b> {row['curso']}</div>
        {estado_badge}
      </div>
      <div class="grid">
        <div><b>Folio:</b> <small>{row['folio']}</small></div>
        <div><b>Fecha:</b> {_serialize(row['fecha_emision']) or '-'}</div>
      </div>
      <div class="row" style="margin:8px 0"><a class="btn" href="{pdf_url}" target="_blank">Ver PDF</a></div>
      <hr/>
      <form method="post" action="/admin/anular" class="stack">
        <input type="hidden" name="token" value="{token}">
        <input type="hidden" name="folio" value="{row['folio']}">
        <label>Motivo (opcional)</label>
        <input name="motivo" placeholder="Ej. duplicado, error de datos" />
        <div class="row" style="display:flex;gap:8px;align-items:center;margin-top:8px;">
          <button class="btn" type="submit">Anular ahora</button>
          <a class="btn" href="/admin/pdfs?token={token}">Cancelar</a>
        </div>
      </form>
      <small class="muted">Nota: Solo cambia el estado a <b>ANULADO</b>. El PDF y la fecha se mantienen.</small>
    </div>
    """
    return HTMLResponse(_html_layout(body))


@app.post("/admin/anular")
def admin_anular_confirm(token: str = Form(...), folio: str = Form(...), motivo: str | None = Form(None)):
    """
    Realiza la anulación (cambia estado a ANULADO).
    """
    if token != ADMIN_TOKEN:
        raise HTTPException(status_code=401, detail="No autorizado")

    conn = conectar_db()
    try:
        cur = conn.cursor()
        # Solo anula si no está ya anulado
        cur.execute("""
            UPDATE diploma
               SET estado='ANULADO'
             WHERE folio=%s AND estado <> 'ANULADO'
        """, (folio,))
        afectadas = cur.rowcount
        conn.commit()
    finally:
        conn.close()

    if afectadas == 0:
        msg = f"Folio {folio} ya estaba ANULADO o no existe."
    else:
        # Si quieres, podrías guardar 'motivo' en una tabla externa de auditoría.
        msg = f"Folio {folio} ANULADO correctamente."

    # Regresa al índice con mensaje
    safe = msg.replace("\r", " ").replace("\n", " ")
    return RedirectResponse(f"/admin/pdfs?token={token}&msg={safe}", status_code=303)


# =================== ADMIN: Restaurar folio ===================

from fastapi import Form

@app.get("/admin/restaurar", response_class=HTMLResponse)
def admin_restaurar_form(token: str, folio: str):
    if token != ADMIN_TOKEN:
        return HTMLResponse(_html_layout("""
        <h1>Restaurar diploma</h1>
        <div class="card"><span class="badge bad">No autorizado</span></div>
        """), status_code=401)

    conn = conectar_db()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("""
            SELECT d.folio, d.estado, d.fecha_emision, d.pdf_path,
                   a.nombre AS alumno, e.nombre AS escuela, IFNULL(c.nombre,'-') AS curso
            FROM diploma d
            JOIN alumno a ON a.alumno_id = d.alumno_id
            JOIN escuela e ON e.escuela_id = a.escuela_id
            LEFT JOIN curso c ON c.curso_id = d.curso_id
            WHERE d.folio=%s
        """, (folio,))
        row = cur.fetchone()
    finally:
        conn.close()

    if not row:
        return HTMLResponse(_html_layout(f"""
        <h1>Restaurar diploma</h1>
        <div class="card">
          <span class="badge bad">Folio no encontrado</span>
          <p>El folio <code>{folio}</code> no existe.</p>
          <div class="row"><a class="btn" href="/admin/pdfs?token={token}">Volver</a></div>
        </div>
        """), status_code=404)

    body = f"""
    <h1>Restaurar diploma</h1>
    <div class="card">
      <div class="row" style="display:flex;justify-content:space-between;align-items:center;">
        <div><b>Alumno:</b> {row['alumno']} &nbsp;|&nbsp; <b>Escuela:</b> {row['escuela']} &nbsp;|&nbsp; <b>Curso:</b> {row['curso']}</div>
        {_estado_badge_html(row['estado'])}
      </div>
      <div class="grid">
        <div><b>Folio:</b> <small>{row['folio']}</small></div>
        <div><b>Fecha:</b> {_serialize(row['fecha_emision']) or '-'}</div>
      </div>
      <hr/>
      <form method="post" action="/admin/restaurar" class="stack">
        <input type="hidden" name="token" value="{token}">
        <input type="hidden" name="folio" value="{row['folio']}">
        <div class="row" style="display:flex;gap:8px;align-items:center;margin-top:8px;">
          <button class="btn" type="submit">Restaurar ahora</button>
          <a class="btn" href="/admin/pdfs?token={token}">Cancelar</a>
        </div>
      </form>
      <small class="muted">Cambia el estado a <b>VALIDO</b>.</small>
    </div>
    """
    return HTMLResponse(_html_layout(body))


@app.post("/admin/restaurar")
def admin_restaurar_confirm(token: str = Form(...), folio: str = Form(...)):
    if token != ADMIN_TOKEN:
        raise HTTPException(status_code=401, detail="No autorizado")

    conn = conectar_db()
    try:
        cur = conn.cursor()
        cur.execute("""
            UPDATE diploma
               SET estado='VALIDO'
             WHERE folio=%s AND estado <> 'VALIDO'
        """, (folio,))
        afectadas = cur.rowcount
        conn.commit()
    finally:
        conn.close()

    msg = (f"Folio {folio} RESTAURADO a VALIDO."
           if afectadas > 0 else
           f"Folio {folio} ya estaba VALIDO o no existe.")

    safe = msg.replace("\r", " ").replace("\n", " ")
    return RedirectResponse(f"/admin/pdfs?token={token}&msg={safe}", status_code=303)


# =================== ADMIN: Descargar plantilla CSV ===================

@app.get("/admin/csv_template")
def admin_csv_template(token: str):
    if token != ADMIN_TOKEN:
        raise HTTPException(status_code=401, detail="No autorizado")

    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["nombre", "curp", "escuela", "grado", "curso"])
    w.writerow(["Ana Torres", "TOAA040506MDFLRS08", "Sec. Técnica 12", "Secundaria 1", "Computación Básica"])
    w.writerow(["Juan Pérez", "PEPJ010203HDFRNV09", "Colegio Alfa", "Bachillerato 3", "Excel Intermedio"])
    data = buf.getvalue()

    return Response(
        content=data,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=plantilla_alumnos.csv"},
    )

@app.get("/admin/carga", response_class=HTMLResponse)
def admin_carga_form(token: str, msg: str | None = None):
    if token != ADMIN_TOKEN:
        return HTMLResponse(_html_layout("""
        <h1>Carga masiva de alumnos</h1>
        <div class="card"><span class="badge bad">No autorizado</span></div>
        """), status_code=401)

    alerta = f"<div class='row'><span class='badge ok'>{msg}</span></div>" if msg else ""

    body = f"""
    <h1>Carga masiva de alumnos</h1>
    <div class="card">
      {alerta}
      <p class="muted">Sube un CSV con columnas: <code>nombre,curp,escuela,grado,curso</code>.</p>
      <div class="row" style="display:flex; gap:10px; align-items:center;">
        <a class="btn" href="/admin/csv_template?token={token}">Descargar plantilla</a>
        <a class="btn" href="/admin/pdfs?token={token}">Volver</a>
      </div>
      <hr/>
      <form method="post" action="/admin/carga" enctype="multipart/form-data" class="stack">
        <input type="hidden" name="token" value="{token}">
        <input type="file" name="archivo" accept=".csv" required>
        <button class="btn" type="submit">Subir y procesar</button>
      </form>
    </div>
    """
    return HTMLResponse(_html_layout(body))


@app.post("/admin/carga", response_class=HTMLResponse)
async def admin_carga_procesar(token: str = Form(...), archivo: UploadFile = File(...)):
    if token != ADMIN_TOKEN:
        return HTMLResponse(_html_layout("""
        <h1>Carga masiva de alumnos</h1>
        <div class="card"><span class="badge bad">No autorizado</span></div>
        """), status_code=401)

    # Lee CSV (soporta BOM UTF-8)
    raw = await archivo.read()
    text = raw.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))

    # Normaliza nombres de columnas
    needed = {"nombre","curp","escuela","grado","curso"}
    if set(x.strip().lower() for x in reader.fieldnames or []) != needed:
        body = f"""
        <h1>Carga masiva de alumnos</h1>
        <div class="card">
          <span class="badge bad">Estructura inválida</span>
          <p>Encabezados esperados: <code>{", ".join(sorted(needed))}</code></p>
          <a class="btn" href="/admin/carga?token={token}">Volver</a>
        </div>
        """
        return HTMLResponse(_html_layout(body), status_code=400)

    # Procesa filas
    resultados = []  # lista de dicts: {fila, curp, status, detalle}
    conn = conectar_db()
    try:
        cur = conn.cursor(dictionary=True)

        for idx, row in enumerate(reader, start=1):
            nombre  = (row.get("nombre") or "").strip()
            curp    = (row.get("curp") or "").strip().upper()
            escuela = (row.get("escuela") or "").strip()
            grado   = (row.get("grado") or "").strip()
            curso   = (row.get("curso") or "").strip()

            if not (nombre and curp and escuela):
                resultados.append({"fila": idx, "curp": curp, "status": "ERROR", "detalle": "Faltan campos obligatorios (nombre/curp/escuela)."})
                continue
            if not validar_curp(curp):
                resultados.append({"fila": idx, "curp": curp, "status": "ERROR", "detalle": "CURP inválido."})
                continue

            try:
                # Escuela
                cur.execute("SELECT escuela_id FROM escuela WHERE nombre=%s LIMIT 1", (escuela,))
                e = cur.fetchone()
                if not e:
                    cur.execute("INSERT INTO escuela (nombre) VALUES (%s)", (escuela,))
                    conn.commit()
                    cur.execute("SELECT LAST_INSERT_ID() AS id")
                    e = {"escuela_id": cur.fetchone()["id"]}
                escuela_id = e["escuela_id"]

                # Grado (opcional)
                grado_id = None
                if grado:
                    cur.execute("SELECT grado_id FROM grado WHERE nombre=%s LIMIT 1", (grado,))
                    g = cur.fetchone()
                    if not g:
                        cur.execute("INSERT INTO grado (nombre) VALUES (%s)", (grado,))
                        conn.commit()
                        cur.execute("SELECT LAST_INSERT_ID() AS id")
                        g = {"grado_id": cur.fetchone()["id"]}
                    grado_id = g["grado_id"]

                # Curso (opcional pero recomendado)
                curso_id = None
                if curso:
                    cur.execute("""
                        SELECT curso_id FROM curso
                        WHERE nombre=%s AND escuela_id=%s LIMIT 1
                    """, (curso, escuela_id))
                    c = cur.fetchone()
                    if not c:
                        # Si no existe, lo creamos con un profesor genérico (o NULL si tu esquema lo permite)
                        # Como tu curso requiere profesor_id, elegimos cualquiera de la escuela o creamos uno.
                        cur.execute("SELECT profesor_id FROM profesor WHERE escuela_id=%s LIMIT 1", (escuela_id,))
                        p = cur.fetchone()
                        if not p:
                            cur.execute("INSERT INTO profesor (nombre, escuela_id) VALUES (%s,%s)", ("Profesor Generico", escuela_id))
                            conn.commit()
                            cur.execute("SELECT LAST_INSERT_ID() AS id")
                            p = {"profesor_id": cur.fetchone()["id"]}
                        cur.execute("""
                            INSERT INTO curso (nombre, escuela_id, profesor_id, grado_id)
                            VALUES (%s, %s, %s, %s)
                        """, (curso, escuela_id, p["profesor_id"], grado_id))
                        conn.commit()
                        cur.execute("SELECT LAST_INSERT_ID() AS id")
                        c = {"curso_id": cur.fetchone()["id"]}
                    curso_id = c["curso_id"]

                # Alumno (upsert por CURP)
                cur.execute("SELECT alumno_id FROM alumno WHERE curp=%s", (curp,))
                a = cur.fetchone()
                if not a:
                    cur.execute("""
                        INSERT INTO alumno (nombre, curp, escuela_id, grado_id)
                        VALUES (%s, %s, %s, %s)
                    """, (nombre, curp, escuela_id, grado_id))
                    conn.commit()
                    cur.execute("SELECT LAST_INSERT_ID() AS id")
                    a = {"alumno_id": cur.fetchone()["id"]}
                else:
                    cur.execute("""
                        UPDATE alumno SET nombre=%s, escuela_id=%s, grado_id=%s
                        WHERE alumno_id=%s
                    """, (nombre, escuela_id, grado_id, a["alumno_id"]))
                    conn.commit()
                alumno_id = a["alumno_id"]

                # Inscripción al curso (si hay)
                if curso_id:
                    cur.execute("""
                        INSERT INTO inscripcion (alumno_id, curso_id)
                        VALUES (%s, %s)
                        ON DUPLICATE KEY UPDATE curso_id=VALUES(curso_id)
                    """, (alumno_id, curso_id))
                    conn.commit()

                resultados.append({"fila": idx, "curp": curp, "status": "OK", "detalle": "Insertado/actualizado"})
            except Exception as ex:
                conn.rollback()
                resultados.append({"fila": idx, "curp": curp, "status": "ERROR", "detalle": str(ex)})

    finally:
        conn.close()

    # Arma tabla de resultados
    filas = "".join(
        f"<tr><td>{r['fila']}</td><td><code>{r['curp']}</code></td><td>{r['status']}</td><td>{r['detalle']}</td></tr>"
        for r in resultados
    ) or "<tr><td colspan='4'>Sin filas</td></tr>"

    body = f"""
    <h1>Carga masiva de alumnos</h1>
    <div class="card">
      <div class="row" style="display:flex; gap:10px; align-items:center;">
        <a class="btn" href="/admin/carga?token={token}">Volver</a>
        <a class="btn" href="/admin/pdfs?token={token}">Ir a diplomas</a>
        <a class="btn" href="/admin/generar?token={token}">⚙️ Crear y regenerar</a>
      </div>
      <hr/>
      <table class="tbl">
        <thead><tr><th>Fila</th><th>CURP</th><th>Resultado</th><th>Detalle</th></tr></thead>
        <tbody>{filas}</tbody>
      </table>
    </div>
    """
    return HTMLResponse(_html_layout(body))
