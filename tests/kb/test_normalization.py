from kb.normalization import identity_key, normalize


def test_normalize_preserves_legacy_semantics():
    assert normalize("  Молоко, Ёлочка!  ") == "молоко елочка"


def test_normalize_uses_nfkc_for_reference_title_grain():
    assert normalize("ＡＢＣ Молоко") == "abc молоко"


def test_identity_key_removes_offer_quantities_only():
    assert identity_key("Креветка тигровая 16/20 2 кг") == "креветка тигровая"
    assert identity_key("Молоко 3,2% 1 л") == "молоко"


def test_identity_key_does_not_strip_product_words():
    assert identity_key("Картофельное пюре 250 г") == "картофельное пюре"
