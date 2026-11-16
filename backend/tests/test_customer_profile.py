"""Unit tests for customer profile synchronization service."""
from __future__ import annotations

import pytest

from app.models.entities import CustomerProfile


def test_customer_profile_model_fields():
    """Verify CustomerProfile model has all expected attributes."""
    expected_attrs = [
        "id",
        "document_id",
        "name_english",
        "customer_id",
        "account_number",
        "branch_name",
        "gender",
        "marital_status",
        "dob_bs",
        "nationality",
        "email",
        "mobile",
        "permanent_address",
        "current_address",
        "education",
        "verification_status",
        "created_at",
        "updated_at",
    ]
    for attr in expected_attrs:
        assert hasattr(CustomerProfile, attr), f"CustomerProfile missing attribute: {attr}"


def test_customer_profile_tablename():
    """Verify the correct table name is set."""
    assert CustomerProfile.__tablename__ == "customer_profiles"


def test_format_address_helper():
    """Verify address formatting from address components."""
    from app.services.extraction.customer import _format_address

    components = {
        "ward": "14",
        "municipality": "Kathmandu",
        "district": "Kathmandu",
        "province": "Bagmati Province",
        "country": "Nepal",
    }
    result = _format_address(components)
    assert "Ward 14" in result
    assert "Kathmandu" in result
    assert "Nepal" in result


def test_format_address_empty():
    """Verify empty dict returns None."""
    from app.services.extraction.customer import _format_address

    assert _format_address({}) is None


def test_sync_returns_none_for_missing_doc(client):
    """sync_customer_profile returns None when document doesn't exist."""
    from app.database.session import get_db
    from app.services.extraction.customer import sync_customer_profile

    db = next(get_db())
    result = sync_customer_profile(db, document_id=99999)
    assert result is None
