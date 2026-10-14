from utils.urls import extract_instagram_urls, normalize_instagram_url


class TestExtract:
    def test_single_reel_in_prose(self):
        text = "check this https://www.instagram.com/reel/CxAbCdEf123/?igsh=xyz nice"
        assert extract_instagram_urls(text) == [
            "https://www.instagram.com/reel/CxAbCdEf123/"
        ]

    def test_multiple_links_preserve_order(self):
        text = (
            "a https://www.instagram.com/reel/AAAA1111/ and "
            "b https://www.instagram.com/p/BBBB2222/ and "
            "c https://www.instagram.com/tv/CCCC3333/"
        )
        assert extract_instagram_urls(text) == [
            "https://www.instagram.com/reel/AAAA1111/",
            "https://www.instagram.com/p/BBBB2222/",
            "https://www.instagram.com/tv/CCCC3333/",
        ]

    def test_duplicate_links_deduplicated(self):
        text = "https://instagram.com/reel/SAME123/ and https://www.instagram.com/reel/SAME123/?x=1"
        assert extract_instagram_urls(text) == ["https://www.instagram.com/reel/SAME123/"]

    def test_share_link(self):
        assert extract_instagram_urls("see https://www.instagram.com/share/reel/AbCdEf1234/") == [
            "https://www.instagram.com/share/reel/AbCdEf1234/"
        ]

    def test_short_domain_instagr_am(self):
        assert extract_instagram_urls("http://instagr.am/p/Cabc_12-x/") == [
            "https://www.instagram.com/p/Cabc_12-x/"
        ]

    def test_bare_domain_without_scheme(self):
        assert extract_instagram_urls("instagram.com/reel/CODE123 plz") == [
            "https://www.instagram.com/reel/CODE123/"
        ]

    def test_trailing_sentence_punctuation_stripped(self):
        assert extract_instagram_urls("watch this: https://www.instagram.com/reel/CODE123/.") == [
            "https://www.instagram.com/reel/CODE123/"
        ]

    def test_non_instagram_ignored(self):
        text = "https://youtube.com/watch?v=abc https://t.me/somechannel plain text"
        assert extract_instagram_urls(text) == []

    def test_empty_and_none(self):
        assert extract_instagram_urls("") == []
        assert extract_instagram_urls(None) == []

    def test_link_inside_angle_brackets(self):
        assert extract_instagram_urls("<https://instagram.com/reel/BRKT123/>") == [
            "https://www.instagram.com/reel/BRKT123/"
        ]


class TestNormalize:
    def test_reels_plural_normalized_to_reel(self):
        assert normalize_instagram_url("https://www.instagram.com/reels/CODE123/") == (
            "https://www.instagram.com/reel/CODE123/"
        )

    def test_mobile_host_normalized(self):
        assert normalize_instagram_url("https://m.instagram.com/reel/CODE123/?utm=x") == (
            "https://www.instagram.com/reel/CODE123/"
        )

    def test_stories_kept(self):
        assert normalize_instagram_url("https://instagram.com/stories/username/987654/") == (
            "https://www.instagram.com/stories/username/987654/"
        )

    def test_unknown_path_returns_none(self):
        assert normalize_instagram_url("https://www.instagram.com/explore/tags/cats/") is None
        assert normalize_instagram_url("https://www.instagram.com/") is None

    def test_non_instagram_host_returns_none(self):
        assert normalize_instagram_url("https://evil.com/reel/CODE123/") is None
        assert normalize_instagram_url("https://instagram.com.evil.io/reel/CODE123/") is None

    def test_kind_without_code_returns_none(self):
        assert normalize_instagram_url("https://www.instagram.com/reel/") is None

    def test_share_with_extra_segments(self):
        assert normalize_instagram_url("https://www.instagram.com/share/reel/XYZ9/") == (
            "https://www.instagram.com/share/reel/XYZ9/"
        )
