import os
import mysql.connector
from mysql.connector import Error

def get_db_connection():
    """Crea una conexión MySQL usando las variables de entorno."""
    try:
        connection = mysql.connector.connect(
            host=os.getenv("DB_HOST"),
            user=os.getenv("DB_USER"),
            password=os.getenv("DB_PASSWORD"),
            database=os.getenv("DB_NAME"),
            port=os.getenv("DB_PORT")
        )
        if connection.is_connected():
            print("✅ Conectado correctamente a MySQL")
            return connection
    except Error as e:
        print("⚠️ Error de conexión MySQL:", e)
        return None
