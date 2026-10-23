"""Shared WebSocket/VNC bridge; authorization is enforced by each transport adapter."""
import asyncio
import contextlib
import anyio
from fastapi import WebSocket
from starlette.websockets import WebSocketDisconnect, WebSocketState
from app.security import audit
VNC_CLOSE_TIMEOUT = 5

async def bridge(ws: WebSocket, job):
    offered = ws.scope.get("subprotocols") or []
    display = job.display
    sock = display.vnc_socket if display else None
    try:
        if not sock:
            raise OSError("no VNC server")
        reader, writer = await asyncio.open_unix_connection(sock)
    except (OSError, AttributeError, NotImplementedError):
        await ws.close(code=1011)
        return

    async def to_vnc() -> None:
        while True:
            message = await ws.receive()
            if message["type"] == "websocket.disconnect":
                raise WebSocketDisconnect(message.get("code", 1000))
            data = message.get("bytes")
            if data is None:  # RFB is binary only: a text frame is a protocol error
                await ws.close(code=1003)
                return
            writer.write(data)
            await writer.drain()

    async def to_browser() -> None:
        while data := await reader.read(65536):
            await ws.send_bytes(data)

    async def until_closed() -> None:  # solved, expired or cancelled: cut the viewer even if VNC lingers
        while job.status == "needs_captcha" and job.display is display:
            await anyio.sleep(1)

    # Structured concurrency (anyio, like Starlette itself): a cancellation of this handler (client
    # gone, server shutdown) reaches the pumps and leaves as the canceller's own cancellation, never
    # as a stray CancelledError; an unexpected pump error propagates instead of being swallowed.
    try:
        await ws.accept(subprotocol="binary" if "binary" in offered else None)
        audit(ws, "captcha_vnc_open", job=job.id)
        async with anyio.create_task_group() as pumps:
            async def pump(side) -> None:
                try:
                    await side()
                except (WebSocketDisconnect, ConnectionError):
                    pass  # the browser or the VNC server hung up: the normal end of a session
                pumps.cancel_scope.cancel()  # whichever side ends first ends the whole bridge

            for side in (to_vnc, to_browser, until_closed):
                pumps.start_soon(pump, side)
    finally:
        # Release both ends even if this handler is being cancelled: shielded, but bounded so a
        # stuck peer cannot hold the handler.
        with anyio.move_on_after(VNC_CLOSE_TIMEOUT, shield=True):
            writer.close()
            with contextlib.suppress(OSError):  # the VNC server may already have reset the socket
                await writer.wait_closed()
            if ws.application_state is WebSocketState.CONNECTED:
                with contextlib.suppress(WebSocketDisconnect):  # the browser is already gone
                    await ws.close()
        audit(ws, "captcha_vnc_close", job=job.id)
