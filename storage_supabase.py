# storage_supabase.py
import os
import uuid
import mimetypes
import requests
from pathlib import Path

# Carga .env automáticamente
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass  # si no está python-dotenv, no rompemos; pero entonces dependerás del entorno

# === Lee variables ===
SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")
SUPABASE_BUCKET = os.getenv("SUPABASE_BUCKET", "diplomas")  # por si no está, usa "diplomas"

# Endpoints de Storage v1
STORAGE_BASE = f"{SUPABASE_URL}/storage/v1"
OBJECT_URL = f"{STORAGE_BASE}/object"  # subir/bajar
PUBLIC_BASE = f"{OBJECT_URL}/public"   # si el bucket es público, las URL públicas salen de aquí

def _assert_env():
    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        raise RuntimeError("Faltan variables SUPABASE_URL o SUPABASE_SERVICE_KEY en el .env")

def supa_check() -> dict:
    """
    Devuelve información útil para comprobar configuración.
    """
    _assert_env()
    return {
        "url": SUPABASE_URL,
        "bucket": SUPABASE_BUCKET,
        "has_key": bool(SUPABASE_SERVICE_KEY),
        "object_url": OBJECT_URL,
        "public_base": f"{PUBLIC_BASE}/{SUPABASE_BUCKET}",
    }

def _auth_headers(extra: dict | None = None):
    _assert_env()
    base = {
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
        "apikey": SUPABASE_SERVICE_KEY,
    }
    if extra:
        base.update(extra)
    return base

def upload_pdf(local_path: str, dest_name: str | None = None, bucket: str | None = None, upsert: bool = True) -> str:
    """
    Sube un PDF desde un archivo local. (Ahora es una función de conveniencia).
    """
    p = Path(local_path)
    if not p.exists():
        raise FileNotFoundError(f"No existe el archivo: {local_path}")

    with open(p, "rb") as f:
        data = f.read()

    # Llama a la nueva función para hacer el trabajo real
    return upload_pdf_from_bytes(data, dest_name or p.name, bucket, upsert)

# ====================================================================
# ESTA ES LA FUNCIÓN CLAVE QUE FALTABA
# ====================================================================
def upload_pdf_from_bytes(data: bytes, dest_name: str, bucket: str | None = None, upsert: bool = True) -> str:
    """
    Sube los bytes de un PDF a Supabase Storage y devuelve la URL pública.
    Esta función es para subidas desde memoria, sin archivos locales.
    """
    bucket = bucket or SUPABASE_BUCKET
    _assert_env()

    if not dest_name:
        dest_name = f"{uuid.uuid4()}.pdf"

    # POST/PUT a /object/{bucket}/{dest_name}
    url = f"{OBJECT_URL}/{bucket}/{dest_name}"
    headers = _auth_headers({
        "Content-Type": "application/pdf",
        "x-upsert": "true" if upsert else "false",
    })
    resp = requests.post(url, headers=headers, data=data, timeout=60)

    # Respuestas válidas: 200/201/204
    if resp.status_code not in (200, 201, 204):
        raise RuntimeError(f"Error al subir a Supabase: {resp.status_code} {resp.text}")

    # Construimos URL pública (asumiendo bucket público)
    public_url = f"{PUBLIC_BASE}/{bucket}/{dest_name}"
    return public_url
# ====================================================================

def delete_object(path: str, bucket: str | None = None) -> bool:
    """
    Elimina un objeto del bucket. `path` es la ruta dentro del bucket (ej. 'alumnos/folio.pdf').
    """
    bucket = bucket or SUPABASE_BUCKET
    _assert_env()

    url = f"{STORAGE_BASE}/object/{bucket}/{path}"
    resp = requests.delete(url, headers=_auth_headers(), timeout=30)
    return resp.status_code in (200, 204)

def make_public(path: str, bucket: str | None = None) -> str:
    """
    Si el bucket es público, basta con construir la URL pública. Devuelve esa URL.
    (En Supabase, la 'publicidad' se configura a nivel de bucket).
    """
    bucket = bucket or SUPABASE_BUCKET
    _assert_env()
    return f"{PUBLIC_BASE}/{bucket}/{path}"