"""tests for cr01 express delivery"""

import io  # lets us catch printed text in memory
import json  # reads the cli output and save file
from contextlib import redirect_stdout  # grabs what the cli prints
from pathlib import Path  # easier file paths
import tempfile  # throwaway folder so real saves never change
import unittest  # python's built in test framework
from unittest.mock import patch  # fakes keyboard input for the menu

from supplydesk.cli import build_parser, main  # command line pieces we test
from supplydesk.menu import read_request  # the menu prompt we test
from supplydesk.service import OrderService  # the class we are testing


def item(product_id, quantity):  # small helper so tests are shorter
    return {"product_id": product_id, "quantity": quantity}  # same shape the service expects


class ExpressTestCase(unittest.TestCase):  # shared setup for every express test
    def setUp(self):  # runs before every single test
        self.directory = tempfile.TemporaryDirectory()  # fresh empty folder
        self.addCleanup(self.directory.cleanup)  # delete the folder after the test
        self.path = Path(self.directory.name) / "state.json"  # save file inside it
        self.service = OrderService(self.path)  # service using that save file

    def stock(self, product_id):  # gets current stock for one product
        for product in self.service.catalog():  # go through evry product
            if product["product_id"] == product_id:  # found the one we want
                return product["stock"]  # send back its stock
        raise AssertionError("missing product " + product_id)  # product should always exist


class ExpressPricingTests(ExpressTestCase):  # the three examples from the change request
    def test_regular_express_two_notebooks(self):  # $10 plus $12 express
        quote = self.service.quote("regular", [item("notebook", 2)], "express")  # regular express quote
        self.assertEqual(quote["fulfillment"], "express")  # fulfillment is kept as express
        self.assertEqual(quote["subtotal_cents"], 1000)  # 2 notebooks
        self.assertEqual(quote["discount_cents"], 0)  # regular gets no discount
        self.assertEqual(quote["delivery_cents"], 1200)  # express is always $12
        self.assertEqual(quote["total_cents"], 2200)  # $22 total

    def test_student_express_two_hoodies(self):  # discount only comes off the items
        quote = self.service.quote("student", [item("hoodie", 2)], "express")  # student express quote
        self.assertEqual(quote["discount_cents"], 800)  # 10 percent of $80 same as before
        self.assertEqual(quote["delivery_cents"], 1200)  # express fee not discounted
        self.assertEqual(quote["total_cents"], 8400)  # 80 minus 8 plus 12

    def test_express_fee_never_waived(self):  # standard is free over $100 but express is not
        request = ("regular", [item("hoodie", 3)])  # $120 of hoodies
        standard = self.service.quote(*request, "delivery")  # standard delivery quote
        express = self.service.quote(*request, "express")  # express quote
        self.assertEqual(standard["delivery_cents"], 0)  # standard still free over $100
        self.assertEqual(standard["total_cents"], 12000)  # $120
        self.assertEqual(express["delivery_cents"], 1200)  # express still charged
        self.assertEqual(express["total_cents"], 13200)  # $132


class ExpressOrderTests(ExpressTestCase):  # placing reopening and cancelling express orders
    def test_express_quote_and_order_match(self):  # quote and order have to agree
        request = ("student", [item("hoodie", 1), item("mug", 2)], "express")  # same request for both
        quote = self.service.quote(*request)  # get the quote
        order = self.service.place_order(*request)  # then place it
        for key in quote:  # every field in the quote
            self.assertEqual(order[key], quote[key], key)  # should match the order

    def test_express_order_kept_after_reopen_and_cancel(self):  # nothing about the order should chnage
        order = self.service.place_order("regular", [item("notebook", 2)], "express")  # place express order
        reopened = OrderService(self.path).get_order(order["order_id"])  # reopen from the save file
        self.assertEqual(reopened, order)  # exact same order after reopening
        cancelled = OrderService(self.path).cancel_order(order["order_id"])  # cancel from a fresh service
        self.assertEqual(cancelled["status"], "cancelled")  # status changed
        for key in ("fulfillment", "items", "delivery_cents", "discount_cents", "total_cents"):  # fields cr01 lists
            self.assertEqual(cancelled[key], order[key], key)  # all kept the same

    def test_express_follows_stock_and_numbering_rules(self):  # express uses the same rules as everything else
        first = self.service.place_order("regular", [item("bag", 2)], "express")  # first express order
        self.assertEqual(first["order_id"], "ORD-0001")  # ids still start at 1
        self.assertEqual(self.stock("bag"), 2)  # 4 minus 2
        self.service.cancel_order(first["order_id"])  # cancel it
        self.assertEqual(self.stock("bag"), 4)  # stock is back
        second = self.service.place_order("regular", [item("bag", 1)], "express")  # another order
        self.assertEqual(second["order_id"], "ORD-0002")  # id not reused
        with self.assertRaises(ValueError):  # still cant order more than stock
            self.service.quote("regular", [item("bag", 9)], "express")  # way over the stock


class ExpressValidationTests(ExpressTestCase):  # other fulfillment values still rejected
    def test_other_fulfillment_values_still_invalid(self):  # only the three options work
        for fulfillment in ("Express", "overnight", "", None):  # bad values including wrong case
            with self.subTest(fulfillment=fulfillment):  # shows which one failed if any do
                with self.assertRaises(ValueError):  # each one should be rejected
                    self.service.quote("regular", [item("mug", 1)], fulfillment)  # try it

    def test_pickup_and_delivery_unchanged(self):  # old options still work like before
        pickup = self.service.quote("regular", [item("notebook", 2)])  # default is pickup
        delivery = self.service.quote("student", [item("hoodie", 2)], "delivery")  # standard delivery
        self.assertEqual(pickup["fulfillment"], "pickup")  # default didnt change
        self.assertEqual(pickup["delivery_cents"], 0)  # pickup still free
        self.assertEqual(delivery["delivery_cents"], 600)  # standard still $6
        self.assertEqual(delivery["total_cents"], 7800)  # same as the original smoke test


class ExpressInterfaceTests(ExpressTestCase):  # cli and menu should both know about express
    def test_cli_quote_express_matches_example(self):  # example command from cr01
        output = io.StringIO()  # holds the printed text
        with redirect_stdout(output):  # catch what gets printed
            status = main(["--data", str(self.path), "quote", "--customer", "student",
                           "--fulfillment", "express", "--item", "hoodie:2"])  # the example command
        self.assertEqual(status, 0)  # success exit code
        self.assertEqual(json.loads(output.getvalue())["total_cents"], 8400)  # matches the expected total

    def test_cli_place_express_and_help(self):  # place works and help shows express
        output = io.StringIO()  # holds the printed text
        with redirect_stdout(output):  # catch what gets printed
            status = main(["--data", str(self.path), "place", "--fulfillment", "express",
                           "--item", "notebook:2"])  # place an express order
        self.assertEqual(status, 0)  # success exit code
        self.assertEqual(json.loads(output.getvalue())["fulfillment"], "express")  # saved as express
        help_text = io.StringIO()  # holds the help text
        with redirect_stdout(help_text), self.assertRaises(SystemExit):  # help prints then exits
            build_parser().parse_args(["quote", "--help"])  # ask for the quote help
        self.assertIn("express", help_text.getvalue())  # express shows up in the help

    def test_menu_accepts_express_and_keeps_defaults(self):  # interactive menu prompt
        service = self.service  # menu reads the catalog from here
        with patch("builtins.input", side_effect=["student", "mug", "1", "", "express"]) as fake:  # typed answers
            with redirect_stdout(io.StringIO()):  # hide the catalog table
                self.assertEqual(read_request(service), ("student", [item("mug", 1)], "express"))  # express goes through
        self.assertIn("express", fake.call_args_list[-1].args[0])  # fulfillment prompt mentions express
        with patch("builtins.input", side_effect=["", "mug", "1", "", ""]):  # leave customer and fulfillment blank
            with redirect_stdout(io.StringIO()):  # hide the catalog table
                self.assertEqual(read_request(service), ("regular", [item("mug", 1)], "pickup"))  # defaults unchanged


if __name__ == "__main__":  # only runs when this file is run directly
    unittest.main()  # run every test in this file
