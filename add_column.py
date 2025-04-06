from app import db, app
from models import Transaction
from sqlalchemy import text

with app.app_context():
    try:
        # Add the is_confirmed_db column if it doesn't exist (PostgreSQL syntax)
        with db.engine.connect() as connection:
            # Primero verificamos si la columna ya existe
            check_query = text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name='transactions' 
                AND column_name='is_confirmed_db'
            """)
            result = connection.execute(check_query)
            column_exists = result.fetchone() is not None
            
            # Si la columna no existe, la agregamos
            if not column_exists:
                connection.execute(text("""
                    ALTER TABLE transactions 
                    ADD COLUMN is_confirmed_db BOOLEAN DEFAULT FALSE
                """))
                connection.commit()
                print("تم إضافة عمود is_confirmed_db بنجاح")
            else:
                print("العمود is_confirmed_db موجود بالفعل")
    except Exception as e:
        print(f"حدث خطأ: {str(e)}")
