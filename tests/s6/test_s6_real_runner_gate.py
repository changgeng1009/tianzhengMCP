from __future__ import annotations

import pytest

from mcp_nextgen.backends.real_autocad_com import RealAutoCadComBackendError
from mcp_nextgen.backends.s6_synthetic_runner import run_s6_synthetic_mvp


def test_s6_real_runner_fails_before_any_com_activation_without_explicit_gate(tmp_path):
    with pytest.raises(RealAutoCadComBackendError) as error:
        run_s6_synthetic_mvp(
            artifact_root=tmp_path, run_id="run", job_id="job.1", integration_enabled=False,
            client_importer=lambda _name: (_ for _ in ()).throw(AssertionError("不得导入 COM")),
        )
    assert error.value.code == "S6_EXTERNAL_INTEGRATION_DISABLED"
