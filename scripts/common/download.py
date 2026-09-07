"""Fetching and decoding source files - shared by the dataset build scripts."""

from __future__ import annotations

import urllib.error
import urllib.request
from email.message import Message
from pathlib import Path

# Some publishing hosts answer plain scripted requests with 403.
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


def disposition_filename(header: str | None) -> str | None:
    """The filename out of a Content-Disposition header, if it carries one."""
    if not header:
        return None
    message = Message()
    message["content-disposition"] = header
    return message.get_filename()


def fetch(url: str, dest_dir: Path, *, force: bool = False, filename: str | None = None,
          fallback: str = "download", magic: bytes | None = None,
          help_url: str | None = None, local_flag: str = "--source") -> Path:
    """Download `url` into `dest_dir`, reusing the cached copy unless `force`.

    filename   : name to cache under; derived from the URL or the response when omitted
    magic      : leading bytes the download must start with, e.g. b"PK" for a zip
    help_url   : landing page to point at when the host refuses the request
    local_flag : the caller's option for supplying an already-downloaded file
    """
    dest_dir.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})

    print("Source   : %s" % url)
    try:
        response = urllib.request.urlopen(request)
    except urllib.error.HTTPError as error:
        raise SystemExit(
            "HTTP %s %s\n"
            "The URL did not serve the file.%s\n"
            "Pass a current link with --url, or download it by hand into\n"
            "%s and pass %s."
            % (error.code, error.reason,
               "\nCheck the dataset page: %s" % help_url if help_url else "",
               dest_dir, local_flag)
        ) from error
    except urllib.error.URLError as error:
        raise SystemExit("Could not reach %s: %s" % (url, error.reason)) from error

    with response:
        name = filename
        if not name:
            tail = url.split("?")[0].rstrip("/").rsplit("/", 1)[-1]
            name = (tail if "." in tail
                    else disposition_filename(response.headers.get("Content-Disposition"))
                    or fallback)
        target = dest_dir / name

        if target.exists() and not force:
            print("Cached   : %s (%.1f MB) - pass --force to re-download"
                  % (target, target.stat().st_size / 1e6))
            return target

        total = int(response.headers.get("Content-Length") or 0)
        print("Download : %s%s" % (target.name, " (%.1f MB)" % (total / 1e6) if total else ""))
        read = 0
        with open(target, "wb") as handle:
            while True:
                chunk = response.read(1 << 20)
                if not chunk:
                    break
                handle.write(chunk)
                read += len(chunk)
                if total:
                    print("           %6.1f%%" % (100 * read / total), end="\r", flush=True)
    print("           %.1f MB written        " % (read / 1e6))

    if magic:
        with open(target, "rb") as handle:
            if handle.read(len(magic)) != magic:
                raise SystemExit("%s does not look like the expected format - check the URL."
                                 % target)
    return target


def decode(raw: bytes) -> str:
    """Text out of bytes whose encoding the publisher does not declare.

    Open datasets arrive as UTF-8 from modern portals and Latin-1 from older
    ones; trying in this order never silently mangles a UTF-8 file.
    """
    for encoding in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("latin-1")
