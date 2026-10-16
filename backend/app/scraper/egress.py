"""Egress proxy of the isolated CAPTCHA browser: the `captcha-egress` service (docker-compose.yml).

captcha-browser has no route to anything: its Chromium reaches the web only through this proxy, which
- only opens HTTPS tunnels (CONNECT to port 443): plain HTTP and every other port are refused;
- only to an allowlist of host names (LinkedIn and its CAPTCHA providers), never to an IP literal;
- resolves the name itself and refuses any non-public address (private/LAN, loopback, link-local and
  cloud metadata, CGNAT, Docker networks...), then connects to the address it checked (no DNS rebinding).
Refusals are logged (host and reason only) so a missing CAPTCHA domain can be spotted and added with
CAPTCHA_ALLOWED_DOMAINS.

    python -m app.scraper.egress
"""

import asyncio
import ipaddress
import logging
import os
import socket

log = logging.getLogger("captcha-egress")

PORT = 3128
DEFAULT_DOMAINS = (
    "linkedin.com", "licdn.com",                         # LinkedIn and its static files
    "arkoselabs.com", "funcaptcha.com",                  # Arkose Labs CAPTCHA (used by LinkedIn)
    "www.google.com", "www.gstatic.com", "www.recaptcha.net",  # reCAPTCHA
)
MAX_CLIENTS = 128
TIMEOUT = 10
REFUSED = b"HTTP/1.1 403 Forbidden\r\nX-PasseFiltre-Egress: refused\r\nContent-Length: 0\r\nConnection: close\r\n\r\n"
FAILED = b"HTTP/1.1 502 Bad Gateway\r\nX-PasseFiltre-Egress: refused\r\nContent-Length: 0\r\nConnection: close\r\n\r\n"


def allowed_domains() -> tuple[str, ...]:
    extra = os.getenv("CAPTCHA_ALLOWED_DOMAINS", "")
    return DEFAULT_DOMAINS + tuple(d.strip().strip(".").lower() for d in extra.split(",") if d.strip().strip("."))


def host_allowed(host: str, domains: tuple[str, ...]) -> bool:
    """The domain itself or one of its subdomains; never an IP literal."""
    host = host.lower().rstrip(".")
    try:
        ipaddress.ip_address(host)
        return False
    except ValueError:
        pass
    return any(host == d or host.endswith("." + d) for d in domains)


def is_public(address: str) -> bool:
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return False
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    return ip.is_global and not ip.is_multicast


def parse_connect(head: bytes) -> tuple[str, int] | None:
    """'CONNECT host:443 HTTP/1.1' -> ('host', 443); anything else -> None."""
    parts = head.split(b"\r\n", 1)[0].decode("latin-1").split()
    if len(parts) != 3 or parts[0] != "CONNECT" or not parts[2].startswith("HTTP/1."):
        return None
    host, _, port = parts[1].rpartition(":")
    if not host or not port.isdigit():
        return None
    return host.strip("[]"), int(port)


async def resolve(host: str, port: int) -> list[str]:
    infos = await asyncio.get_running_loop().getaddrinfo(host, port, type=socket.SOCK_STREAM)
    return list(dict.fromkeys(info[4][0] for info in infos))


async def _pipe(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    try:
        while data := await reader.read(65536):
            writer.write(data)
            await writer.drain()
    except (OSError, asyncio.IncompleteReadError):
        pass
    finally:
        try:
            writer.write_eof()
        except (OSError, RuntimeError):
            pass


class Egress:
    def __init__(self, domains: tuple[str, ...] | None = None, resolver=resolve) -> None:
        self.domains = domains or allowed_domains()
        self.resolve = resolver
        self.slots = asyncio.Semaphore(MAX_CLIENTS)

    async def handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            async with self.slots:
                await self._handle(reader, writer)
        finally:
            writer.close()

    async def _refuse(self, writer: asyncio.StreamWriter, target: str, reason: str, answer: bytes = REFUSED) -> None:
        log.warning("refused %s: %s", target[:300], reason)
        writer.write(answer)
        try:
            await writer.drain()
        except OSError:
            pass

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            head = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), TIMEOUT)
        except (asyncio.TimeoutError, asyncio.IncompleteReadError, asyncio.LimitOverrunError, OSError):
            return
        target = parse_connect(head)
        if target is None:
            return await self._refuse(writer, head.split(b"\r\n", 1)[0].decode("latin-1"), "only HTTPS tunnels")
        host, port = target
        name = f"{host}:{port}"
        if port != 443:
            return await self._refuse(writer, name, "port")
        if not host_allowed(host, self.domains):
            return await self._refuse(writer, name, "host not in the allowlist")
        try:
            addresses = await asyncio.wait_for(self.resolve(host, port), TIMEOUT)
        except (OSError, asyncio.TimeoutError):
            return await self._refuse(writer, name, "DNS failure", FAILED)
        public = [a for a in addresses if is_public(a)]
        if not public or len(public) != len(addresses):
            return await self._refuse(writer, name, f"non-public address {sorted(set(addresses) - set(public))}")
        for address in public:
            try:
                up_reader, up_writer = await asyncio.wait_for(asyncio.open_connection(address, port), TIMEOUT)
                break
            except (OSError, asyncio.TimeoutError):
                continue
        else:
            return await self._refuse(writer, name, "unreachable", FAILED)
        try:
            writer.write(b"HTTP/1.1 200 Connection established\r\n\r\n")
            await writer.drain()
            await asyncio.gather(_pipe(reader, up_writer), _pipe(up_reader, writer))
        finally:
            up_writer.close()


async def serve(port: int = PORT) -> None:
    egress = Egress()
    server = await asyncio.start_server(egress.handle, "0.0.0.0", port)
    log.info("listening on :%s, allowed: %s", port, ", ".join(egress.domains))
    async with server:
        await server.serve_forever()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    try:
        asyncio.run(serve())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
