from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import uuid
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin

db = SQLAlchemy()

class User(db.Model, UserMixin):
    """نموذج للمستخدمين المشرفين."""
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.now)
    last_login = db.Column(db.DateTime, nullable=True)
    
    def set_password(self, password):
        """تعيين كلمة المرور المشفرة."""
        self.password_hash = generate_password_hash(password)
        
    def check_password(self, password):
        """التحقق من صحة كلمة المرور."""
        return check_password_hash(self.password_hash, password)
    
    def __repr__(self):
        return f'<User {self.username}>'

class Transaction(db.Model):
    """Model for wallet transactions."""
    __tablename__ = 'transactions'
    
    id = db.Column(db.Integer, primary_key=True)
    wallet = db.Column(db.String(50), nullable=False)  # Jaib, Jawali, Cash
    type = db.Column(db.String(10), nullable=False)    # credit, debit
    amount = db.Column(db.Float, nullable=False)
    currency = db.Column(db.String(10), nullable=False)  # YER, SAR, USD
    details = db.Column(db.Text, nullable=True)
    counterparty = db.Column(db.String(255), nullable=True)
    balance = db.Column(db.Float, nullable=True)
    balance_currency = db.Column(db.String(10), nullable=True)
    raw_message = db.Column(db.Text, nullable=True)
    timestamp = db.Column(db.DateTime, default=datetime.now)
    created_at = db.Column(db.DateTime, default=datetime.now)
    is_confirmed_db = db.Column(db.Boolean, default=False)  # Nueva columna para almacenar el estado de confirmación
    status = db.Column(db.String(20), default='pending')  # حالة الطلب: pending, completed, rejected, cancelled, failed
    executed_by = db.Column(db.String(100), nullable=True)  # المشرف الذي نفذ العملية
    
    # قائمة القيم المسموح بها للحالة
    VALID_STATUSES = ['pending', 'completed', 'rejected', 'cancelled', 'failed']
    
    # خصائص افتراضية للأعمدة الجديدة
    @property
    def transaction_id(self):
        """Get a unique transaction ID."""
        # إذا لم يكن هناك عمود transaction_id في قاعدة البيانات، استخدم معرف فريد مبني على معرف المعاملة
        return f"TX{self.id:06d}"
    
    @property
    def is_confirmed(self):
        """Check if transaction is confirmed."""
        # استخدم القيمة المخزنة في قاعدة البيانات
        return self.is_confirmed_db
    
    @property
    def confirmation_status(self):
        """Return standardized confirmation status string."""
        return "confirmed" if self.is_confirmed_db else "unconfirmed"
    
    @property
    def state(self):
        """Return standardized state value for compatibility."""
        return self.status
    
    def to_dict(self):
        """Convert transaction to dictionary."""
        return {
            'id': self.id,
            'transaction_id': self.transaction_id,
            'wallet': self.wallet,
            'type': self.type,
            'amount': float(self.amount) if self.amount is not None else 0.0,
            'currency': self.currency,
            'details': self.details,
            'counterparty': self.counterparty,
            'balance': float(self.balance) if self.balance is not None else 0.0,
            'balance_currency': self.balance_currency,
            'raw_message': self.raw_message,
            'timestamp': self.timestamp.isoformat() if self.timestamp else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'is_confirmed': self.is_confirmed,
            'confirmation_status': self.confirmation_status,
            'status': self.status,
            'state': self.status,  # For compatibility
            'executed_by': self.executed_by if self.executed_by else None
        }
    
    @classmethod
    def from_dict(cls, data):
        """Create transaction from dictionary."""
        # Standardize status value
        status = data.get('status', 'pending')
        if status not in cls.VALID_STATUSES:
            status = 'pending'
            
        transaction = cls(
            wallet=data.get('wallet'),
            type=data.get('type'),
            amount=data.get('amount'),
            currency=data.get('currency'),
            details=data.get('details'),
            counterparty=data.get('counterparty'),
            balance=data.get('balance'),
            balance_currency=data.get('balance_currency'),
            raw_message=data.get('raw_message'),
            status=status,
            executed_by=data.get('executed_by')
        )
        
        # Handle timestamp if provided
        timestamp = data.get('timestamp')
        if timestamp:
            try:
                if isinstance(timestamp, str):
                    transaction.timestamp = datetime.fromisoformat(timestamp)
                else:
                    transaction.timestamp = timestamp
            except (ValueError, TypeError):
                # If timestamp format is invalid, use current time
                transaction.timestamp = datetime.now()
        
        # Handle is_confirmed if provided
        is_confirmed = data.get('is_confirmed')
        if is_confirmed is not None:
            transaction.is_confirmed_db = is_confirmed
        
        # Also check confirmation_status if provided
        confirmation_status = data.get('confirmation_status')
        if confirmation_status is not None:
            transaction.is_confirmed_db = confirmation_status.lower() == 'confirmed'
        
        return transaction
