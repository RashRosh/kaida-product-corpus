from kb.measurements import extract_measurements


def test_unknown_title_stays_unresolved(resolver):
    result = resolver.resolve("Совершенно новый неизвестный товар", "Прочее")
    assert result.mapping_status == "UNRESOLVED"
    assert result.canonical_product_id == ""


def test_provisional_product_is_not_promoted(resolver):
    result = resolver.resolve("Картошка", "Десерты")
    assert result.canonical_product_id == "KAIDA-P0817"
    assert result.mapping_status == "PROVISIONAL_MAPPING"


def test_quantity_attributes_do_not_change_product_rule(resolver):
    small = resolver.resolve("Креветка тигровая 16/20 1 кг", "Морепродукты")
    large = resolver.resolve("Креветка тигровая 20/30 2 кг", "Морепродукты")
    assert small.canonical_product_id == large.canonical_product_id == "KAIDA-P0218"
    assert extract_measurements(small.raw_title) != extract_measurements(large.raw_title)


def test_same_lexeme_needs_compatible_context(resolver):
    result = resolver.resolve("Яблоко", "Горячие напитки")
    assert result.canonical_product_id != "KAIDA-P0432"
