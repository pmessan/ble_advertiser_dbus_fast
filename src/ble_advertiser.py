#!/usr/bin/env python3
from enum import Enum
from typing import Any, Dict, List

import asyncio

from dbus_fast import BusType, Message, MessageType, Variant
from dbus_fast.aio import MessageBus
from dbus_fast.service import ServiceInterface, method, dbus_property


# DBus Interfaces
OBJECT_MANAGER_INTERFACE = "org.freedesktop.DBus.ObjectManager"
PROPERTIES_INTERFACE = "org.freedesktop.DBus.Properties"

# Bluez specific DBUS
BLUEZ_SERVICE = "org.bluez"
ADAPTER_INTERFACE = "org.bluez.Adapter1"
ADVERTISEMENT_MONITOR_INTERFACE = "org.bluez.AdvertisementMonitor1"
LE_ADVERTISING_MANAGER_INTERFACE = "org.bluez.LEAdvertisingManager1"
LE_ADVERTISEMENT_IFACE = "org.bluez.LEAdvertisement1"


class DBusType(str):
    """
    dbus_fast wants to use string constants for type annotationa instead of normal Python types.

    Using the string constants directly as type annotations raises syntax errors, so we define them here.

    mypy does not like string constants as types.
        - TypeVar() does not work,
        - Type[] does not work
        - ...
    So we ignore the type check for valid-types only for these constants.

    TODO: can we make mypy and dbus_fast happy somehow with string constants as types?
    Maybe this will be fixed in a future version of dbus_fast.
    """

    String = "s"
    ArrayofString = "as"
    DictIntVariant = "a{qv}"


def unpack_variants(dictionary: Dict[str, Variant]) -> Dict[str, Any]:
    """Recursively unpacks all ``Variant`` types in a dictionary to their
    corresponding Python types.

    ``dbus-next`` doesn't automatically do this, so this needs to be called on
    all dictionaries ("a{sv}") returned from D-Bus messages.
    """
    unpacked = {}
    for k, v in dictionary.items():
        v = v.value if isinstance(v, Variant) else v
        if isinstance(v, dict):
            v = unpack_variants(v)
        elif isinstance(v, list):
            v = [x.value if isinstance(x, Variant) else x for x in v]
        unpacked[k] = v
    return unpacked


class BLEAdvertisement(ServiceInterface):
    def __init__(
        self,
        advertising_type: str = "broadcast",
        service_uuids: List[str] = ["ABCD"],
        manufacturer_data: Dict[int, Variant] = {
            0x123: Variant("ay", bytes([1, 2, 3, 4, 5]))
        },
        local_name: str = "TestAdvertisement",
    ):
        self.path = "/org/bluez/advertisement/test1"
        self.service_name = LE_ADVERTISEMENT_IFACE
        self._advertisement_type = advertising_type
        self._service_uuids = service_uuids
        self._manufacturer_data = manufacturer_data
        self.service_data = None
        self._local_name = local_name
        super().__init__(self.service_name)

    @dbus_property(name="Type")
    def advertisement_type(self) -> DBusType.String:
        return self._advertisement_type

    @dbus_property(name="ServiceUUIDs")
    def service_uuids(self) -> DBusType.ArrayofString:
        return self._service_uuids

    @dbus_property(name="ManufacturerData")
    def manufacturer_data(self) -> DBusType.DictIntVariant:
        return self._manufacturer_data

    @dbus_property(name="LocalName")
    def local_name(self) -> DBusType.String:
        return self._local_name

    @advertisement_type.setter
    def set_advertisement_type(self, ad_type: DBusType.String):
        self._advertisement_type = ad_type

    @service_uuids.setter
    def add_service_uuid(self, uuid: DBusType.String):
        self._service_uuids.append(uuid)

    @manufacturer_data.setter
    def add_manufacturer_data(self, data: DBusType.DictIntVariant):
        self._manufacturer_data = data

    @local_name.setter
    def add_local_name(self, name: DBusType.String):
        self._local_name = name

    @method(name="Release")
    def Release(self) -> None:
        print("%s: Released!" % self.path)


async def main():
    bus = await MessageBus(bus_type=BusType.SYSTEM).connect()
    test = BLEAdvertisement()
    bus.export(test.path, test)

    reply = await bus.request_name(LE_ADVERTISEMENT_IFACE)
    reply = await bus.call(
        Message(
            destination=BLUEZ_SERVICE,
            path="/",
            member="GetManagedObjects",
            interface=OBJECT_MANAGER_INTERFACE,
        )
    )

    adapter_path = "/org/bluez/hci0"
    for path, interfaces in reply.body[0].items():
        props = unpack_variants(interfaces)

        if LE_ADVERTISING_MANAGER_INTERFACE in props:
            adapter_path = path

    # call UnregisterAdvertisement
    reply = await bus.call(
        Message(
            destination=BLUEZ_SERVICE,
            path=adapter_path,
            member="UnregisterAdvertisement",
            interface=LE_ADVERTISING_MANAGER_INTERFACE,
            signature="o",
            body=[test.path],
        )
    )

    # call RegisterAdvertisement
    reply = await bus.call(
        Message(
            destination=BLUEZ_SERVICE,
            path=adapter_path,
            member="RegisterAdvertisement",
            interface=LE_ADVERTISING_MANAGER_INTERFACE,
            signature="oa{sv}",
            body=[test.path, {}],
        )
    )
    if reply is not None:
        if reply.message_type == MessageType.METHOD_RETURN:
            print("Advertisement registered")
        elif reply.message_type == MessageType.ERROR:
            print(f"Error:  {reply.body}")

    await bus.wait_for_disconnect()


if __name__ == "__main__":
    asyncio.run(main())
