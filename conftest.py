# Import the integration before the Home Assistant test harness mounts its own
# test config dir, so our custom_components package wins in sys.modules.
import custom_components.rnli_launches  # noqa: F401
import pytest


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield
