from core.naming import sanitize_sample_name


def test_ascii_passthrough():
    assert sanitize_sample_name("kick drum") == "kick drum"


def test_cyrillic_transliteration():
    assert sanitize_sample_name("Привіт собаки") == "Privit sobaki"


def test_accented_latin():
    assert sanitize_sample_name("Ünïcödé") == "Unicode"


def test_cjk_transliteration():
    result = sanitize_sample_name("キック")
    assert result.isascii()
    assert len(result) > 0


def test_mixed_ascii_and_unicode():
    assert sanitize_sample_name("my Кік drum") == "my Kik drum"


def test_empty_string():
    assert sanitize_sample_name("") == ""


def test_whitespace_collapse():
    assert sanitize_sample_name("a   b") == "a b"


def test_non_printable_stripped():
    assert sanitize_sample_name("kick\x00drum\x01") == "kickdrum"


def test_already_clean():
    assert sanitize_sample_name("001 snare_tight") == "001 snare_tight"
