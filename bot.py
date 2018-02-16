import yaml, os, mongoengine
from db import Session, Order
from telegram.ext import Updater, CommandHandler
from telegram import ParseMode
from jinja2 import Environment, FileSystemLoader
from functools import wraps

# tools

def session_check(func):
    @wraps(func)
    def decorator(*args, **kwargs):
        bot, update = args
        chat_id = str(update.message.chat_id)
        username = update.message.from_user.username        
        session = Session.get(chat_id=chat_id)
        
        if not session:
            update.message.reply_text('No active session, please start a new one')
            return

        kwargs.update(
            chat_id=chat_id, 
            username=username, 
            session=session
        )

        return func(*args, **kwargs)
    return decorator

def is_digit(string):
    try:
        float(string)
        return True
    except ValueError:
        return False

def extract_order_details(order_string):
        order = ''
        quantity = None
        for word in order_string.split(' '):
            if word.isdigit() and not quantity:
                quantity = int(word)
            else:
                if order:
                    order += ' '
                order += word

        quantity = quantity or 1

        return quantity, order

def render_template(template, **kwargs):
    return j2_env.get_template(template).render(**kwargs)

# handlers

def show_help(bot, update):
    """ Show help message when command /help is issued """

    chat_id = str(update.message.chat.id)
    msg = render_template('help.html')
    update.message.reply_text(msg, parse_mode=ParseMode.HTML)

def start_session(bot, update):
    """ Start new session when command /start is issued """

    chat_id = str(update.message.chat.id)
    username = update.message.from_user.username

    if Session.get(chat_id=chat_id):
        update.message.reply_text('A session is already started')
        return 
    
    session = Session(chat_id=chat_id, created_by=username)
    session.save()
    
    update.message.reply_text('New session is started')

@session_check
def end_session(bot, update, **kwargs):
    """ End active session when command /end is issued """

    session = kwargs.get('session')
    session.delete()
    update.message.reply_text('Session is ended')

@session_check
def set_price(bot, update, **kwargs):
    """ Set order price when command /set <order> = <price> is issued """

    session = kwargs.get('session')
    orders = update.message.text.replace('/set ', '').split(',')

    for order in orders:
        order, price = [x.strip() for x in order.split('=')]
        if is_digit(price):
            price = abs(float(price))
            Order.objects(session=session, order=order).update(price=price)

@session_check
def set_service(bot, update, **kwargs):
    """ Set service when command /service is issued """

    session = kwargs.get('session')
    service = update.message.text.replace('/service ', '').strip()
    if is_digit(service):
        service = abs(float(service))
        session.update(service=service)

@session_check
def set_tax(bot, update, **kwargs):
    """ Set tax when command /tax is issued """

    session = kwargs.get('session')
    tax = update.message.text.replace('/tax ', '').strip()
    if is_digit(tax):
        tax = abs(float(tax))
        session.update(tax=tax)
        
@session_check
def my_orders(bot, update, **kwargs):
    """ List user's orders when command /me is issued """

    session = kwargs.get('session')
    username = kwargs.get('username')

    orders = Order.objects.filter(session=session, username=username)
    msg = render_template('me.html', orders=orders, username=username)
    update.message.reply_text(msg, parse_mode=ParseMode.HTML)

@session_check
def all_orders(bot, update, **kwargs):
    """ List all orders when command /all is issued """
    
    chat_id = kwargs.get('chat_id')
    session = kwargs.get('session')
    username = kwargs.get('username')

    pipeline = [
        {'$match': {
            'session':session.id
            }
        },
        {
            '$group':{
                '_id':{'order':'$order'}, 
                'quantity':{'$sum': "$quantity"}, 
                'price':{'$first':'$price'}, 
                'users':{'$push':{'username':'$username', 'quantity':'$quantity'}}
            }
        }
    ]

    orders = Order.objects.aggregate(*pipeline)
    msg = render_template('all.html', orders=orders)
    update.message.reply_text(msg, parse_mode=ParseMode.HTML)

@session_check
def bill(bot, update, **kwargs):
    """ Show bill when command /bill is issued """
    
    chat_id = kwargs.get('chat_id')
    session = kwargs.get('session')

    normalized_service = 0
    normalized_tax = 0
    service = session.service
    tax = session.tax

    number_of_users = len(Order.objects.distinct('username'))

    if number_of_users:
        normalized_service = service / number_of_users
        normalized_tax = tax / number_of_users

    pipeline = [
        {
            '$match': {'session': session.id}
        },
        {
            '$group':{
                '_id':{'username':'$username'},
                'net':{'$sum':{'$multiply':["$price", "$quantity"]}},
            }
        },
        {
            '$addFields':{
                'total':{'$add':['$net', normalized_service, normalized_tax]}
            }
        }
    ]

    unknown_orders = Order.objects(price=None)
    bill = Order.objects.aggregate(*pipeline)

    msg = render_template(
        'bill.html',
        bill=bill, 
        unknown_orders=unknown_orders,
        service=service,
        tax=tax,
    )
    update.message.reply_text(msg, parse_mode=ParseMode.HTML)

@session_check
def add_order(bot, update, **kwargs):
    """ Add new order(s) when command /add is issued """
    
    chat_id = kwargs.get('chat_id')
    session = kwargs.get('session')
    username = kwargs.get('username')

    if update.message.reply_to_message:
        payload = update.message.reply_to_message.text.replace('/add', '')
    else:
        payload = update.message.text.replace('/add', '')

    orders = payload.split('+')

    for order_string in orders:
        quantity, order = extract_order_details(order_string.strip())

        if not order:
            update.message.reply_text('Invalid order')
            return
        
        # check if the order exists in user's order
        exists_order = Order.get(session=session, 
                                 username=username, 
                                 order=order)

        # if the order exists in user's order, increment quantity
        if exists_order:
            exists_order.update(inc__quantity=quantity)
        
        # else, record the new order
        else: 
            order_object = Order(session=session, 
                                 username=username, 
                                 quantity=quantity, 
                                 order=order)
            order_object.save()

@session_check
def delete_order(bot, update, **kwargs):
    """ Delete order(s) when command /delete is issued """
    
    session = kwargs.get('session')
    username = kwargs.get('username')
    
    if update.message.reply_to_message:
        payload = update.message.reply_to_message.text.replace('/add', '')
    else:
        payload = update.message.text.replace('/delete', '')

    orders = payload.split('+')

    for order_string in orders:
        quantity, order = extract_order_details(order_string.strip())
        quantity = abs(int(quantity))

        order_obj = Order.get(session=session, 
                              username=username, 
                              order=order)
                              
        if order_obj:
            if quantity >= order_obj.quantity:
                order_obj.delete()
            else:
                order_obj.update(inc__quantity= -quantity)

def main():    
    
    updater = Updater(config['telegram']['token'])

    dp = updater.dispatcher

    # handlers

    dp.add_handler(CommandHandler('start', start_session))
    dp.add_handler(CommandHandler('end', end_session))
    dp.add_handler(CommandHandler('add', add_order))
    dp.add_handler(CommandHandler('delete', delete_order))
    dp.add_handler(CommandHandler('set', set_price))
    dp.add_handler(CommandHandler('service', set_service))
    dp.add_handler(CommandHandler('tax', set_tax))
    dp.add_handler(CommandHandler('me', my_orders))
    dp.add_handler(CommandHandler('all', all_orders))
    dp.add_handler(CommandHandler('bill', bill))
    dp.add_handler(CommandHandler('help', show_help))

    updater.start_polling()
    
    updater.idle()

if __name__ == '__main__':
    
     # load configrations 
    with open('config.yaml', 'r') as config_file:
        config = yaml.load(config_file)

    # connect to db
    mongoengine.connect(** config['database'])

    # load templates
    j2_env = Environment(loader=FileSystemLoader(searchpath='./templates'), trim_blocks=True)

    # start
    main()

    