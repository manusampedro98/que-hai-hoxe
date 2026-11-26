import os
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Settings:
    db_path: Path = field(default_factory=lambda: ROOT / "data" / "catalog.sqlite3")
    demo: bool = False
    allowed_hosts: tuple[str, ...] = ("127.0.0.1", "localhost")
    allowed_peers: tuple[str, ...] | None = None

    @classmethod
    def from_env(cls):
        # LAN is enabled only through an explicitly approved launch, never implicitly.
        import ipaddress
        hosts = ["127.0.0.1", "localhost"]
        peers = None
        lan = os.environ.get("QHH_LAN_IP")
        if lan:
            address = ipaddress.IPv4Address(lan)
            networks = tuple(ipaddress.IPv4Network(value) for value in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"))
            if not any(address in network for network in networks):
                raise ValueError("QHH_LAN_IP debe ser una IPv4 RFC1918 concreta")
            mobile = ipaddress.IPv4Address(os.environ.get("QHH_MOBILE_IP", ""))
            if not any(mobile in network for network in networks) or mobile == address:
                raise ValueError("QHH_MOBILE_IP debe identificar el móvil privado autorizado")
            hosts.append(str(address))
            peers = (str(address), str(mobile), "127.0.0.1")
        return cls(demo=os.environ.get("QHH_DEMO") == "1", allowed_hosts=tuple(hosts), allowed_peers=peers)
