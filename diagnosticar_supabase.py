# diagnosticar_supabase.py
#!/usr/bin/env python3
"""
Diagnostica la conexión con Supabase
"""

import os
import requests
from dotenv import load_dotenv

load_dotenv()

def diagnosticar_supabase():
    print("🔍 DIAGNÓSTICO DE SUPABASE\n")
    
    # Verificar variables de entorno
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_SERVICE_KEY")
    supabase_public = os.getenv("SUPABASE_PUBLIC_BASE")
    
    print("1. 📋 Variables de entorno:")
    print(f"   SUPABASE_URL: {'✅' if supabase_url else '❌'} {'Configurada' if supabase_url else 'FALTANTE'}")
    print(f"   SUPABASE_SERVICE_KEY: {'✅' if supabase_key else '❌'} {'Configurada' if supabase_key else 'FALTANTE'}")
    print(f"   SUPABASE_PUBLIC_BASE: {'✅' if supabase_public else '❌'} {'Configurada' if supabase_public else 'FALTANTE'}")
    
    if not all([supabase_url, supabase_key, supabase_public]):
        print("\n❌ Faltan variables de Supabase en el entorno")
        return False
    
    # Probar conexión a Supabase
    print("\n2. 🔌 Probando conexión a Supabase...")
    try:
        from supabase import create_client, Client
        
        supabase: Client = create_client(supabase_url, supabase_key)
        
        # Intentar listar buckets (operación simple)
        response = supabase.storage.list_buckets()
        
        if hasattr(response, 'error') and response.error:
            print(f"   ❌ Error de Supabase: {response.error}")
            return False
        else:
            print("   ✅ Conexión a Supabase: EXITOSA")
            print(f"   📦 Buckets disponibles: {len(response) if response else 0}")
            
            # Verificar bucket específico
            buckets = [bucket.name for bucket in response] if response else []
            if "diplomas" in buckets:
                print("   ✅ Bucket 'diplomas': ENCONTRADO")
                
                # Listar archivos en el bucket
                files_response = supabase.storage.from_("diplomas").list()
                if files_response:
                    print(f"   📄 Archivos en bucket: {len(files_response)}")
                    for file in files_response[:3]:  # Mostrar primeros 3
                        print(f"      - {file['name']}")
                else:
                    print("   📄 Archivos en bucket: 0 (vacío)")
            else:
                print("   ❌ Bucket 'diplomas': NO ENCONTRADO")
                
            return True
            
    except Exception as e:
        print(f"   ❌ Error de conexión: {e}")
        return False

def diagnosticar_urls_bd():
    """Diagnostica las URLs en la base de datos"""
    print("\n3. 🗄️ Diagnóstico de URLs en Base de Datos:")
    
    import mysql.connector
    
    try:
        conn = mysql.connector.connect(
            host=os.getenv("DB_HOST"),
            port=int(os.getenv("DB_PORT", "3306")),
            user=os.getenv("DB_USER"),
            password=os.getenv("DB_PASSWORD"),
            database=os.getenv("DB_NAME")
        )
        cur = conn.cursor(dictionary=True)
        
        # Contar tipos de URLs
        cur.execute("""
            SELECT 
                COUNT(*) as total,
                SUM(CASE WHEN pdf_url LIKE 'http%' THEN 1 ELSE 0 END) as supabase_urls,
                SUM(CASE WHEN pdf_url LIKE '/pdfs/%' THEN 1 ELSE 0 END) as local_urls,
                SUM(CASE WHEN pdf_url IS NULL OR pdf_url = '' THEN 1 ELSE 0 END) as sin_url
            FROM diploma
        """)
        stats = cur.fetchone()
        
        print(f"   📊 Total diplomas: {stats['total']}")
        print(f"   🔗 URLs Supabase: {stats['supabase_urls']}")
        print(f"   📁 URLs locales: {stats['local_urls']}")
        print(f"   ❌ Sin URL: {stats['sin_url']}")
        
        # Mostrar ejemplos
        cur.execute("SELECT folio, pdf_url FROM diploma LIMIT 3")
        ejemplos = cur.fetchall()
        
        print(f"\n   📝 Ejemplos de URLs:")
        for ej in ejemplos:
            tipo = "Supabase" if ej['pdf_url'] and ej['pdf_url'].startswith('http') else "Local" if ej['pdf_url'] else "Ninguna"
            print(f"      - {ej['folio'][:8]}...: {tipo}")
        
        cur.close()
        conn.close()
        
        return stats['supabase_urls'] > 0
        
    except Exception as e:
        print(f"   ❌ Error BD: {e}")
        return False

def main():
    print("🚀 DIAGNÓSTICO COMPLETO DEL SISTEMA\n")
    
    supabase_ok = diagnosticar_supabase()
    bd_ok = diagnosticar_urls_bd()
    
    print(f"\n📊 RESUMEN:")
    print(f"   Supabase: {'✅ CONECTADO' if supabase_ok else '❌ PROBLEMAS'}")
    print(f"   URLs en BD: {'✅ SUPABASE' if bd_ok else '❌ LOCALES/VACÍAS'}")
    
    if supabase_ok and bd_ok:
        print("\n🎉 El sistema está configurado correctamente para Supabase")
        print("   Las descargas deberían funcionar en producción")
    else:
        print("\n🔧 PROBLEMAS IDENTIFICADOS:")
        if not supabase_ok:
            print("   - Supabase no está configurado o no conecta")
        if not bd_ok:
            print("   - Las URLs en la BD no son de Supabase")
        
        print(f"\n🎯 SOLUCIÓN: Ejecuta 'python sincronizar_supabase.py'")

if __name__ == "__main__":
    main()