"""
ملف إعدادات تطبيق MetaBitAnalysis
"""
import os

# إعدادات التطبيق
DEBUG = True
SECRET_KEY = 'wallet_sms_analyzer_secret_key'

# إعدادات قاعدة البيانات
SQLALCHEMY_DATABASE_URI = 'postgresql://metabit_safty_db_user:i7jQbcMMM2sg7k12PwweDO1koIUd3ppF@dpg-cvc9e8bv2p9s73ad9g5g-a.singapore-postgres.render.com/metabit_safty_db'
SQLALCHEMY_TRACK_MODIFICATIONS = False

# إعدادات API
API_KEY = os.environ.get('API_KEY', 'MetaBit_API_Key_24X7')  # للإنتاج، استخدم متغيرات البيئة
API_RATE_LIMIT = 100  # عدد الطلبات المسموح بها في الدقيقة
