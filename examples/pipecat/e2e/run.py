import asyncio
import os
import sys
import time
import uuid

import aiohttp
from dotenv import load_dotenv
from loguru import logger
from pipecat.transports.daily.utils import (
    DailyRESTHelper,
    DailyRoomParams,
    DailyRoomProperties,
)

import finchvox

from barista import run_barista
from customer import run_customer

load_dotenv(override=True)

finchvox.init(service_name="pipecat-e2e")

E2E_TIMEOUT = int(os.getenv("E2E_TIMEOUT", "120"))


async def main():
    room_url = None
    rest = None

    async with aiohttp.ClientSession() as session:
        rest = DailyRESTHelper(
            daily_api_key=os.getenv("DAILY_API_KEY"),
            aiohttp_session=session,
        )

        logger.info("Creating Daily room...")
        room = await rest.create_room(
            DailyRoomParams(
                name=f"e2e-{uuid.uuid4().hex[:8]}",
                properties=DailyRoomProperties(
                    exp=time.time() + 300,
                    eject_at_room_exp=True,
                ),
            )
        )
        room_url = room.url
        logger.info(f"Room created: {room_url}")

        barista_token = await rest.get_token(room_url, expiry_time=300)
        customer_token = await rest.get_token(room_url, expiry_time=300)

        done_event = asyncio.Event()

        logger.info("Starting barista bot...")
        barista_task = asyncio.create_task(
            run_barista(room_url, barista_token, done_event)
        )

        await asyncio.sleep(3)

        logger.info("Starting customer bot...")
        customer_task = asyncio.create_task(run_customer(room_url, customer_token))

        exit_code = 0
        try:
            await asyncio.wait_for(done_event.wait(), timeout=E2E_TIMEOUT)
            logger.info("Order submitted successfully!")
        except asyncio.TimeoutError:
            logger.error(f"Timed out after {E2E_TIMEOUT}s")
            exit_code = 1
        finally:
            logger.info("Cleaning up...")
            barista_task.cancel()
            customer_task.cancel()
            await asyncio.gather(barista_task, customer_task, return_exceptions=True)

            try:
                await rest.delete_room_by_url(room_url)
                logger.info("Room deleted")
            except Exception as e:
                logger.warning(f"Failed to delete room: {e}")

    logger.info("Done.")
    sys.exit(exit_code)


if __name__ == "__main__":
    asyncio.run(main())
