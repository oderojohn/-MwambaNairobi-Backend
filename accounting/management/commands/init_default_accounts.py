from django.core.management.base import BaseCommand
from accounting.models import Account, AccountType


class Command(BaseCommand):
    help = 'Initialize default chart of accounts'

    def handle(self, *args, **options):
        default_accounts = [
            # Assets (1000-1999)
            {'code': '1000', 'name': 'Cash', 'account_type': AccountType.ASSET, 'description': 'Cash on hand'},
            {'code': '1100', 'name': 'Bank', 'account_type': AccountType.ASSET, 'description': 'Bank accounts'},
            {'code': '1200', 'name': 'Accounts Receivable', 'account_type': AccountType.ASSET, 'description': 'Customer receivables'},
            {'code': '1300', 'name': 'Inventory', 'account_type': AccountType.ASSET, 'description': 'Stock inventory'},
            {'code': '1400', 'name': 'Prepaid Expenses', 'account_type': AccountType.ASSET, 'description': 'Prepaid expenses'},
            {'code': '1500', 'name': 'Fixed Assets', 'account_type': AccountType.ASSET, 'description': 'Property, plant & equipment'},
            {'code': '1600', 'name': 'Accumulated Depreciation', 'account_type': AccountType.ASSET, 'description': 'Depreciation of fixed assets', 'is_contra': True},
            
            # Liabilities (2000-2999)
            {'code': '2000', 'name': 'Accounts Payable', 'account_type': AccountType.LIABILITY, 'description': 'Supplier payables'},
            {'code': '2100', 'name': 'Notes Payable', 'account_type': AccountType.LIABILITY, 'description': 'Notes and loans'},
            {'code': '2200', 'name': 'Accrued Expenses', 'account_type': AccountType.LIABILITY, 'description': 'Accrued expenses'},
            {'code': '2300', 'name': 'Tax Payable', 'account_type': AccountType.LIABILITY, 'description': 'Tax liabilities'},
            {'code': '2400', 'name': 'Unearned Revenue', 'account_type': AccountType.LIABILITY, 'description': 'Advance payments'},
            
            # Equity (3000-3999)
            {'code': '3000', 'name': 'Owner\'s Capital', 'account_type': AccountType.EQUITY, 'description': 'Owner investment'},
            {'code': '3100', 'name': 'Retained Earnings', 'account_type': AccountType.EQUITY, 'description': 'Accumulated profits'},
            {'code': '3200', 'name': 'Owner\'s Drawings', 'account_type': AccountType.EQUITY, 'description': 'Owner withdrawals', 'is_contra': True},
            
            # Revenue (4000-4999)
            {'code': '4000', 'name': 'Sales Revenue', 'account_type': AccountType.REVENUE, 'description': 'Product sales'},
            {'code': '4100', 'name': 'Service Revenue', 'account_type': AccountType.REVENUE, 'description': 'Service income'},
            {'code': '4200', 'name': 'Interest Income', 'account_type': AccountType.REVENUE, 'description': 'Interest earned'},
            {'code': '4300', 'name': 'Other Income', 'account_type': AccountType.REVENUE, 'description': 'Miscellaneous income'},
            {'code': '4400', 'name': 'Sales Returns', 'account_type': AccountType.REVENUE, 'description': 'Returns and allowances', 'is_contra': True},
            {'code': '4500', 'name': 'Sales Discounts', 'account_type': AccountType.REVENUE, 'description': 'Discounts given', 'is_contra': True},
            
            # Expenses (5000-5999)
            {'code': '5000', 'name': 'Cost of Goods Sold', 'account_type': AccountType.EXPENSE, 'description': 'Cost of sales'},
            {'code': '5100', 'name': 'Salaries & Wages', 'account_type': AccountType.EXPENSE, 'description': 'Staff salaries'},
            {'code': '5200', 'name': 'Rent Expense', 'account_type': AccountType.EXPENSE, 'description': 'Office/shop rent'},
            {'code': '5300', 'name': 'Utilities', 'account_type': AccountType.EXPENSE, 'description': 'Electricity, water, etc.'},
            {'code': '5400', 'name': 'Telephone & Internet', 'account_type': AccountType.EXPENSE, 'description': 'Communication costs'},
            {'code': '5500', 'name': 'Transport & Delivery', 'account_type': AccountType.EXPENSE, 'description': 'Transportation costs'},
            {'code': '5600', 'name': 'Advertising', 'account_type': AccountType.EXPENSE, 'description': 'Marketing costs'},
            {'code': '5700', 'name': 'Supplies', 'account_type': AccountType.EXPENSE, 'description': 'Office supplies'},
            {'code': '5800', 'name': 'Insurance', 'account_type': AccountType.EXPENSE, 'description': 'Insurance premiums'},
            {'code': '5900', 'name': 'Depreciation Expense', 'account_type': AccountType.EXPENSE, 'description': 'Asset depreciation'},
            {'code': '6000', 'name': 'Professional Fees', 'account_type': AccountType.EXPENSE, 'description': 'Legal, accounting fees'},
            {'code': '6100', 'name': 'Bank Charges', 'account_type': AccountType.EXPENSE, 'description': 'Bank fees'},
            {'code': '6200', 'name': 'Interest Expense', 'account_type': AccountType.EXPENSE, 'description': 'Interest paid'},
            {'code': '6300', 'name': 'Miscellaneous Expense', 'account_type': AccountType.EXPENSE, 'description': 'Other expenses'},
        ]
        
        created_count = 0
        for acc_data in default_accounts:
            is_contra = acc_data.pop('is_contra', False)
            if not Account.objects.filter(code=acc_data['code']).exists():
                Account.objects.create(
                    code=acc_data['code'],
                    name=acc_data['name'],
                    account_type=acc_data['account_type'],
                    description=acc_data.get('description', ''),
                    is_contra=is_contra
                )
                created_count += 1
                self.stdout.write(f"Created: {acc_data['code']} - {acc_data['name']}")
        
        self.stdout.write(self.style.SUCCESS(f'\nSuccessfully created {created_count} default accounts'))
