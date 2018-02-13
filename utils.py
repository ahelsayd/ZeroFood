

def get_order_details(order_string):
    quantity = 1 
    price = order = None
    for word in order_string.split(' '):
        # quantity
        if word.endswith('x') and word[:word.find('x')].isdigit():
            quantity = int(word[:word.find('x')])
        # price
        elif word.startswith('$') and word[1:].isdigit():
            price = float(word[1:])
        # order
        else:
            order = word

    return quantity, order, price