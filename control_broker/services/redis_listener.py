"""Redis stream listener for commands."""

import asyncio
from pydantic import ValidationError
import redis.asyncio as redis

from ..models import StreamCommand
from ..core import Config
from .connection_manager import ConnectionManager


class RedisCommandListener:
    """Listens to Redis command stream and forwards to tanks."""
    
    def __init__(self, redis_client: redis.Redis, config: Config, manager: ConnectionManager):
        self.redis_client = redis_client
        self.config = config
        self.manager = manager

    async def start(self) -> None:
        """Start listening to the command stream."""
        stream = self.config.redis_command_stream
        last_id = self.config.redis_command_stream_start
        print(f"[REDIS] Command listener started on stream '{stream}' from '{last_id}'")

        while True:
            try:
                results = await self.redis_client.xread(
                    streams={stream: last_id},
                    count=20,
                    block=5000,
                )
                if not results:
                    continue

                for _, messages in results:
                    for message_id, data in messages:
                        last_id = message_id
                        await self._process_message(message_id, data, stream)

            except asyncio.CancelledError:
                print("[REDIS] Command listener cancelled")
                break
            except Exception as exc:
                print(f"[ERROR] Command listener error: {exc}")
                await asyncio.sleep(1.0)

    async def _process_message(self, message_id: str, data: dict, stream: str) -> None:
        """Process a single message from the stream."""
        try:
            payload = StreamCommand(**data)
        except ValidationError as exc:
            print(f"[WARN] Invalid stream payload {data}: {exc}")
            return

        payload_dict = payload.dict(exclude_none=True)
        tank_id = payload_dict.pop("tankId")

        delivered = False
        try:
            await self.manager.forward_to_tank(tank_id, payload_dict)
            print(f"[REDIS] Dispatched command to {tank_id}: {payload_dict}")
            delivered = True
        except LookupError as exc:
            print(f"[WARN] Tank {tank_id} unavailable: {exc}")
        except Exception as send_error:
            print(f"[ERROR] Failed to send command to {tank_id}: {send_error}")

        if delivered:
            try:
                await self.redis_client.xdel(stream, message_id)
            except Exception as delete_error:
                print(f"[WARN] Unable to delete stream entry {message_id}: {delete_error}")
