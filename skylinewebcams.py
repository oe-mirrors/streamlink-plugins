import logging
import re

from urllib.parse import urljoin
from streamlink.exceptions import PluginError
from streamlink.plugin import Plugin, pluginmatcher

from streamlink.stream import HLSStream

log = logging.getLogger(__name__)


@pluginmatcher(re.compile(
    r"https?://(?:www\.)?skylinewebcams\.com/(?:[\w-]+/){5}.+\.html"
))
class SkylineWebcams(Plugin):
    _source_re = re.compile(r"(source):\s*'(.+?)'")
    _yt_source_re = re.compile(r"YT\.Player\('live'.*?(videoId):\s*'(.+?)'")
    _HD_AUTH_BASE = "https://hd-auth.skylinewebcams.com/"

    def _get_streams(self):
        res = self.session.http.get(self.url)
        m = self._source_re.search(res.text) or self._yt_source_re.search(res.text)
        if m:
            if m.group(1) == "source" and ".m3u8" in m.group(2):
                url = urljoin(self._HD_AUTH_BASE, m.group(2))
                url = url.replace("livee.", "live.")
                log.debug(url)
                streams = HLSStream.parse_variant_playlist(self.session, url)
                if not streams:
                    return {"live": HLSStream(self.session, url)}
                else:
                    return streams
            elif m.group(1) == "videoId":
                url = "youtube.com/embed/{0}".format(m.group(2))
                return self.session.streams(url)
        elif m:
            raise PluginError("Unexpected source format: {0}".format(m.group(1)))
        else:
            raise PluginError("Could not extract source.")


__plugin__ = SkylineWebcams
