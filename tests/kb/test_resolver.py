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


def test_dairy_brand_fat_and_volume_are_offer_attributes(resolver):
    result = resolver.resolve("Молоко FoodMaster 3,2% 1 л", "Молочная продукция")
    assert result.canonical_product_id == "KAIDA-P0265"
    assert result.attributes["brand"] == "FoodMaster"
    assert result.attributes["percentages"] == [3.2]
    assert result.attributes["measurements"][0]["unit"] == "l"


def test_process_does_not_change_shrimp_product_identity(resolver):
    result = resolver.resolve(
        "Креветка тигровая свежемороженая 16/20 1 кг", "Морепродукты"
    )
    assert result.canonical_product_id == "KAIDA-P0218"
    assert result.attributes["process"] == ["замороженный"]


def test_generic_salmon_does_not_mean_pacific_salmon(resolver):
    result = resolver.resolve("Лосось", "Рыба")
    assert result.canonical_product_id != "KAIDA-P0174"


def test_caviar_species_stays_child_product(resolver):
    generic = resolver.resolve("Красная икра", "Рыба и морепродукты")
    species = resolver.resolve("Икра кеты", "Рыба и морепродукты")
    assert generic.canonical_product_id == "KAIDA-P0252"
    assert species.canonical_product_id == "KAIDA-P0254"


def test_culinary_transformation_creates_distinct_product_identity(resolver):
    fries = resolver.resolve("Картофель фри", "Гарниры")
    puree = resolver.resolve("Картофельное пюре", "Гарниры")
    assert fries.canonical_product_id == "KAIDA-P0826"
    assert puree.canonical_product_id == "KAIDA-P0827"
    assert fries.canonical_product_id != puree.canonical_product_id
    assert fries.mapping_status == puree.mapping_status == "PROVISIONAL_MAPPING"


def test_stable_baked_form_keeps_filling_as_attribute(resolver):
    result = resolver.resolve("Круассан с шоколадом", "Выпечка")
    assert result.canonical_product_id == "KAIDA-P0693"
    assert result.attributes["filling"] == "шоколадом"
