"""Operations used by the command-line order desk."""

from supplydesk.storage import JsonStore  # handles loading and saving the json file

MIN_QUANTITY = 1  # smallest amount you can order of one item
MAX_QUANTITY = 99  # biggest amount you can order of one item
STUDENT_DISCOUNT_MIN_CENTS = 5000  # subtotal needed for the student discont
STUDENT_DISCOUNT_PERCENT = 10  # students get 10 percent off
DELIVERY_FEE_CENTS = 600  # delivery costs $6
EXPRESS_FEE_CENTS = 1200  # express always costs $12 and is never free
FREE_DELIVERY_MIN_CENTS = 10000  # delivery is free at $100 after the discount


class OrderService:  # all the business rules live here
    def __init__(self, state_path=".supplydesk/state.json"):  # default save file if none is given
        self.store = JsonStore(state_path)  # the store that reads and writes the save file

    def catalog(self):  # list of products with their stock
        return self.store.load()["catalog"]  # just the catalog part of the state

    def quote(self, customer_type, items, fulfillment="pickup"):  # price check that saves nothing
        state = self.store.load()  # get the current stock
        return self._build_quote(state, customer_type, items, fulfillment)  # shared pricing code does the work

    def place_order(self, customer_type, items, fulfillment="pickup"):  # actually buys the items
        state = self.store.load()  # get the current stock
        quote = self._build_quote(state, customer_type, items, fulfillment)  # same checks and prices as a quote
        order = {  # the order is the quote plus an id and a status
            "order_id": "ORD-" + str(state["next_order_number"]).zfill(4),  # like ORD-0001
            "status": "placed",  # every new order starts as placed
            **quote,  # copy in all the quote fields
        }  # end of the order
        self._change_stock(state, order["items"], -1)  # take the units out of stock
        state["next_order_number"] += 1  # next order gets the next number
        state["orders"].append(order)  # add to history
        self.store.save(state)  # write everything to the save file
        return order  # give the new order back

    def list_orders(self):  # every order in the order they were placed
        return self.store.load()["orders"]  # includes cancelled ones too

    def get_order(self, order_id):  # find one order by its id
        return self._find_order(self.store.load(), order_id)  # helper does the searching

    def cancel_order(self, order_id):  # cancels an order and puts stock back
        state = self.store.load()  # get the saved state
        order = self._find_order(state, order_id)  # errors if the id doesnt exist
        self._change_stock(state, order["items"], 1)  # put the units back
        order["status"] = "cancelled"  # mark it cancelled but keep it in history
        self.store.save(state)  # save the changes
        return order  # send back the cancelled order

    def _build_quote(self, state, customer_type, items, fulfillment):  # shared by quote and place_order so the rules only live once
        self._check_request(customer_type, items, fulfillment)  # make sure the basics are valid first
        lines = [self._price_line(state, item) for item in items]  # check and price every item
        subtotal = sum(line["line_total_cents"] for line in lines)  # add up all the lines
        discount = self._calculate_discount(customer_type, subtotal)  # student discount if any
        delivery = self._calculate_delivery(fulfillment, subtotal - discount)  # delivery fee if any
        return {  # everything the quote needs
            "customer_type": customer_type,  # regular or student
            "fulfillment": fulfillment,  # pickup or delivery
            "items": lines,  # the priced lines
            "subtotal_cents": subtotal,  # before discount
            "discount_cents": discount,  # student discount
            "delivery_cents": delivery,  # delivery fee
            "total_cents": subtotal - discount + delivery,  # final price
        }  # end of the quote

    def _check_request(self, customer_type, items, fulfillment):  # checks everything except the items themselves
        if customer_type not in ("regular", "student"):  # only these two types exist
            raise ValueError("Customer type must be regular or student.")  # bad customer type
        if fulfillment not in ("pickup", "delivery", "express"):  # only these three options exist
            raise ValueError("Fulfillment must be pickup, delivery or express.")  # bad fulfillment
        if not isinstance(items, list) or not items:  # needs a list with at least one item
            raise ValueError("An order must contain at least one item.")  # empty or wrong type

    def _price_line(self, state, item):  # checks one item and works out its price
        if not isinstance(item, dict):  # every item has to be a dictionary
            raise ValueError("Each item must contain a product_id and quantity.")  # wrong item shape
        product = self._find_product(state, item.get("product_id"))  # look up the product
        if product is None:  # product id doesnt exist
            raise ValueError("Unknown product.")  # fake product
        quantity = item.get("quantity")  # how many they want
        if type(quantity) is not int or quantity < MIN_QUANTITY or quantity > MAX_QUANTITY:  # whole number in range only
            raise ValueError("Quantity must be an integer from 1 to 99.")  # bad quantity
        if quantity > product["stock"]:  # not enough left for this line
            raise ValueError("Not enough stock for " + product["product_id"] + ".")  # out of stock
        return {  # the priced line
            "product_id": product["product_id"],  # product id
            "name": product["name"],  # product name
            "unit_price_cents": product["unit_price_cents"],  # price for one
            "quantity": quantity,  # how many
            "line_total_cents": product["unit_price_cents"] * quantity,  # price times quantity
        }  # end of the line

    def _calculate_discount(self, customer_type, subtotal):  # works out the student discount
        if customer_type == "student" and subtotal > STUDENT_DISCOUNT_MIN_CENTS:  # student discount check
            return (subtotal * STUDENT_DISCOUNT_PERCENT + 50) // 100  # adding 50 rounds half a cent up
        return 0  # everyone else gets nothing

    def _calculate_delivery(self, fulfillment, discounted_subtotal):  # works out the delivery fee
        if fulfillment == "express":  # express is a flat fee no matter the total
            return EXPRESS_FEE_CENTS  # never waived
        if fulfillment == "delivery" and discounted_subtotal < FREE_DELIVERY_MIN_CENTS:  # delivery under $100 costs extra
            return DELIVERY_FEE_CENTS  # charge the fee
        return 0  # pickup or big standard orders are free

    def _find_product(self, state, product_id):  # finds a product in the catalog
        for product in state["catalog"]:  # look through every product
            if product["product_id"] == product_id:  # found the one we want
                return product  # send it back
        return None  # no product with that id

    def _find_order(self, state, order_id):  # finds an order in the history
        for order in state["orders"]:  # look through each order
            if order["order_id"] == order_id:  # found it
                return order  # send it back
        raise ValueError("Unknown order: " + order_id)  # no order with that id

    def _change_stock(self, state, lines, direction):  # negative direction takes stock out and positve puts it back
        for line in lines:  # go through each item line
            product = self._find_product(state, line["product_id"])  # find the product
            product["stock"] += direction * line["quantity"]  # update the stock count
