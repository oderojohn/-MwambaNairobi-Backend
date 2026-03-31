from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db.models import Sum, Q
from django.db.models.functions import Coalesce
from decimal import Decimal
from datetime import date, timedelta

from .models import Account, JournalEntry, JournalEntryLine, RecurringExpense, AutomaticEntryRule, AccountType
from .serializers import (
    AccountSerializer, AccountListSerializer, 
    JournalEntrySerializer, JournalEntryCreateSerializer,
    RecurringExpenseSerializer, AutomaticEntryRuleSerializer,
    TrialBalanceSerializer, ProfitLossSerializer, GeneralLedgerSerializer
)


class AccountViewSet(viewsets.ModelViewSet):
    """ViewSet for Chart of Accounts"""
    queryset = Account.objects.all()
    permission_classes = [IsAuthenticated]
    
    def get_serializer_class(self):
        if self.action == 'list':
            return AccountListSerializer
        return AccountSerializer
    
    def get_queryset(self):
        queryset = Account.objects.all()
        
        # Filter by account type
        account_type = self.request.query_params.get('account_type')
        if account_type:
            queryset = queryset.filter(account_type=account_type)
        
        # Filter by active status
        is_active = self.request.query_params.get('is_active')
        if is_active is not None:
            queryset = queryset.filter(is_active=is_active.lower() == 'true')
        
        # Filter parent accounts only
        parent_only = self.request.query_params.get('parent_only')
        if parent_only and parent_only.lower() == 'true':
            queryset = queryset.filter(parent__isnull=True)
        
        return queryset
    
    @action(detail=False, methods=['get'])
    def by_type(self, request):
        """Get accounts grouped by type"""
        accounts_by_type = {}
        for acc_type, _ in AccountType.choices:
            accounts = Account.objects.filter(account_type=acc_type, is_active=True)
            accounts_by_type[acc_type] = AccountListSerializer(accounts, many=True).data
        return Response(accounts_by_type)
    
    @action(detail=True, methods=['get'])
    def ledger(self, request, pk=None):
        """Get general ledger for specific account"""
        account = self.get_object()
        
        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')
        
        entries = JournalEntryLine.objects.filter(account=account).select_related('journal_entry')
        
        if start_date:
            entries = entries.filter(journal_entry__date__gte=start_date)
        if end_date:
            entries = entries.filter(journal_entry__date__lte=end_date)
        
        entries = entries.order_by('journal_entry__date', 'journal_entry__entry_number')
        
        # Calculate running balance
        running_balance = Decimal('0')
        ledger_data = []
        
        for entry in entries:
            if account.account_type in [AccountType.ASSET, AccountType.EXPENSE]:
                running_balance += entry.debit_amount - entry.credit_amount
            else:
                running_balance += entry.credit_amount - entry.debit_amount
            
            if account.is_contra:
                running_balance = -running_balance
            
            ledger_data.append({
                'date': entry.journal_entry.date,
                'entry_number': entry.journal_entry.entry_number,
                'description': entry.journal_entry.description,
                'debit': entry.debit_amount,
                'credit': entry.credit_amount,
                'balance': running_balance,
                'account_code': account.code,
                'account_name': account.name,
                'reference': entry.journal_entry.reference
            })
        
        return Response(ledger_data)


class JournalEntryViewSet(viewsets.ModelViewSet):
    """ViewSet for Journal Entries"""
    queryset = JournalEntry.objects.all()
    permission_classes = [IsAuthenticated]
    
    def get_serializer_class(self):
        if self.action in ['create', 'update', 'partial_update']:
            return JournalEntryCreateSerializer
        return JournalEntrySerializer
    
    def get_queryset(self):
        queryset = JournalEntry.objects.all().prefetch_related('entries__account')
        
        # Filter by date range
        start_date = self.request.query_params.get('start_date')
        end_date = self.request.query_params.get('end_date')
        
        if start_date:
            queryset = queryset.filter(date__gte=start_date)
        if end_date:
            queryset = queryset.filter(date__lte=end_date)
        
        # Filter by source
        source = self.request.query_params.get('source')
        if source:
            queryset = queryset.filter(source=source)
        
        # Filter auto entries
        is_auto = self.request.query_params.get('is_auto')
        if is_auto is not None:
            queryset = queryset.filter(is_auto=is_auto.lower() == 'true')
        
        # Search by description or entry number
        search = self.request.query_params.get('search')
        if search:
            queryset = queryset.filter(
                Q(description__icontains=search) | 
                Q(entry_number__icontains=search) |
                Q(reference__icontains=search)
            )
        
        return queryset.order_by('-date', '-entry_number')
    
    @action(detail=False, methods=['post'])
    def post_recurring(self, request):
        """Post all due recurring expenses"""
        from django.utils import timezone
        today = timezone.now().date()
        
        recurring_expenses = RecurringExpense.objects.filter(is_active=True)
        posted_count = 0
        
        for expense in recurring_expenses:
            if expense.should_post_today():
                # Create journal entry
                entry_number = f"RE-{today.strftime('%Y%m%d')}-{expense.id:04d}"
                
                journal_entry = JournalEntry.objects.create(
                    entry_number=entry_number,
                    date=today,
                    description=f"Recurring: {expense.name}",
                    reference=f"REC-{expense.id}",
                    is_auto=True,
                    source='recurring_expense',
                    created_by=request.user
                )
                
                # Debit expense account
                JournalEntryLine.objects.create(
                    journal_entry=journal_entry,
                    account=expense.account,
                    debit_amount=expense.amount,
                    credit_amount=0,
                    description=expense.name
                )
                
                # Credit cash/bank account (assuming cash)
                cash_account = Account.objects.filter(
                    code='1000',
                    is_active=True
                ).first()
                
                if cash_account:
                    JournalEntryLine.objects.create(
                        journal_entry=journal_entry,
                        account=cash_account,
                        debit_amount=0,
                        credit_amount=expense.amount,
                        description=expense.name
                    )
                
                expense.last_posted = today
                expense.save()
                posted_count += 1
        
        return Response({
            'message': f'Posted {posted_count} recurring expenses',
            'posted_count': posted_count
        })


class RecurringExpenseViewSet(viewsets.ModelViewSet):
    """ViewSet for Recurring Expenses"""
    queryset = RecurringExpense.objects.all()
    serializer_class = RecurringExpenseSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        queryset = RecurringExpense.objects.all()
        
        is_active = self.request.query_params.get('is_active')
        if is_active is not None:
            queryset = queryset.filter(is_active=is_active.lower() == 'true')
        
        return queryset


class AutomaticEntryRuleViewSet(viewsets.ModelViewSet):
    """ViewSet for Automatic Entry Rules"""
    queryset = AutomaticEntryRule.objects.all()
    serializer_class = AutomaticEntryRuleSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        queryset = AutomaticEntryRule.objects.all()
        
        is_active = self.request.query_params.get('is_active')
        if is_active is not None:
            queryset = queryset.filter(is_active=is_active.lower() == 'true')
        
        source_model = self.request.query_params.get('source_model')
        if source_model:
            queryset = queryset.filter(source_model=source_model)
        
        return queryset


class ReportsViewSet(viewsets.ViewSet):
    """ViewSet for Financial Reports"""
    permission_classes = [IsAuthenticated]
    
    @action(detail=False, methods=['get'])
    def trial_balance(self, request):
        """Generate Trial Balance Report"""
        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')
        
        if not start_date:
            start_date = date.today().replace(day=1)
        if not end_date:
            end_date = date.today()
        
        accounts = Account.objects.filter(is_active=True).order_by('code')
        trial_balance = []
        
        total_debits = Decimal('0')
        total_credits = Decimal('0')
        
        for account in accounts:
            # Calculate balance in date range
            entries = JournalEntryLine.objects.filter(
                account=account,
                journal_entry__date__gte=start_date,
                journal_entry__date__lte=end_date
            ).aggregate(
                total_debit=Coalesce(Sum('debit_amount'), Decimal('0')),
                total_credit=Coalesce(Sum('credit_amount'), Decimal('0'))
            )
            
            debit = entries['total_debit']
            credit = entries['total_credit']
            
            if account.account_type in [AccountType.ASSET, AccountType.EXPENSE]:
                balance = debit - credit
            else:
                balance = credit - debit
            
            if account.is_contra:
                balance = -balance
            
            # Only show accounts with activity
            if debit != 0 or credit != 0:
                if balance >= 0:
                    trial_balance.append({
                        'account_code': account.code,
                        'account_name': account.name,
                        'account_type': account.account_type,
                        'debit': balance if account.account_type in [AccountType.ASSET, AccountType.EXPENSE] else Decimal('0'),
                        'credit': balance if account.account_type not in [AccountType.ASSET, AccountType.EXPENSE] else Decimal('0')
                    })
                else:
                    # Negative balance goes to opposite side
                    trial_balance.append({
                        'account_code': account.code,
                        'account_name': account.name,
                        'account_type': account.account_type,
                        'debit': -balance if account.account_type not in [AccountType.ASSET, AccountType.EXPENSE] else Decimal('0'),
                        'credit': -balance if account.account_type in [AccountType.ASSET, AccountType.EXPENSE] else Decimal('0')
                    })
                
                total_debits += trial_balance[-1]['debit']
                total_credits += trial_balance[-1]['credit']
        
        return Response({
            'report_date': date.today(),
            'start_date': start_date,
            'end_date': end_date,
            'accounts': trial_balance,
            'total_debits': total_debits,
            'total_credits': total_credits,
            'is_balanced': total_debits == total_credits
        })
    
    @action(detail=False, methods=['get'])
    def profit_loss(self, request):
        """Generate Profit & Loss Report"""
        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')
        
        if not start_date:
            # Default to current month
            today = date.today()
            start_date = today.replace(day=1)
        if not end_date:
            end_date = date.today()
        
        revenue_accounts = Account.objects.filter(
            account_type=AccountType.REVENUE, 
            is_active=True
        ).order_by('code')
        
        expense_accounts = Account.objects.filter(
            account_type=AccountType.EXPENSE, 
            is_active=True
        ).order_by('code')
        
        revenue_lines = []
        total_revenue = Decimal('0')
        
        for account in revenue_accounts:
            entries = JournalEntryLine.objects.filter(
                account=account,
                journal_entry__date__gte=start_date,
                journal_entry__date__lte=end_date
            ).aggregate(
                total_credit=Coalesce(Sum('credit_amount'), Decimal('0')),
                total_debit=Coalesce(Sum('debit_amount'), Decimal('0'))
            )
            
            amount = entries['total_credit'] - entries['total_debit']
            if amount != 0:
                revenue_lines.append({
                    'account_code': account.code,
                    'account_name': account.name,
                    'account_type': 'revenue',
                    'amount': amount
                })
                total_revenue += amount
        
        expense_lines = []
        total_expenses = Decimal('0')
        
        for account in expense_accounts:
            entries = JournalEntryLine.objects.filter(
                account=account,
                journal_entry__date__gte=start_date,
                journal_entry__date__lte=end_date
            ).aggregate(
                total_debit=Coalesce(Sum('debit_amount'), Decimal('0')),
                total_credit=Coalesce(Sum('credit_amount'), Decimal('0'))
            )
            
            amount = entries['total_debit'] - entries['total_credit']
            if amount != 0:
                expense_lines.append({
                    'account_code': account.code,
                    'account_name': account.name,
                    'account_type': 'expense',
                    'amount': amount
                })
                total_expenses += amount
        
        net_profit = total_revenue - total_expenses
        
        return Response({
            'report_date': date.today(),
            'start_date': start_date,
            'end_date': end_date,
            'revenue': revenue_lines,
            'expenses': expense_lines,
            'total_revenue': total_revenue,
            'total_expenses': total_expenses,
            'net_profit': net_profit,
            'is_profitable': net_profit >= 0
        })
    
    @action(detail=False, methods=['get'])
    def balance_sheet(self, request):
        """Generate Balance Sheet Report"""
        end_date = request.query_params.get('end_date')
        if not end_date:
            end_date = date.today()
        
        # Assets
        asset_accounts = Account.objects.filter(
            account_type=AccountType.ASSET, 
            is_active=True
        ).order_by('code')
        
        assets = []
        total_assets = Decimal('0')
        
        for account in asset_accounts:
            entries = JournalEntryLine.objects.filter(
                account=account,
                journal_entry__date__lte=end_date
            ).aggregate(
                total_debit=Coalesce(Sum('debit_amount'), Decimal('0')),
                total_credit=Coalesce(Sum('credit_amount'), Decimal('0'))
            )
            
            amount = entries['total_debit'] - entries['total_credit']
            if account.is_contra:
                amount = -amount
            
            if amount != 0:
                assets.append({
                    'account_code': account.code,
                    'account_name': account.name,
                    'amount': amount
                })
                total_assets += amount
        
        # Liabilities
        liability_accounts = Account.objects.filter(
            account_type=AccountType.LIABILITY, 
            is_active=True
        ).order_by('code')
        
        liabilities = []
        total_liabilities = Decimal('0')
        
        for account in liability_accounts:
            entries = JournalEntryLine.objects.filter(
                account=account,
                journal_entry__date__lte=end_date
            ).aggregate(
                total_credit=Coalesce(Sum('credit_amount'), Decimal('0')),
                total_debit=Coalesce(Sum('debit_amount'), Decimal('0'))
            )
            
            amount = entries['total_credit'] - entries['total_debit']
            if account.is_contra:
                amount = -amount
            
            if amount != 0:
                liabilities.append({
                    'account_code': account.code,
                    'account_name': account.name,
                    'amount': amount
                })
                total_liabilities += amount
        
        # Equity
        equity_accounts = Account.objects.filter(
            account_type=AccountType.EQUITY, 
            is_active=True
        ).order_by('code')
        
        # Calculate net income from P&L
        revenue = JournalEntryLine.objects.filter(
            account__account_type=AccountType.REVENUE,
            journal_entry__date__lte=end_date
        ).aggregate(total=Coalesce(Sum('credit_amount'), Decimal('0')))['total'] or Decimal('0')
        
        expenses = JournalEntryLine.objects.filter(
            account__account_type=AccountType.EXPENSE,
            journal_entry__date__lte=end_date
        ).aggregate(total=Coalesce(Sum('debit_amount'), Decimal('0')))['total'] or Decimal('0')
        
        net_income = revenue - expenses
        
        equity = []
        total_equity = Decimal('0')
        
        for account in equity_accounts:
            entries = JournalEntryLine.objects.filter(
                account=account,
                journal_entry__date__lte=end_date
            ).aggregate(
                total_credit=Coalesce(Sum('credit_amount'), Decimal('0')),
                total_debit=Coalesce(Sum('debit_amount'), Decimal('0'))
            )
            
            amount = entries['total_credit'] - entries['total_debit']
            if amount != 0:
                equity.append({
                    'account_code': account.code,
                    'account_name': account.name,
                    'amount': amount
                })
                total_equity += amount
        
        # Add net income to equity
        equity.append({
            'account_code': 'NET_INCOME',
            'account_name': 'Net Income (Current Period)',
            'amount': net_income
        })
        total_equity += net_income
        
        return Response({
            'report_date': end_date,
            'assets': assets,
            'total_assets': total_assets,
            'liabilities': liabilities,
            'total_liabilities': total_liabilities,
            'equity': equity,
            'total_equity': total_equity,
            'total_liabilities_equity': total_liabilities + total_equity,
            'is_balanced': total_assets == (total_liabilities + total_equity)
        })
