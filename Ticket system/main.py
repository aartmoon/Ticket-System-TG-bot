import random
import sqlite3
import smtplib
import pandas as pd
from telebot import TeleBot, types
from telebot.types import LabeledPrice
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from config import *



class DBManager:
    DB_NAME = 'data.sql'

    @classmethod
    def init_db(cls):
        with sqlite3.connect(cls.DB_NAME) as conn:
            cur = conn.cursor()
            cur.execute('''CREATE TABLE IF NOT EXISTS users (
                            name VARCHAR(50),
                            pass VARCHAR(50),
                            promo VARCHAR(50),
                            count INTEGER,
                            price INTEGER,
                            event VARCHAR(50)
                        )''')
            conn.commit()

    @classmethod
    def add_ticket(cls, user_name, ticket_code, promo, price, event):
        with sqlite3.connect(cls.DB_NAME) as conn:
            cur = conn.cursor()
            cur.execute("INSERT INTO users (name, pass, promo, count, price, event) VALUES (?, ?, ?, ?, ?, ?)",
                        (user_name, ticket_code, promo, 0, price, event))
            conn.commit()

    @classmethod
    def get_tickets_by_user(cls, user_name):
        with sqlite3.connect(cls.DB_NAME) as conn:
            cur = conn.cursor()
            cur.execute("SELECT pass, event FROM users WHERE name = ?", (user_name,))
            return cur.fetchall()

    @classmethod
    def get_all_tickets(cls):
        with sqlite3.connect(cls.DB_NAME) as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM users")
            return cur.fetchall()

    @classmethod
    def update_ticket_usage(cls, ticket_code, new_count):
        with sqlite3.connect(cls.DB_NAME) as conn:
            cur = conn.cursor()
            cur.execute("UPDATE users SET count = ? WHERE pass = ?", (new_count, ticket_code))
            conn.commit()

    @classmethod
    def reset_ticket_usage(cls, ticket_code):
        with sqlite3.connect(cls.DB_NAME) as conn:
            cur = conn.cursor()
            cur.execute("UPDATE users SET count = 0 WHERE pass = ?", (ticket_code,))
            conn.commit()

    @classmethod
    def drop_and_recreate_table(cls):
        with sqlite3.connect(cls.DB_NAME) as conn:
            cur = conn.cursor()
            cur.execute("DROP TABLE IF EXISTS users")
            cur.execute('''CREATE TABLE IF NOT EXISTS users (
                            name VARCHAR(50),
                            pass VARCHAR(50),
                            promo VARCHAR(50),
                            count INTEGER,
                            price INTEGER,
                            event VARCHAR(50)
                        )''')
            conn.commit()


DBManager.init_db()

def delete_last_messages(bot: TeleBot, chat_id: int, message_ids: list):
    for msg_id in message_ids:
        try:
            bot.delete_message(chat_id, msg_id)
        except Exception:
            pass

def generate_ticket(is_gold: bool) -> str:
    prefix = 'G' if is_gold else 'S'
    return f"{prefix}{int(random.uniform(100_000, 999_999))}"


def safe_generate_ticket(is_gold: bool, user_name: str, promo: str, price: int, event: str) -> str:
    ticket_code = generate_ticket(is_gold)
    # if dublicate
    existing = DBManager.get_tickets_by_user(user_name)
    if any(ticket_code in ticket for ticket in existing):
        ticket_code = generate_ticket(is_gold)
    DBManager.add_ticket(user_name, ticket_code, promo, price, event)
    return ticket_code

user_id = None
admin_mode = False
current_promo = ''
current_event = ''
current_price = 0
current_ticket_type_gold = True # true for gold

bot = TeleBot(TOKEN)

@bot.message_handler(commands=['start'])
def command_start(message):
    global user_id
    user_id = message.from_user.username
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton('Купить билет', callback_data='quest_buy'),
        types.InlineKeyboardButton('FAQ', callback_data='quest_faq'),
        types.InlineKeyboardButton('Ввести промокод', callback_data='quest_promo'),
        types.InlineKeyboardButton('Мои билеты', callback_data='quest_tickets')
    )
    bot.send_message(message.chat.id,
                     "Привет!\nЯ бот для покупки билетов.\nИспользуй меню ниже!",
                     reply_markup=markup)
    delete_last_messages(bot, message.chat.id, [message.id])


@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    global current_event
    if call.message:
        if call.data == 'quest_buy':
            events_msg = "Выбери мероприятие:\n"
            for idx, event in enumerate(EVENTS):
                if event:
                    events_msg += f"\n/{event}\n{EVENT_DESCRIPTIONS[idx]}\n"
            events_msg += "\n/start - в главное меню"
            bot.send_message(call.message.chat.id, events_msg)
        elif call.data == 'quest_faq':
            bot.send_message(call.message.chat.id,
                             f"{FAQ_DEFAULT}\n\n||@SunsTicket||\n\n/start - в главное меню",
                             parse_mode='MarkdownV2')
        elif call.data == 'quest_promo':
            bot.send_message(call.message.chat.id, "Введи промокод\n/start - в главное меню")
        elif call.data == 'quest_tickets':
            tickets = DBManager.get_tickets_by_user(user_id)
            if tickets:
                info = "\n".join([f"Билет: {t[0]}, Мероприятие: {t[1]}" for t in tickets])
                bot.send_message(call.message.chat.id, info)
                bot.send_message(call.message.chat.id,
                                 f"Количество билетов: {len(tickets)}\n/start - в главное меню")
            else:
                bot.send_message(call.message.chat.id, "У тебя нет билетов.\n/start - в главное меню")
        delete_last_messages(bot, call.message.chat.id, [call.message.id])


@bot.message_handler(commands=['buy_standart'])
def buy_standard(message):
    delete_last_messages(bot, message.chat.id, [message.id])
    global current_price, current_promo, current_ticket_type_gold
    current_ticket_type_gold = False
    current_price = PRICE_STANDARD - (DISCOUNT if current_promo else 0)
    prices = [LabeledPrice(label='Билет', amount=current_price), LabeledPrice(label='STS', amount=0)]
    bot.send_invoice(message.chat.id,
                     title='Итого:',
                     description='Оплати, чтобы получить билет!',
                     invoice_payload='Ticket',
                     provider_token=PROVIDER_TOKEN,
                     currency='rub',
                     prices=prices,
                     start_parameter='213123')
    msg = ("Цена с учётом промокода" if current_promo
           else "Промокод не активирован, если он у тебя есть, напиши его в чат")
    bot.send_message(message.chat.id, f"{msg}\n/start - в главное меню")


@bot.message_handler(commands=['buy_gold'])
def buy_gold(message):
    delete_last_messages(bot, message.chat.id, [message.id])
    global current_price, current_promo, current_ticket_type_gold
    current_ticket_type_gold = True
    current_price = PRICE_GOLD - (DISCOUNT if current_promo else 0)
    prices = [LabeledPrice(label='Билет GOLD', amount=current_price), LabeledPrice(label='STS', amount=0)]
    bot.send_invoice(message.chat.id,
                     title='Итого:',
                     description='Оплати, чтобы получить билет!',
                     invoice_payload='HAPPY FRIDAYS COUPON',
                     provider_token=PROVIDER_TOKEN,
                     currency='rub',
                     prices=prices,
                     start_parameter='213123')
    msg = ("Цена с учётом промокода" if current_promo
           else "Промокод не активирован, если он у тебя есть, напиши его в чат")
    bot.send_message(message.chat.id, f"{msg}\n/start - в главное меню")


@bot.pre_checkout_query_handler(func=lambda query: True)
def checkout(pre_checkout_query):
    bot.answer_pre_checkout_query(pre_checkout_query.id,
                                  ok=True,
                                  error_message="Ошибка, проверь реквизиты\n/start - в главное меню")


@bot.message_handler(content_types=['successful_payment'])
def payment_success(message):
    global current_ticket_type_gold, current_promo, current_price, current_event, user_id
    ticket = safe_generate_ticket(current_ticket_type_gold, user_id, current_promo, current_price, current_event)
    bot.send_message(message.chat.id,
                     f"Вот твой билет:\n\n`{ticket}`\n\nСпасибо за покупку!\n/start - в главное меню",
                     parse_mode='Markdown')

    bot.send_message(408098978, f"Купили билет, @{user_id}")
    delete_last_messages(bot, message.chat.id, [message.id])


# lalala
@bot.message_handler(content_types=['text'])
def text_handler(message):
    global current_promo, admin_mode, current_event, EVENTS, EVENT_DESCRIPTIONS, FAQ_DEFAULT, PROMOCODES, PRICE_STANDARD, PRICE_GOLD, DISCOUNT
    text = message.text.strip()

    if message.chat.type != 'private':
        return

    #if event
    if text.startswith("/") and text[1:] in EVENTS:
        return


    if text in PROMOCODES:
        current_promo = text
        bot.send_message(message.chat.id,
                         "Промокод активирован\nВведи '0', чтобы обнулить промо\n/start - в главное меню")
    elif text == '0':
        current_promo = ''
        bot.send_message(message.chat.id, "Промокод обнулён\n/start - в главное меню")

    #admin
    elif text == 'Parol1234':
        admin_mode = True
        bot.send_message(message.chat.id, "Доступ АДМИНА выдан\n/start - в главное меню")

    elif admin_mode:
        if text.startswith('edit des'):
            try:
                idx = int(text[9]) - 1
                new_description = text[11:]
                EVENT_DESCRIPTIONS[idx] = new_description
                bot.send_message(message.chat.id, "Описание изменено\n/start - в главное меню")
            except Exception:
                bot.send_message(message.chat.id, "Ошибка ввода для edit des")
        elif text == 'data':
            users = DBManager.get_all_tickets()
            if users:
                count = len(users)
                total = sum(user[4] for user in users)
                info = "\n".join([f"{idx + 1}. {u[0]} | {u[1]} | {u[2]} | {u[3]} | {u[4]}р. | {u[5]}"
                                  for idx, u in enumerate(users)])
                bot.send_message(message.chat.id,
                                 f"Количество билетов: {count}, Общая цена: {total}р.\n/start - в главное меню")

                # to excel
                df = pd.DataFrame(users, columns=['name', 'pass', 'promo', 'count', 'price', 'event'])
                excel_file = 'datae.xlsx'
                df.to_excel(excel_file, index=False)
                with open(excel_file, 'rb') as f:
                    bot.send_document(message.chat.id, f)
            else:
                bot.send_message(message.chat.id, "Таблица пуста\n/start - в главное меню")
        elif text == 'delete':
            DBManager.drop_and_recreate_table()
            bot.send_message(message.chat.id, "Таблица пересоздана\n/start - в главное меню")
        elif text.startswith('s '):
            # s G1234567
            ticket_code = text[2:10]
            tickets = DBManager.get_tickets_by_user(user_id)

            if not any(ticket_code in t for t in tickets):
                bot.send_message(message.chat.id, "НЕТ ТАКОГО БИЛЕТА")
            else:

                DBManager.update_ticket_usage(ticket_code, 1)
                bot.send_message(message.chat.id, "Билет обновлён")

        elif text.startswith('p '):
            promo_code = text[2:]
            # promo checker
            count = sum(1 for t in DBManager.get_all_tickets() if promo_code in t)
            if count == 0:
                bot.send_message(message.chat.id, "НЕ ИСПОЛЬЗОВАН")
            else:
                bot.send_message(message.chat.id, f"Промо использован {count} раз(а)\n/start - в главное меню")
        elif text.startswith('n '):
            ticket_code = text[2:10]
            tickets = DBManager.get_tickets_by_user(user_id)
            if not any(ticket_code in t for t in tickets):
                bot.send_message(message.chat.id, "НЕТ ТАКОГО БИЛЕТА")
            else:
                DBManager.reset_ticket_usage(ticket_code)
                bot.send_message(message.chat.id, "БИЛЕТ МОЖНО ИСПОЛЬЗОВАТЬ ЗАНОВО\n/start - в главное меню")
        elif text.startswith('edit event'):
            try:
                idx = int(text[11]) - 1
                new_event = text[13:]
                EVENTS[idx] = new_event
                bot.send_message(message.chat.id, "Мероприятие изменено\n/start - в главное меню")
            except Exception:
                bot.send_message(message.chat.id, "Ошибка ввода для edit event")
        elif text.startswith('add promo'):
            new_promo = text[10:]
            PROMOCODES.add(new_promo)
            bot.send_message(message.chat.id, f"Создан промокод {new_promo}\n/start - в главное меню")
        elif text == 'promocodes':
            promos = "\n".join(PROMOCODES)
            bot.send_message(message.chat.id, f"Промокоды:\n{promos}")
        elif text.startswith('price standard'):
            try:
                new_price = int(text[15:])
                global PRICE_STANDARD
                PRICE_STANDARD = new_price
                bot.send_message(message.chat.id, f"Успех, новая цена: {new_price // 100}\n/start - в главное меню")
            except Exception:
                bot.send_message(message.chat.id, "Неверное значение. Пример: price standard 35000")
        elif text.startswith('price gold'):
            try:
                new_price = int(text[11:])
                global PRICE_GOLD
                PRICE_GOLD = new_price
                bot.send_message(message.chat.id, f"Успех, новая цена: {new_price // 100}\n/start - в главное меню")
            except Exception:
                bot.send_message(message.chat.id, "Неверное значение. Пример: price gold 35000")
        elif text.startswith('faq'):
            FAQ_DEFAULT = text[4:]
            bot.send_message(message.chat.id, "FAQ обновлён\n/start - в главное меню")
        elif text.startswith('skidka'):
            try:
                global DISCOUNT
                DISCOUNT = int(text[7:])
                bot.send_message(message.chat.id, "Скидка обновлена\n/start - в главное меню")
            except Exception:
                bot.send_message(message.chat.id, "Ошибка ввода для skidka")
        elif text == 'events':
            events_list = "\n".join([f"{idx + 1}. {event}" for idx, event in enumerate(EVENTS) if event])
            bot.send_message(message.chat.id, f"Список мероприятий:\n{events_list}\n/start - в главное меню")

        elif any(text == f"/{event}" for event in EVENTS if event):
            current_event = text[1:]
            bot.send_message(message.chat.id,
                             "Вводи /buy_standart для покупки стандарта или /buy_gold для GOLD билета\n/start - в главное меню")
        else:
            bot.send_message(message.chat.id, "Не понял тебя\n/start - в главное меню")
    delete_last_messages(bot, message.chat.id, [message.id])


if __name__ == '__main__':
    bot.infinity_polling(skip_pending=True)