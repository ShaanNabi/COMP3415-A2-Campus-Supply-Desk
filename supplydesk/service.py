"""Operations used by the command-line order desk."""

from supplydesk.storage import JsonStore  # handles loading and saving the json file

MIN_QUANTITY = 1  # smallest amount you can order of one item
MAX_QUANTITY = 99  # biggest amount you can order of one item
STUDENT_DISCOUNT_MIN_CENTS = 5000  # subtotal needed for the student discont
STUDENT_DISCOUNT_PERCENT = 10  # students get 10 percent off
DELIVERY_FEE_CENTS = 600  # delivery costs $6
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
        }  # end of the dictionary
        for line in order["items"]:  # go through each item line
            for product in state["catalog"]:  # find the matching product
                if product["product_id"] == line["product_id"]:  # same product id
                    product["stock"] -= line["quantity"]  # take the units out of stock
        state["next_order_number"] += 1  # next order gets the next number
        state["orders"].append(order)  # add to history
        self.store.save(state)  # write everything to the save file
        return order  # give the new order back

    def list_orders(self):  # every order in the order they were placed
        return self.store.load()["orders"]  # includes cancelled ones too

    def get_order(self, order_id):  # find one order by its id
        state = self.store.load()  # get the saved orders
        for order in state["orders"]:  # look through each order
            if order["order_id"] == order_id:  # found it
                return order  # send it back
        raise ValueError("Unknown order: " + order_id)  # no order with that id

    def cancel_order(self, order_id):  # cancels an order and puts stock back
        state = self.store.load()  # get the saved state
        order = None  # will hold the order if we find it
        for candidate in state["orders"]:  # look through each order
            if candidate["order_id"] == order_id:  # found the right one
                order = candidate  # keep it
                break  # stop looking
        if order is None:  # never found it
            raise ValueError("Unknown order: " + order_id)  # unknown id is an error
        for line in order["items"]:  # go through each item in the order
            for product in state["catalog"]:  # find the matching product
                if product["product_id"] == line["product_id"]:  # same product id
                    product["stock"] += line["quantity"]  # put the units back
        order["status"] = "cancelled"  # mark it cancelled but keep it in history
        self.store.save(state)  # save the changes
        return order  # send back the cancelled order

    def _build_quote(self, state, customer_type, items, fulfillment):  # shared by quote and place_order so the rules only live once
        if customer_type not in ("regular", "student"):  # only these two types exist
            raise ValueError("Customer type must be regular or student.")  # reject the request
        if fulfillment not in ("pickup", "delivery"):  # only these two options exist
            raise ValueError("Fulfillment must be pickup or delivery.")  # reject the request
        if not isinstance(items, list) or not items:  # needs a list with at least one item
            raise ValueError("An order must contain at least one item.")  # reject the request
        lines = []  # the priced item lines
        subtotal = 0  # running total before discount
        for item in items:  # check and price each item
            if not isinstance(item, dict):  # every item has to be a dictionary
                raise ValueError("Each item must contain a product_id and quantity.")  # reject the request
            product = None  # will hold the product if we find it
            for candidate in state["catalog"]:  # look through the catalog
                if candidate["product_id"] == item.get("product_id"):  # found the product
                    product = candidate  # keep it
                    break  # stop looking
            if product is None:  # product id doesnt exist
                raise ValueError("Unknown product.")  # reject the request
            quantity = item.get("quantity")  # how many they want
            if type(quantity) is not int or quantity < MIN_QUANTITY or quantity > MAX_QUANTITY:  # whole number in range only
                raise ValueError("Quantity must be an integer from 1 to 99.")  # reject the request
            if quantity > product["stock"]:  # not enough left
                raise ValueError("Not enough stock for " + product["product_id"] + ".")  # reject the request
            line_total = product["unit_price_cents"] * quantity  # price for this line
            subtotal += line_total  # add it to the subtotal
            lines.append({  # save the line details
                "product_id": product["product_id"],  # product id
                "name": product["name"],  # product name
                "unit_price_cents": product["unit_price_cents"],  # price for one
                "quantity": quantity,  # how many
                "line_total_cents": line_total,  # price times quantity
            })  # end of the line
        discount = 0  # no discount by default
        if customer_type == "student" and subtotal > STUDENT_DISCOUNT_MIN_CENTS:  # student discount check
            discount = (subtotal * STUDENT_DISCOUNT_PERCENT + 50) // 100  # adding 50 rounds half a cent up
        delivery = 0  # pickup is free
        if fulfillment == "delivery" and subtotal - discount < FREE_DELIVERY_MIN_CENTS:  # delivery under $100 costs extra
            delivery = DELIVERY_FEE_CENTS  # add the delivery fee
        return {  # everything the quote needs
            "customer_type": customer_type,  # regular or student
            "fulfillment": fulfillment,  # pickup or delivery
            "items": lines,  # the priced lines
            "subtotal_cents": subtotal,  # before discount
            "discount_cents": discount,  # student discount
            "delivery_cents": delivery,  # delivery fee
            "total_cents": subtotal - discount + delivery,  # final price
        }  # end of the dictionary