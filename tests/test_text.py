from utils.text import (
    Paragraph,
    Segment,
    build_paragraphs,
    clean_segments,
    format_timestamp,
    parse_srt,
    render_transcript,
    word_count,
)


def seg(start: float, text: str, end: float | None = None) -> Segment:
    return Segment(start, end if end is not None else start + 2.0, text)


class TestCleanSegments:
    def test_strips_music_tags(self):
        result = clean_segments([seg(0, "[MUSIC] Hello world"), seg(3, "Second line")])
        assert [s.text for s in result] == ["Hello world", "Second line"]

    def test_tag_variants(self):
        for variant in ("(music)", "[Music]", "[BLANK_AUDIO]", "[silence]", "[APPLAUSE]"):
            result = clean_segments([seg(0, f"{variant} keep me")])
            assert result[0].text == "keep me"

    def test_keep_tags_option(self):
        result = clean_segments([seg(0, "[MUSIC] Hello")], keep_tags=True)
        assert result[0].text == "[MUSIC] Hello"

    def test_tag_only_segment_dropped(self):
        result = clean_segments([seg(0, "[MUSIC]"), seg(3, "hello")])
        assert [s.text for s in result] == ["hello"]

    def test_consecutive_duplicates_collapsed(self):
        result = clean_segments([
            seg(0, "Thank you for watching"),
            seg(3, "Thank you for watching."),  # punctuation differs only
            seg(6, "THANK YOU FOR WATCHING"),   # case differs only
            seg(9, "Real content"),
        ])
        assert [s.text for s in result] == [
            "Thank you for watching",
            "Real content",
        ]

    def test_non_consecutive_duplicates_kept(self):
        result = clean_segments([seg(0, "hello"), seg(3, "world"), seg(6, "hello")])
        assert len(result) == 3

    def test_whitespace_normalized(self):
        result = clean_segments([seg(0, "  so   much    space  ")])
        assert result[0].text == "so much space"


class TestParagraphs:
    def test_gap_creates_paragraph_break(self):
        paragraphs = build_paragraphs([
            seg(0, "First paragraph, quite a bit of text to pass the minimum length check."),
            seg(40, "New paragraph after a long silence gap of forty seconds."),
        ])
        assert len(paragraphs) == 2
        assert paragraphs[0].start == 0
        assert paragraphs[1].start == 40

    def test_short_gap_stays_one_paragraph(self):
        paragraphs = build_paragraphs([seg(0, "one."), seg(1.5, "two."), seg(3, "three.")])
        assert len(paragraphs) == 1

    def test_devanagari_danda_is_sentence_end(self):
        segments = [
            seg(0, "यह एक लंबा वाक्य है। " * 8),
            seg(3, "यह दूसरा वाक्य है। " * 8),
        ]
        paragraphs = build_paragraphs(segments, target_chars=80)
        assert len(paragraphs) >= 2


class TestRenderTranscript:
    def test_markers_every_interval(self):
        paragraphs = [
            Paragraph("p1", 0),
            Paragraph("p2", 10),
            Paragraph("p3", 50),
            Paragraph("p4", 95),
        ]
        out = render_transcript(paragraphs, with_timestamps=True, interval_s=45)
        lines = out.split("\n\n")
        assert lines[0].startswith("[0:00]")
        assert not lines[1].startswith("[")  # 10s since last marker < 45
        assert lines[2].startswith("[0:50]")
        assert lines[3].startswith("[1:35]")

    def test_no_timestamps(self):
        out = render_transcript(
            [Paragraph("hello", 0), Paragraph("world", 100)],
            with_timestamps=False,
        )
        assert out == "hello\n\nworld"


class TestFormatTimestamp:
    def test_minutes_seconds(self):
        assert format_timestamp(83) == "1:23"

    def test_hours(self):
        assert format_timestamp(3725) == "1:02:05"

    def test_zero(self):
        assert format_timestamp(0) == "0:00"

    def test_negative_clamped(self):
        assert format_timestamp(-5) == "0:00"


class TestSrtParsing:
    def test_parse_basic_srt(self):
        content = (
            "1\n00:00:01,000 --> 00:00:03,500\nHello there\n\n"
            "2\n00:00:04,000 --> 00:00:06,000\nSecond line\ncontinued\n\n"
        )
        segments = parse_srt(content)
        assert len(segments) == 2
        assert segments[0].start == 1.0
        assert segments[0].end == 3.5
        assert segments[0].text == "Hello there"
        assert segments[1].text == "Second line continued"

    def test_garbage_ignored(self):
        assert parse_srt("not an srt at all") == []


class TestWordCount:
    def test_count(self):
        assert word_count("one two three") == 3
        assert word_count("") == 0


class TestHinglishTransliteration:
    def test_clean_segments_to_roman_urdu(self):
        # Urdu reel sample: "اوبر پہ کیاب ریکویس کرو اور کچھ ہی سیکنڈ میں ڈرائیور مل جاتا ہے"
        input_segs = [seg(0, "اوبر پہ کیاب ریکویس کرو اور کچھ ہی سیکنڈ میں ڈرائیور مل جاتا ہے")]
        cleaned = clean_segments(input_segs, to_roman=True)
        assert len(cleaned) == 1
        res = cleaned[0].text.lower()
        assert "uber" in res
        assert "driver" in res or "draewr" in res

    def test_clean_segments_to_roman_devanagari(self):
        input_segs = [seg(0, "नमस्ते दोस्तों, कैसे हैं आप सब?")]
        cleaned = clean_segments(input_segs, to_roman=True)
        assert len(cleaned) == 1
        res = cleaned[0].text.lower()
        assert "namaste" in res

    def test_clean_segments_native_preserves_script(self):
        input_segs = [seg(0, "नमस्ते दोस्तों")]
        cleaned = clean_segments(input_segs, to_roman=False)
        assert cleaned[0].text == "नमस्ते दोस्तों"
