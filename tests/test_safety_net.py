import io  # lets us catch printed text in memory
import json  # reads and writes the save file
from contextlib import redirect_stderr, redirect_stdout  # grabs what the cli prints
from pathlib import Path  # easier file paths
import tempfile  # makes a throwaway folder so real saves never change
import unittest  # python's built in test framework

from supplydesk.cli import main  # the command line entry point
from supplydesk.service import OrderService  # the class we are testing


def item(product_id, quantity):  # small helper so tests are shorter
    return {"product_id": product_id, "quantity": quantity}  # same shape the service expects


class ServiceTestCase(unittest.TestCase):  # shared setup every test class uses
    def setUp(self):  # runs before every single test
        self.directory = tempfile.TemporaryDirectory()  # fresh empty folder
        self.addCleanup(self.directory.cleanup)  # delete the folder after the tset
        self.path = Path(self.directory.name) / "state.json"  # save file inside it
        self.service = OrderService(self.path)  # service using that save file

    def stock(self, product_id):  # gets current stock for one product
        for product in self.service.catalog():  # go through evry product
            if product["product_id"] == product_id:  # found the one we want
                return product["stock"]  # send back its stock
        raise AssertionError("missing product " + product_id)  # product should always exist

    def saved_text(self):  # raw save file text so we can compare before and after
        return self.path.read_text(encoding="utf-8") if self.path.exists() else None  # none if nothing saved yet


# category 1 normal behavior
class NormalBehaviorTests(ServiceTestCase):  # everyday stuff a user does
    def test_multi_item_regular_pickup_quote(self):  # quote with two different products
        quote = self.service.quote("regular", [item("notebook", 2), item("mug", 1)])  # 2 notebooks and 1 mug
        self.assertEqual([line["line_total_cents"] for line in quote["items"]], [1000, 1500])  # each line priced right
        self.assertEqual(quote["subtotal_cents"], 2500)  # 1000 plus 1500
        self.assertEqual(quote["discount_cents"], 0)  # regular gets no discount
        self.assertEqual(quote["delivery_cents"], 0)  # pickup is free
        self.assertEqual(quote["total_cents"], 2500)  # final total is $25

    def test_place_order_deducts_stock_and_saves(self):  # placing an order should update everything
        order = self.service.place_order("regular", [item("notebook", 3)])  # buy 3 notebooks
        self.assertEqual(order["status"], "placed")  # new orders start as placed
        self.assertEqual(order["total_cents"], 1500)  # 3 times 500
        self.assertEqual(self.stock("notebook"), 17)  # 20 minus 3
        self.assertEqual(OrderService(self.path).list_orders(), [order])  # reopening still shows the order

    def test_quote_does_not_create_save_file_or_reserve_stock(self):  # quotes are just a preview
        self.service.quote("regular", [item("hoodie", 5)])  # quote every hoodie
        self.assertFalse(self.path.exists())  # no save file made
        self.assertEqual(self.stock("hoodie"), 5)  # stock not touched


# category 2 boundary behavior
class BoundaryBehaviorTests(ServiceTestCase):  # edges where off by one bugs hide
    def test_student_discount_applies_at_exactly_5000(self):  # spec says at least $50 gets the discont
        quote = self.service.quote("student", [item("bag", 2)])  # 2 bags is exactly $50
        self.assertEqual(quote["subtotal_cents"], 5000)  # confirm we are right on the limit
        self.assertEqual(quote["discount_cents"], 500)  # should get 10 percent off
        self.assertEqual(quote["total_cents"], 4500)  # $50 minus $5

    def test_no_student_discount_just_below_5000(self):  # just under the limit gets nothing
        quote = self.service.quote("student", [item("hoodie", 1), item("notebook", 1)])  # $45 total
        self.assertEqual(quote["subtotal_cents"], 4500)  # under $50
        self.assertEqual(quote["discount_cents"], 0)  # no discount yet

    def test_delivery_free_at_exactly_10000(self):  # spec says delivery is free at $100
        quote = self.service.quote("regular", [item("bag", 4)], "delivery")  # 4 bags is exactly $100
        self.assertEqual(quote["subtotal_cents"], 10000)  # right on the limit
        self.assertEqual(quote["delivery_cents"], 0)  # delivery should be free
        self.assertEqual(quote["total_cents"], 10000)  # nothing extra added

    def test_delivery_charged_when_discount_drops_below_10000(self):  # discount comes off before the delivery check
        quote = self.service.quote("student", [item("hoodie", 2), item("bag", 1)], "delivery")  # $105 before discount
        self.assertEqual(quote["discount_cents"], 1050)  # 10 percent off
        self.assertEqual(quote["delivery_cents"], 600)  # $94.50 is under $100 so delivery costs $6
        self.assertEqual(quote["total_cents"], 10050)  # 10500 minus 1050 plus 600

    def test_quantity_limits(self):  # quantity has to be 1 to 99
        self.assertEqual(self.service.quote("regular", [item("notebook", 1)])["total_cents"], 500)  # 1 is the smallest allowed
        for quantity in (0, -1, 100):  # values outside the range
            with self.assertRaises(ValueError):  # each one should be rejected
                self.service.quote("regular", [item("notebook", quantity)])  # try the bad quantity

    def test_can_order_all_remaining_stock(self):  # buying the last item should work
        self.service.place_order("regular", [item("bag", 4)])  # buy every bag
        self.assertEqual(self.stock("bag"), 0)  # none left
        with self.assertRaises(ValueError):  # now even 1 more should fail
            self.service.quote("regular", [item("bag", 1)])  # try to quote one more


# category 3 invalid or exceptional behavior
class InvalidBehaviorTests(ServiceTestCase):  # bad input should be rejected safely
    def test_invalid_requests_raise_value_error(self):  # lots of bad requets in one test
        bad_requests = [  # each one breaks a different rule
            ("teacher", [item("mug", 1)], "pickup"),  # customer type not allowed
            ("regular", [item("mug", 1)], "drone"),  # fulfillment not allowed
            ("regular", [], "pickup"),  # empty order
            ("regular", "mug", "pickup"),  # items is not a list
            ("regular", [item("laptop", 1)], "pickup"),  # product does not exist
            ("regular", [item("mug", True)], "pickup"),  # boolean is not a real quantity
            ("regular", [item("mug", 1.0)], "pickup"),  # decimals not allowed
            ("regular", [item("mug", "2")], "pickup"),  # text number not allowed in the service
            ("regular", [item("mug", 9)], "pickup"),  # only 8 mugs in stock
        ]  # end of the bad requests list
        for request in bad_requests:  # go through each bad request
            with self.subTest(request=request):  # shows which one failed if any do
                with self.assertRaises(ValueError):  # every one should raise
                    self.service.place_order(*request)  # try to place it

    def test_rejected_order_does_not_change_saved_data(self):  # a failed order should leave nothing behnd
        self.service.place_order("regular", [item("mug", 1)])  # one good order first
        before = self.saved_text()  # remember the save file
        with self.assertRaises(ValueError):  # second line is a fake product so this fails
            self.service.place_order("regular", [item("mug", 1), item("laptop", 1)])  # half good half bad
        self.assertEqual(self.saved_text(), before)  # save file did not change
        self.assertEqual(self.service.place_order("regular", [item("mug", 1)])["order_id"], "ORD-0002")  # no order number was wasted

    def test_duplicate_lines_cannot_exceed_combined_stock(self):  # spec says repeated products add together
        with self.assertRaises(ValueError):  # 6 bags total but only 4 exist
            self.service.place_order("regular", [item("bag", 3), item("bag", 3)])  # same product on two lines
        self.assertEqual(self.stock("bag"), 4)  # stock should not change

    def test_unknown_order_id_raises(self):  # looking up a fake order
        with self.assertRaises(ValueError):  # get should fail
            self.service.get_order("ORD-9999")  # order that doesnt exist
        with self.assertRaises(ValueError):  # cancel should fail too
            self.service.cancel_order("ORD-9999")  # same fake order
        self.assertFalse(self.path.exists())  # nothing got saved

    def test_malformed_save_file_raises_instead_of_resetting(self):  # broken save file should not wipe data
        self.path.write_text("{ not json", encoding="utf-8")  # write garbage into the save file
        with self.assertRaises(ValueError):  # loading it should error
            self.service.catalog()  # any load will do
        self.assertEqual(self.saved_text(), "{ not json")  # file was not overwritten

    def test_cli_rejected_command_returns_status_2(self):  # cli should exit with 2 on bad input
        error = io.StringIO()  # holds the error text
        with redirect_stderr(error):  # catch the error message
            status = main(["--data", str(self.path), "place", "--item", "laptop:1"])  # order a fake product
        self.assertEqual(status, 2)  # rejected input exit code
        self.assertIn("Error", error.getvalue())  # an error message was printed
        self.assertFalse(self.path.exists())  # nothing got saved


# category 4 behavior important to preserve during refactoring
class PreservedBehaviorTests(ServiceTestCase):  # things the refactor must not break
    def test_quote_and_placed_order_match(self):  # quote and order should have the same numbers
        request = ("student", [item("hoodie", 1), item("mug", 2)], "delivery")  # same request for both
        quote = self.service.quote(*request)  # get the quote
        order = self.service.place_order(*request)  # then place it
        for key in ("customer_type", "fulfillment", "items", "subtotal_cents",  # every shared field
                    "discount_cents", "delivery_cents", "total_cents"):  # including all the money
            self.assertEqual(order[key], quote[key], key)  # each one should match

    def test_order_ids_increase_and_are_not_reused_after_cancel(self):  # cancelled ids stay taken
        first = self.service.place_order("regular", [item("pen-pack", 1)])  # first order
        self.service.cancel_order(first["order_id"])  # cancel it
        second = self.service.place_order("regular", [item("pen-pack", 1)])  # place another
        self.assertEqual(first["order_id"], "ORD-0001")  # ids start at 1
        self.assertEqual(second["order_id"], "ORD-0002")  # next id is 2 not 1 again

    def test_cancelled_order_stays_in_history_with_totals(self):  # cancel should not delete the ordr
        order = self.service.place_order("student", [item("hoodie", 2)])  # first order
        self.service.place_order("regular", [item("mug", 1)])  # second order
        self.service.cancel_order(order["order_id"])  # cancel the first one
        history = OrderService(self.path).list_orders()  # reopen and read history
        self.assertEqual([o["order_id"] for o in history], ["ORD-0001", "ORD-0002"])  # both still there in order
        self.assertEqual(history[0]["status"], "cancelled")  # first one is marked cancelled
        self.assertEqual(history[0]["total_cents"], order["total_cents"])  # total kept the same
        self.assertEqual(history[0]["items"], order["items"])  # items kept the same

    def test_cancelling_twice_does_not_restore_stock_again(self):  # spec says second cancel changes nothing
        order = self.service.place_order("regular", [item("bag", 2)])  # buy 2 bags
        self.service.cancel_order(order["order_id"])  # cancel once
        self.service.cancel_order(order["order_id"])  # cancel again
        self.assertEqual(self.stock("bag"), 4)  # should be back to 4 not more

    def test_history_keeps_original_prices(self):  # old orders keep the price they were bought at
        order = self.service.place_order("regular", [item("mug", 1)])  # buy a mug for $15
        state = json.loads(self.saved_text())  # open the save file
        state["catalog"][3]["unit_price_cents"] = 9999  # change the mug price
        self.path.write_text(json.dumps(state), encoding="utf-8")  # save the new price
        self.assertEqual(self.service.get_order(order["order_id"])["total_cents"], 1500)  # order still says $15

    def test_cli_place_prints_json_order(self):  # cli output format should stay the smae
        output = io.StringIO()  # holds the printed text
        with redirect_stdout(output):  # catch what gets printed
            status = main(["--data", str(self.path), "place", "--item", "notebook:2"])  # place through the cli
        self.assertEqual(status, 0)  # success exit code
        self.assertEqual(json.loads(output.getvalue())["total_cents"], 1000)  # printed json has the right total


if __name__ == "__main__":  # only runs when this file is run directly
    unittest.main()  # run every test in this file
