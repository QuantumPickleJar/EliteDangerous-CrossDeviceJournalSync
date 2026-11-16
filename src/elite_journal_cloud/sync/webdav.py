"""Small Nextcloud WebDAV adapter with bounded, verified, non-redirecting requests."""

from __future__ import annotations

from urllib.parse import quote, unquote, urlsplit

import httpx
from defusedxml import ElementTree

from elite_journal_cloud.journal.snapshot import MAX_SNAPSHOT_BYTES, digest


class TransferError(Exception):
    """Only stable error codes may leave the transport boundary."""

    def __init__(self, code: str, permanent: bool = False):
        super().__init__(code)
        self.code = code
        self.permanent = permanent


class WebDAV:
    def __init__(
        self, url: str, username: str, password: str, transport: httpx.BaseTransport | None = None
    ):
        parsed = urlsplit(url)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
            or any(part in {".", ".."} for part in unquote(parsed.path).split("/"))
            or "\\" in unquote(parsed.path)
        ):
            raise ValueError("WebDAV requires an HTTPS collection URL without embedded secrets")
        self.base = url.rstrip("/") + "/"
        self.base_path = unquote(urlsplit(self.base).path)
        self.origin = (parsed.scheme, parsed.netloc)
        self.endpoint = digest((self.base + "\n" + username).encode())
        self.client = httpx.Client(
            auth=(username, password), timeout=30, follow_redirects=False, transport=transport
        )

    def close(self) -> None:
        self.client.close()

    def _url(self, path: str) -> str:
        if any(part in {"", ".", ".."} for part in path.split("/")) or "\\" in path:
            raise TransferError("unsafe_remote_path", True)
        return self.base + quote(path, safe="/")

    def request(
        self,
        method: str,
        path: str,
        *,
        data: bytes | None = None,
        headers: dict[str, str] | None = None,
        accepted: tuple[int, ...] = (200,),
        limit: int = MAX_SNAPSHOT_BYTES,
    ) -> bytes:
        try:
            with self.client.stream(method, self._url(path), content=data, headers=headers) as res:
                if res.status_code not in accepted:
                    status = res.status_code
                    raise TransferError(f"http_{status}", status in {400, 401, 403, 404, 405, 413})
                chunks = bytearray()
                for chunk in res.iter_bytes(chunk_size=65536):
                    chunks.extend(chunk)
                    if len(chunks) > limit:
                        raise TransferError("response_too_large", True)
                return bytes(chunks)
        except httpx.HTTPError:
            raise TransferError("network_error") from None

    def mkdir(self, path: str) -> None:
        self.request("MKCOL", path, accepted=(201, 405), limit=65536)

    def immutable_put(self, path: str, data: bytes) -> None:
        # A previous interrupted attempt may already have created the object.
        self.request(
            "PUT",
            path,
            data=data,
            headers={"If-None-Match": "*"},
            accepted=(201, 204, 412),
            limit=65536,
        )
        observed = self.request("GET", path, limit=max(len(data), 1))
        if digest(observed) != digest(data):
            raise TransferError("remote_integrity_failure", True)

    def listdir(self, path: str) -> list[str]:
        body = b'<d:propfind xmlns:d="DAV:"><d:prop><d:resourcetype/></d:prop></d:propfind>'
        xml = self.request(
            "PROPFIND",
            path,
            data=body,
            headers={"Depth": "1", "Content-Type": "application/xml"},
            accepted=(207,),
            limit=2 * 1024 * 1024,
        )
        try:
            tree = ElementTree.fromstring(xml)
            if tree.tag != "{DAV:}multistatus":
                raise ValueError
            result: set[str] = set()
            prefix = self.base_path + path.rstrip("/") + "/"
            for response in tree.findall("{DAV:}response"):
                href = response.findtext("{DAV:}href", default="")
                parsed = urlsplit(href)
                if parsed.netloc and (parsed.scheme, parsed.netloc) != self.origin:
                    raise ValueError
                target = unquote(parsed.path).rstrip("/")
                if target == prefix.rstrip("/"):
                    continue
                if not target.startswith(prefix):
                    raise ValueError
                child = target[len(prefix) :]
                if not child or "/" in child or "\\" in child or child in {".", ".."}:
                    raise ValueError
                result.add(child)
            return sorted(result)
        except Exception:
            raise TransferError("invalid_dav_listing", True) from None
