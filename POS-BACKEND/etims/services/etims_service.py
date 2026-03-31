"""
KRA eTIMS Integration Service

This service handles all communication with the KRA eTIMS API
including fiscal receipt registration, status checks, and offline sync.

All API calls are made from the backend server - never from the frontend.
"""
import json
import time
import requests
from datetime import datetime
from django.conf import settings
from django.utils import timezone
from django.db import transaction
from typing import Optional, Dict, Any, Tuple

from ..models import (
    ETimsConfiguration,
    FiscalReceipt,
    FiscalReceiptItem,
    OfflineTransactionQueue,
    ETimsApiLog
)
from ..serializers import KRAFiscalPayloadSerializer


class ETimsApiError(Exception):
    """Custom exception for eTIMS API errors"""
    def __init__(self, message, response_data=None):
        super().__init__(message)
        self.response_data = response_data


class ETimsService:
    """
    Service for KRA eTIMS API communication
    
    All methods handle their own API logging and error handling.
    """
    
    BASE_URL_SANDBOX = 'https://etims-test.kra.go.ke/etimsapi'
    BASE_URL_PROD = 'https://etims.kra.go.ke/etimsapi'
    
    def __init__(self, config: ETimsConfiguration = None):
        """
        Initialize with optional configuration.
        If not provided, uses the active configuration.
        """
        if config is None:
            config = ETimsConfiguration.objects.filter(is_active=True).first()
        
        if config is None:
            raise ValueError("No active eTIMS configuration found")
        
        self.config = config
        self.base_url = self.BASE_URL_SANDBOX if config.is_sandbox else self.BASE_URL_PROD
    
    def _get_headers(self) -> Dict[str, str]:
        """Generate API headers with authentication"""
        timestamp = datetime.utcnow().strftime('%Y%m%d%H%M%S')
        
        return {
            'Content-Type': 'application/json',
            'APIKey': self.config.api_key,
            'APISecret': self.config.api_secret,
            'Timestamp': timestamp,
        }
    
    def _log_api_call(
        self,
        endpoint: str,
        method: str,
        request_data: Dict = None,
        response_data: Dict = None,
        status_code: int = None,
        success: bool = False,
        error_details: str = None,
        duration_ms: int = None,
        fiscal_receipt: FiscalReceipt = None
    ) -> ETimsApiLog:
        """Log API call to database"""
        return ETimsApiLog.objects.create(
            endpoint=endpoint,
            method=method,
            request_payload=request_data,
            response_payload=response_data,
            status_code=status_code,
            success=success,
            error_details=error_details,
            duration_ms=duration_ms,
            fiscal_receipt=fiscal_receipt
        )
    
    def _make_request(
        self,
        endpoint: str,
        method: str,
        data: Dict = None,
        fiscal_receipt: FiscalReceipt = None
    ) -> Tuple[Dict, bool]:
        """
        Make API request to KRA eTIMS
        
        Returns: (response_data, success)
        """
        url = f"{self.base_url}/{endpoint}"
        headers = self._get_headers()
        
        start_time = time.time()
        success = False
        response_data = None
        status_code = None
        error_details = None
        
        try:
            if method == 'GET':
                response = requests.get(url, headers=headers, params=data, timeout=30)
            elif method == 'POST':
                response = requests.post(url, headers=headers, json=data, timeout=30)
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")
            
            status_code = response.status_code
            duration_ms = int((time.time() - start_time) * 1000)
            
            if response.status_code in [200, 201]:
                response_data = response.json()
                success = True
            else:
                try:
                    response_data = response.json()
                    error_details = response_data.get('error', response.text)
                except:
                    error_details = response.text
            
        except requests.exceptions.Timeout:
            error_details = "Request timed out"
        except requests.exceptions.RequestException as e:
            error_details = str(e)
            duration_ms = int((time.time() - start_time) * 1000)
        
        # Log the API call
        self._log_api_call(
            endpoint=endpoint,
            method=method,
            request_data=data,
            response_data=response_data,
            status_code=status_code,
            success=success,
            error_details=error_details,
            duration_ms=duration_ms,
            fiscal_receipt=fiscal_receipt
        )
        
        if not success and error_details:
            raise ETimsApiError(error_details, response_data)
        
        return response_data, success
    
    def register_fiscal_receipt(self, fiscal_receipt: FiscalReceipt) -> Dict:
        """
        Register a fiscal receipt with KRA eTIMS
        
        Args:
            fiscal_receipt: FiscalReceipt model instance
            
        Returns:
            Dict with KRA response data
        """
        # Build payload
        payload = self._build_fiscal_payload(fiscal_receipt)
        
        # Make API call
        response_data, success = self._make_request(
            endpoint='fiscalReceipt',
            method='POST',
            data=payload,
            fiscal_receipt=fiscal_receipt
        )
        
        if success:
            # Update fiscal receipt with KRA response
            fiscal_receipt.status = 'signed' if response_data.get('success') else 'failed'
            fiscal_receipt.kra_serial = response_data.get('serial_number')
            fiscal_receipt.receipt_datetime = response_data.get('timestamp', timezone.now())
            fiscal_receipt.raw_response = response_data
            fiscal_receipt.sent_at = timezone.now()
            fiscal_receipt.save()
            
            return response_data
        else:
            fiscal_receipt.status = 'failed'
            fiscal_receipt.error_message = response_data.get('error', 'Unknown error')
            fiscal_receipt.raw_response = response_data
            fiscal_receipt.sent_at = timezone.now()
            fiscal_receipt.save()
            
            raise ETimsApiError(
                fiscal_receipt.error_message,
                response_data
            )
    
    def _build_fiscal_payload(self, fiscal_receipt: FiscalReceipt) -> Dict:
        """
        Build KRA-compliant fiscal receipt payload
        """
        # Get items
        items = []
        for item in fiscal_receipt.items.all():
            items.append({
                'productCode': item.product_code,
                'productName': item.product_name,
                'hsCode': item.hs_code or '',
                'quantity': str(item.quantity),
                'unitPrice': str(item.unit_price),
                'taxRate': str(item.tax_rate),
                'taxAmount': str(item.tax_amount),
                'discountAmount': str(item.discount_amount),
                'lineTotal': str(item.line_total)
            })
        
        payload = {
            'tin': self.config.tin,
            'branchId': self.config.branch_id,
            'deviceSerial': self.config.device_serial,
            'receiptNumber': fiscal_receipt.receipt_number,
            'receiptDateTime': fiscal_receipt.created_at.isoformat(),
            'transactionType': fiscal_receipt.transaction_type,
            'customerTin': fiscal_receipt.customer_tin or '',
            'customerName': fiscal_receipt.customer_name or '',
            'totalAmount': str(fiscal_receipt.total_amount),
            'taxAmount': str(fiscal_receipt.tax_amount),
            'discountAmount': str(fiscal_receipt.discount_amount),
            'items': items
        }
        
        return payload
    
    def void_fiscal_receipt(self, fiscal_receipt: FiscalReceipt, void_reason: str) -> Dict:
        """
        Void a previously registered fiscal receipt
        
        Args:
            fiscal_receipt: FiscalReceipt to void
            void_reason: Reason for voiding
            
        Returns:
            Dict with KRA response data
        """
        payload = {
            'tin': self.config.tin,
            'branchId': self.config.branch_id,
            'deviceSerial': self.config.device_serial,
            'originalReceiptNumber': fiscal_receipt.receipt_number,
            'voidReason': void_reason,
            'voidDateTime': timezone.now().isoformat()
        }
        
        response_data, success = self._make_request(
            endpoint='voidReceipt',
            method='POST',
            data=payload,
            fiscal_receipt=fiscal_receipt
        )
        
        if success:
            fiscal_receipt.status = 'voided'
            fiscal_receipt.raw_response = response_data
            fiscal_receipt.save()
        
        return response_data
    
    def check_connection(self) -> Dict:
        """
        Check connection to KRA eTIMS API
        
        Returns:
            Dict with connection status
        """
        try:
            response_data, success = self._make_request(
                endpoint='ping',
                method='GET'
            )
            
            return {
                'connected': success,
                'message': response_data.get('message', 'Connected') if success else 'Connection failed',
                'environment': 'sandbox' if self.config.is_sandbox else 'production'
            }
        except Exception as e:
            return {
                'connected': False,
                'message': str(e),
                'environment': 'sandbox' if self.config.is_sandbox else 'production'
            }


class FiscalReceiptService:
    """
    Service for managing fiscal receipts
    """
    
    @staticmethod
    def create_from_sale(sale) -> FiscalReceipt:
        """
        Create fiscal receipt from a sale
        
        Args:
            sale: Sale model instance
            
        Returns:
            FiscalReceipt instance
        """
        with transaction.atomic():
            # Get eTIMS config
            config = ETimsConfiguration.objects.filter(is_active=True).first()
            
            # Create receipt
            receipt = FiscalReceipt.objects.create(
                sale=sale,
                receipt_number=sale.receipt_number,
                total_amount=sale.final_amount,
                tax_amount=sale.tax_amount,
                discount_amount=sale.discount_amount,
                customer_tin=sale.customer.tin if sale.customer else None,
                customer_name=sale.customer.name if sale.customer else None,
                transaction_type='sale',
                status='pending'
            )
            
            # Create items
            for item in sale.saleitem_set.all():
                # Calculate tax amount
                line_total = float(item.unit_price) * int(item.quantity)
                tax_amount = line_total - (line_total / 1.16)  # 16% VAT
                
                FiscalReceiptItem.objects.create(
                    receipt=receipt,
                    product_code=item.product.sku or str(item.product.id),
                    product_name=item.product.name,
                    hs_code=item.product.hs_code if hasattr(item.product, 'hs_code') else '',
                    quantity=item.quantity,
                    unit_price=item.unit_price,
                    tax_rate=16.0,
                    tax_amount=tax_amount,
                    discount_amount=item.discount or 0,
                    line_total=line_total
                )
            
            return receipt
    
    @staticmethod
    def create_from_return(return_record) -> FiscalReceipt:
        """
        Create fiscal receipt from a return
        
        Args:
            return_record: Return model instance
            
        Returns:
            FiscalReceipt instance
        """
        with transaction.atomic():
            receipt = FiscalReceipt.objects.create(
                return_record=return_record,
                sale=return_record.sale,
                receipt_number=f"RET-{return_record.id}",
                total_amount=return_record.total_refund or 0,
                tax_amount=0,
                discount_amount=0,
                customer_tin=return_record.sale.customer.tin if return_record.sale.customer else None,
                customer_name=return_record.sale.customer.name if return_record.sale.customer else None,
                transaction_type='return',
                status='pending'
            )
            
            # Create items from return items
            for item in return_record.items.all():
                FiscalReceiptItem.objects.create(
                    receipt=receipt,
                    product_code=item.product.sku or str(item.product.id),
                    product_name=item.product.name,
                    quantity=item.quantity,
                    unit_price=item.unit_price,
                    tax_rate=0,  # Returns typically don't have tax
                    tax_amount=0,
                    discount_amount=0,
                    line_total=float(item.unit_price) * item.quantity
                )
            
            return receipt
    
    @staticmethod
    def register_pending_receipts() -> Dict:
        """
        Register all pending fiscal receipts
        
        Returns:
            Dict with results
        """
        pending_receipts = FiscalReceipt.objects.filter(status='pending')
        results = {
            'total': pending_receipts.count(),
            'success': 0,
            'failed': 0,
            'errors': []
        }
        
        for receipt in pending_receipts:
            try:
                etims = ETimsService()
                etims.register_fiscal_receipt(receipt)
                results['success'] += 1
            except ETimsApiError as e:
                results['failed'] += 1
                results['errors'].append({
                    'receipt': str(receipt.receipt_number),
                    'error': str(e)
                })
        
        return results


class OfflineSyncService:
    """
    Service for handling offline transactions
    """
    
    @staticmethod
    def queue_transaction(
        transaction_type: str,
        reference_id: str,
        payload: Dict
    ) -> OfflineTransactionQueue:
        """
        Queue a transaction for offline sync
        
        Args:
            transaction_type: Type of transaction (sale, return, void)
            reference_id: Reference ID for the transaction
            payload: Transaction payload
            
        Returns:
            OfflineTransactionQueue instance
        """
        return OfflineTransactionQueue.objects.create(
            transaction_type=transaction_type,
            reference_id=reference_id,
            payload=payload,
            status='pending'
        )
    
    @staticmethod
    def process_offline_transactions() -> Dict:
        """
        Process all pending offline transactions
        
        Returns:
            Dict with processing results
        """
        pending = OfflineTransactionQueue.objects.filter(
            status='pending',
            retry_count__lt=3
        )
        
        results = {
            'total': pending.count(),
            'processed': 0,
            'failed': 0
        }
        
        for item in pending:
            item.status = 'processing'
            item.save()
            
            try:
                etims = ETimsService()
                
                if item.transaction_type == 'sale':
                    # Handle sale
                    pass
                elif item.transaction_type == 'return':
                    # Handle return
                    pass
                elif item.transaction_type == 'void':
                    # Handle void
                    pass
                
                item.status = 'completed'
                item.processed_at = timezone.now()
                item.save()
                results['processed'] += 1
                
            except Exception as e:
                item.retry_count += 1
                item.last_error = str(e)
                
                if item.retry_count >= item.max_retries:
                    item.status = 'failed'
                
                item.save()
                results['failed'] += 1
        
        return results
