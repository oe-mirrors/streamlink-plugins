import logging
import re

from streamlink.compat import urljoin
from streamlink.exceptions import PluginError
from streamlink.plugin import Plugin
from streamlink.stream import HLSStream

log = logging.getLogger(__name__)


class SkylineWebcams(Plugin):
    _url_re = re.compile(r"https?://(?:www\.)?skylinewebcams\.com/(?:[\w-]+/){5}.+\.html")
    _source_re = re.compile(r"source:\s*'(.+?)'")
    _HD_AUTH_BASE = "https://hd-auth.skylinewebcams.com/"

    @classmethod
    def can_handle_url(cls, url):
        return cls._url_re.match(url) is not None

    def _get_streams(self):
        res = self.session.http.get(self.url)
        m = self._source_re.search(res.text)
        if m and ".m3u8" in m.group(1):
            url = urljoin(self._HD_AUTH_BASE, m.group(1))
            url = url.replace("livee.", "live.")
            log.debug(url)
            streams = HLSStream.parse_variant_playlist(self.session, url)
            if not streams:
                return {"live": HLSStream(self.session, url)}
            else:
                return streams
        elif m:
            raise PluginError("Unexpected source format: {0}".format(m.group(1)))
        else:
            raise PluginError("Could not extract source.")


__plugin__ = SkylineWebcams
