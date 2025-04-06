"""
سكريبت لإنشاء جداول قاعدة البيانات وإضافة مستخدم مشرف افتراضي
"""
from flask import Flask
from models import db, User, Transaction
import os

app = Flask(__name__)

# استخدام قاعدة بيانات SQLite المحلية
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///metabit_safty_db.sqlite'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.secret_key = 'wallet_sms_analyzer_secret_key'

db.init_app(app)

def create_tables_and_admin():
    """إنشاء جداول قاعدة البيانات وإضافة مستخدم مشرف افتراضي"""
    with app.app_context():
        # إنشاء جميع الجداول
        print("إنشاء جداول قاعدة البيانات...")
        try:
            db.create_all()
            print("تم إنشاء جميع الجداول بنجاح")
        except Exception as e:
            print(f"خطأ أثناء إنشاء الجداول: {e}")
            return
        
        # إضافة مستخدم مشرف افتراضي
        try:
            # التحقق من وجود المستخدم
            admin = User.query.filter_by(username='admin').first()
            if not admin:
                admin = User(
                    username='admin',
                    email='admin@example.com',
                    is_admin=True
                )
                admin.set_password('admin123')
                db.session.add(admin)
                db.session.commit()
                print("تم إنشاء مستخدم مشرف افتراضي:")
                print("اسم المستخدم: admin")
                print("كلمة المرور: admin123")
            else:
                print("المستخدم المشرف موجود بالفعل")
        except Exception as e:
            db.session.rollback()
            print(f"خطأ أثناء إنشاء المستخدم المشرف: {e}")

if __name__ == "__main__":
    create_tables_and_admin()
