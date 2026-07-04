"""
Shared network helpers.

Some download hosts (e.g. gyan.dev, the FFmpeg build server) present TLS
chains that the Windows certificate store rejects while the Mozilla CA
bundle from certifi accepts. urlopen() below retries with certifi before
giving up — certificate verification itself is never disabled.
"""
import ssl
import urllib.error
import urllib.request

_UA = {'User-Agent': 'Mozilla/5.0'}


def _certifi_context():
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()


def urlopen(url, timeout=30):
    """urllib.request.urlopen with UA header and certifi SSL fallback"""
    req = urllib.request.Request(url, headers=_UA)
    try:
        return urllib.request.urlopen(req, timeout=timeout)
    except urllib.error.URLError as e:
        if 'CERTIFICATE_VERIFY_FAILED' in str(e):
            return urllib.request.urlopen(req, timeout=timeout,
                                          context=_certifi_context())
        raise


__all__ = ['urlopen']
