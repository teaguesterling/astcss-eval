from typing import Dict, List, Optional
from datetime import datetime
from dataclasses import dataclass
import sys
sys.path.append('/mnt/aux-data/teague/Projects/MindMeld/cop-testing/framework')
from cop_python.annotations import intent, invariant, risk, implementation_status, decision
from ..models.order import Order
from ..models.user import User


@dataclass
class NotificationMessage:
    recipient: str
    subject: str
    body: str
    notification_type: str
    created_at: datetime
    sent_at: Optional[datetime] = None
    delivery_status: str = "pending"  # pending, sent, failed


class NotificationService:
    def __init__(self):
        self.messages: List[NotificationMessage] = []
        self.delivery_preferences: Dict[str, Dict[str, bool]] = {}

    @intent("Send order confirmation notification to customer")
    @invariant("order.user is not None and order.order_id is not None")
    @risk("LOW", details="Notification failures affect customer experience but not core business")
    @decision("Email notifications", alternatives=["SMS", "Push notifications", "Multi-channel"])
    @implementation_status("IMPLEMENTED")
    def send_order_confirmation(self, order: Order) -> bool:
        user = order.user
        
        # Check user preferences
        if not self._should_send_notification(user.user_id, "order_confirmation"):
            return True  # Respect user preference, but don't fail
            
        subject = f"Order Confirmation - #{order.order_id}"
        body = self._generate_order_confirmation_body(order)
        
        message = NotificationMessage(
            recipient=user.email,
            subject=subject,
            body=body,
            notification_type="order_confirmation",
            created_at=datetime.now()
        )
        
        return self._send_message(message)

    @intent("Send shipping notification when order ships")
    @invariant("order.status == OrderStatus.SHIPPED")
    @implementation_status("IMPLEMENTED")
    def send_shipping_notification(self, order: Order) -> bool:
        user = order.user
        
        if not self._should_send_notification(user.user_id, "shipping_updates"):
            return True
            
        subject = f"Your Order Has Shipped - #{order.order_id}"
        body = self._generate_shipping_notification_body(order)
        
        message = NotificationMessage(
            recipient=user.email,
            subject=subject,
            body=body,
            notification_type="shipping_notification",
            created_at=datetime.now()
        )
        
        return self._send_message(message)

    @intent("Send delivery confirmation when order is delivered")
    @invariant("order.status == OrderStatus.DELIVERED")
    @implementation_status("IMPLEMENTED")
    def send_delivery_confirmation(self, order: Order) -> bool:
        user = order.user
        
        if not self._should_send_notification(user.user_id, "delivery_updates"):
            return True
            
        subject = f"Order Delivered - #{order.order_id}"
        body = self._generate_delivery_confirmation_body(order)
        
        message = NotificationMessage(
            recipient=user.email,
            subject=subject,
            body=body,
            notification_type="delivery_confirmation",
            created_at=datetime.now()
        )
        
        return self._send_message(message)

    @intent("Send order cancellation notification")
    @invariant("order.status == OrderStatus.CANCELLED")
    @implementation_status("IMPLEMENTED")
    def send_order_cancellation(self, order: Order, reason: str = "") -> bool:
        user = order.user
        
        subject = f"Order Cancelled - #{order.order_id}"
        body = self._generate_cancellation_body(order, reason)
        
        message = NotificationMessage(
            recipient=user.email,
            subject=subject,
            body=body,
            notification_type="order_cancellation",
            created_at=datetime.now()
        )
        
        return self._send_message(message)

    @intent("Send low inventory alert to administrators")
    @invariant("product_id is not None and current_stock >= 0")
    @risk("MEDIUM", details="Inventory alerts are critical for business operations")
    @implementation_status("IMPLEMENTED")
    def send_low_inventory_alert(self, product_id: str, product_name: str, 
                                current_stock: int, threshold: int) -> bool:
        # Send to admin email (would be configurable)
        admin_email = "admin@ecommerce.com"
        
        subject = f"Low Inventory Alert - {product_name}"
        body = f"""
        Product: {product_name} (ID: {product_id})
        Current Stock: {current_stock}
        Alert Threshold: {threshold}
        
        Please restock this product soon to avoid stockouts.
        """
        
        message = NotificationMessage(
            recipient=admin_email,
            subject=subject,
            body=body,
            notification_type="inventory_alert",
            created_at=datetime.now()
        )
        
        return self._send_message(message)

    @intent("Check if user wants to receive specific notification type")
    @implementation_status("IMPLEMENTED")
    def _should_send_notification(self, user_id: str, notification_type: str) -> bool:
        user_prefs = self.delivery_preferences.get(user_id, {})
        return user_prefs.get(notification_type, True)  # Default to sending

    @intent("Send message through configured delivery channel")
    @risk("LOW", details="Message delivery failures should be logged and retried")
    @decision("Simulated email delivery", alternatives=["SMTP server", "Third-party service"])
    @implementation_status("IMPLEMENTED")
    def _send_message(self, message: NotificationMessage) -> bool:
        # Simulate email delivery
        try:
            # In real implementation, would use SMTP or email service
            message.sent_at = datetime.now()
            message.delivery_status = "sent"
            self.messages.append(message)
            return True
        except Exception:
            message.delivery_status = "failed"
            self.messages.append(message)
            return False

    @intent("Generate order confirmation email body")
    @implementation_status("IMPLEMENTED")
    def _generate_order_confirmation_body(self, order: Order) -> str:
        items_text = "\n".join([
            f"- {item.product.name} x{item.quantity} @ ${item.unit_price} = ${item.get_total_price()}"
            for item in order.items
        ])
        
        return f"""
        Dear {order.user.first_name} {order.user.last_name},
        
        Thank you for your order! Here are the details:
        
        Order ID: {order.order_id}
        Order Date: {order.created_at.strftime('%Y-%m-%d %H:%M')}
        
        Items:
        {items_text}
        
        Subtotal: ${order.subtotal}
        Tax: ${order.tax_amount}
        Shipping: ${order.shipping_cost}
        Total: ${order.total_amount}
        
        Shipping Address:
        {order.shipping_address.street}
        {order.shipping_address.city}, {order.shipping_address.state} {order.shipping_address.zip_code}
        
        We'll send you updates as your order is processed and shipped.
        
        Thank you for shopping with us!
        """

    @intent("Generate shipping notification email body")
    @implementation_status("IMPLEMENTED")
    def _generate_shipping_notification_body(self, order: Order) -> str:
        return f"""
        Dear {order.user.first_name} {order.user.last_name},
        
        Great news! Your order #{order.order_id} has been shipped and is on its way to you.
        
        Tracking information will be available shortly.
        
        Expected delivery: 3-5 business days
        
        Shipping Address:
        {order.shipping_address.street}
        {order.shipping_address.city}, {order.shipping_address.state} {order.shipping_address.zip_code}
        
        Thank you for your patience!
        """

    @intent("Generate delivery confirmation email body")
    @implementation_status("IMPLEMENTED")
    def _generate_delivery_confirmation_body(self, order: Order) -> str:
        return f"""
        Dear {order.user.first_name} {order.user.last_name},
        
        Your order #{order.order_id} has been delivered!
        
        We hope you enjoy your purchase. If you have any issues with your order,
        please don't hesitate to contact our customer service team.
        
        Thank you for shopping with us!
        """

    @intent("Generate order cancellation email body")
    @implementation_status("IMPLEMENTED")
    def _generate_cancellation_body(self, order: Order, reason: str) -> str:
        return f"""
        Dear {order.user.first_name} {order.user.last_name},
        
        Your order #{order.order_id} has been cancelled.
        
        {f"Reason: {reason}" if reason else ""}
        
        If payment was processed, a refund will be issued to your original payment method
        within 3-5 business days.
        
        If you have any questions, please contact our customer service team.
        """

    @intent("Update user notification preferences")
    @invariant("user_id is not None")
    @implementation_status("IMPLEMENTED")
    def update_notification_preferences(self, user_id: str, 
                                      preferences: Dict[str, bool]) -> bool:
        self.delivery_preferences[user_id] = preferences
        return True

    @intent("Get delivery statistics for monitoring")
    @implementation_status("IMPLEMENTED")
    def get_delivery_statistics(self) -> Dict[str, int]:
        total_messages = len(self.messages)
        sent_count = sum(1 for msg in self.messages if msg.delivery_status == "sent")
        failed_count = sum(1 for msg in self.messages if msg.delivery_status == "failed")
        pending_count = sum(1 for msg in self.messages if msg.delivery_status == "pending")
        
        return {
            "total_messages": total_messages,
            "sent": sent_count,
            "failed": failed_count,
            "pending": pending_count
        }