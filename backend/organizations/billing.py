from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from django.conf import settings
from django.utils import timezone

from organizations.models import OrganizationBillingProfile

try:
	import stripe
except Exception:  # pragma: no cover
	stripe = None


@dataclass
class BillingCheckoutSession:
	session_id: str
	checkout_url: str


def stripe_is_configured() -> bool:
	return bool(stripe and getattr(settings, 'STRIPE_SECRET_KEY', None))


def _get_stripe_client():
	if not stripe_is_configured():
		raise RuntimeError('Stripe is not configured.')
	stripe.api_key = settings.STRIPE_SECRET_KEY
	return stripe


def create_addon_checkout_session(
	*,
	billing_profile: OrganizationBillingProfile,
	add_extra_users: int,
	add_extra_organizations: int,
	actor_user,
	success_url: str | None = None,
	cancel_url: str | None = None,
) -> BillingCheckoutSession:
	client = _get_stripe_client()
	add_extra_users = max(0, int(add_extra_users or 0))
	add_extra_organizations = max(0, int(add_extra_organizations or 0))

	if add_extra_users <= 0 and add_extra_organizations <= 0:
		raise ValueError('Select at least one add-on before checkout.')

	line_items: list[dict[str, Any]] = []
	if add_extra_users > 0:
		line_items.append(
			{
				'quantity': add_extra_users,
				'price_data': {
					'currency': 'eur',
					'unit_amount': OrganizationBillingProfile.EXTRA_USER_YEARLY_EUR * 100,
					'product_data': {
						'name': 'HEFAISTOS Extra User Capacity (Yearly)',
						'description': 'Additional annual user slot for HEFAISTOS subscription.',
					},
				},
			}
		)

	if add_extra_organizations > 0:
		line_items.append(
			{
				'quantity': add_extra_organizations,
				'price_data': {
					'currency': 'eur',
					'unit_amount': OrganizationBillingProfile.EXTRA_ORG_YEARLY_EUR * 100,
					'product_data': {
						'name': 'HEFAISTOS Extra Organization Capacity (Yearly)',
						'description': 'Additional annual managed organization slot for HEFAISTOS subscription.',
					},
				},
			}
		)

	resolved_success = success_url or getattr(settings, 'STRIPE_BILLING_SUCCESS_URL', '')
	resolved_cancel = cancel_url or getattr(settings, 'STRIPE_BILLING_CANCEL_URL', '')
	if not resolved_success or not resolved_cancel:
		raise ValueError('Billing success and cancel URLs are not configured.')

	metadata = {
		'billing_kind': 'capacity_addon',
		'organization_id': str(billing_profile.organization_id),
		'initiated_by_user_id': str(actor_user.id),
		'add_extra_users': str(add_extra_users),
		'add_extra_organizations': str(add_extra_organizations),
	}

	session_args: dict[str, Any] = {
		'mode': 'payment',
		'line_items': line_items,
		'success_url': resolved_success,
		'cancel_url': resolved_cancel,
		'metadata': metadata,
	}

	if billing_profile.stripe_customer_id:
		session_args['customer'] = billing_profile.stripe_customer_id
	elif getattr(actor_user, 'email', ''):
		session_args['customer_email'] = actor_user.email

	session = client.checkout.Session.create(**session_args)
	checkout_url = getattr(session, 'url', None)
	if not checkout_url:
		raise RuntimeError('Stripe checkout URL was not returned.')

	return BillingCheckoutSession(session_id=str(session.id), checkout_url=str(checkout_url))


def apply_addon_capacity(
	*,
	billing_profile: OrganizationBillingProfile,
	stripe_session_id: str,
	stripe_customer_id: str | None,
	add_extra_users: int,
	add_extra_organizations: int,
) -> OrganizationBillingProfile:
	add_extra_users = max(0, int(add_extra_users or 0))
	add_extra_organizations = max(0, int(add_extra_organizations or 0))

	if billing_profile.last_checkout_session_id == stripe_session_id:
		return billing_profile

	billing_profile.extra_users = int(billing_profile.extra_users or 0) + add_extra_users
	billing_profile.extra_organizations = int(billing_profile.extra_organizations or 0) + add_extra_organizations
	billing_profile.last_checkout_session_id = stripe_session_id
	billing_profile.last_payment_at = timezone.now()
	if stripe_customer_id:
		billing_profile.stripe_customer_id = stripe_customer_id

	# Keep existing max_users semantics in sync with purchased user capacity.
	target_max_users = billing_profile.max_users
	organization = billing_profile.organization
	organization.max_users = target_max_users
	organization.save(update_fields=['max_users', 'updated_at'])

	billing_profile.save(
		update_fields=[
			'extra_users',
			'extra_organizations',
			'last_checkout_session_id',
			'last_payment_at',
			'stripe_customer_id',
			'updated_at',
		]
	)
	return billing_profile
