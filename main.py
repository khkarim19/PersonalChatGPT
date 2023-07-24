import openai as openai
import telebot
import json
import time
import sqlite3
from datetime import datetime

with open('config.json') as f:
    config = json.load(f)
openai.api_key = config["OpenAIToken"]
db_link = config["dblink"]


def create_table():
    conn = sqlite3.connect(db_link, check_same_thread=False)
    with conn:
        conn.execute("CREATE TABLE IF NOT EXISTS User (tg_id integer PRIMARY KEY,"
                     "nickname varchar,firstname varchar,lastname varchar);")

        conn.execute("CREATE TABLE IF NOT EXISTS Reply (id integer PRIMARY KEY AUTOINCREMENT,"
                     "answer text,time_of_reply integer);")

        conn.execute("CREATE TABLE IF NOT EXISTS Prompt (id integer PRIMARY KEY AUTOINCREMENT,"
                     "user_id integer,prompt text,date varchar,reply_id integer,"
                     "FOREIGN KEY (user_id) REFERENCES User,"
                     "FOREIGN KEY (reply_id) REFERENCES Reply);")
        conn.commit()


def write_to_db(message):
    conn = sqlite3.connect(db_link, check_same_thread=False)
    with conn:
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM User WHERE tg_id = ?", (message.chat.id,))
        existing_user = cur.fetchone()

        if existing_user is not None:
            conn.execute("INSERT INTO Prompt (user_id, prompt, date) VALUES(?, ?, ?);",
                         (message.chat.id, message.text, get_time()))
        else:
            conn.execute("INSERT INTO User (tg_id, nickname, firstname, lastname) VALUES (?, ?, ?, ?);",
                         (message.chat.id, message.chat.username, message.chat.first_name, message.chat.last_name))
            conn.execute("INSERT INTO Prompt (user_id, prompt, date) VALUES(?, ?, ?);",
                         (message.chat.id, message.text, get_time()))
            print(f"Добавил пользователя {message.chat.username} в базу данных")
        conn.commit()


def extract_messages(id):
    conn = sqlite3.connect(db_link, check_same_thread=False)
    cur = conn.cursor()
    cur.execute('SELECT prompt FROM Prompt INNER JOIN User ON prompt.user_id = User.tg_id WHERE User.tg_id = ? ORDER BY id   DESC LIMIT 5', (id,))
    messages = [result[0] for result in cur.fetchall()]
    print(messages)
    conn.close()
    return messages


def write_reply(reply, secs):
    conn = sqlite3.connect(db_link, check_same_thread=False)
    with conn:
        cur = conn.cursor()
        cur.execute('INSERT INTO Reply (answer, time_of_reply) VALUES (?, ?) RETURNING id;', (reply, secs))
        id_of_reply = cur.fetchone()
        conn.execute('UPDATE Prompt SET reply_id = ? WHERE id = (SELECT MAX(id) FROM Prompt);', id_of_reply)
        conn.commit()


def get_time():
    now = datetime.now()
    date = now.strftime("%d:%m:%Y %H:%M:%S")
    return date


def show_stat(stat_type):
    conn = sqlite3.connect(db_link, check_same_thread=False)
    cur = conn.cursor()
    if stat_type == 'stat':
        cur.execute("SELECT firstname FROM User")
        users = [result[0] for result in cur.fetchall()]
        result_string = '\n\n'.join(users)
    elif stat_type == 'last5':
        cur.execute("SELECT prompt FROM Prompt ORDER BY id DESC LIMIT 5;")
        users = [result[0] for result in cur.fetchall()]
        result_string = '\n\n'.join(users)
    return result_string


def ask_bot(message, prev_messages):
    messages = []
    if not prev_messages:
        all_messages = []
    else:
        all_messages = prev_messages.copy()
    all_messages.append(message)
    for m in all_messages:
        messages.append({"role": "user", "content": m})

    chat = openai.ChatCompletion.create(model="gpt-3.5-turbo", messages=messages)
    reply = chat.choices[0].message.content
    reply = reply.strip()
    return reply


token = config["TGToken"]
bot = telebot.TeleBot(token)


@bot.message_handler(commands=['start'])
def start_message(message):
    bot.send_message(message.chat.id, "Введите запрос")


@bot.message_handler(func=lambda message: True)
def echo_message(message):
    if (message.chat.id == 244287364) and (message.text == "stat"):
        bot.send_message(message.chat.id, show_stat(message.text))
    elif (message.chat.id == 244287364) and (message.text == "last5"):
        bot.send_message(message.chat.id, show_stat(message.text))
    else:
        start_time = datetime.now()
        msg = bot.send_message(message.chat.id, "Запрос принят!")
        time.sleep(1)
        write_to_db(message)
        userMessages = extract_messages(message.chat.id)
        bot.edit_message_text(chat_id=message.chat.id, message_id=msg.message_id, text="Запрос выполняется...")
        result = ask_bot(message.text, userMessages)
        end_time = datetime.now()
        elapsed = end_time - start_time
        elapsed_seconds = elapsed.total_seconds()
        bot.edit_message_text(chat_id=message.chat.id, message_id=msg.message_id, text=result)
        write_reply(result, elapsed_seconds)
        print(f"Пользователь {message.chat.first_name} ждал ответа {elapsed_seconds} секунд")


create_table()
bot.polling()
