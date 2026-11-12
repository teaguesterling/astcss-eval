from typing import Dict, Optional, Any
from decimal import Decimal
from dataclasses import dataclass
from datetime import datetime
import hashlib
import sys
sys.path.append('/mnt/aux-data/teague/Projects/MindMeld/cop-testing/framework')
from cop_python.annotations import intent, invariant, risk, implementation_status, decision
from ..models.order import Order, PaymentInfo
from ..models.user import User


@dataclass
class PaymentResult:
    success: bool
    transaction_id: Optional[str] = None
    error_message: Optional[str] = None
    error_code: Optional[str] = None
    processed_amount: Decimal = Decimal('0')


@dataclass
class RefundResult:
    success: bool
    refund_id: Optional[str] = None
    error_message: Optional[str] = None
    refunded_amount: Decimal = Decimal('0')


class PaymentService:
    def __init__(self):
        self.transactions: Dict[str, Dict[str, Any]] = {}
        self.failed_attempts: Dict[str, int] = {}

    @intent("Process secure payment transactions with fraud detection")
    @invariant("amount > 0 and amount <= order.total_amount")
    @risk("HIGH", details="Handles sensitive payment data and financial transactions")
    @decision("Use tokenized payment processing", alternatives=["Direct card processing", "Third-party gateway"])
    @implementation_status("IMPLEMENTED")
    def process_payment(self, order: Order, payment_info: PaymentInfo) -> PaymentResult:
        if order.total_amount <= 0:
            return PaymentResult(
                success=False,
                error_message="Invalid payment amount",
                error_code="INVALID_AMOUNT"
            )

        # Fraud detection checks
        fraud_check = self._perform_fraud_detection(order, payment_info)
        if not fraud_check.get("passed", False):
            return PaymentResult(
                success=False,
                error_message=f"Payment blocked: {fraud_check.get('reason', 'Fraud detected')}",
                error_code="FRAUD_DETECTED"
            )

        # Validate payment method
        if not self._validate_payment_method(payment_info):
            return PaymentResult(
                success=False,
                error_message="Invalid payment method or details",
                error_code="INVALID_PAYMENT_METHOD"
            )

        # Process payment based on method
        if payment_info.payment_method == "credit_card":
            return self._process_credit_card(order, payment_info)
        elif payment_info.payment_method == "paypal":
            return self._process_paypal(order, payment_info)
        elif payment_info.payment_method == "bank_transfer":
            return self._process_bank_transfer(order, payment_info)
        else:
            return PaymentResult(
                success=False,
                error_message="Unsupported payment method",
                error_code="UNSUPPORTED_METHOD"
            )

    @intent("Detect potentially fraudulent payment attempts")
    @invariant("order.total_amount > 0")
    @risk("HIGH", details="Fraud detection affects legitimate customers and business revenue")
    @decision("Multi-factor fraud detection", alternatives=["Rule-based only", "ML-based only"])
    @implementation_status("IMPLEMENTED")
    def _perform_fraud_detection(self, order: Order, payment_info: PaymentInfo) -> Dict[str, Any]:
        user_id = order.user.user_id
        
        # Check failed attempt history
        failed_count = self.failed_attempts.get(user_id, 0)
        if failed_count >= 3:
            return {"passed": False, "reason": "Too many failed attempts"}

        # Amount-based checks
        if order.total_amount > Decimal('10000'):
            return {"passed": False, "reason": "Amount exceeds limit"}

        # Billing/shipping address mismatch
        billing_addr = payment_info.billing_address
        shipping_addr = order.shipping_address
        if (billing_addr.state != shipping_addr.state and 
            order.total_amount > Decimal('500')):
            return {"passed": False, "reason": "Address mismatch on high-value order"}

        # Velocity checks (simplified)
        recent_orders = sum(1 for t in self.transactions.values() 
                          if t.get("user_id") == user_id and 
                          (datetime.now() - t.get("created_at", datetime.min)).hours < 1)
        if recent_orders >= 5:
            return {"passed": False, "reason": "Too many recent orders"}

        return {"passed": True, "risk_score": 0.1}

    @intent("Validate payment method and credentials")
    @invariant("payment_info.payment_method in ['credit_card', 'paypal', 'bank_transfer']")
    @risk("HIGH", details="Payment validation prevents fraud but must not block legitimate payments")
    @implementation_status("IMPLEMENTED")
    def _validate_payment_method(self, payment_info: PaymentInfo) -> bool:
        method = payment_info.payment_method
        details = payment_info.payment_details

        if method == "credit_card":
            return (
                "card_number" in details and
                "cvv" in details and
                "expiry_month" in details and
                "expiry_year" in details and
                len(details["card_number"]) >= 13 and
                len(details["cvv"]) in [3, 4]
            )
        elif method == "paypal":
            return "paypal_email" in details
        elif method == "bank_transfer":
            return "account_number" in details and "routing_number" in details
        return False

    @intent("Process credit card payment transaction")
    @invariant("order.total_amount > 0")
    @risk("HIGH", details="Credit card processing involves PCI compliance and sensitive data")
    @implementation_status("IMPLEMENTED")
    def _process_credit_card(self, order: Order, payment_info: PaymentInfo) -> PaymentResult:
        # Generate transaction ID
        transaction_id = self._generate_transaction_id(order, payment_info)
        
        # Simulate credit card processing
        card_details = payment_info.payment_details
        
        # Basic card validation
        if not self._validate_credit_card(card_details):
            self._record_failed_attempt(order.user.user_id)
            return PaymentResult(
                success=False,
                error_message="Invalid credit card details",
                error_code="INVALID_CARD"
            )

        # Simulate payment processing (would be external API call)
        success = self._simulate_payment_gateway(order.total_amount, card_details)
        
        if success:
            # Record successful transaction
            self.transactions[transaction_id] = {
                "order_id": order.order_id,
                "user_id": order.user.user_id,
                "amount": order.total_amount,
                "payment_method": "credit_card",
                "created_at": datetime.now(),
                "status": "completed"
            }
            
            # Clear failed attempts on success
            self.failed_attempts.pop(order.user.user_id, None)
            
            return PaymentResult(
                success=True,
                transaction_id=transaction_id,
                processed_amount=order.total_amount
            )
        else:
            self._record_failed_attempt(order.user.user_id)
            return PaymentResult(
                success=False,
                error_message="Payment declined by bank",
                error_code="PAYMENT_DECLINED"
            )

    @intent("Validate credit card number and details")
    @invariant("card_details contains required fields")
    @risk("HIGH", details="Card validation must be secure and PCI compliant")
    @implementation_status("IMPLEMENTED")
    def _validate_credit_card(self, card_details: Dict[str, Any]) -> bool:
        card_number = card_details.get("card_number", "")
        cvv = card_details.get("cvv", "")
        expiry_month = card_details.get("expiry_month", 0)
        expiry_year = card_details.get("expiry_year", 0)
        
        # Basic Luhn algorithm check (simplified)
        if not self._luhn_check(card_number):
            return False
            
        # Expiry date validation
        current_year = datetime.now().year
        current_month = datetime.now().month
        
        if expiry_year < current_year or (expiry_year == current_year and expiry_month < current_month):
            return False
            
        return True

    @intent("Perform Luhn algorithm check on credit card number")
    @invariant("len(card_number) >= 13")
    @implementation_status("IMPLEMENTED")
    def _luhn_check(self, card_number: str) -> bool:
        # Remove spaces and non-digits
        card_number = ''.join(filter(str.isdigit, card_number))
        
        if len(card_number) < 13:
            return False
            
        # Luhn algorithm
        total = 0
        reverse_digits = card_number[::-1]
        
        for i, digit in enumerate(reverse_digits):
            n = int(digit)
            if i % 2 == 1:  # Every second digit from right
                n *= 2
                if n > 9:
                    n = n // 10 + n % 10
            total += n
            
        return total % 10 == 0

    @intent("Simulate external payment gateway processing")
    @risk("MEDIUM", details="Payment gateway simulation for development/testing")
    @implementation_status("IMPLEMENTED")
    def _simulate_payment_gateway(self, amount: Decimal, card_details: Dict[str, Any]) -> bool:
        # Simulate different success rates based on amount
        if amount > Decimal('5000'):
            return False  # High amounts more likely to fail
        return True  # Simplified - always succeed for demo

    @intent("Process PayPal payment transaction")
    @invariant("order.total_amount > 0")
    @risk("MEDIUM", details="PayPal integration requires secure API handling")
    @implementation_status("IMPLEMENTED")
    def _process_paypal(self, order: Order, payment_info: PaymentInfo) -> PaymentResult:
        transaction_id = self._generate_transaction_id(order, payment_info)
        
        # Simulate PayPal processing
        self.transactions[transaction_id] = {
            "order_id": order.order_id,
            "user_id": order.user.user_id,
            "amount": order.total_amount,
            "payment_method": "paypal",
            "created_at": datetime.now(),
            "status": "completed"
        }
        
        return PaymentResult(
            success=True,
            transaction_id=transaction_id,
            processed_amount=order.total_amount
        )

    @intent("Process bank transfer payment")
    @invariant("order.total_amount > 0")
    @risk("LOW", details="Bank transfers are typically secure but slower")
    @implementation_status("IMPLEMENTED")
    def _process_bank_transfer(self, order: Order, payment_info: PaymentInfo) -> PaymentResult:
        transaction_id = self._generate_transaction_id(order, payment_info)
        
        # Bank transfers require manual verification
        self.transactions[transaction_id] = {
            "order_id": order.order_id,
            "user_id": order.user.user_id,
            "amount": order.total_amount,
            "payment_method": "bank_transfer",
            "created_at": datetime.now(),
            "status": "pending_verification"
        }
        
        return PaymentResult(
            success=True,
            transaction_id=transaction_id,
            processed_amount=order.total_amount
        )

    @intent("Generate unique transaction identifier")
    @implementation_status("IMPLEMENTED")
    def _generate_transaction_id(self, order: Order, payment_info: PaymentInfo) -> str:
        data = f"{order.order_id}_{order.user.user_id}_{datetime.now().isoformat()}"
        return hashlib.md5(data.encode()).hexdigest()

    @intent("Record failed payment attempt for fraud detection")
    @implementation_status("IMPLEMENTED")
    def _record_failed_attempt(self, user_id: str) -> None:
        self.failed_attempts[user_id] = self.failed_attempts.get(user_id, 0) + 1

    @intent("Process refund for completed transaction")
    @invariant("amount > 0 and transaction_id exists")
    @risk("MEDIUM", details="Refunds affect financial records and customer satisfaction")
    @implementation_status("IMPLEMENTED")
    def process_refund(self, transaction_id: str, amount: Decimal, 
                      reason: str = "") -> RefundResult:
        if amount <= 0:
            return RefundResult(
                success=False,
                error_message="Invalid refund amount"
            )
            
        transaction = self.transactions.get(transaction_id)
        if not transaction:
            return RefundResult(
                success=False,
                error_message="Transaction not found"
            )
            
        if amount > transaction["amount"]:
            return RefundResult(
                success=False,
                error_message="Refund amount exceeds original transaction"
            )
            
        # Generate refund ID
        refund_id = f"REF_{transaction_id}_{datetime.now().strftime('%Y%m%d%H%M%S')}"
        
        # Process refund (would be external API call)
        transaction["refunded_amount"] = transaction.get("refunded_amount", Decimal('0')) + amount
        transaction["status"] = "refunded" if transaction["refunded_amount"] >= transaction["amount"] else "partially_refunded"
        
        return RefundResult(
            success=True,
            refund_id=refund_id,
            refunded_amount=amount
        )