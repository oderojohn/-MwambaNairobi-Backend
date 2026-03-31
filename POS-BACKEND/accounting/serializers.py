from rest_framework import serializers
from .models import Account, JournalEntry, JournalEntryLine, RecurringExpense, AutomaticEntryRule, AccountType


class AccountSerializer(serializers.ModelSerializer):
    balance = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    account_type_display = serializers.CharField(source='get_account_type_display', read_only=True)
    children_count = serializers.SerializerMethodField()
    
    class Meta:
        model = Account
        fields = [
            'id', 'name', 'code', 'account_type', 'account_type_display',
            'description', 'parent', 'is_active', 'is_contra', 
            'allow_manual_entry', 'balance', 'children_count',
            'created_at', 'updated_at'
        ]
    
    def get_children_count(self, obj):
        return obj.children.count()


class AccountListSerializer(serializers.ModelSerializer):
    """Simplified serializer for listing accounts"""
    account_type_display = serializers.CharField(source='get_account_type_display', read_only=True)
    balance = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    
    class Meta:
        model = Account
        fields = ['id', 'name', 'code', 'account_type', 'account_type_display', 'balance', 'is_active']


class JournalEntryLineSerializer(serializers.ModelSerializer):
    account_name = serializers.CharField(source='account.name', read_only=True)
    account_code = serializers.CharField(source='account.code', read_only=True)
    account_type = serializers.CharField(source='account.account_type', read_only=True)
    
    class Meta:
        model = JournalEntryLine
        fields = [
            'id', 'account', 'account_name', 'account_code', 'account_type',
            'debit_amount', 'credit_amount', 'description'
        ]


class JournalEntrySerializer(serializers.ModelSerializer):
    entries = JournalEntryLineSerializer(many=True, read_only=True)
    created_by_username = serializers.CharField(source='created_by.username', read_only=True)
    total_debit = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    total_credit = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    is_balanced = serializers.BooleanField(read_only=True)
    
    class Meta:
        model = JournalEntry
        fields = [
            'id', 'entry_number', 'date', 'description', 'reference',
            'is_auto', 'source', 'created_by', 'created_by_username',
            'entries', 'total_debit', 'total_credit', 'is_balanced',
            'created_at', 'updated_at'
        ]


class JournalEntryCreateSerializer(serializers.ModelSerializer):
    entries = JournalEntryLineSerializer(many=True)
    
    class Meta:
        model = JournalEntry
        fields = ['id', 'date', 'description', 'reference', 'source', 'entries']
    
    def validate_entries(self, value):
        if not value:
            raise serializers.ValidationError("At least one journal entry line is required")
        
        total_debit = sum(entry.get('debit_amount', 0) for entry in value)
        total_credit = sum(entry.get('credit_amount', 0) for entry in value)
        
        if total_debit != total_credit:
            raise serializers.ValidationError(
                f"Journal entry is not balanced. Debits: {total_debit}, Credits: {total_credit}"
            )
        
        return value
    
    def create(self, validated_data):
        entries_data = validated_data.pop('entries')
        
        # Generate entry number
        from django.utils import timezone
        today = timezone.now().date()
        prefix = f"JE-{today.strftime('%Y%m%d')}"
        
        # Get the last entry number for today
        last_entry = JournalEntry.objects.filter(
            entry_number__startswith=prefix
        ).order_by('-entry_number').first()
        
        if last_entry:
            last_num = int(last_entry.entry_number.split('-')[-1])
            new_num = last_num + 1
        else:
            new_num = 1
        
        entry_number = f"{prefix}-{new_num:04d}"
        validated_data['entry_number'] = entry_number
        validated_data['created_by'] = self.context['request'].user
        
        journal_entry = JournalEntry.objects.create(**validated_data)
        
        for entry_data in entries_data:
            JournalEntryLine.objects.create(
                journal_entry=journal_entry,
                account_id=entry_data['account'],
                debit_amount=entry_data.get('debit_amount', 0),
                credit_amount=entry_data.get('credit_amount', 0),
                description=entry_data.get('description', '')
            )
        
        return journal_entry


class RecurringExpenseSerializer(serializers.ModelSerializer):
    account_name = serializers.CharField(source='account.name', read_only=True)
    account_code = serializers.CharField(source='account.code', read_only=True)
    
    class Meta:
        model = RecurringExpense
        fields = [
            'id', 'name', 'account', 'account_name', 'account_code',
            'amount', 'frequency', 'start_date', 'end_date',
            'is_active', 'last_posted', 'notes', 'created_at'
        ]


class AutomaticEntryRuleSerializer(serializers.ModelSerializer):
    debit_account_name = serializers.CharField(source='debit_account.name', read_only=True)
    credit_account_name = serializers.CharField(source='credit_account.name', read_only=True)
    
    class Meta:
        model = AutomaticEntryRule
        fields = [
            'id', 'name', 'source_model', 'trigger_event',
            'debit_account', 'debit_account_name',
            'debit_amount_type', 'debit_amount_value', 'debit_amount_field',
            'credit_account', 'credit_account_name',
            'credit_amount_type', 'credit_amount_value', 'credit_amount_field',
            'is_active', 'description'
        ]


class TrialBalanceSerializer(serializers.Serializer):
    """Serializer for Trial Balance Report"""
    account_code = serializers.CharField()
    account_name = serializers.CharField()
    account_type = serializers.CharField()
    debit = serializers.DecimalField(max_digits=12, decimal_places=2)
    credit = serializers.DecimalField(max_digits=12, decimal_places=2)


class ProfitLossSerializer(serializers.Serializer):
    """Serializer for Profit & Loss Report"""
    account_code = serializers.CharField()
    account_name = serializers.CharField()
    account_type = serializers.CharField()
    amount = serializers.DecimalField(max_digits=12, decimal_places=2)


class GeneralLedgerSerializer(serializers.Serializer):
    """Serializer for General Ledger Report"""
    date = serializers.DateField()
    entry_number = serializers.CharField()
    description = serializers.CharField()
    debit = serializers.DecimalField(max_digits=12, decimal_places=2)
    credit = serializers.DecimalField(max_digits=12, decimal_places=2)
    balance = serializers.DecimalField(max_digits=12, decimal_places=2)
    account_code = serializers.CharField()
    account_name = serializers.CharField()
