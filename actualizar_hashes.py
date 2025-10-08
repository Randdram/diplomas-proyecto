import os, re, hashlib, mysql.connector as m
from dotenv import load_dotenv
load_dotenv()

DB = dict(
    host=os.getenv("DB_HOST"), port=int(os.getenv("DB_PORT")),
    user=os.getenv("DB_USER"), password=os.getenv("DB_PASSWORD"),
    database=os.getenv("DB_NAME"),
)

PATRON = re.compile(r"^DIPLOMA_(\d+)_(.{36})\.pdf$", re.I)

def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1<<20), b""):
            h.update(chunk)
    return h.hexdigest()

def main():
    out_dir = os.path.join(os.getcwd(), "out")
    if not os.path.isdir(out_dir):
        print("No existe la carpeta 'out'.")
        return
    conn = m.connect(**DB)
    cur = conn.cursor()
    n = 0
    for fname in os.listdir(out_dir):
        mobj = PATRON.match(fname)
        if not mobj:
            continue
        alumno_id, folio = mobj.groups()
        full = os.path.join(out_dir, fname)
        hash_hex = sha256_file(full)
        cur.execute("UPDATE diploma SET hash_sha256=%s WHERE folio=%s", (hash_hex, folio))
        if cur.rowcount:
            n += 1
            print(f"Actualizado hash de {fname}")
    conn.commit()
    cur.close(); conn.close()
    print(f"Actualizados {n} registro(s).")

if __name__ == "__main__":
    main()
