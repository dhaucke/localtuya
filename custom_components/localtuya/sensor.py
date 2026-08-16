"""Platform to present any Tuya DP as a sensor."""
import logging
from functools import partial

import voluptuous as vol
from homeassistant.components.sensor import (
    DEVICE_CLASSES,
    DOMAIN,
    SensorDeviceClass,
)
from homeassistant.const import (
    CONF_DEVICES,
    CONF_DEVICE_CLASS,
    CONF_ENTITIES,
    CONF_FRIENDLY_NAME,
    CONF_PLATFORM,
    CONF_UNIT_OF_MEASUREMENT,
    PERCENTAGE,
    STATE_UNKNOWN,
)

from .common import LocalTuyaEntity, async_setup_entry as generic_async_setup_entry
from .const import CONF_BATTERY_DP, CONF_SCALING, DOMAIN as LOCALTUYA_DOMAIN, TUYA_DEVICES

_LOGGER = logging.getLogger(__name__)

DEFAULT_PRECISION = 2


def flow_schema(dps):
    """Return schema used in config flow."""
    return {
        vol.Optional(CONF_UNIT_OF_MEASUREMENT): str,
        vol.Optional(CONF_DEVICE_CLASS): vol.In(DEVICE_CLASSES),
        vol.Optional(CONF_SCALING): vol.All(
            vol.Coerce(float), vol.Range(min=-1000000.0, max=1000000.0)
        ),
    }


class LocaltuyaSensor(LocalTuyaEntity):
    """Representation of a Tuya sensor."""

    def __init__(
        self,
        device,
        config_entry,
        sensorid,
        **kwargs,
    ):
        """Initialize the Tuya sensor."""
        super().__init__(device, config_entry, sensorid, _LOGGER, **kwargs)
        self._state = STATE_UNKNOWN

    @property
    def state(self):
        """Return sensor state."""
        return self._state

    @property
    def device_class(self):
        """Return the class of this device."""
        return self._config.get(CONF_DEVICE_CLASS)

    @property
    def unit_of_measurement(self):
        """Return the unit of measurement of this entity, if any."""
        return self._config.get(CONF_UNIT_OF_MEASUREMENT)

    def status_updated(self):
        """Device status was updated."""
        state = self.dps(self._dp_id)
        scale_factor = self._config.get(CONF_SCALING)
        if scale_factor is not None and isinstance(state, (int, float)):
            state = round(state * scale_factor, DEFAULT_PRECISION)
        self._state = state

    # No need to restore state for a sensor
    async def restore_state_when_connected(self):
        """Do nothing for a sensor."""
        return


class LocaltuyaBatterySensor(LocalTuyaEntity):
    """Auto-added battery sensor for a vacuum's battery_dp.

    HA 2026.8 removed VacuumEntity.battery_level entirely (it's gone from
    homeassistant.components.vacuum, not just deprecated), so the vacuum
    card no longer shows battery % for any integration still setting it -
    same fix HA core applied to its own vacuum integrations: a dedicated
    battery sensor instead of a vacuum attribute. The battery_dp isn't a
    user-configured CONF_ENTITIES entry (it's a field on the vacuum
    entity's own config), so it needs a synthetic default_config instead
    of the normal get_entity_config lookup.
    """

    def __init__(self, device, config_entry, dp_id, vacuum_name, **kwargs):
        """Initialize the battery sensor."""
        super().__init__(
            device,
            config_entry,
            dp_id,
            _LOGGER,
            default_config={CONF_FRIENDLY_NAME: f"{vacuum_name} Battery"},
            **kwargs,
        )
        self._state = STATE_UNKNOWN

    @property
    def device_class(self):
        """Return the class of this device."""
        return SensorDeviceClass.BATTERY

    @property
    def unit_of_measurement(self):
        """Return the unit of measurement of this entity."""
        return PERCENTAGE

    def status_updated(self):
        """Device status was updated."""
        self._state = self.dps(self._dp_id)

    # No need to restore state for a sensor
    async def restore_state_when_connected(self):
        """Do nothing for a sensor."""
        return


def _battery_sensors_for_device(tuyainterface, dev_entry):
    """Build auto battery sensors for every vacuum entity with a battery_dp."""
    battery_sensors = []
    for entity_config in dev_entry[CONF_ENTITIES]:
        if entity_config[CONF_PLATFORM] != "vacuum":
            continue
        battery_dp = entity_config.get(CONF_BATTERY_DP)
        if not battery_dp:
            continue
        tuyainterface.dps_to_request[battery_dp] = None
        battery_sensors.append(
            LocaltuyaBatterySensor(
                tuyainterface,
                dev_entry,
                battery_dp,
                entity_config[CONF_FRIENDLY_NAME],
            )
        )
    return battery_sensors


_setup_configured_sensors = partial(generic_async_setup_entry, DOMAIN, LocaltuyaSensor, flow_schema)


async def async_setup_entry(hass, config_entry, async_add_entities):
    """Set up user-configured dp-sensors plus auto battery sensors for vacuums."""
    await _setup_configured_sensors(hass, config_entry, async_add_entities)

    all_battery_sensors = []
    for dev_id, dev_entry in config_entry.data[CONF_DEVICES].items():
        tuyainterface = hass.data[LOCALTUYA_DOMAIN][TUYA_DEVICES][dev_id]
        battery_sensors = _battery_sensors_for_device(tuyainterface, dev_entry)
        if battery_sensors:
            tuyainterface.add_entities(battery_sensors)
            all_battery_sensors.extend(battery_sensors)

    if all_battery_sensors:
        async_add_entities(all_battery_sensors)
