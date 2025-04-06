from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, make_response
from flask_bootstrap import Bootstrap
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
import datetime
import json
import os
import re
import pytz
from babel.dates import format_datetime
from flask_cors import CORS
import pandas as pd
from datetime import datetime
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from io import BytesIO
import base64
from models import db, Transaction, User
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, BooleanField, SubmitField
from wtforms.validators import DataRequired, Email, Length, EqualTo
from functools import wraps

app = Flask(__name__)
app.config.from_object('config')
app.secret_key = 'wallet_sms_analyzer_secret_key'
app.config['UPLOAD_FOLDER'] = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')

# إعداد Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = 'يرجى تسجيل الدخول للوصول إلى هذه الصفحة'
login_manager.login_message_category = 'info'

# Configure PostgreSQL database
app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://metabit_safty_db_user:i7jQbcMMM2sg7k12PwweDO1koIUd3ppF@dpg-cvc9e8bv2p9s73ad9g5g-a.singapore-postgres.render.com/metabit_safty_db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# تهيئة قاعدة البيانات وأداة الترحيل
db.init_app(app)
migrate = Migrate(app, db)

# إعداد CORS للسماح بالطلبات من نطاقات محددة
CORS(app, resources={r"/api/*": {"origins": "*"}})  # في الإنتاج، قم بتحديد النطاقات بدلاً من "*"

# مفتاح API السري - في الإنتاج، يجب تخزينه في متغيرات البيئة أو ملف التهيئة
API_KEY = "MetaBit_API_Key_24X7"

# Define wallet types
WALLET_TYPES = ['Jaib', 'Jawali', 'Cash', 'KuraimiIMB', 'ONE Cash']

# تكوين منطقة التوقيت لليمن
YEMEN_TIMEZONE = pytz.timezone('Asia/Aden')

# دالة مساعدة لتنسيق التاريخ والوقت بتوقيت اليمن
def format_yemen_datetime(dt_str=None):
    """تنسيق التاريخ والوقت حسب توقيت اليمن"""
    if dt_str:
        try:
            dt = datetime.strptime(dt_str, '%Y-%m-%d %H:%M:%S')
            dt = pytz.utc.localize(dt).astimezone(YEMEN_TIMEZONE)
        except:
            return dt_str
    else:
        dt = datetime.now(YEMEN_TIMEZONE)
    
    return format_datetime(dt, format='dd/MM/yyyy hh:mm:ss a', locale='ar_YE')

# إضافة دالة مساعدة لاستخدامها في القوالب
@app.template_filter('yemen_time')
def yemen_time_filter(dt_str):
    """تحويل التاريخ والوقت إلى تنسيق 12 ساعة"""
    try:
        dt = datetime.strptime(dt_str, '%Y-%m-%d %H:%M:%S')
        # تحويل إلى توقيت اليمن
        dt = dt.replace(tzinfo=pytz.UTC).astimezone(YEMEN_TIMEZONE)
        # تنسيق بنظام 12 ساعة مع إظهار ص/م
        return dt.strftime('%I:%M:%S %p %d/%m/%Y')
    except:
        return dt_str

# Define currency symbols and codes
CURRENCIES = {
    'ر.ي': 'YER',
    'ر.س': 'SAR',
    'د.أ': 'USD'
}

# Ensure the data directory exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# إضافة متغير now تلقائياً إلى جميع القوالب
@app.context_processor
def inject_now():
    """تضمين متغير التاريخ الحالي في جميع القوالب تلقائياً."""
    return {'now': datetime.now()}

# دالة مساعدة لتحليل رسائل SMS
def parse_jaib_sms(message):
    """Parse SMS messages from Jaib wallet."""
    transaction = {}
    
    # Check if it's a credit or debit transaction
    if 'اضيف' in message:
        transaction['type'] = 'credit'
        amount_pattern = r'اضيف (\d+(?:\.\d+)?)([^م]+)'
    elif 'خصم' in message:
        transaction['type'] = 'debit'
        amount_pattern = r'خصم (\d+(?:\.\d+)?)([^م]+)'
    else:
        return None
    
    # Extract amount and currency
    amount_match = re.search(amount_pattern, message)
    if amount_match:
        transaction['amount'] = float(amount_match.group(1))
        currency_raw = amount_match.group(2).strip()
        transaction['currency'] = CURRENCIES.get(currency_raw, currency_raw)
    
    # Extract balance
    balance_match = re.search(r'رص:(\d+(?:\.\d+)?)([^م]+)', message)
    if balance_match:
        transaction['balance'] = float(balance_match.group(1))
        balance_currency_raw = balance_match.group(2).strip()
        transaction['balance_currency'] = CURRENCIES.get(balance_currency_raw, balance_currency_raw)
    
    # Extract transaction details
    if 'مقابل' in message:
        details_match = re.search(r'مقابل ([^ر]+)', message)
        if details_match:
            transaction['details'] = details_match.group(1).strip()
    
    # Extract recipient/sender if available
    if 'من' in message and 'مقابل' in message:
        sender_match = re.search(r'من (.+?)(?:$|\n)', message)
        if sender_match:
            transaction['counterparty'] = sender_match.group(1).strip()
    elif 'الى' in message:
        recipient_match = re.search(r'الى (.+?)(?:$|\n)', message)
        if recipient_match:
            transaction['counterparty'] = recipient_match.group(1).strip()
    
    return transaction

def parse_jawali_sms(message):
    """Parse SMS messages from Jawali wallet."""
    transaction = {}
    
    if 'استلمت مبلغ' in message:
        transaction['type'] = 'credit'
        # Extract amount and currency
        amount_match = re.search(r'استلمت مبلغ (\d+(?:\.\d+)?) ([A-Z]+)', message)
        if amount_match:
            transaction['amount'] = float(amount_match.group(1))
            transaction['currency'] = amount_match.group(2)
        
        # Extract sender
        sender_match = re.search(r'من (\d+)', message)
        if sender_match:
            transaction['counterparty'] = sender_match.group(1)
        
        # Extract balance
        balance_match = re.search(r'رصيدك هو (\d+(?:\.\d+)?)', message)
        if balance_match:
            transaction['balance'] = float(balance_match.group(1))
            # Extract balance currency
            balance_currency_match = re.search(r'رصيدك هو \d+(?:\.\d+)? ([A-Z]+)', message)
            if balance_currency_match:
                transaction['balance_currency'] = balance_currency_match.group(1)
        
        transaction['details'] = 'استلام مبلغ'
    
    return transaction

import re  # تأكد من وجود هذا السطر في أعلى الملف

def parse_cash_sms(message):
    """Parse SMS messages from Cash wallet."""
    transaction = {}
    
    if 'إضافة' in message:
        transaction['type'] = 'credit'
        # استخراج المبلغ والعملة مع السماح بوجود مسافات اختيارية
        # تم تعديل التعبير النمطي هنا (مثلاً، السطر 5-6)
        amount_match = re.search(r'إضافة\s*(\d+(?:\.\d+)?)([^م]+)', message)
        if amount_match:
            transaction['amount'] = float(amount_match.group(1))
            transaction['currency'] = amount_match.group(2)
        
        # استخراج جهة الإرسال (المُرسِل)
        # تم تعديل التعبير النمطي للسماح بمسافات إضافية (مثلاً، السطر 9-10)
        sender_match = re.search(r'من\s+(.+?)\s+رصيدك', message)
        if sender_match:
            transaction['counterparty'] = sender_match.group(1).strip()
        
        # استخراج الرصيد والعملة الخاصة به
        # تم تعديل التعبير النمطي للسماح بمسافات اختيارية (مثلاً، السطر 13-14)
        balance_match = re.search(r'رصيدك\s*(\d+(?:\.\d+)?)\s*([A-Z]+)', message)
        if balance_match:
            transaction['balance'] = float(balance_match.group(1))
            transaction['balance_currency'] = balance_match.group(2)
        
        transaction['details'] = 'إضافة رصيد'
    
    elif 'سحب' in message:
        transaction['type'] = 'debit'
        # استخراج المبلغ والعملة عند السحب
        # تم تعديل التعبير النمطي للسماح بمسافات اختيارية (مثلاً، السطر 21-22)
        amount_match = re.search(r'سحب\s*(\d+(?:\.\d+)?)\s*([A-Z]+)', message)
        if amount_match:
            transaction['amount'] = float(amount_match.group(1))
            transaction['currency'] = amount_match.group(2)
        
        # استخراج الرصيد والعملة الخاصة به عند السحب
        # تم تعديل التعبير النمطي هنا أيضاً (مثلاً، السطر 25-26)
        balance_match = re.search(r'رصيدك\s*(\d+(?:\.\d+)?)\s*([A-Z]+)', message)
        if balance_match:
            transaction['balance'] = float(balance_match.group(1))
            transaction['balance_currency'] = balance_match.group(2)
        
        transaction['details'] = 'سحب رصيد'
    
    return transaction

def parse_kuraimi_sms(message):
    """Parse SMS messages from KuraimiIMB bank."""
    transaction = {}
    
    # Print debug information to diagnose forwardSMS issues
    print(f"جاري تحليل رسالة كريمي: {message}")
    
    # Check if it's a credit or debit transaction
    if 'أودع' in message:
        transaction['type'] = 'credit'
        # Extract sender
        sender_match = re.search(r'أودع/(.+?) لحسابك', message)
        if sender_match:
            transaction['counterparty'] = sender_match.group(1).strip()
        
        # Extract amount and currency - تحسين التعبير النمطي
        amount_match = re.search(r'لحسابك(\d+(?:[\.\,٫]\d+)?)\s*([A-Z]+)', message)
        if not amount_match:
            # صيغة بديلة بدون مسافات
            amount_match = re.search(r'لحسابك(\d+(?:[\.\,٫]\d+)?)([A-Z]+)', message)
        
        if amount_match:
            # Handle amount with decimal separator (both . and ٫)
            amount_str = amount_match.group(1).replace('٫', '.')
            transaction['amount'] = float(amount_str)
            transaction['currency'] = amount_match.group(2)
        
        # محاولة استخراج الرصيد بعدة صيغ مختلفة
        # الصيغة الأولى: رصيدك مباشرة متبوعًا بالرقم والعملة (مثل رصيدك1669521٫31YER)
        balance_match = re.search(r'رصيدك(\d+(?:[\.\,٫]\d+)?)([A-Z]+)', message)
        
        # إذا لم يجد الصيغة الأولى، نجرب الصيغة الثانية مع وجود مسافات محتملة
        if not balance_match:
            balance_match = re.search(r'رصيدك\s*(\d+(?:[\.\,٫]\d+)?)\s*([A-Z]+)', message)
        
        # إذا لم يجد أيضًا، نجرب الصيغة الثالثة بدون كلمة "رصيدك" (للعملات الأخرى)
        if not balance_match:
            balance_match = re.search(r'([A-Z]+)رصيدك\s*(\d+(?:[\.٫\,]\d+)?)', message)
            if balance_match:
                # في هذه الحالة ترتيب المجموعات مختلف
                balance_currency = balance_match.group(1)
                balance_str = balance_match.group(2).replace('٫', '.')
                try:
                    transaction['balance'] = float(balance_str)
                    transaction['balance_currency'] = balance_currency
                    print(f"تم استخراج الرصيد (الصيغة 3): {balance_str} {balance_currency}")
                except ValueError as e:
                    print(f"خطأ في تحويل الرصيد: {balance_str}, الخطأ: {e}")
                
                transaction['details'] = 'إيداع في الحساب'
                return transaction
        
        if balance_match:
            # Handle balance with decimal separator (both . and ٫)
            balance_str = balance_match.group(1).replace('٫', '.')
            try:
                transaction['balance'] = float(balance_str)
                transaction['balance_currency'] = balance_match.group(2)
                print(f"تم استخراج الرصيد: {balance_str} {balance_match.group(2)}")
            except ValueError as e:
                print(f"خطأ في تحويل الرصيد: {balance_str}, الخطأ: {e}")
        else:
            print(f"فشل في العثور على الرصيد في الرسالة: '{message}'")
        
        transaction['details'] = 'إيداع في الحساب'
    
    elif 'تم تحويل' in message:
        transaction['type'] = 'debit'
        # Extract amount - تحسين التعبير النمطي
        amount_match = re.search(r'تم تحويل(\d+(?:[\.\,٫]\d+)?)', message)
        if amount_match:
            # Handle amount with decimal separator (both . and ٫)
            amount_str = amount_match.group(1).replace('٫', '.')
            transaction['amount'] = float(amount_str)
        
        # Extract recipient - تحسين التعبير النمطي ليتعامل مع صيغ مختلفة
        recipient_match = re.search(r'لحساب (.+?) رصيدك', message)
        if not recipient_match:
            # صيغة بديلة بدون مسافات
            recipient_match = re.search(r'لحساب(.+?)رصيدك', message)
        
        if recipient_match:
            transaction['counterparty'] = recipient_match.group(1).strip()
        
        # Extract balance and currency - تحسين التعبير النمطي
        balance_match = re.search(r'رصيدك(\d+(?:[\.\,٫]\d+)?)([A-Z]+)', message)
        if not balance_match:
            # صيغة بديلة مع مسافات محتملة
            balance_match = re.search(r'رصيدك\s*(\d+(?:[\.\,٫]\d+)?)\s*([A-Z]+)', message)
        
        if balance_match:
            # Handle balance with decimal separator (both . and ٫)
            balance_str = balance_match.group(1).replace('٫', '.')
            transaction['balance'] = float(balance_str)
            transaction['balance_currency'] = balance_match.group(2)
            transaction['currency'] = balance_match.group(2)
        
        transaction['details'] = 'تحويل من الحساب'
        
        # Extract received date if available
        date_match = re.search(r'Received At: (.+)', message)
        if date_match:
            transaction['received_at'] = date_match.group(1).strip()
    
    return transaction

def parse_onecash_sms(message):
    """Parse SMS messages from ONE Cash wallet."""
    transaction = {}
    
    # Check if it's a credit transaction (received money)
    if 'استلمت' in message:
        transaction['type'] = 'credit'
        
        # Extract amount
        amount_match = re.search(r'استلمت ([0-9,.]+)', message)
        if amount_match:
            amount_str = amount_match.group(1).replace(',', '')
            transaction['amount'] = float(amount_str)
        
        # Extract sender
        sender_match = re.search(r'من (.+?)\n', message)
        if sender_match:
            transaction['counterparty'] = sender_match.group(1).strip()
        
        # Extract balance and currency
        balance_match = re.search(r'رصيدك([0-9,.]+) (ر\.ي)', message)
        if balance_match:
            balance_str = balance_match.group(1).replace(',', '')
            transaction['balance'] = float(balance_str)
            currency_raw = balance_match.group(2).strip()
            transaction['balance_currency'] = CURRENCIES.get(currency_raw, currency_raw)
            transaction['currency'] = CURRENCIES.get(currency_raw, currency_raw)
        
        transaction['details'] = 'استلام مبلغ'
    
    # Check if it's a debit transaction (sent money)
    elif 'حولت' in message:
        transaction['type'] = 'debit'
        
        # Extract amount
        amount_match = re.search(r'حولت([0-9,.]+)', message)
        if amount_match:
            amount_str = amount_match.group(1).replace(',', '')
            transaction['amount'] = float(amount_str)
        
        # Extract recipient
        recipient_match = re.search(r'لـ(.+?)\n', message)
        if recipient_match:
            transaction['counterparty'] = recipient_match.group(1).strip()
        
        # Extract fees if available
        fees_match = re.search(r'رسوم ([0-9,.]+)', message)
        if fees_match:
            transaction['fees'] = float(fees_match.group(1).replace(',', ''))
        
        # Extract balance and currency
        balance_match = re.search(r'رصيدك ([0-9,.]+)(ر\.ي)', message)
        if balance_match:
            balance_str = balance_match.group(1).replace(',', '')
            transaction['balance'] = float(balance_str)
            currency_raw = balance_match.group(2).strip()
            transaction['balance_currency'] = CURRENCIES.get(currency_raw, currency_raw)
            transaction['currency'] = CURRENCIES.get(currency_raw, currency_raw)
        
        transaction['details'] = 'تحويل مبلغ'
    
    return transaction

def parse_sms(sms_text):
    """Parse SMS text to extract transaction data."""
    transactions = []
    
    # Split the text into individual SMS messages
    sms_messages = re.split(r'\n\s*\n', sms_text)
    
    for message in sms_messages:
        if not message.strip():
            continue
        
        # Extract the wallet type from the "From:" line
        wallet_match = re.search(r'From: ([^\n]+)', message)
        if not wallet_match:
            continue
        
        wallet_name = wallet_match.group(1).strip()
        message_body = message.replace(wallet_match.group(0), '').strip()
        
        # اطبع اسم المحفظة ونص الرسالة للتشخيص
        print(f"محاولة تحليل رسالة من المحفظة: '{wallet_name}'")
        print(f"محتوى الرسالة: '{message_body[:50]}...'")
        
        transaction = None
        
        # تعديل طريقة التعرف على المحافظ لتكون أكثر مرونة
        if wallet_name == 'Jaib':
            transaction = parse_jaib_sms(message_body)
        elif wallet_name == 'Jawali':
            transaction = parse_jawali_sms(message_body)
        elif wallet_name == 'Cash':
            transaction = parse_cash_sms(message_body)
        elif wallet_name == 'KuraimiIMB':
            print("تحليل رسالة بنك الكريمي...")
            transaction = parse_kuraimi_sms(message_body)
        elif wallet_name == 'ONE Cash':
            print("تحليل رسالة ون كاش...")
            transaction = parse_onecash_sms(message_body)
        # تجربة تحديد نوع المحفظة من محتوى الرسالة إذا لم يتم التعرف عليها من الاسم
        else:
            if 'محفظة جيب' in message_body:
                transaction = parse_jaib_sms(message_body)
                wallet_name = 'Jaib'
            elif 'جوالي' in message_body:
                transaction = parse_jawali_sms(message_body)
                wallet_name = 'Jawali'
            elif 'كاش' in message_body and not 'ون كاش' in message_body:
                transaction = parse_cash_sms(message_body)
                wallet_name = 'Cash'
            elif 'الكريمي' in message_body or 'كريمي' in message_body:
                transaction = parse_kuraimi_sms(message_body)
                wallet_name = 'KuraimiIMB'
            elif 'ون كاش' in message_body or 'ONE' in message_body:
                transaction = parse_onecash_sms(message_body)
                wallet_name = 'ONE Cash'
            
        if transaction and all(key in transaction for key in ['amount', 'currency']):
            print(f"تم اكتشاف معاملة صالحة: {transaction}")
            
            # تنظيف قيمة العملة من المسافات الزائدة
            if 'currency' in transaction and transaction['currency']:
                transaction['currency'] = transaction['currency'].strip()
                
                # التأكد من أن العملة هي إحدى العملات المدعومة
                if transaction['currency'] not in ['YER', 'USD', 'SAR']:
                    print(f"عملة غير معروفة: {transaction['currency']}، سيتم استخدام YER بدلاً منها")
                    transaction['currency'] = 'YER'
            
            transaction['wallet'] = wallet_name
            transaction['raw_message'] = message
            transaction['timestamp'] = datetime.now(YEMEN_TIMEZONE).strftime('%Y-%m-%d %H:%M:%S')
            transactions.append(transaction)
        else:
            print(f"لم يتم اكتشاف معاملة صالحة من الرسالة")
    
    return transactions

def save_transactions(transactions):
    """Save transactions to the database."""
    count = 0
    
    # Get the latest transaction for each wallet/currency to check balance consistency
    latest_transactions = {}
    for wallet in WALLET_TYPES:
        latest_transactions[wallet] = {}
        for currency in ['YER', 'SAR', 'USD']:
            latest_tx = Transaction.query.filter_by(wallet=wallet, currency=currency).order_by(Transaction.timestamp.desc()).first()
            if latest_tx:
                latest_transactions[wallet][currency] = latest_tx.balance
            else:
                latest_transactions[wallet][currency] = 0
    
    for tx_data in transactions:
        # Create a new transaction object
        transaction = Transaction.from_dict(tx_data)
        
        # Add to database
        db.session.add(transaction)
        count += 1
    
    # Commit changes
    db.session.commit()
    
    return count

def load_transactions():
    """Load all transactions from the database."""
    transactions = Transaction.query.all()
    result = []
    for transaction in transactions:
        result.append({
            'id': transaction.id,
            'transaction_id': transaction.transaction_id,
            'wallet': transaction.wallet,
            'type': transaction.type,
            'amount': float(transaction.amount) if transaction.amount is not None else 0.0,
            'currency': transaction.currency,
            'details': transaction.details,
            'counterparty': transaction.counterparty,
            'balance': float(transaction.balance) if transaction.balance is not None else 0.0,
            'timestamp': transaction.timestamp.isoformat() if transaction.timestamp else None,
            'is_confirmed': transaction.is_confirmed
        })
    return result

def generate_transaction_summary(transactions):
    """Generate a summary of transactions organized by wallet and currency."""
    if not transactions:
        return None
    
    # Initialize summary structure
    summary = {
        wallet: {currency: {'credits': 0.0, 'debits': 0.0, 'net': 0.0} 
                for currency in ['YER', 'SAR', 'USD']}
        for wallet in WALLET_TYPES
    }
    
    # Process each transaction directly
    for tx in transactions:
        # Check if tx is a dict or SQLAlchemy object and extract fields accordingly
        if isinstance(tx, dict):
            wallet = tx.get('wallet')
            currency = tx.get('currency')
            tx_type = tx.get('type')
            tx_amount = tx.get('amount')
            tx_id = tx.get('id')
        else:
            wallet = tx.wallet
            currency = tx.currency
            tx_type = tx.type
            tx_amount = tx.amount
            tx_id = tx.id
        
        if wallet in summary and currency in summary[wallet]:
            try:
                amount = float(tx_amount) if tx_amount is not None else 0.0
                
                if tx_type == 'credit':
                    summary[wallet][currency]['credits'] += amount
                elif tx_type == 'debit':
                    summary[wallet][currency]['debits'] += amount
                
                # Recalculate net balance
                summary[wallet][currency]['net'] = summary[wallet][currency]['credits'] - summary[wallet][currency]['debits']
                
                # Debug output to help diagnose the issue
                print(f"Updated summary for {wallet}/{currency}: Credits={summary[wallet][currency]['credits']}, Debits={summary[wallet][currency]['debits']}, Net={summary[wallet][currency]['net']}")
            except (ValueError, TypeError) as e:
                print(f"Error processing transaction {tx_id}: {str(e)}")
    
    return summary

def generate_charts(transactions):
    """Generate charts for transaction visualization."""
    if not transactions:
        return {}
    
    df = pd.DataFrame(transactions)
    charts = {}
    
    # Ensure required columns exist
    required_columns = ['currency', 'type', 'amount']
    if not all(col in df.columns for col in required_columns):
        return charts
    
    # Transaction type distribution by currency
    plt.figure(figsize=(10, 6))
    for currency in df['currency'].unique():
        currency_df = df[df['currency'] == currency]
        
        # Count transactions by type
        type_counts = currency_df['type'].value_counts()
        
        plt.bar(
            [f"{currency} - {t}" for t in type_counts.index],
            type_counts.values
        )
    
    plt.title('Transaction Types by Currency')
    plt.xlabel('Currency - Transaction Type')
    plt.ylabel('Number of Transactions')
    plt.xticks(rotation=45)
    plt.tight_layout()
    
    # Save to BytesIO
    img_bytes = BytesIO()
    plt.savefig(img_bytes, format='png')
    img_bytes.seek(0)
    
    # Convert to base64 for embedding in HTML
    img_base64 = base64.b64encode(img_bytes.read()).decode('utf-8')
    charts['transaction_types'] = img_base64
    
    plt.close()
    
    # Amount distribution by currency and type
    plt.figure(figsize=(10, 6))
    
    # Group by currency and type, sum amounts
    if len(df) > 0:
        grouped = df.groupby(['currency', 'type'])['amount'].sum().unstack()
        grouped.plot(kind='bar', ax=plt.gca())
        
        plt.title('Transaction Amounts by Currency and Type')
        plt.xlabel('Currency')
        plt.ylabel('Total Amount')
        plt.legend(title='Transaction Type')
        plt.tight_layout()
        
        # Save to BytesIO
        img_bytes = BytesIO()
        plt.savefig(img_bytes, format='png')
        img_bytes.seek(0)
        
        # Convert to base64 for embedding in HTML
        img_base64 = base64.b64encode(img_bytes.read()).decode('utf-8')
        charts['amount_distribution'] = img_base64
    
    plt.close()
    
    return charts

def generate_wallet_charts(transactions):
    """Generate charts specifically for wallet analysis."""
    import matplotlib.pyplot as plt
    import matplotlib
    matplotlib.use('Agg')
    import io
    import base64
    import numpy as np
    from collections import defaultdict
    
    charts = {}
    
    # Skip chart generation if there are no transactions
    if not transactions:
        return {}
    
    # Set Arabic font for matplotlib
    plt.rcParams['font.family'] = 'sans-serif'
    plt.rcParams['font.sans-serif'] = ['Arial', 'DejaVu Sans', 'Liberation Sans', 'Bitstream Vera Sans', 'sans-serif']
    
    # Prepare data
    wallet_data = defaultdict(lambda: {'credit': 0, 'debit': 0, 'transactions': 0})
    currency_data = defaultdict(lambda: {'credit': 0, 'debit': 0, 'transactions': 0})
    
    for transaction in transactions:
        wallet = transaction.wallet
        currency = transaction.currency.strip() if transaction.currency else 'YER'
        
        # Ensure currency is supported, default to YER if not
        if currency not in ['YER', 'USD', 'SAR']:
            currency = 'YER'
        
        wallet_data[wallet]['transactions'] += 1
        currency_data[currency]['transactions'] += 1
        
        if transaction.type == 'credit':
            wallet_data[wallet]['credit'] += transaction.amount
            currency_data[currency]['credit'] += transaction.amount
        else:
            wallet_data[wallet]['debit'] += transaction.amount
            currency_data[currency]['debit'] += transaction.amount
    
    # Chart 1: Wallet Transaction Count
    plt.figure(figsize=(10, 6))
    wallets = list(wallet_data.keys())
    transaction_counts = [wallet_data[w]['transactions'] for w in wallets]
    
    plt.bar(wallets, transaction_counts, color='#2196F3')
    plt.title('عدد المعاملات حسب المحفظة')
    plt.xlabel('المحفظة')
    plt.ylabel('عدد المعاملات')
    plt.xticks(rotation=45)
    
    # Save chart to bytes
    img_bytes = io.BytesIO()
    plt.savefig(img_bytes, format='png', bbox_inches='tight')
    img_bytes.seek(0)
    
    # Convert to base64 for embedding in HTML
    img_base64 = base64.b64encode(img_bytes.read()).decode('utf-8')
    charts['wallet_transaction_count'] = img_base64
    
    plt.close()
    
    # Chart 2: Currency Transaction Count
    plt.figure(figsize=(10, 6))
    currencies = list(currency_data.keys())
    currency_counts = [currency_data[c]['transactions'] for c in currencies]
    
    plt.bar(currencies, currency_counts, color='#FF9800')
    plt.title('عدد المعاملات حسب العملة')
    plt.xlabel('العملة')
    plt.ylabel('عدد المعاملات')
    
    # Save chart to bytes
    img_bytes = io.BytesIO()
    plt.savefig(img_bytes, format='png', bbox_inches='tight')
    img_bytes.seek(0)
    
    # Convert to base64 for embedding in HTML
    img_base64 = base64.b64encode(img_bytes.read()).decode('utf-8')
    charts['currency_transaction_count'] = img_base64
    
    plt.close()
    
    # Chart 3: Wallet Credit vs Debit
    plt.figure(figsize=(12, 6))
    
    x = np.arange(len(wallets))
    width = 0.35
    
    credits = [wallet_data[w]['credit'] for w in wallets]
    debits = [wallet_data[w]['debit'] for w in wallets]
    
    plt.bar(x - width/2, credits, width, label='إيداع', color='#4CAF50')
    plt.bar(x + width/2, debits, width, label='سحب', color='#F44336')
    
    plt.xlabel('المحفظة')
    plt.ylabel('المبلغ')
    plt.title('الإيداعات والسحوبات حسب المحفظة')
    plt.xticks(x, wallets, rotation=45)
    plt.legend()
    
    # Save chart to bytes
    img_bytes = io.BytesIO()
    plt.savefig(img_bytes, format='png', bbox_inches='tight')
    img_bytes.seek(0)
    
    # Convert to base64 for embedding in HTML
    img_base64 = base64.b64encode(img_bytes.read()).decode('utf-8')
    charts['wallet_credit_debit'] = img_base64
    
    plt.close()
    
    return charts

@app.route('/')
@login_required
def index():
    """Render the home page."""
    try:
        # تعديل طريقة جلب المعاملات ليتم ترتيبها حسب التاريخ الأحدث
        transactions = Transaction.query.order_by(Transaction.timestamp.desc()).all()
        wallets = {}
        for transaction in transactions:
            if transaction.wallet not in wallets:
                wallets[transaction.wallet] = {'total': 0, 'currencies': {}}
            
            if transaction.currency not in wallets[transaction.wallet]['currencies']:
                wallets[transaction.wallet]['currencies'][transaction.currency] = 0
            
            wallets[transaction.wallet]['currencies'][transaction.currency] += 1
            wallets[transaction.wallet]['total'] += 1
        
        # Generate summary data for each wallet and currency
        summary = {}
        currencies = ['YER', 'SAR', 'USD']  # المفترضة لجميع المحافظ
        
        for wallet in WALLET_TYPES:
            summary[wallet] = {}
            
            # تهيئة جميع العملات بقيم افتراضية
            for currency in currencies:
                summary[wallet][currency] = {'credits': 0, 'debits': 0, 'net': 0}
                
            # تحديث البيانات للعملات التي لديها معاملات فعلية
            for transaction in [t for t in transactions if t.wallet == wallet]:
                # تنظيف قيمة العملة من المسافات الزائدة
                currency = transaction.currency.strip() if transaction.currency else 'YER'
                
                # التأكد من أن العملة موجودة في قائمة العملات المدعومة
                if currency not in currencies:
                    app.logger.warning(f"عملة غير معروفة: {currency}، سيتم استخدام YER بدلاً منها")
                    currency = 'YER'
                
                if transaction.type == 'credit':
                    summary[wallet][currency]['credits'] += transaction.amount
                else:
                    summary[wallet][currency]['debits'] += transaction.amount
                
                summary[wallet][currency]['net'] = (
                    summary[wallet][currency]['credits'] - 
                    summary[wallet][currency]['debits']
                )
        
        # Generate wallet charts
        charts = generate_wallet_charts(transactions)
        
        # Create response with proper headers to prevent caching
        response = make_response(render_template(
            'index.html',
            wallets=wallets,
            transactions=transactions,
            summary=summary,
            charts=charts,
            now=format_yemen_datetime()
        ))
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        return response
    except Exception as e:
        print(f"Error in index: {e}")
        return jsonify({
            'status': 'error',
            'message': f'Server error: {str(e)}'
        }), 500

@app.route('/wallet/<wallet_name>')
@login_required
def wallet(wallet_name):
    """Display wallet details and transactions."""
    if wallet_name not in WALLET_TYPES:
        flash('المحفظة غير موجودة', 'danger')
        return redirect(url_for('index'))
    
    # استخراج معلمات الفلترة من الطلب
    filter_type = request.args.get('type', '')  # نوع المعاملة (credit/debit)
    filter_currency = request.args.get('currency', '')  # العملة
    filter_date_from = request.args.get('date_from', '')  # تاريخ البداية
    filter_date_to = request.args.get('date_to', '')  # تاريخ النهاية
    filter_counterparty = request.args.get('counterparty', '')  # الطرف المقابل
    filter_amount_min = request.args.get('amount_min', '')  # الحد الأدنى للمبلغ
    filter_amount_max = request.args.get('amount_max', '')  # الحد الأقصى للمبلغ
    
    # Get transactions for this wallet - sort by timestamp ascending (oldest first) for processing
    query = Transaction.query.filter_by(wallet=wallet_name)
    
    # تطبيق الفلترة
    if filter_type:
        query = query.filter(Transaction.type == filter_type)
    if filter_currency:
        query = query.filter(Transaction.currency == filter_currency)
    if filter_counterparty:
        query = query.filter(Transaction.counterparty.ilike(f'%{filter_counterparty}%'))
    if filter_date_from:
        try:
            date_from = datetime.datetime.strptime(filter_date_from, '%Y-%m-%d')
            query = query.filter(Transaction.timestamp >= date_from)
        except ValueError:
            pass
    if filter_date_to:
        try:
            date_to = datetime.datetime.strptime(filter_date_to, '%Y-%m-%d')
            # Add one day to include the end date fully
            date_to = date_to + datetime.timedelta(days=1)
            query = query.filter(Transaction.timestamp < date_to)
        except ValueError:
            pass
    if filter_amount_min:
        try:
            amount_min = float(filter_amount_min)
            query = query.filter(Transaction.amount >= amount_min)
        except ValueError:
            pass
    if filter_amount_max:
        try:
            amount_max = float(filter_amount_max)
            query = query.filter(Transaction.amount <= amount_max)
        except ValueError:
            pass
    
    # تنفيذ الاستعلام وترتيب النتائج
    transactions = query.order_by(Transaction.timestamp.asc(), Transaction.id.asc()).all()
    
    print(f"===== تحليل تأكيد المعاملات لمحفظة {wallet_name} =====")
    
    # Initialize dictionary to store confirmation status
    confirmed_status = {}
    db_updates_needed = False
    
    # Group transactions by currency
    transactions_by_currency = {}
    for tx in transactions:
        if tx.currency not in transactions_by_currency:
            transactions_by_currency[tx.currency] = []
        transactions_by_currency[tx.currency].append(tx)
    
    # Process each currency separately
    for currency, txs in transactions_by_currency.items():
        print(f"\n----- العملة: {currency} -----")
        
        # First transaction for each currency is not confirmed (can't verify)
        if len(txs) > 0:
            first_tx = txs[0]
            confirmed_status[first_tx.id] = False
            
            # Update database if different
            if first_tx.is_confirmed_db != False:
                first_tx.is_confirmed_db = False
                db_updates_needed = True
                
            print(f"معاملة {first_tx.transaction_id}: أول معاملة للعملة {currency} - غير مؤكدة")
        
        # Process remaining transactions
        for i in range(1, len(txs)):
            current_tx = txs[i]
            prev_tx = txs[i-1]
            
            tx_code = getattr(current_tx, 'transaction_id', f"TX{current_tx.id}")
            
            # Get current balance and previous balance
            try:
                current_balance = float(current_tx.balance)
                prev_balance = float(prev_tx.balance)
                amount = float(current_tx.amount)
                
                # Calculate expected balance based on previous transaction
                if current_tx.type == 'credit':
                    expected_balance = prev_balance + amount
                else:  # debit
                    expected_balance = prev_balance - amount
                
                # Round values to prevent floating point precision issues
                current_balance = round(current_balance, 2)
                expected_balance = round(expected_balance, 2)
                
                # Compare with a small tolerance (0.01) as in the account-deteils project
                is_confirmed = abs(current_balance - expected_balance) <= 0.01
                confirmed_status[current_tx.id] = is_confirmed
                
                # Update database if different
                if current_tx.is_confirmed_db != is_confirmed:
                    current_tx.is_confirmed_db = is_confirmed
                    db_updates_needed = True
                
                if is_confirmed:
                    print(f"معاملة {tx_code}: مؤكدة - الرصيد المتوقع {expected_balance:.2f} يتطابق مع الرصيد الفعلي {current_balance:.2f}")
                else:
                    print(f"معاملة {tx_code}: غير مؤكدة - الرصيد المتوقع {expected_balance:.2f} لا يتطابق مع الرصيد الفعلي {current_balance:.2f}")
            
            except (ValueError, TypeError):
                confirmed_status[current_tx.id] = False
                
                # Update database if different
                if current_tx.is_confirmed_db != False:
                    current_tx.is_confirmed_db = False
                    db_updates_needed = True
                    
                print(f"معاملة {tx_code}: غير مؤكدة - خطأ في تحويل الرصيد إلى رقم")
    
    # Save changes to database if needed
    if db_updates_needed:
        try:
            db.session.commit()
            print("تم تحديث حالات التأكيد في قاعدة البيانات")
        except Exception as e:
            db.session.rollback()
            print(f"خطأ في تحديث قاعدة البيانات: {str(e)}")
    
    # Sort transactions by timestamp, then by id in descending order for display
    # This handles cases where timestamps are identical (common with imported data)
    sorted_transactions = sorted(
        transactions, 
        key=lambda x: (x.timestamp, x.id), 
        reverse=True
    )
    
    # Generate transaction summary
    summary = generate_transaction_summary(transactions)
    
    # Generate charts if there are transactions
    charts = None
    if transactions:
        charts = generate_charts(transactions)
    
    # Add a no-cache header to ensure the browser doesn't cache the response
    response = make_response(render_template('wallet.html', 
                                            wallet_name=wallet_name, 
                                            transactions=sorted_transactions, 
                                            summary=summary, 
                                            charts=charts, 
                                            confirmed_status=confirmed_status,
                                            # إضافة معلومات الفلترة إلى سياق القالب
                                            filter_applied=any([filter_type, filter_currency, filter_date_from, 
                                                               filter_date_to, filter_counterparty, 
                                                               filter_amount_min, filter_amount_max]),
                                            filter_count=len(transactions),
                                            now=format_yemen_datetime()))
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response

@app.route('/upload', methods=['POST'])
def upload():
    """Process uploaded SMS text."""
    sms_text = request.form.get('sms_text', '')
    
    if not sms_text:
        flash('No SMS text provided', 'error')
        return redirect(url_for('index'))
    
    transactions = parse_sms(sms_text)
    
    if not transactions:
        flash('No valid transactions found in the SMS text', 'warning')
        return redirect(url_for('index'))
    
    num_saved = save_transactions(transactions)
    flash(f'Successfully processed {num_saved} transactions', 'success')
    
    return redirect(url_for('index'))

@app.route('/upload/<wallet_name>', methods=['POST'])
@login_required
def upload_wallet(wallet_name):
    """Process uploaded SMS text for a specific wallet."""
    if wallet_name not in WALLET_TYPES:
        flash(f'محفظة غير معروفة: {wallet_name}', 'error')
        return redirect(url_for('index'))
    
    sms_text = request.form.get('sms_text', '')
    
    if not sms_text:
        flash('لم يتم توفير نص الرسائل', 'error')
        return redirect(url_for('wallet', wallet_name=wallet_name))
    
    # Add the wallet name to the beginning of each message if not already there
    lines = sms_text.split('\n')
    processed_lines = []
    
    for line in lines:
        if line.strip() and not line.startswith(f'From: {wallet_name}'):
            if not any(line.startswith(f'From: {w}') for w in WALLET_TYPES):
                processed_lines.append(f'From: {wallet_name} \n{line}')
            else:
                processed_lines.append(line)
        else:
            processed_lines.append(line)
    
    processed_sms = '\n'.join(processed_lines)
    
    transactions = parse_sms(processed_sms)
    
    if not transactions:
        flash('لم يتم العثور على معاملات صالحة في نص الرسائل', 'warning')
        return redirect(url_for('wallet', wallet_name=wallet_name))
    
    num_saved = save_transactions(transactions)
    flash(f'تمت معالجة {num_saved} معاملات بنجاح', 'success')
    
    return redirect(url_for('wallet', wallet_name=wallet_name))

@app.route('/clear', methods=['POST'])
def clear_data():
    """Clear all transaction data."""
    # Delete all transactions from the database
    Transaction.query.delete()
    db.session.commit()
    flash('All transaction data has been cleared', 'success')
    
    return redirect(url_for('index'))

@app.route('/clear/<wallet_name>', methods=['POST'])
@login_required
def clear_wallet_data(wallet_name):
    """Clear transaction data for a specific wallet."""
    if wallet_name not in WALLET_TYPES:
        flash(f'محفظة غير معروفة: {wallet_name}', 'error')
        return redirect(url_for('index'))
    
    # Delete transactions for the specified wallet from the database
    transactions_to_delete = Transaction.query.filter_by(wallet=wallet_name).all()
    for transaction in transactions_to_delete:
        db.session.delete(transaction)
    db.session.commit()
    flash(f'تم مسح جميع بيانات معاملات محفظة {wallet_name}', 'success')
    
    return redirect(url_for('wallet', wallet_name=wallet_name))

@app.route('/delete-transaction/<int:transaction_id>', methods=['POST'])
@login_required
def delete_transaction(transaction_id):
    """حذف معاملة محددة بواسطة معرفها"""
    wallet_name = None
    
    try:
        # البحث عن المعاملة بواسطة المعرف
        transaction = Transaction.query.get_or_404(transaction_id)
        wallet_name = transaction.wallet
        
        # حذف المعاملة
        db.session.delete(transaction)
        db.session.commit()
        
        flash('تم حذف المعاملة بنجاح.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'حدث خطأ أثناء حذف المعاملة: {str(e)}', 'danger')
        
    # إعادة التوجيه إلى صفحة المحفظة إذا كان wallet_name معروفًا، وإلا إلى الصفحة الرئيسية
    if wallet_name:
        return redirect(url_for('wallet', wallet_name=wallet_name))
    else:
        return redirect(url_for('index'))

@app.route('/update-transaction-status/<int:transaction_id>', methods=['POST'])
@login_required
def update_transaction_status(transaction_id):
    """تحديث حالة الطلب والمشرف الذي نفذ العملية"""
    try:
        # البحث عن المعاملة بواسطة المعرف
        transaction = Transaction.query.get_or_404(transaction_id)
        
        # الحصول على البيانات من النموذج
        status = request.form.get('status')
        executed_by = request.form.get('executed_by')
        is_confirmed = request.form.get('is_confirmed') == 'true'
        
        # التحقق من صحة البيانات
        if status not in Transaction.VALID_STATUSES:
            flash('حالة الطلب غير صالحة', 'danger')
            return redirect(url_for('wallet', wallet_name=transaction.wallet))
        
        # تحديث البيانات
        transaction.status = status
        transaction.executed_by = executed_by
        
        # تحديث حالة التأكيد إذا تم تغييرها
        if is_confirmed != transaction.is_confirmed_db:
            transaction.is_confirmed_db = is_confirmed
            app.logger.info(f"تم تحديث حالة التأكيد للمعاملة {transaction_id} إلى {is_confirmed}")
        
        db.session.commit()
        flash('تم تحديث حالة الطلب بنجاح', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'حدث خطأ أثناء تحديث حالة الطلب: {str(e)}', 'danger')
        
    # إعادة التوجيه إلى صفحة المحفظة
    return redirect(url_for('wallet', wallet_name=transaction.wallet))

@app.route('/export', methods=['GET'])
def export_data():
    """Export transaction data as JSON."""
    transactions = load_transactions()
    
    return jsonify(transactions)

@app.route('/forward-sms-setup')
def forward_sms_setup():
    """Render the Forward SMS setup guide page."""
    # تم إلغاء هذه الصفحة وإعادة توجيهها إلى الصفحة الرئيسية
    return redirect(url_for('index'))

@app.route('/api/receive-sms', methods=['POST', 'GET'])
def receive_sms():
    """Receive SMS from Forward SMS app."""
    print("=== RECEIVED REQUEST TO /api/receive-sms ===")
    print(f"Method: {request.method}")
    print(f"Headers: {dict(request.headers)}")
    print(f"Form data: {request.form}")
    print(f"Args: {request.args}")
    
    if request.is_json:
        print(f"JSON data: {request.get_json()}")
    
    try:
        if request.method == 'POST':
            # Get SMS data from request
            sms_text = None
            sender = None
            
            # Try to get the formatted text from JSON (as shown in the screenshot)
            if request.is_json:
                try:
                    data = request.get_json()
                    print(f"Processing JSON data: {data}")
                    
                    if 'text' in data:
                        formatted_text = data.get('text', '')
                        print(f"Found formatted text: {formatted_text}")
                        
                        # The format should be "From: {sender}<br>{msg}"
                        if '<br>' in formatted_text:
                            parts = formatted_text.split('<br>', 1)
                            if len(parts) == 2 and parts[0].startswith('From:'):
                                sender = parts[0].replace('From:', '').strip()
                                sms_text = parts[1].strip()
                                print(f"Successfully parsed formatted text - Sender: '{sender}', Text: '{sms_text}'")
                            else:
                                print(f"Formatted text doesn't match expected format: {formatted_text}")
                        else:
                            print(f"No <br> found in formatted text: {formatted_text}")
                except Exception as e:
                    print(f"Error parsing JSON: {e}")
            
            # If we couldn't extract from the formatted text, try other methods
            if not sms_text:
                # Check form data
                if request.form:
                    print(f"Processing form data: {request.form}")
                    sms_text = request.form.get('msg', '')
                    if not sms_text:
                        sms_text = request.form.get('text', '')
                    sender = request.form.get('sender', '')
                    
                    print(f"Extracted from form - Sender: '{sender}', Text: '{sms_text}'")
                
                # Check URL parameters
                if not sms_text:
                    sms_text = request.args.get('msg', '')
                    if not sms_text:
                        sms_text = request.args.get('text', '')
                    if not sender:
                        sender = request.args.get('sender', '')
                    
                    print(f"Extracted from URL params - Sender: '{sender}', Text: '{sms_text}'")
                
                # Check if data is in the request body but not parsed
                if not sms_text and request.data:
                    try:
                        # Try to parse as JSON
                        body_data = json.loads(request.data.decode('utf-8'))
                        print(f"Processing raw body data as JSON: {body_data}")
                        
                        if 'text' in body_data:
                            formatted_text = body_data.get('text', '')
                            if '<br>' in formatted_text:
                                parts = formatted_text.split('<br>', 1)
                                if len(parts) == 2 and parts[0].startswith('From:'):
                                    sender = parts[0].replace('From:', '').strip()
                                    sms_text = parts[1].strip()
                                    print(f"Successfully parsed formatted text from raw JSON - Sender: '{sender}', Text: '{sms_text}'")
                            else:
                                sms_text = body_data.get('msg', '')
                                sender = body_data.get('sender', '')
                                print(f"Extracted from raw JSON - Sender: '{sender}', Text: '{sms_text}'")
                    except Exception as e:
                        print(f"Error parsing request body: {e}")
            
            # Log final extracted data
            print(f"Final extracted data - Sender: '{sender}', Text: '{sms_text}'")
            
            if not sms_text:
                print("No SMS text found in request")
                return jsonify({
                    'status': 'error',
                    'message': 'No SMS text provided'
                }), 400
            
            # إذا كان sender لا يزال None، استخدم قيمة افتراضية
            if sender is None:
                sender = "Unknown"
                print(f"Using default sender: {sender}")
            
            # Try to detect wallet type from message content if sender is not recognized
            if sender not in WALLET_TYPES:
                # Check for Kuraimi patterns in the message
                if ('أودع' in sms_text or 'تم تحويل' in sms_text) and ('رصيدك' in sms_text or 'لحسابك' in sms_text):
                    if any(currency in sms_text for currency in ['SAR', 'YER', 'USD']):
                        print(f"Detected KuraimiIMB from message content, changing sender from '{sender}' to 'KuraimiIMB'")
                        sender = 'KuraimiIMB'
                # Check for ONE Cash patterns in the message
                elif ('استلمت' in sms_text or 'حولت' in sms_text) and 'ر.ي' in sms_text:
                    print(f"Detected ONE Cash from message content, changing sender from '{sender}' to 'ONE Cash'")
                    sender = 'ONE Cash'
            
            # Format the SMS in the expected format and clean any newlines or HTML characters
            sms_text = sms_text.replace('<br>', '\n').replace('&nbsp;', ' ')
            formatted_sms = f"From: {sender} \n{sms_text}"
            print(f"Formatted SMS for processing: {formatted_sms}")
            
            # Parse and save the SMS
            transactions = parse_sms(formatted_sms)
            print(f"Parsed transactions: {transactions}")
            
            if transactions:
                num_saved = save_transactions(transactions)
                return jsonify({
                    'status': 'success',
                    'message': f'Successfully processed {num_saved} transactions',
                    'transactions': transactions
                }), 200
            else:
                return jsonify({
                    'status': 'warning',
                    'message': 'No valid transactions found in the SMS'
                }), 200
    except Exception as e:
        print(f"Error in receive_sms: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'status': 'error',
            'message': f'Server error: {str(e)}'
        }), 500
    
    return jsonify({
        'status': 'error',
        'message': 'Invalid request'
    }), 400

# ====== واجهة برمجة التطبيقات (API) ======

# دالة مساعدة للتحقق من مفتاح API
def verify_api_key():
    """التحقق من صحة مفتاح API في رأس الطلب."""
    api_key = request.headers.get('X-API-KEY')
    expected_key = API_KEY  # استخدام المتغير العالمي API_KEY المعرف في بداية الملف
    
    # تسجيل معلومات التصحيح
    app.logger.info(f"المفتاح المستلم: {api_key}")
    app.logger.info(f"المفتاح المتوقع: {expected_key}")
    
    return api_key == expected_key

@app.route('/api/wallets', methods=['GET'])
def api_get_wallets():
    """الحصول على قائمة المحافظ المتاحة"""
    if not verify_api_key():
        return jsonify({"error": "غير مصرح به", "code": 401}), 401
    
    # الحصول على المحافظ الفريدة من قاعدة البيانات
    wallets = db.session.query(Transaction.wallet).distinct().all()
    wallet_list = [wallet[0] for wallet in wallets]
    
    return jsonify({
        "status": "success",
        "wallets": wallet_list,
        "count": len(wallet_list)
    })

@app.route('/api/transactions', methods=['GET'])
def api_get_transactions(specific_wallet=None):
    """الحصول على جميع المعاملات مع دعم التصفية والترتيب"""
    if not verify_api_key():
        return jsonify({"error": "غير مصرح به", "code": 401}), 401
    
    # معلمات التصفية الاختيارية
    wallet = specific_wallet or request.args.get('wallet')
    currency = request.args.get('currency')
    transaction_type = request.args.get('type')  # credit/debit
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    limit = request.args.get('limit', default=100, type=int)
    
    # بناء الاستعلام الأساسي
    query = Transaction.query
    
    # تطبيق الفلاتر
    if wallet:
        query = query.filter_by(wallet=wallet)
    if currency:
        try:
            # تحسين معالجة العملة للتعامل مع YER بشكل صحيح
            if currency in ['YER', 'USD', 'SAR']:
                query = query.filter_by(currency=currency)
            else:
                app.logger.warning(f"عملة غير معروفة: {currency}، سيتم تجاهلها")
        except Exception as e:
            app.logger.error(f"خطأ في معالجة العملة: {str(e)}")
            # استخدام استعلام أكثر مرونة في حالة الخطأ
            query = query
    if transaction_type:
        query = query.filter_by(type=transaction_type)
    if start_date:
        try:
            start_date_obj = datetime.strptime(start_date, '%Y-%m-%d')
            query = query.filter(Transaction.timestamp >= start_date_obj)
        except ValueError:
            return jsonify({"error": "تنسيق تاريخ البداية غير صالح. استخدم YYYY-MM-DD"}), 400
    if end_date:
        try:
            end_date_obj = datetime.strptime(end_date, '%Y-%m-%d')
            # إضافة يوم واحد لتضمين معاملات اليوم المحدد
            end_date_obj = end_date_obj.replace(hour=23, minute=59, second=59)
            query = query.filter(Transaction.timestamp <= end_date_obj)
        except ValueError:
            return jsonify({"error": "تنسيق تاريخ النهاية غير صالح. استخدم YYYY-MM-DD"}), 400
    
    # ترتيب النتائج تنازليًا حسب التاريخ
    query = query.order_by(Transaction.timestamp.desc())
    
    # تطبيق الحد
    if limit:
        query = query.limit(limit)
    
    # تنفيذ الاستعلام
    transactions = query.all()
    
    # تحويل النتائج إلى JSON
    result = []
    for transaction in transactions:
        # استخدام الدالة to_dict للحصول على تمثيل موحد للمعاملة
        transaction_dict = transaction.to_dict()
        result.append(transaction_dict)
    
    return jsonify({
        "status": "success",
        "count": len(result),
        "transactions": result
    })

@app.route('/api/wallets/<wallet_name>/transactions', methods=['GET'])
def api_get_wallet_transactions(wallet_name):
    """الحصول على معاملات محفظة محددة"""
    if not verify_api_key():
        return jsonify({"error": "غير مصرح به", "code": 401}), 401
    
    # التحقق من وجود المحفظة
    wallet_exists = db.session.query(Transaction.wallet).filter_by(wallet=wallet_name).first()
    if not wallet_exists:
        return jsonify({"error": f"المحفظة {wallet_name} غير موجودة", "code": 404}), 404
    
    # استخدام معلمات الطلب الحالية مع تمرير معلمة المحفظة عبر دالة api_get_transactions
    return api_get_transactions(wallet_name)

@app.route('/api/transaction/<transaction_id>', methods=['GET'])
def api_get_transaction(transaction_id):
    """الحصول على معاملة محددة بواسطة معرفها"""
    if not verify_api_key():
        return jsonify({"error": "غير مصرح به", "code": 401}), 401
    
    # البحث عن المعاملة باستخدام المعرف
    transaction = None
    
    # محاولة البحث باستخدام معرف المعاملة المخصص (TX...)
    if transaction_id.startswith('TX'):
        transaction = Transaction.query.filter_by(transaction_id=transaction_id).first()
    
    # إذا لم يتم العثور على المعاملة، نبحث باستخدام المعرف الرقمي
    if not transaction and transaction_id.isdigit():
        transaction = Transaction.query.get(int(transaction_id))
    
    if not transaction:
        return jsonify({
            "success": False,
            "error": f"المعاملة {transaction_id} غير موجودة", 
            "code": 404
        }), 404
    
    # استخدام الدالة to_dict للحصول على تمثيل موحد للمعاملة
    transaction_data = transaction.to_dict()
    
    # إضافة معلومات إضافية قد تكون مفيدة للتحقق من المعاملة
    transaction_data.update({
        "wallet": transaction.wallet,
        "amount": float(transaction.amount) if transaction.amount is not None else 0.0,
        "currency": transaction.currency,
        "counterparty": transaction.counterparty,
        "transaction_id": transaction.transaction_id,
        "id": transaction.id
    })
    
    return jsonify({
        "success": True,
        "transaction": transaction_data
    })

@app.route('/api/transactions/update-status-v1', methods=['POST'])
def api_update_transaction_v2():
    """تحديث حالة المعاملة وبيانات المشرف من المشروع الأول"""
    try:
        # تسجيل استلام الطلب
        app.logger.info("تم استلام طلب تحديث حالة المعاملة")
        app.logger.info(f"البيانات المستلمة: {request.data}")
        app.logger.info(f"الرؤوس: {request.headers}")
        
        # التحقق من مفتاح API
        if not verify_api_key():
            app.logger.error("مفتاح API غير صالح")
            return jsonify({
                'success': False,
                'error': 'مفتاح API غير صالح'
            }), 401
        
        # الحصول على البيانات من الطلب
        data = request.get_json()
        if not data:
            app.logger.error("لم يتم توفير بيانات في الطلب")
            return jsonify({
                'success': False,
                'error': 'لم يتم توفير بيانات في الطلب'
            }), 400
        
        # التحقق من وجود البيانات المطلوبة
        required_fields = ['transaction_id', 'wallet', 'status']
        missing_fields = [field for field in required_fields if field not in data]
        if missing_fields:
            app.logger.error(f"البيانات غير مكتملة: {missing_fields}")
            return jsonify({
                'success': False,
                'error': f'البيانات غير مكتملة: {", ".join(missing_fields)}'
            }), 400
        
        # التحقق من صحة قيمة الحالة
        status = data.get('status')
        if status not in Transaction.VALID_STATUSES:
            app.logger.warning(f"تم استلام حالة غير صالحة: {status}")
            status = 'pending'  # استخدام القيمة الافتراضية
        transaction.status = status
        
        # تحديث المنفذ إذا تم توفيره
        executed_by = data.get('executed_by')
        if executed_by:
            transaction.executed_by = executed_by
        
        # تحديث حالة التأكيد إذا تم توفيرها
        is_confirmed = data.get('is_confirmed')
        if is_confirmed is not None:
            # تحويل القيمة إلى قيمة منطقية
            if isinstance(is_confirmed, str):
                is_confirmed = is_confirmed.lower() in ['true', '1', 'yes', 'نعم', 'مؤكدة', 'تم التأكيد']
            transaction.is_confirmed_db = bool(is_confirmed)
            app.logger.info(f"تم تحديث حالة التأكيد للمعاملة {transaction_id} إلى {is_confirmed}")
        
        try:
            db.session.commit()
            app.logger.info(f"تم تحديث المعاملة {transaction_id} بنجاح")
            
            # إعادة المعاملة المحدثة
            return jsonify({
                "success": True,
                "message": f'تم تحديث حالة المعاملة {transaction_id} بنجاح',
                "transaction": transaction.to_dict()
            })
        except Exception as e:
            db.session.rollback()
            app.logger.error(f"خطأ أثناء تحديث المعاملة: {str(e)}")
            return jsonify({
                "success": False,
                "error": f"خطأ أثناء تحديث المعاملة: {str(e)}",
                "code": 500
            }), 500
    
    except Exception as e:
        db.session.rollback()
        app.logger.error(f"خطأ أثناء تحديث المعاملة: {str(e)}")
        return jsonify({
            "success": False,
            "error": f"خطأ أثناء تحديث المعاملة: {str(e)}",
            "code": 500
        }), 500

@app.route('/api/docs', methods=['GET'])
@login_required
def api_docs():
    """توثيق واجهة برمجة التطبيقات"""
    now = datetime.now()  # إضافة متغير التاريخ الحالي
    return render_template('api_docs.html', now=now)

# إضافة مسار متوافق مع التطبيق الثاني
@app.route('/api/transactions/wallet/<wallet_name>', methods=['GET'])
def api_get_transactions_alt_route(wallet_name):
    """مسار بديل للحصول على معاملات محفظة محددة (للتوافق مع التطبيقات الخارجية)"""
    return api_get_wallet_transactions(wallet_name)

@app.route('/api/update-transaction-alt', methods=['POST'])
def api_update_transaction():
    """تحديث حالة معاملة"""
    if not verify_api_key():
        return jsonify({"error": "غير مصرح به", "code": 401}), 401
    
    # الحصول على البيانات من الطلب
    data = request.get_json()
    if not data:
        return jsonify({"error": "البيانات المطلوبة غير موجودة", "code": 400}), 400
    
    # التحقق من وجود المعرف
    transaction_id = data.get('transaction_id')
    if not transaction_id:
        return jsonify({"error": "معرف المعاملة مطلوب", "code": 400}), 400
    
    # البحث عن المعاملة
    transaction = None
    
    # محاولة البحث باستخدام معرف المعاملة المخصص (TX...)
    if isinstance(transaction_id, str) and transaction_id.startswith('TX'):
        transaction = Transaction.query.filter_by(transaction_id=transaction_id).first()
    
    # إذا لم يتم العثور على المعاملة، نبحث باستخدام المعرف الرقمي
    if not transaction and str(transaction_id).isdigit():
        transaction = Transaction.query.get(int(transaction_id))
    
    if not transaction:
        return jsonify({
            "success": False,
            "error": f"المعاملة {transaction_id} غير موجودة", 
            "code": 404
        }), 404
    
    # تحديث البيانات
    status = data.get('status')
    executed_by = data.get('executed_by')
    is_confirmed = data.get('is_confirmed')
    currency = data.get('currency')
    
    # التحقق من صحة الحالة
    if status is not None:
        if status not in Transaction.VALID_STATUSES:
            app.logger.warning(f"تم استلام حالة غير صالحة: {status}")
            status = 'pending'  # استخدام القيمة الافتراضية
        transaction.status = status
    
    # تحديث المنفذ إذا تم توفيره
    if executed_by is not None:
        transaction.executed_by = executed_by
    
    # تحديث حالة التأكيد إذا تم توفيرها
    if is_confirmed is not None:
        # تحويل القيمة إلى قيمة منطقية
        if isinstance(is_confirmed, str):
            is_confirmed = is_confirmed.lower() in ['true', '1', 'yes', 'نعم', 'مؤكدة', 'تم التأكيد']
        transaction.is_confirmed_db = bool(is_confirmed)
        app.logger.info(f"تم تحديث حالة التأكيد للمعاملة {transaction_id} إلى {is_confirmed}")
    
    # تحديث العملة إذا تم توفيرها
    if currency is not None:
        # التحقق من صحة العملة
        if currency in ['YER', 'USD', 'SAR']:
            transaction.currency = currency
            app.logger.info(f"تم تحديث عملة المعاملة {transaction_id} إلى {currency}")
        else:
            app.logger.warning(f"تم استلام عملة غير صالحة: {currency}، سيتم تجاهلها")
    
    try:
        db.session.commit()
        app.logger.info(f"تم تحديث المعاملة {transaction_id} بنجاح")
        
        # إعادة المعاملة المحدثة
        return jsonify({
            "success": True,
            "message": "تم تحديث المعاملة بنجاح",
            "transaction": transaction.to_dict()
        })
    except Exception as e:
        db.session.rollback()
        app.logger.error(f"خطأ أثناء تحديث المعاملة: {str(e)}")
        return jsonify({
            "success": False,
            "error": f"خطأ أثناء تحديث المعاملة: {str(e)}",
            "code": 500
        }), 500

@app.route('/api/wallets/<wallet_name>/summary', methods=['GET'])
def api_get_wallet_summary(wallet_name):
    """الحصول على ملخص محفظة محددة"""
    if not verify_api_key():
        return jsonify({"error": "غير مصرح به", "code": 401}), 401
    
    # التحقق من وجود المحفظة
    wallet_exists = db.session.query(Transaction.wallet).filter_by(wallet=wallet_name).first()
    if not wallet_exists:
        return jsonify({"error": f"المحفظة {wallet_name} غير موجودة", "code": 404}), 404
    
    # الحصول على العملات المختلفة للمحفظة
    currencies = db.session.query(Transaction.currency).filter_by(wallet=wallet_name).distinct().all()
    currencies = [currency[0] for currency in currencies]
    
    # تجميع المعلومات لكل عملة
    summary = {}
    for currency in currencies:
        # إجمالي الإيداعات
        credit_sum = db.session.query(db.func.sum(Transaction.amount)).filter_by(
            wallet=wallet_name, currency=currency, type='credit'
        ).scalar() or 0
        
        # إجمالي السحوبات
        debit_sum = db.session.query(db.func.sum(Transaction.amount)).filter_by(
            wallet=wallet_name, currency=currency, type='debit'
        ).scalar() or 0
        
        # آخر رصيد
        latest_transaction = Transaction.query.filter_by(
            wallet=wallet_name, currency=currency
        ).order_by(Transaction.timestamp.desc()).first()
        
        latest_balance = latest_transaction.balance if latest_transaction else 0
        latest_date = latest_transaction.timestamp.isoformat() if latest_transaction and latest_transaction.timestamp else None
        
        # عدد المعاملات
        transaction_count = Transaction.query.filter_by(
            wallet=wallet_name, currency=currency
        ).count()
        
        summary[currency] = {
            'credits': float(credit_sum),
            'debits': float(debit_sum),
            'net': float(credit_sum - debit_sum),
            'latest_balance': float(latest_balance),
            'latest_transaction_date': latest_date,
            'transaction_count': transaction_count
        }
    
    return jsonify({
        "status": "success",
        "wallet": wallet_name,
        "summary": summary
    })

# تحميل المستخدم لـ Flask-Login
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# وظيفة مساعدة للتحقق من صلاحيات المشرف
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            flash('ليس لديك صلاحية للوصول إلى هذه الصفحة', 'danger')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# نموذج تسجيل الدخول
class LoginForm(FlaskForm):
    username = StringField('اسم المستخدم', validators=[DataRequired()])
    password = PasswordField('كلمة المرور', validators=[DataRequired()])
    remember_me = BooleanField('تذكرني')
    submit = SubmitField('تسجيل الدخول')

# طرق تسجيل الدخول وتسجيل الخروج
@app.route('/login', methods=['GET', 'POST'])
def login():
    """صفحة تسجيل الدخول للمشرفين."""
    if current_user.is_authenticated:
        return redirect(url_for('admin_dashboard'))
    
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data).first()
        if user is None or not user.check_password(form.password.data):
            flash('اسم المستخدم أو كلمة المرور غير صحيحة', 'danger')
            return redirect(url_for('login'))
        
        login_user(user, remember=form.remember_me.data)
        user.last_login = datetime.now()
        db.session.commit()
        
        next_page = request.args.get('next')
        if not next_page or not next_page.startswith('/'):
            next_page = url_for('admin_dashboard')
        return redirect(next_page)
    
    now = datetime.now()  # إضافة متغير التاريخ الحالي
    return render_template('login.html', title='تسجيل الدخول', form=form, now=now)

@app.route('/logout')
@login_required
def logout():
    """تسجيل الخروج."""
    logout_user()
    flash('تم تسجيل الخروج بنجاح', 'success')
    return redirect(url_for('index'))

@app.route('/admin')
@login_required
@admin_required
def admin_dashboard():
    """لوحة تحكم المشرف."""
    wallets = db.session.query(Transaction.wallet).distinct().all()
    wallet_list = [wallet[0] for wallet in wallets]
    
    # إحصائيات سريعة
    total_transactions = Transaction.query.count()
    wallet_counts = {}
    for wallet in wallet_list:
        wallet_counts[wallet] = Transaction.query.filter_by(wallet=wallet).count()
    
    return render_template('admin_dashboard.html', title='لوحة تحكم المشرف',
                           wallets=wallet_list, wallet_counts=wallet_counts,
                           total_transactions=total_transactions)

@app.route('/admin/create-user', methods=['GET', 'POST'])
@login_required
@admin_required
def create_user():
    """إنشاء مستخدم جديد."""
    class UserForm(FlaskForm):
        username = StringField('اسم المستخدم', validators=[DataRequired(), Length(min=3, max=64)])
        email = StringField('البريد الإلكتروني', validators=[DataRequired(), Email()])
        password = PasswordField('كلمة المرور', validators=[DataRequired(), Length(min=8)])
        confirm_password = PasswordField('تأكيد كلمة المرور', validators=[DataRequired(), EqualTo('password')])
        is_admin = BooleanField('صلاحيات المشرف')
        submit = SubmitField('إنشاء المستخدم')
    
    form = UserForm()
    if form.validate_on_submit():
        # التحقق من عدم وجود مستخدم بنفس الاسم أو البريد
        if User.query.filter_by(username=form.username.data).first():
            flash('اسم المستخدم مستخدم بالفعل', 'danger')
            return redirect(url_for('create_user'))
        
        if User.query.filter_by(email=form.email.data).first():
            flash('البريد الإلكتروني مستخدم بالفعل', 'danger')
            return redirect(url_for('create_user'))
        
        # إنشاء المستخدم الجديد
        user = User(username=form.username.data, email=form.email.data,
                    is_admin=form.is_admin.data)
        user.set_password(form.password.data)
        
        db.session.add(user)
        db.session.commit()
        
        flash(f'تم إنشاء المستخدم {form.username.data} بنجاح', 'success')
        return redirect(url_for('admin_dashboard'))
    
    return render_template('create_user.html', title='إنشاء مستخدم جديد', form=form)

if __name__ == '__main__':
    # Ensure the upload folder exists
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    
    # إنشاء جداول قاعدة البيانات إذا لم تكن موجودة
    with app.app_context():
        db.create_all()
        
        # التحقق من وجود المستخدمين وإنشاء مستخدم مشرف افتراضي إذا لم يكن هناك أي مستخدم
        if User.query.count() == 0:
            print("إنشاء مستخدم مشرف افتراضي...")
            default_admin = User(
                username="admin",
                email="admin@metabit.com",
                is_admin=True
            )
            default_admin.set_password("MetaBit@2025")
            db.session.add(default_admin)
            db.session.commit()
            print("تم إنشاء مستخدم المشرف الافتراضي:")
            print("اسم المستخدم: admin")
            print("كلمة المرور: MetaBit@2025")
            print("يرجى تغيير كلمة المرور بعد تسجيل الدخول.")
    
    # Get port from environment variable for Render compatibility
    port = int(os.environ.get('PORT', 5000))
    
    # Run the app with the specified port and host
    app.run(host='0.0.0.0', port=port, debug=True)

@app.route('/api/transaction/<transaction_id>/status', methods=['GET'])
def api_get_transaction_status(transaction_id):
    """الحصول على حالة معاملة محددة بواسطة المعرف (مخصص للتحقق من المعاملات)"""
    if not verify_api_key():
        return jsonify({"error": "غير مصرح به", "code": 401}), 401
    
    # البحث عن المعاملة باستخدام المعرف
    transaction = None
    wallet = request.args.get('wallet')
    
    # محاولة البحث باستخدام معرف المعاملة المخصص (TX...)
    if transaction_id.startswith('TX'):
        if wallet:
            transaction = Transaction.query.filter_by(transaction_id=transaction_id, wallet=wallet).first()
        else:
            transaction = Transaction.query.filter_by(transaction_id=transaction_id).first()
    
    # إذا لم يتم العثور على المعاملة، نبحث باستخدام المعرف الرقمي
    if not transaction and transaction_id.isdigit():
        if wallet:
            transaction = Transaction.query.filter_by(id=int(transaction_id), wallet=wallet).first()
        else:
            transaction = Transaction.query.get(int(transaction_id))
    
    if not transaction:
        return jsonify({
            "success": False,
            "error": f"المعاملة {transaction_id} غير موجودة", 
            "code": 404
        }), 404
    
    # إعداد استجابة موحدة تحتوي على جميع الحقول المطلوبة للتحقق
    response = {
        "success": True,
        "transaction_id": transaction.transaction_id,
        "id": transaction.id,
        "status": transaction.status,
        "state": transaction.status,  # للتوافق مع الإصدارات السابقة
        "confirmation_status": transaction.confirmation_status,
        "is_confirmed": transaction.is_confirmed,
        "executed_by": transaction.executed_by if transaction.executed_by else None,
        "wallet": transaction.wallet,
        "amount": float(transaction.amount) if transaction.amount is not None else 0.0,
        "currency": transaction.currency,
        "counterparty": transaction.counterparty
    }
    
    return jsonify(response)

@app.route('/api/wallets/<wallet_name>/transactions/<transaction_id>', methods=['GET'])
def api_get_wallet_transaction(wallet_name, transaction_id):
    """الحصول على معاملة محددة في محفظة محددة (للتوافق مع المشروع الأول)"""
    if not verify_api_key():
        return jsonify({"error": "غير مصرح به", "code": 401}), 401
    
    # البحث عن المعاملة باستخدام المعرف والمحفظة
    transaction = None
    
    # محاولة البحث باستخدام معرف المعاملة المخصص (TX...)
    if transaction_id.startswith('TX'):
        transaction = Transaction.query.filter_by(transaction_id=transaction_id, wallet=wallet_name).first()
    
    # إذا لم يتم العثور على المعاملة، نبحث باستخدام المعرف الرقمي
    if not transaction and transaction_id.isdigit():
        transaction = Transaction.query.filter_by(id=int(transaction_id), wallet=wallet_name).first()
    
    if not transaction:
        return jsonify({
            "success": False,
            "error": f"المعاملة {transaction_id} غير موجودة في محفظة {wallet_name}", 
            "code": 404
        }), 404
    
    # استخدام الدالة to_dict للحصول على تمثيل موحد للمعاملة
    return jsonify({
        "success": True,
        "transaction": transaction.to_dict()
    })

@app.route('/api/transactions/update-status', methods=['POST'])
def api_update_transaction_alt():
    """تحديث حالة معاملة"""
    if not verify_api_key():
        return jsonify({"error": "غير مصرح به", "code": 401}), 401
    
    # الحصول على البيانات من الطلب
    data = request.get_json()
    if not data:
        return jsonify({"error": "البيانات المطلوبة غير موجودة", "code": 400}), 400
    
    # التحقق من وجود المعرف
    transaction_id = data.get('transaction_id')
    if not transaction_id:
        return jsonify({"error": "معرف المعاملة مطلوب", "code": 400}), 400
    
    # البحث عن المعاملة
    transaction = None
    
    # محاولة البحث باستخدام معرف المعاملة المخصص (TX...)
    if isinstance(transaction_id, str) and transaction_id.startswith('TX'):
        transaction = Transaction.query.filter_by(transaction_id=transaction_id).first()
    
    # إذا لم يتم العثور على المعاملة، نبحث باستخدام المعرف الرقمي
    if not transaction and str(transaction_id).isdigit():
        transaction = Transaction.query.get(int(transaction_id))
    
    if not transaction:
        return jsonify({
            "success": False,
            "error": f"المعاملة {transaction_id} غير موجودة", 
            "code": 404
        }), 404
    
    # تحديث البيانات
    status = data.get('status')
    executed_by = data.get('executed_by')
    is_confirmed = data.get('is_confirmed')
    currency = data.get('currency')
    
    # التحقق من صحة الحالة
    if status is not None:
        if status not in Transaction.VALID_STATUSES:
            app.logger.warning(f"تم استلام حالة غير صالحة: {status}")
            status = 'pending'  # استخدام القيمة الافتراضية
        transaction.status = status
    
    # تحديث المنفذ إذا تم توفيره
    if executed_by is not None:
        transaction.executed_by = executed_by
    
    # تحديث حالة التأكيد إذا تم توفيرها
    if is_confirmed is not None:
        # تحويل القيمة إلى قيمة منطقية
        if isinstance(is_confirmed, str):
            is_confirmed = is_confirmed.lower() in ['true', '1', 'yes', 'نعم', 'مؤكدة', 'تم التأكيد']
        transaction.is_confirmed_db = bool(is_confirmed)
        app.logger.info(f"تم تحديث حالة التأكيد للمعاملة {transaction_id} إلى {is_confirmed}")
    
    # تحديث العملة إذا تم توفيرها
    if currency is not None:
        # التحقق من صحة العملة
        if currency in ['YER', 'USD', 'SAR']:
            transaction.currency = currency
            app.logger.info(f"تم تحديث عملة المعاملة {transaction_id} إلى {currency}")
        else:
            app.logger.warning(f"تم استلام عملة غير صالحة: {currency}، سيتم تجاهلها")
    
    try:
        db.session.commit()
        app.logger.info(f"تم تحديث المعاملة {transaction_id} بنجاح")
        
        # إعادة المعاملة المحدثة
        return jsonify({
            "success": True,
            "message": "تم تحديث المعاملة بنجاح",
            "transaction": transaction.to_dict()
        })
    except Exception as e:
        db.session.rollback()
        app.logger.error(f"خطأ أثناء تحديث المعاملة: {str(e)}")
        return jsonify({
            "success": False,
            "error": f"خطأ أثناء تحديث المعاملة: {str(e)}",
            "code": 500
        }), 500
