from datetime import date

from services.markdown import VideoMeta, build_md_filename, render_markdown

META = VideoMeta(
    url="https://www.instagram.com/reel/CxAbCdEf123/",
    author="somecreator",
    title="somecreator on Instagram: my cool reel",
    upload_date=date(2026, 3, 14),
    duration_s=83,
    caption="Original caption here\nsecond line",
    language="hi",
    model_name="large-v3-turbo-q5_0",
)


class TestRenderMarkdown:
    def test_frontmatter_fields_and_order(self):
        md = render_markdown(META, "transcript body")
        lines = md.split("\n")
        assert lines[0] == "---"
        expected_keys = [
            "source:", "platform:", "author:", "title:", "uploaded:",
            "duration:", "language:", "transcribed:", "model:", "tags:",
        ]
        found_keys = [l.split(" ")[0] for l in lines[1:11]]
        assert found_keys == expected_keys

    def test_frontmatter_values(self):
        md = render_markdown(META, "body")
        assert 'source: "https://www.instagram.com/reel/CxAbCdEf123/"' in md
        assert "platform: instagram" in md
        assert 'author: "somecreator"' in md
        assert 'uploaded: "2026-03-14"' in md
        assert 'duration: "1:23"' in md
        assert 'language: "hi"' in md
        assert "tags: [transcript, instagram]" in md
        assert "transcribed:" in md  # ISO timestamp present

    def test_body_structure(self):
        md = render_markdown(META, "[0:00] Hello world")
        assert "# somecreator on Instagram: my cool reel" in md
        assert "**Video:** [https://www.instagram.com/reel/CxAbCdEf123/](https://www.instagram.com/reel/CxAbCdEf123/)" in md
        assert "## Transcript" in md
        assert "[0:00] Hello world" in md
        assert "## Caption" in md
        assert "Original caption here" in md

    def test_no_caption_section_when_missing(self):
        meta = VideoMeta(url="u", title="t", duration_s=10, language="en")
        md = render_markdown(meta, "body")
        assert "## Caption" not in md

    def test_title_with_quotes_and_colons_survives_yaml(self):
        import json

        weird = 'Weird: "quoted" title\nwith newline'
        meta = VideoMeta(url="u", title=weird, duration_s=1)
        md = render_markdown(meta, "body")
        title_line = next(line for line in md.split("\n") if line.startswith("title:"))
        # Must stay a single YAML line with the newline escaped by quoting.
        assert title_line == "title: " + json.dumps(weird, ensure_ascii=False)

    def test_empty_transcript_placeholder(self):
        meta = VideoMeta(url="u", title="t", duration_s=1)
        md = render_markdown(meta, "")
        assert "_(no speech detected)_" in md

    def test_title_fallback(self):
        meta = VideoMeta(url="u", title="", duration_s=1)
        md = render_markdown(meta, "body")
        assert "# Instagram video" in md


    def test_youtube_frontmatter_and_platform(self):
        meta = VideoMeta(
            url="https://www.youtube.com/shorts/dQw4w9WgXcQ",
            author="RickAstley",
            title="",
            duration_s=45,
        )
        md = render_markdown(meta, "Short transcript")
        assert 'source: "https://www.youtube.com/shorts/dQw4w9WgXcQ"' in md
        assert "platform: youtube" in md
        assert "tags: [transcript, youtube]" in md
        assert "# YouTube Short" in md

        # Fallback filename for youtube
        empty_meta = VideoMeta(url="https://www.youtube.com/shorts/dQw4w9WgXcQ")
        assert "_youtube_" in build_md_filename(empty_meta)


class TestFilename:
    def test_filename_shape(self):
        name = build_md_filename(META)
        # 2026-03-14_somecreator_<8-hex>.md
        assert name.startswith("2026-03-14_somecreator_")
        assert name.endswith(".md")
        shortid = name.split("_")[-1][:8]
        assert len(shortid) == 8 and all(c in "0123456789abcdef" for c in shortid)

    def test_filename_strips_forbidden_characters(self):
        meta = VideoMeta(
            url="https://www.instagram.com/reel/XYZ789/",
            author='Bad/Author: *Weird* "Name"',
        )
        name = build_md_filename(meta)
        for ch in '\\/*?:"<>|#[]^':
            assert ch not in name
        assert name.split("_")[1] == "Bad"

    def test_filename_falls_back_to_title_then_default(self):
        meta = VideoMeta(url="https://www.instagram.com/reel/ABC123/", title="Video Title Here")
        assert "_Video_Title_Here_" in build_md_filename(meta)
        empty = VideoMeta(url="https://www.instagram.com/reel/DEF456/")
        assert "_instagram_" in build_md_filename(empty)

    def test_filename_uses_today_when_no_upload_date(self):
        meta = VideoMeta(url="u", author="a")
        name = build_md_filename(meta, date_override=date(2020, 1, 2))
        assert name.startswith("2020-01-02_a_")

    def test_shortid_is_stable(self):
        assert build_md_filename(META) == build_md_filename(META)


class TestSerializationRoundtrip:
    def test_meta_dict_roundtrip(self):
        data = META.to_dict()
        restored = VideoMeta.from_dict(data)
        assert restored == META

