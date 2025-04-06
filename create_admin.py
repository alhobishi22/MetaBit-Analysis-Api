"""
سكريبت لإنشاء حساب المشرف الأول في النظام
"""
import os
import sys
from getpass import getpass
from flask import Flask
from models import db, User

app = Flask(__name__)
app.config.from_object('config')
db.init_app(app)

def create_admin():
    """إنشاء حساب المشرف الأول."""
    with app.app_context():
        # التحقق مما إذا كان هناك مستخدمين مسبقاً
        if User.query.count() > 0:
            print("يوجد مستخدمين بالفعل في النظام. استخدم الواجهة لإنشاء المزيد.")
            sys.exit(1)
        
        print("إنشاء حساب المشرف الأول")
        print("-" * 30)
        
        # جمع بيانات المستخدم
        username = input("اسم المستخدم: ")
        if not username:
            print("يجب إدخال اسم المستخدم")
            sys.exit(1)
            
        email = input("البريد الإلكتروني: ")
        if not email or '@' not in email:
            print("يجب إدخال بريد إلكتروني صحيح")
            sys.exit(1)
            
        password = getpass("كلمة المرور: ")
        if not password or len(password) < 8:
            print("يجب أن تكون كلمة المرور 8 أحرف على الأقل")
            sys.exit(1)
            
        confirm_password = getpass("تأكيد كلمة المرور: ")
        if password != confirm_password:
            print("كلمتا المرور غير متطابقتين")
            sys.exit(1)
            
        # إنشاء المستخدم في قاعدة البيانات
        user = User(username=username, email=email, is_admin=True)
        user.set_password(password)
        
        db.session.add(user)
        db.session.commit()
        
        print("\nتم إنشاء حساب المشرف بنجاح:")
        print(f"اسم المستخدم: {username}")
        print(f"البريد الإلكتروني: {email}")
        print("يمكنك الآن تسجيل الدخول باستخدام هذه البيانات.")

if __name__ == '__main__':
    create_admin()
