from __future__ import unicode_literals

import re

from streamlink.plugin.api import useragents
from streamlink.plugin import pluginmatcher
from streamlink.plugins.livestream import Livestream


@pluginmatcher(
    re.compile(r"https?://(?:www)\.(?:(radio21|rockland))\.de/(?:musik/)?(?:tv)?(?:programm/)")
)
class Radio2See(Livestream):
    """
    Support for www.radio21.de/tv & www.rockland.de/tv Live TV stream
    """

    _streamsrc_re = re.compile(r"""<iframe.+?src=["'](?P<streamsrc>[^"']+)["']""", re.DOTALL)

    def _get_streams(self):
        headers = {
            "User-Agent": useragents.CHROME,
        }

        res = self.session.http.get(self.url, headers=headers)
        src_m = self._streamsrc_re.search(res.text)
        if src_m:
            self.url = src_m.group("streamsrc")
            return Livestream._get_streams(self)
        else:
            self.logger.error("Could not find the Livestream source for Radio2See")


__plugin__ = Radio2See
