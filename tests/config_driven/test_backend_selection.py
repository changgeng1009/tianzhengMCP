from __future__ import annotations

import pytest

from adapters.registry import BackendNotAvailable, BackendRegistry, BackendSelector


def test_req_043_offline_available():
    result = BackendSelector().select("offline")
    assert result.availability_status == "AVAILABLE"
    assert result.real_execution_supported is False


def test_req_044_nextgen_mock_available():
    result = BackendSelector().select("nextgen_mock", mock_allowed=True)
    assert result.availability_status == "AVAILABLE_FOR_MOCK"
    assert result.mock_supported is True


def test_req_045_original_adapter_is_offline_only():
    result = BackendSelector().select("original_redraw_adapter")
    assert result.availability_status == "AVAILABLE_FOR_OFFLINE_PLANNING"
    assert result.real_execution_supported is False


@pytest.mark.parametrize(
    ("requirement", "backend"),
    [
        (46, "legacy_contract_disabled"),
        (47, "nextgen_real"),
        (48, "autocad_dotnet_plugin"),
        (49, "tianzheng_water_real"),
        (50, "tianzheng_hvac_real"),
    ],
)
def test_req_046_to_050_unavailable_backends(requirement, backend):
    assert requirement in range(46, 51)
    with pytest.raises(BackendNotAvailable):
        BackendSelector().select(backend)


def test_req_051_real_execution_is_blocked():
    with pytest.raises(BackendNotAvailable) as caught:
        BackendSelector().select("offline", require_real_execution=True)
    assert caught.value.code == "BACKEND_NOT_AVAILABLE"


def test_req_052_mock_never_impersonates_real():
    with pytest.raises(BackendNotAvailable) as caught:
        BackendSelector().select("nextgen_mock", require_real_execution=True, mock_allowed=True)
    assert caught.value.details["real_backend_available"] is False


def test_backend_registry_status_truth_table():
    contracts = {item.backend_id: item for item in BackendRegistry().list()}
    assert contracts["legacy_contract_disabled"].support_level == "DISABLED_CONTRACT_ONLY"
    assert all(not item.real_execution_supported for item in contracts.values())
