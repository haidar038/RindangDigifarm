import os, requests, logging
from requests.auth import HTTPBasicAuth
from flask import url_for, current_app
from datetime import datetime, timedelta

XENDIT_SECRET = os.getenv('XENDIT_SECRET_KEY')
XENDIT_PUBLIC = os.getenv('XENDIT_PUBLIC_API_KEY')
XENDIT_BASE   = 'https://api.xendit.co'
API_VERSION   = '2022-07-31'

class XenditError(Exception):
    """Custom exception for Xendit API errors"""
    def __init__(self, message, status_code=None, error_code=None, response=None):
        self.message = message
        self.status_code = status_code
        self.error_code = error_code
        self.response = response
        super().__init__(self.message)

class XenditClient:
    @staticmethod
    def _handle_response(response, operation_name):
        """Handle API response and raise appropriate exceptions"""
        try:
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as e:
            error_data = {}
            try:
                error_data = response.json()
            except:
                error_data = {"message": "Could not parse error response"}

            error_message = error_data.get('message', f"Error in {operation_name}")
            error_code = error_data.get('error_code', 'unknown')

            current_app.logger.error(
                f"Xendit API error in {operation_name}: {error_message} "
                f"(Status: {response.status_code}, Error code: {error_code})"
            )

            raise XenditError(
                message=error_message,
                status_code=response.status_code,
                error_code=error_code,
                response=error_data
            )
        except requests.exceptions.RequestException as e:
            current_app.logger.error(f"Request error in {operation_name}: {str(e)}")
            raise XenditError(f"Connection error in {operation_name}: {str(e)}")
        except Exception as e:
            current_app.logger.error(f"Unexpected error in {operation_name}: {str(e)}")
            raise XenditError(f"Unexpected error in {operation_name}: {str(e)}")

    @staticmethod
    def create_qr_code(seller_id, external_id=None, amount=None):
        """
        Create a QR code for a transaction

        This method can create both static and dynamic QR codes:
        - If amount is provided, creates a dynamic QR code with a fixed amount
        - If amount is not provided, creates a static QR code that can be used multiple times

        Args:
            seller_id: ID of the seller
            external_id: Optional external ID (e.g., order-123)
            amount: Optional fixed amount for the QR code

        Returns:
            Dictionary containing QR code details including qr_string
        """
        url = f"{XENDIT_BASE}/qr_codes"

        # Use provided external_id or generate one based on seller_id
        reference_id = external_id or f'market-{seller_id}'

        # Determine QR type based on amount
        qr_type = 'DYNAMIC' if amount else 'STATIC'

        payload = {
            'reference_id': reference_id,
            'type': qr_type,
            'currency': 'IDR',
            'channel_code': 'ID_DANA'  # Required channel code for Indonesian QR payments
        }

        # Add amount if provided (for dynamic QR)
        if amount:
            payload['amount'] = amount

        # Add callback URL
        payload['callback_url'] = url_for('public.xendit_webhook', _external=True)

        headers = {'api-version': API_VERSION}

        try:
            resp = requests.post(
                url,
                json=payload,
                auth=HTTPBasicAuth(XENDIT_SECRET, ''),
                headers=headers
            )
            data = XenditClient._handle_response(resp, "create_qr_code")
            return data
        except XenditError as e:
            current_app.logger.error(f"Failed to create QR code: {e.message}")
            raise
        except Exception as e:
            current_app.logger.error(f"Unexpected error creating QR code: {str(e)}")
            raise XenditError(f"Unexpected error creating QR code: {str(e)}")

    @staticmethod
    def create_static_qr(seller_id, external_id=None, amount=None):
        """
        Create a QR code for a transaction (Legacy method, use create_qr_code instead)

        This method is maintained for backward compatibility.

        Args:
            seller_id: ID of the seller
            external_id: Optional external ID (e.g., order-123)
            amount: Optional fixed amount for the QR code

        Returns:
            Dictionary containing QR code details including qr_string
        """
        current_app.logger.warning("create_static_qr is deprecated, use create_qr_code instead")
        return XenditClient.create_qr_code(seller_id, external_id, amount)

    @staticmethod
    def simulate_payment(qr_id, amount):
        """
        Simulate a payment (for testing purposes)

        Args:
            qr_id: QR code ID or external_id
            amount: Payment amount

        Returns:
            Dictionary containing payment details
        """
        # Check if we're in test mode
        if current_app.config.get('XENDIT_MODE', 'test') != 'test':
            raise XenditError("Payment simulation is only available in test mode")

        # For QR IDs that start with 'order-', we need to handle them differently
        # as they are external_ids, not actual Xendit QR IDs
        if qr_id.startswith('order-'):
            current_app.logger.info(f"Using external_id for simulation: {qr_id}")
            # Return a simulated success response
            return {
                'simulated': True,
                'external_id': qr_id,
                'amount': amount,
                'status': 'COMPLETED'
            }

        # Try to simulate using QR ID
        # URL format based on Xendit documentation
        url = f"{XENDIT_BASE}/qr_codes/{qr_id}/payments/simulate"

        # Prepare payload according to documentation
        payload = {
            'amount': amount
        }

        headers = {'api-version': API_VERSION}

        current_app.logger.info(f"Simulating payment for QR ID: {qr_id} with amount: {amount}")

        try:
            resp = requests.post(
                url,
                json=payload,
                auth=HTTPBasicAuth(XENDIT_SECRET, ''),
                headers=headers
            )
            return XenditClient._handle_response(resp, "simulate_payment")
        except XenditError as e:
            error_message = str(e.message).lower()

            # Handle specific error cases
            if 'not found' in error_message:
                current_app.logger.error(f"QR code not found: {qr_id}")
            elif 'invalid amount' in error_message:
                current_app.logger.error(f"Invalid amount for QR payment: {amount}")
            elif 'already paid' in error_message:
                current_app.logger.warning(f"QR code already paid: {qr_id}")
                # Return a success response for already paid QR
                return {
                    'simulated': True,
                    'external_id': qr_id,
                    'amount': amount,
                    'status': 'COMPLETED',
                    'message': 'QR code already paid'
                }

            # Log the error and re-raise
            current_app.logger.error(f"Failed to simulate payment: {e.message}")
            raise
        except Exception as e:
            current_app.logger.error(f"Unexpected error simulating payment: {str(e)}")
            raise XenditError(f"Unexpected error simulating payment: {str(e)}")

    @staticmethod
    def create_va(external_id, bank_code, name, expected_amount=None, expiration_date=None, seller_id=None):
        """
        Create a virtual account

        Args:
            external_id: External ID for the VA
            bank_code: Bank code (e.g., 'BCA', 'BNI')
            name: Account holder name
            expected_amount: Optional expected payment amount
            expiration_date: Optional expiration date
            seller_id: Optional ID of the seller (for backward compatibility)

        Returns:
            Dictionary containing VA details
        """
        url = f"{XENDIT_BASE}/v2/payment_methods/recurring_virtual_accounts"
        payload = {
            "external_id": external_id,
            "bank_code": bank_code,
            "name": name,
        }

        # Add optional parameters if provided
        if expected_amount:
            payload["expected_amount"] = expected_amount

        if expiration_date:
            payload["expiration_date"] = expiration_date
        else:
            # Default expiration: 24 hours from now
            expiration = datetime.now() + timedelta(hours=24)
            payload["expiration_date"] = expiration.strftime("%Y-%m-%d %H:%M:%S")

        try:
            resp = requests.post(
                url,
                json=payload,
                auth=HTTPBasicAuth(XENDIT_SECRET, ''),
                headers={'api-version': API_VERSION}
            )
            return XenditClient._handle_response(resp, "create_va")
        except XenditError as e:
            current_app.logger.error(f"Failed to create VA: {e.message}")
            raise
        except Exception as e:
            current_app.logger.error(f"Unexpected error creating VA: {str(e)}")
            raise XenditError(f"Unexpected error creating VA: {str(e)}")

    @staticmethod
    def get_va_payment_status(payment_id):
        """
        Get the status of a VA payment

        Args:
            payment_id: Payment ID

        Returns:
            Dictionary containing payment status details
        """
        url = f"{XENDIT_BASE}/v2/payment_methods/recurring_virtual_accounts/{payment_id}"

        try:
            resp = requests.get(
                url,
                auth=HTTPBasicAuth(XENDIT_SECRET, ''),
                headers={'api-version': API_VERSION}
            )
            return XenditClient._handle_response(resp, "get_va_payment_status")
        except XenditError as e:
            current_app.logger.error(f"Failed to get VA payment status: {e.message}")
            raise
        except Exception as e:
            current_app.logger.error(f"Unexpected error getting VA payment status: {str(e)}")
            raise XenditError(f"Unexpected error getting VA payment status: {str(e)}")

    @staticmethod
    def create_invoice(external_id, amount, payer_email, description, items=None, success_redirect_url=None):
        """
        Create an invoice

        Args:
            external_id: External ID for the invoice
            amount: Invoice amount
            payer_email: Email of the payer
            description: Invoice description
            items: Optional list of items
            success_redirect_url: Optional URL to redirect after successful payment

        Returns:
            Dictionary containing invoice details
        """
        url = f"{XENDIT_BASE}/v2/invoices"
        payload = {
            "external_id": external_id,
            "amount": amount,
            "payer_email": payer_email,
            "description": description,
        }

        if items:
            payload["items"] = items

        if success_redirect_url:
            payload["success_redirect_url"] = success_redirect_url

        try:
            resp = requests.post(
                url,
                json=payload,
                auth=HTTPBasicAuth(XENDIT_SECRET, ''),
                headers={'api-version': API_VERSION}
            )
            return XenditClient._handle_response(resp, "create_invoice")
        except XenditError as e:
            current_app.logger.error(f"Failed to create invoice: {e.message}")
            raise
        except Exception as e:
            current_app.logger.error(f"Unexpected error creating invoice: {str(e)}")
            raise XenditError(f"Unexpected error creating invoice: {str(e)}")
