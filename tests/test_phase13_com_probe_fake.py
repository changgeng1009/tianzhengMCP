from __future__ import annotations


class FakeT30Object:
    def Insert(self, parameters):  # noqa: N802
        return {"handle": "FAKE"}


class FakeCOMEnvironment:
    ActiveDocument = object()
    TDbPipe = FakeT30Object()
    TDbPipeValve = FakeT30Object()


def test_fake_com_probe_reports_capabilities_without_real_autocad() -> None:
    from mcp.t30_writeback.com_probe import T30COMProbe

    probe = T30COMProbe(com_environment=FakeCOMEnvironment(), fake_mode=True)

    environment = probe.probe_environment()
    capabilities = probe.probe_insert_methods()

    assert environment["status"] == "success"
    assert any(cap.object_type == "TDbPipe" and cap.probe_status == "confirmed" for cap in capabilities)
    assert any(cap.object_type == "TDbSprinkler" and cap.probe_status == "not_available" for cap in capabilities)

