from pathlib import Path

from utils.files import (
    clean_dir_contents,
    make_job_dir,
    remove_tree,
    sanitize_filename_part,
    short_id,
)


class TestSanitize:
    def test_spaces_become_underscores(self):
        assert sanitize_filename_part("Some Creator Name") == "Some_Creator_Name"

    def test_forbidden_characters_removed(self):
        result = sanitize_filename_part('a/b\\c:d*e?f"g<h>i|j#k[l]m^n')
        for ch in '\\/:*?"<>|#[]^':
            assert ch not in result

    def test_unicode_preserved(self):
        assert sanitize_filename_part("किसी ने कहा") == "किसी_ने_कहा"

    def test_truncation(self):
        result = sanitize_filename_part("x" * 200, max_len=40)
        assert len(result) == 40

    def test_empty_and_junk_falls_back(self):
        assert sanitize_filename_part("") == "instagram"
        assert sanitize_filename_part("///***///") == "instagram"
        assert sanitize_filename_part(None) == "instagram"

    def test_custom_fallback(self):
        assert sanitize_filename_part("", fallback="clip") == "clip"


class TestShortId:
    def test_deterministic(self):
        assert short_id("https://x/") == short_id("https://x/")

    def test_hex_shape(self):
        sid = short_id("anything")
        assert len(sid) == 8
        assert all(c in "0123456789abcdef" for c in sid)

    def test_different_inputs_differ(self):
        assert short_id("a") != short_id("b")


class TestJobDirs:
    def test_make_and_remove_job_dir(self, tmp_path: Path):
        job_dir = make_job_dir(tmp_path)
        try:
            assert job_dir.is_dir()
            assert job_dir.name.startswith("job_")
            (job_dir / "video.mp4").write_bytes(b"data")
        finally:
            remove_tree(job_dir)
        assert not job_dir.exists()

    def test_remove_tree_none_is_noop(self):
        remove_tree(None)  # must not raise

    def test_clean_dir_contents(self, tmp_path: Path):
        (tmp_path / "file.txt").write_text("x")
        (tmp_path / "sub").mkdir()
        (tmp_path / "sub" / "inner.txt").write_text("y")
        clean_dir_contents(tmp_path)
        assert tmp_path.exists()
        assert list(tmp_path.iterdir()) == []
