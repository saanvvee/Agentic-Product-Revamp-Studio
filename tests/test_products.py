from revamp.products import list_products, load_product


def test_all_product_configs_load():
    names = list_products()
    assert {"umami", "mautic", "plane", "invoiceninja"} <= set(names)
    for n in names:
        p = load_product(n)
        assert p.name == n
        if p.answer_key:
            # The audit must look at the release BEFORE the redesign, and the
            # complaint cut-off must not be after the redesign shipped.
            assert p.ref == p.answer_key.old_ref
            assert p.cutoff <= p.answer_key.shipped_on
