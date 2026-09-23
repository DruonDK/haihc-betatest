"""Useful functions for the IHC component."""

import asyncio
from typing import Any

from homeassistant.core import HomeAssistant, callback
from ihcsdk.ihccontroller import IHCController
from requests.adapters import HTTPAdapter

# Connect/read timeout (seconds) applied to every request to the controller.
# The read timeout must be longer than the SDK's long poll wait (10 s), so a
# normal poll never times out, but a poll left hanging by a dropped network
# connection is aborted and the SDK's re-authenticate logic can recover.
REQUEST_TIMEOUT: tuple[float, float] = (10.0, 30.0)


async def async_pulse(
    hass: HomeAssistant, ihc_controller: IHCController, ihc_id: int
) -> None:
    """Send a short on/off pulse to an IHC controller resource."""
    await async_set_bool(hass, ihc_controller, ihc_id, value=True)
    await asyncio.sleep(0.1)
    await async_set_bool(hass, ihc_controller, ihc_id, value=False)


@callback
def async_set_bool(
    hass: HomeAssistant, ihc_controller: IHCController, ihc_id: int, value: bool
) -> asyncio.Future[bool]:
    """Set a bool value on an IHC controller resource."""
    return hass.async_add_executor_job(
        ihc_controller.set_runtime_value_bool, ihc_id, value
    )


@callback
def async_set_int(
    hass: HomeAssistant, ihc_controller: IHCController, ihc_id: int, value: int
) -> asyncio.Future[bool]:
    """Set a int value on an IHC controller resource."""
    return hass.async_add_executor_job(
        ihc_controller.set_runtime_value_int, ihc_id, value
    )


@callback
def async_set_float(
    hass: HomeAssistant, ihc_controller: IHCController, ihc_id: int, value: float
) -> asyncio.Future[bool]:
    """Set a float value on an IHC controller resource."""
    return hass.async_add_executor_job(
        ihc_controller.set_runtime_value_float, ihc_id, value
    )


def get_controller_serial(ihc_controller: IHCController) -> str:
    """
    Get the controller serial number.

    Having the function makes it easier to patch for testing
    """
    system_info = ihc_controller.client.get_system_info()
    if not system_info or not isinstance(system_info, dict):
        msg = "Unable to get serial number from IHC controller"
        raise ValueError(msg)
    return system_info["serial_number"]


class _TimeoutHTTPAdapter(HTTPAdapter):
    """HTTP adapter that applies a default timeout to every request."""

    def __init__(self, timeout: tuple[float, float], **kwargs: Any) -> None:
        """Initialize the adapter with the timeout to apply."""
        self._timeout = timeout
        super().__init__(**kwargs)

    def send(self, request: Any, **kwargs: Any) -> Any:  # type: ignore[override]
        """Send the request, adding the default timeout when none is given."""
        if kwargs.get("timeout") is None:
            kwargs["timeout"] = self._timeout
        return super().send(request, **kwargs)


def install_request_timeout(
    ihc_controller: IHCController,
    timeout: tuple[float, float] = REQUEST_TIMEOUT,
) -> None:
    """
    Make every request from the ihcsdk to the controller time out.

    The ihcsdk sends its soap requests without a timeout. If the network drops
    while the notify thread is in its long poll, the socket read can block
    forever: no events reach Home Assistant, and unloading the entry hangs
    because the SDK waits for the notify thread to end. Mounting an adapter
    with a timeout on the SDK's requests session fixes both.
    """
    connection = ihc_controller.client.connection
    session = connection.session
    for prefix in ("http://", "https://"):
        # Keep the SDK's retry policy for connection/status errors, but do
        # not retry a read timeout: a hanging poll must fail fast so the
        # notify thread can re-authenticate.
        retries = session.get_adapter(prefix).max_retries.new(read=0)
        session.mount(prefix, _TimeoutHTTPAdapter(timeout, max_retries=retries))
