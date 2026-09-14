"""Shared pytest fixtures for alert-engine tests."""

import pytest


@pytest.fixture
def tmp_alert():
    from alert_engine.aggregation import Alert
    return Alert(
        id="test-1",
        alert_name="TestAlert",
        service="test-service",
        cluster="test-cluster",
        severity="p1",
        timestamp=0.0,
    )
