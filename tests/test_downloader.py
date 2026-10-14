import pytest
from services.downloader import (
    Kind,
    _classify,
    _fail,
    _pick_video_entry,
)

def test_pick_video_entry():
    assert _pick_video_entry({}) is None
    simple = {"id": "123", "title": "test"}
    assert _pick_video_entry(simple) == simple

    playlist = {
        "_type": "playlist",
        "entries": [
            {"id": "e1"},
            {"id": "e2", "formats": [{"url": "http"}], "duration": 10},
        ],
    }
    picked = _pick_video_entry(playlist)
    assert picked["id"] == "e2"

def test_classify_errors():
    err_private = _classify(Exception("This account is private"))
    assert err_private.kind == Kind.PRIVATE
    assert "private" in err_private.user_message

    err_login = _classify(Exception("Please log in or authenticate"))
    assert err_login.kind == Kind.LOGIN_REQUIRED

    err_geo = _classify(Exception("Not available in your country"))
    assert err_geo.kind == Kind.GEO_RESTRICTED

    err_size = _classify(Exception("File is larger than max-filesize"))
    assert err_size.kind == Kind.TOO_LARGE
    assert "too large" in err_size.user_message

    err_404 = _classify(Exception("HTTP Error 404: Not Found"))
    assert err_404.kind == Kind.PRIVATE

def test_fail_formatting():
    f1 = _fail(Kind.TOO_LARGE, limit=500)
    assert "limit is 500 MB" in f1.user_message

    f2 = _fail(Kind.TOO_LARGE, limit="")
    assert "Video file is too large." in f2.user_message
