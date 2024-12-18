import stripe
from flask import url_for, current_app
import uuid
import coinbase_commerce
from coinbase_commerce import Client
from flask import current_app

# Configure Stripe API
stripe.api_key = "sk_test_51QP90fE18ScjA8YPIItIKuBJCeGobfHVyxEJia0TNXl5oyrzYJEowZQYbbvgyk5eOlnIwKz3ypdx2rzj6L68NJO300JcIF3sbB"
coinbase_commerce.api_key = "2d7874d4-6882-438c-bbc9-feaee3743dac"

# Function to create a Stripe checkout session
def create_stripe_checkout_session(cart_items, success_url, cancel_url):
    try:
        line_items = [
            {
                'price_data': {
                    'currency': 'usd',
                    'product_data': {
                        'name': item['title'],
                    },
                    'unit_amount': int(item['price'] * 100),  # Convert dollars to cents
                },
                'quantity': item['quantity'],
            }
            for item in cart_items
        ]

        session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=line_items,
            mode='payment',
            success_url=success_url,
            cancel_url=cancel_url,
        )
        return session.url  # Redirect URL for Stripe Checkout
    except Exception as e:
        current_app.logger.error(f"Stripe checkout session creation failed: {e}")
        return None

# Function to handle cryptocurrency payments with Coinbase Commerce
def create_crypto_payment(cart_items):
    try:
        # Calculate the total price in USD
        total_price_usd = sum(item['price'] * item['quantity'] for item in cart_items)

        # Create a Coinbase charge for the total price in USD
        client = Client(api_key=coinbase_commerce.api_key)

        # Create the charge
        charge_data = {
            "name": "Crypto Payment",
            "description": "Payment for cart items",
            "local_price": {"amount": str(total_price_usd), "currency": "USD"},
            "pricing_type": "fixed_price"
        }
        charge = client.create_charge(**charge_data)

        # Get the payment URL from Coinbase
        payment_address = charge['hosted_url']  # URL for users to complete the payment

        return {
            "amount_usd": total_price_usd,
            "payment_address": payment_address
        }

    except Exception as e:
        current_app.logger.error(f"Crypto payment generation failed: {e}")
        return None

# Main function to choose payment method
def handle_payment(cart_items, payment_method, success_url, cancel_url):
    if payment_method == "stripe":
        # Call the Stripe payment function
        return create_stripe_checkout_session(cart_items, success_url, cancel_url)
    elif payment_method == "crypto":
        # Call the Crypto (Coinbase Commerce) payment function
        return create_crypto_payment(cart_items)
    else:
        current_app.logger.error("Invalid payment method selected")
        return None
