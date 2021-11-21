"""
    radio2see by Billy2011
    Support for www.radio21.de/tv & www.rockland.de/tv Live TV stream
"""
import re

from streamlink.plugin import Plugin, pluginmatcher


@pluginmatcher(re.compile(r"https?://(?:www)\.(?:(radio21|rockland))\.de/(?:musik/)?(?:tv$)"))
class Radio2See(Plugin):
    _streamsrc_re = re.compile(r"""<iframe.*?\ssrc=["'](?P<streamsrc>[^"']+)["']""", re.DOTALL)

    def _get_streams(self):
        res = self.session.http.get(self.url)
        for s in self._streamsrc_re.findall(res.text):
            if "/livestream.com/accounts/" in s:
                return self.session.streams(s)


__plugin__ = Radio2See
