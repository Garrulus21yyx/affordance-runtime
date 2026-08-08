from affordance_runtime.benchmarks.target_loop.reporting import write_run_report


def test_reporting_module_has_no_private_route_fields() -> None:
    source = write_run_report.__module__
    for forbidden in ("selector", "coordinate", "credential", "raw_response"):
        assert forbidden not in source
