import asyncio
import os
import aiohttp

from blanco_smart_home_api_client import (
    BlancoApiClient,
    BlancoApiError,
)


DEVICE_ID = os.environ.get("BLANCO_DEVICE_ID")


async def main():
    if not DEVICE_ID or len(DEVICE_ID) != 64:
        raise SystemExit("BLANCO_DEVICE_ID muss als 64-stellige dev_id gesetzt sein")
    async with aiohttp.ClientSession() as session:
        client = BlancoApiClient(
            session,
            app_version="test-1.0.0",
            app_build="1",
            os_version="macOS",
        )

        try:
            registration = await client.register_app("de")
            print("App-ID:", registration["app_id"])

            auth = await client.authenticate(DEVICE_ID)
            print("Authentifiziert, Gerätetyp:", auth["dev_type"])

            status_code, status = await client.get_device_status(DEVICE_ID)
            print("Status HTTP:", status_code)
            print("Gerätestatus:", status)

            status_code, errors = await client.get_device_errors(DEVICE_ID)
            print("Fehler HTTP:", status_code)
            print("Fehler:", errors)

        except BlancoApiError as error:
            print(type(error).__name__, ":", error)


asyncio.run(main())
