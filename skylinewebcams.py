"""
$description Live webcams from SkylineWebcams (HLS and YouTube cams).
$url skylinewebcams.com
$type live

Based on Billy2011's original plugin (streamlink-27), updated for
Streamlink 8.x. YouTube cams are resolved with yt-dlp (same method as
the WorldCam plugin); Streamlink's own YouTube plugin is only a fallback,
because YouTube often blocks it (403 on youtubei/v1/player).
"""

import logging
import re
import subprocess
import sys
from os.path import exists
from shutil import which
from urllib.parse import urljoin

from streamlink.exceptions import NoStreamsError, PluginError
from streamlink.plugin import Plugin, pluginmatcher
from streamlink.stream.hls import HLSStream
from streamlink.stream.http import HTTPStream

log = logging.getLogger(__name__)

YTDLP_TIMEOUT = 20
# live cams: HLS manifest first, then anything playable
YTDLP_FORMAT = "best[protocol^=m3u8]/best"
# yt-dlp attempts: android_vr client first (no JS needed), then default
YTDLP_ATTEMPTS = (
    ["--extractor-args", "youtube:player_client=android_vr"],
    [],
)
# first yt-dlp release with --js-runtimes
YTDLP_JS_RUNTIMES_VERSION = (2025, 11)

# cached (cmd, version) of yt-dlp, False = not checked yet
_ytdlp = False


def _find_ytdlp():
    """Command (list) and version tuple of yt-dlp, or (None, None).

    The lookup is slow (python -m yt_dlp), so the result is cached for
    the lifetime of the process.
    """
    global _ytdlp
    if _ytdlp is not False:
        return _ytdlp
    _ytdlp = (None, None)
    candidates = []
    for path in (which("yt-dlp"), "/usr/bin/yt-dlp", "/usr/local/bin/yt-dlp"):
        if path and exists(path) and [path] not in candidates:
            candidates.append([path])
    for python in (sys.executable, "/usr/bin/python3"):
        if python and exists(python):
            candidates.append([python, "-m", "yt_dlp"])
    for cmd in candidates:
        try:
            r = subprocess.run(cmd + ["--version"], capture_output=True,
                               text=True, timeout=15)
            if r.returncode == 0:
                _ytdlp = (cmd, _parse_version(r.stdout))
                log.debug("yt-dlp %s: %s", r.stdout.strip(), " ".join(cmd))
                break
        except Exception:
            pass
    return _ytdlp


def _parse_version(text):
    """yt-dlp version '2025.11.12' -> (2025, 11), or None."""
    m = re.match(r"\s*(\d+)\.(\d+)", text or "")
    return (int(m.group(1)), int(m.group(2))) if m else None


def _js_runtime_args(version):
    if not version or version < YTDLP_JS_RUNTIMES_VERSION:
        return []
    for runtime, binary in (("deno", "deno"), ("node", "node"),
                            ("bun", "bun"), ("quickjs", "qjs")):
        path = which(binary)
        if path:
            return ["--js-runtimes", "%s:%s" % (runtime, path)]
    return []


@pluginmatcher(
    # any webcam page: /<lang>/webcam/.../<name>.html
    re.compile(r"https?://(?:www\.)?skylinewebcams\.com/[\w-]+/webcam/(?:[\w-]+/)+[\w-]+\.html")
)
class SkylineWebcams(Plugin):
    _HD_AUTH_BASE = "https://hd-auth.skylinewebcams.com/"
    _REFERER = "https://www.skylinewebcams.com/"

    _source_re = re.compile(r"""(?:url|source)\s*:\s*(["'])(?P<url>[^"']+?\.m3u8[^"']*)\1""")
    _id_re = re.compile(r"""[?&]a=([^&"']+)""")
    _youtube_re = re.compile(r"""videoId\s*:\s*(["'])(?P<id>[\w-]{11})\1""")

    def _get_streams(self):
        res = self.session.http.get(self.url, headers={"Referer": self._REFERER})
        text = res.text

        m = self._source_re.search(text)
        if m:
            return self._skyline_hls(m.group("url"))

        y = self._youtube_re.search(text)
        if y:
            return self._youtube("https://www.youtube.com/watch?v=" + y.group("id"))

        raise PluginError("Could not extract source.")

    def _skyline_hls(self, src):
        # the SkylineWebcams HLS server checks Referer/Origin
        self.session.http.headers.update({
            "Referer": self._REFERER,
            "Origin": self._REFERER.rstrip("/"),
        })
        id_m = self._id_re.search(src)
        if id_m:
            url = urljoin(self._HD_AUTH_BASE, "live.m3u8?a=" + id_m.group(1))
        else:
            url = urljoin(self._HD_AUTH_BASE, src).replace("livee.", "live.")
        log.debug("HLS URL: %s", url)
        streams = HLSStream.parse_variant_playlist(self.session, url)
        return streams or {"live": HLSStream(self.session, url)}

    def _youtube(self, yt_url):
        log.debug("YouTube URL: %s", yt_url)

        stream_url = self._resolve_ytdlp(yt_url)
        if stream_url:
            if ".m3u8" in stream_url:
                streams = HLSStream.parse_variant_playlist(self.session, stream_url)
                return streams or {"live": HLSStream(self.session, stream_url)}
            return {"live": HTTPStream(self.session, stream_url)}

        # fallback: Streamlink's YouTube plugin (often blocked by YouTube)
        log.warning("yt-dlp not available or failed, trying Streamlink's YouTube plugin")
        try:
            return self.session.streams(yt_url)
        except NoStreamsError:
            raise PluginError("YouTube stream not available: " + yt_url)

    def _resolve_ytdlp(self, yt_url):
        cmd, version = _find_ytdlp()
        if not cmd:
            log.warning("yt-dlp not found (opkg install python3-yt-dlp)")
            return None
        base = cmd + ["-g", "--no-playlist", "--no-warnings",
                      "--socket-timeout", "10", "-f", YTDLP_FORMAT] + _js_runtime_args(version)
        for extra in YTDLP_ATTEMPTS:
            try:
                r = subprocess.run(base + extra + [yt_url], capture_output=True,
                                   text=True, timeout=YTDLP_TIMEOUT)
            except subprocess.TimeoutExpired:
                log.warning("yt-dlp timeout (%ss), trying next attempt", YTDLP_TIMEOUT)
                continue
            except Exception as e:
                log.warning("yt-dlp error: %s", e)
                return None
            for line in (r.stdout or "").splitlines():
                line = line.strip()
                if line.startswith(("http://", "https://")):
                    log.debug("yt-dlp URL: %s", line[:100])
                    return line
            log.debug("yt-dlp failed: %s", (r.stderr or "")[-300:])
        return None


__plugin__ = SkylineWebcams
