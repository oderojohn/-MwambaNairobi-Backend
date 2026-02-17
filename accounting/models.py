from django.db import models
from django.contrib.auth.models import User
from decimal import Decimal


class AccountType(models.TextChoices):
    ASSET = 'asset', 'Asset'
    LIABILITY = 'liability', 'Liability'
    EQUITY = 'equity', 'Equity'
    REVENUE = 'revenue', 'Revenue'
    EXPENSE = 'expense', 'Expense'


class Account(models.Model):
    """Chart of Accounts - Main account categories"""
    name = models.CharField(max_length=100)
    account_type = models.CharField(max_length=20, choices=AccountType.choices)
    code = models.CharField(max_length=20, unique=True)  # Account code like 1000, 2000, etc.
    description = models.TextField(blank=True)
    parent = models.ForeignKey('self', on_delete=models.CASCADE, null=True, blank=True, related_name='children')
    is_active = models.BooleanField(default=True)
    is_contra = models.BooleanField(default=False)  # Contra accounts have opposite sign
    allow_manual_entry = models.BooleanField(default=True)  # Can manual entries be made
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['code']
        verbose_name_plural = 'Accounts'

    def __str__(self):
        return f"{self.code} - {self.name}"

    @property
    def balance(self):
        """Calculate current balance from journal entries"""
        from django.db.models import Sum
        result = self.journal_entries.aggregate(
            total_debit=Sum('debit_amount'),
            total_credit=Sum('credit_amount')
        )
        debit = result['total_debit'] or Decimal('0')
        credit = result['total_credit'] or Decimal('0')
        
        if self.account_type in [AccountType.ASSET, AccountType.EXPENSE]:
            # Debit increases, Credit decreases
            balance = debit - credit
        else:
            # Credit increases, Debit decreases
            balance = credit - debit
        
        if self.is_contra:
            balance = -balance
            
        return balance


class JournalEntry(models.Model):
    """General Ledger Journal Entry - Debits and Credits"""
    entry_number = models.CharField(max_length=50, unique=True)
    date = models.DateField()
    description = models.CharField(max_length=500)
    reference = models.CharField(max_length=100, blank=True)  # External reference like invoice number
    is_auto = models.BooleanField(default=False)  # Auto-generated from other transactions
    source = models.CharField(max_length=50, blank=True)  # Source of entry: manual, sale, purchase, etc.
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='journal_entries')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-date', '-entry_number']
        verbose_name = 'Journal Entry'
        verbose_name_plural = 'Journal Entries'

    def __str__(self):
        return f"{self.entry_number} - {self.date}"

    @property
    def total_debit(self):
        return sum(entry.debit_amount for entry in self.entries.all())

    @property
    def total_credit(self):
        return sum(entry.credit_amount for entry in self.entries.all())

    @property
    def is_balanced(self):
        return self.total_debit == self.total_credit


class JournalEntryLine(models.Model):
    """Individual lines in a journal entry"""
    journal_entry = models.ForeignKey(JournalEntry, on_delete=models.CASCADE, related_name='entries')
    account = models.ForeignKey(Account, on_delete=models.CASCADE, related_name='journal_entries')
    debit_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    credit_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    description = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ['id']

    def __str__(self):
        return f"{self.account.code} - Dr: {self.debit_amount} / Cr: {self.credit_amount}"

    def clean(self):
        from django.core.exceptions import ValidationError
        if self.debit_amount > 0 and self.credit_amount > 0:
            raise ValidationError("A journal entry line cannot have both debit and credit")
        if self.debit_amount == 0 and self.credit_amount == 0:
            raise ValidationError("A journal entry line must have either debit or credit")


class RecurringExpense(models.Model):
    """Automatic recurring expenses like rent, bills"""
    name = models.CharField(max_length=100)
    account = models.ForeignKey(Account, on_delete=models.CASCADE, related_name='recurring_expenses')
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    frequency = models.CharField(max_length=20, choices=[
        ('daily', 'Daily'),
        ('weekly', 'Weekly'),
        ('monthly', 'Monthly'),
        ('yearly', 'Yearly'),
    ])
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    last_posted = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return f"{self.name} - {self.amount} ({self.frequency})"

    def should_post_today(self):
        """Check if this expense should be posted today"""
        from datetime import date
        today = date.today()
        
        if not self.is_active:
            return False
        
        if self.end_date and today > self.end_date:
            return False
            
        if self.last_posted and today <= self.last_posted:
            return False
            
        # Check if today matches the frequency
        if self.frequency == 'daily':
            return True
        elif self.frequency == 'weekly':
            return today.weekday() == 0  # Monday
        elif self.frequency == 'monthly':
            return today.day == 1  # First of month
        elif self.frequency == 'yearly':
            return today.month == 1 and today.day == 1
            
        return False


class AutomaticEntryRule(models.Model):
    """Rules for automatic journal entries from other modules"""
    name = models.CharField(max_length=100)
    source_model = models.CharField(max_length=100)  # e.g., 'sales.sale', 'payments.payment'
    trigger_event = models.CharField(max_length=50)  # e.g., 'sale_created', 'payment_received'
    
    # Debit entry
    debit_account = models.ForeignKey(Account, on_delete=models.CASCADE, related_name='debit_rules')
    debit_amount_type = models.CharField(max_length=20, choices=[
        ('fixed', 'Fixed Amount'),
        ('percentage', 'Percentage of Total'),
        ('field', 'From Field'),
    ])
    debit_amount_value = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    debit_amount_field = models.CharField(max_length=50, blank=True)
    
    # Credit entry
    credit_account = models.ForeignKey(Account, on_delete=models.CASCADE, related_name='credit_rules')
    credit_amount_type = models.CharField(max_length=20, choices=[
        ('fixed', 'Fixed Amount'),
        ('percentage', 'Percentage of Total'),
        ('field', 'From Field'),
    ])
    credit_amount_value = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    credit_amount_field = models.CharField(max_length=50, blank=True)
    
    is_active = models.BooleanField(default=True)
    description = models.TextField(blank=True)

    class Meta:
        verbose_name = 'Automatic Entry Rule'
        verbose_name_plural = 'Automatic Entry Rules'

    def __str__(self):
        return f"{self.name} ({self.source_model}.{self.trigger_event})"
