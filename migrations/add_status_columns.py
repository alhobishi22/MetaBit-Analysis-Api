import os
import sys
import psycopg2
from psycopg2 import sql
from dotenv import load_dotenv

# Cargar variables de entorno
load_dotenv()

# Configuración de la base de datos
DB_URI = 'postgresql://metabit_safty_db_user:i7jQbcMMM2sg7k12PwweDO1koIUd3ppF@dpg-cvc9e8bv2p9s73ad9g5g-a.singapore-postgres.render.com/metabit_safty_db'

def add_columns():
    """Agregar columnas de estado y ejecutado_por a la tabla de transacciones."""
    try:
        # Conectar a la base de datos
        conn = psycopg2.connect(DB_URI)
        cur = conn.cursor()
        
        # Verificar si las columnas ya existen
        cur.execute("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'transactions' 
            AND column_name IN ('status', 'executed_by')
        """)
        existing_columns = [col[0] for col in cur.fetchall()]
        
        # Agregar columna de estado si no existe
        if 'status' not in existing_columns:
            print("Agregando columna 'status'...")
            cur.execute("""
                ALTER TABLE transactions 
                ADD COLUMN status VARCHAR(20) DEFAULT 'pending'
            """)
            print("✅ Columna 'status' agregada correctamente.")
        else:
            print("⚠️ La columna 'status' ya existe.")
        
        # Agregar columna de ejecutado_por si no existe
        if 'executed_by' not in existing_columns:
            print("Agregando columna 'executed_by'...")
            cur.execute("""
                ALTER TABLE transactions 
                ADD COLUMN executed_by VARCHAR(100)
            """)
            print("✅ Columna 'executed_by' agregada correctamente.")
        else:
            print("⚠️ La columna 'executed_by' ya existe.")
        
        # Confirmar los cambios
        conn.commit()
        print("✅ Migración completada con éxito.")
        
    except Exception as e:
        print(f"❌ Error al ejecutar la migración: {e}")
        conn.rollback()
    finally:
        # Cerrar la conexión
        if conn:
            cur.close()
            conn.close()

if __name__ == "__main__":
    print("Iniciando migración para agregar columnas de estado y ejecutado_por...")
    add_columns()
