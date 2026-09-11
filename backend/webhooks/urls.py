from django.urls import path

from webhooks import coretide_handler
from webhooks import stripe_billing_handler

urlpatterns = [
    path('coretide/', coretide_handler.coretide_webhook, name='coretide_webhook'),
    path('stripe-billing/', stripe_billing_handler.stripe_billing_webhook, name='stripe_billing_webhook'),
]
