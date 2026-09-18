import unittest

from src.billing import (
    DEFAULT_HAS_UNIT,
    DEFAULT_UNIT,
    DEFAULT_UNIT_PRICE,
    Billing,
    read_billing,
    write_billing,
)


class BillingDefaultsTests(unittest.TestCase):
    def test_dataclass_defaults_match_documented_business_defaults(self):
        billing = Billing()

        self.assertEqual(billing.has_unit, DEFAULT_HAS_UNIT)
        self.assertEqual(billing.unit_price, DEFAULT_UNIT_PRICE)
        self.assertEqual(billing.unit, DEFAULT_UNIT)
        self.assertTrue(billing.is_per_unit)

    def test_from_dict_none_or_empty_falls_back_to_defaults(self):
        for payload in (None, {}):
            with self.subTest(payload=payload):
                self.assertEqual(Billing.from_dict(payload), Billing())

    def test_missing_fields_are_filled_one_by_one(self):
        billing = Billing.from_dict({"unit": "m²"})

        self.assertTrue(billing.has_unit)
        self.assertEqual(billing.unit_price, DEFAULT_UNIT_PRICE)
        self.assertEqual(billing.unit, "m²")

    def test_to_dict_always_serializes_all_three_keys(self):
        self.assertEqual(
            set(Billing().to_dict()),
            {"has_unit", "unit_price", "unit"},
        )


class BillingNormalizationTests(unittest.TestCase):
    def test_disabling_unit_price_zeroes_price_and_drops_unit(self):
        billing = Billing(has_unit=False, unit_price=88.8, unit="m²")

        self.assertFalse(billing.has_unit)
        self.assertEqual(billing.unit_price, 0)
        self.assertEqual(billing.unit, "")
        self.assertFalse(billing.is_per_unit)

    def test_int_price_from_json_is_coerced_to_float(self):
        billing = Billing.from_dict({"has_unit": True, "unit_price": 5, "unit": "个"})

        self.assertIsInstance(billing.unit_price, float)
        self.assertEqual(billing.unit_price, 5.0)

    def test_non_numeric_price_is_replaced_by_default_instead_of_raising(self):
        billing = Billing.from_dict({"has_unit": True, "unit_price": "abc"})

        self.assertEqual(billing.unit_price, DEFAULT_UNIT_PRICE)

    def test_none_price_is_replaced_by_default(self):
        billing = Billing.from_dict({"has_unit": True, "unit_price": None})

        self.assertEqual(billing.unit_price, DEFAULT_UNIT_PRICE)

    def test_none_unit_becomes_empty_string(self):
        billing = Billing.from_dict({"unit": None})

        self.assertEqual(billing.unit, "")

    def test_has_unit_truthiness_is_normalized_to_bool(self):
        self.assertTrue(Billing.from_dict({"has_unit": 1}).has_unit)
        self.assertFalse(Billing.from_dict({"has_unit": 0}).has_unit)

    def test_non_numeric_price_on_disabled_unit_stays_zero(self):
        # has_unit=False 先归零，随后 float() 兜底不应把它重新拉回默认单价
        billing = Billing(has_unit=False, unit_price="abc")

        self.assertEqual(billing.unit_price, 0)


class BillingFormatTests(unittest.TestCase):
    def test_disabled_unit_formats_as_explicit_no_price_label(self):
        self.assertEqual(Billing(has_unit=False, unit_price=50, unit="个").format_price(), "无单价")

    def test_per_unit_price_without_unit_omits_trailing_space(self):
        self.assertEqual(Billing(unit_price=1, unit="").format_price(), "1.00")

    def test_per_unit_price_with_unit_keeps_two_decimals(self):
        self.assertEqual(Billing(unit_price=10, unit="m²").format_price(), "10.00 m²")

    def test_price_is_rounded_to_two_decimals_for_display_only(self):
        billing = Billing(unit_price=3.14159, unit="个")

        self.assertEqual(billing.format_price(), "3.14 个")
        self.assertEqual(billing.unit_price, 3.14159)


class BillingDictBridgeTests(unittest.TestCase):
    def test_round_trip_through_dict_is_lossless(self):
        original = Billing(has_unit=True, unit_price=12.5, unit="个")

        self.assertEqual(Billing.from_dict(original.to_dict()), original)

    def test_read_billing_tolerates_item_without_billing_keys(self):
        billing = read_billing({"id": "ti_1", "name": "抹灰"})

        self.assertEqual(billing, Billing())

    def test_write_billing_overwrites_only_the_three_keys(self):
        item = {"id": "ti_1", "name": "抹灰", "has_unit": False, "unit_price": 0, "unit": ""}

        write_billing(item, Billing(has_unit=True, unit_price=9.5, unit="m²"))

        self.assertEqual(item["id"], "ti_1")
        self.assertEqual(item["name"], "抹灰")
        self.assertIs(item["has_unit"], True)
        self.assertEqual(item["unit_price"], 9.5)
        self.assertEqual(item["unit"], "m²")

    def test_write_then_read_returns_an_equal_value_object(self):
        target = Billing(has_unit=True, unit_price=7.25, unit="工日")
        item: dict = {}

        write_billing(item, target)

        self.assertEqual(read_billing(item), target)


if __name__ == "__main__":
    unittest.main()
