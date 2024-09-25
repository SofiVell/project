import streamlit as st
import threading
import time
import asyncio
from functools import wraps
from sqlite3 import connect, OperationalError
from pymongo import MongoClient
import telebot

BOT_TOKEN = '7282273838:AAHy4bfEmj6JBu3Oj2c8LseGmmJcH2VSvVQ'
DB_PATH = r"C:\Users\user\Telebot.db"

user_roles = {}
user_states = {}

bot = telebot.TeleBot(BOT_TOKEN)

class Database:
    def __init__(self, role):
        self.conn = connect(r"C:\София back up\Professional\1-11\velychko\Telebot.db", timeout=10)
        self.cursor = self.conn.cursor()
        self.role = role

    def admin_only(method):
        @wraps(method)
        def wrapper(self, *args, **kwargs):
            if self.role != "admin":
                raise PermissionError("Тільки адміністратор може виконувати цю операцію.")
            return method(self, *args, **kwargs)
        return wrapper

    def get_tables(self):
        try:
            self.cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
            return [table[0] for table in self.cursor.fetchall()]
        except OperationalError as e:
            st.error(f"База даних заблокована: {e}")
            time.sleep(5)
            return self.get_tables()

    @admin_only
    def rename_table(self, old_name, new_name):
        try:
            self.cursor.execute(f"ALTER TABLE {old_name} RENAME TO {new_name}")
            self.conn.commit()
        except OperationalError:
            st.error("Таблиця зараз заблокована. Спробуйте пізніше.")
        
    @admin_only
    def drop_table(self, table_name):
        try:
            self.cursor.execute(f"DROP TABLE IF EXISTS {table_name}")
            self.conn.commit()
        except OperationalError:
            st.error("Таблиця заблокована. Спробуйте пізніше.")

    @admin_only
    def insert_data(self, table_name, data):
        try:
            placeholders = ', '.join(['?'] * len(data))
            query = f"INSERT INTO {table_name} VALUES ({placeholders})"
            self.cursor.execute(query, data)
            self.conn.commit()
        except OperationalError:
            st.error("Таблиця заблокована. Спробуйте пізніше.")

    def get_data(self, table_name, columns="*", where=None, order_by=None, limit=None):
        query = f"SELECT {columns} FROM {table_name}"
        if where:
            query += f" WHERE {where}"
        if order_by:
            query += f" ORDER BY {order_by}"
        if limit:
            query += f" LIMIT {limit}"
        try:
            self.cursor.execute(query)
            return self.cursor.fetchall()
        except OperationalError as e:
            st.error(f"База даних заблокована: {e}")
            time.sleep(5)
            return self.get_data(table_name, columns, where, order_by, limit)

    def close(self):
        self.conn.close()

class MongoDBManager:
    def __init__(self, db_name, role="user"):
        self.client = MongoClient("mongodb://localhost:27017/")
        self.db = self.client[db_name]
        self.role = role

    def check_admin(self):
        if self.role != "admin":
            raise PermissionError("Тільки адміністратор може виконувати цю операцію.")

    def get_tables(self):
        return self.db.list_collection_names()

    def rename_table(self, old_name, new_name):
        self.check_admin()
        self.db[old_name].rename(new_name)

    def drop_table(self, table_name):
        self.check_admin()
        self.db[table_name].drop()

    def insert_data(self, table_name, data):
        self.check_admin()
        return self.db[table_name].insert_one(data).inserted_id

    def get_data(self, table_name, query=None, projection=None, sort=None):
        query = query if query else {}
        if sort:
            return list(self.db[table_name].find(query, projection).sort(sort))
        return list(self.db[table_name].find(query, projection))

def check_password(password):
    admin_password = '8888'
    return password == admin_password

@bot.message_handler(commands=['start'])
def start_message(message):
    chat_id = message.chat.id
    reset_user_state(chat_id)
    bot.send_message(chat_id, "Привіт! Хочете увійти як адмін?")
    bot.send_message(chat_id, "Введіть пароль або введіть 'ні', щоб продовжити як користувач.")
    user_states[chat_id] = 'awaiting_password'

@bot.message_handler(func=lambda message: user_states.get(message.chat.id) == 'awaiting_password')
def handle_message(message):
    chat_id = message.chat.id
    
    if chat_id not in user_roles:
        if message.text == 'ні':
            user_roles[chat_id] = 'user'
            bot.send_message(chat_id, "Ви ввійшли як користувач.")
            show_menu(chat_id)
        elif check_password(message.text):
            user_roles[chat_id] = 'admin'
            bot.send_message(chat_id, "Ви ввійшли як адміністратор.")
            show_menu(chat_id)
        else:
            bot.send_message(chat_id, "Невірний пароль. Спробуйте ще раз.")
    else:
        role = user_roles[chat_id]
        db = Database(DB_PATH)

        if message.text == 'Переглянути таблиці':
            tables = db.get_tables()
            bot.send_message(chat_id, f"Таблиці: {', '.join(tables)}")
            reset_user_state(chat_id)
            show_menu(chat_id)
        elif message.text == 'Переглянути дані':
            bot.send_message(chat_id, "Введіть ім'я таблиці для перегляду даних.")
            user_states[chat_id] = 'awaiting_view_data'
        elif message.text == 'Додати дані':
            bot.send_message(chat_id, "Введіть ім'я таблиці та дані через кому. Кількість даних повинна відповідати кількості стовпців у таблиці.")
            user_states[chat_id] = 'awaiting_insert_data'
        elif message.text == 'Змінити назву таблиці' and role == 'admin':
            bot.send_message(chat_id, "Введіть стару назву таблиці і нову назву через кому.")
            user_states[chat_id] = 'awaiting_rename_table'
        elif message.text == 'Видалити таблицю' and role == 'admin':
            bot.send_message(chat_id, "Введіть ім'я таблиці для видалення.")
            user_states[chat_id] = 'awaiting_drop_table'
        else:
            bot.send_message(chat_id, "Невідома команда або недостатньо прав для виконання.")

def reset_user_state(chat_id):
    if chat_id in user_states:
        user_states[chat_id] = 'awaiting_password'
    

@bot.message_handler(func=lambda message: user_states.get(message.chat.id) == 'awaiting_view_data')
def handle_view_data(message):
    chat_id = message.chat.id
    db = Database(DB_PATH)
    try:
        table_name = message.text.strip()
        data = db.get_data(table_name)
        if data:
            formatted_data = "\n".join([str(row) for row in data])
            bot.send_message(chat_id, f"Дані з {table_name}:\n{formatted_data}")
        else:
            bot.send_message(chat_id, f"Таблиця {table_name} порожня або не існує.")
    except Exception as e:
        bot.send_message(chat_id, f"Помилка: {str(e)}")
    finally:
        db.close()
    reset_user_state(chat_id)
    show_menu(chat_id)

@bot.message_handler(func=lambda message: user_states.get(message.chat.id) == 'awaiting_insert_data'and user_roles.get(message.chat.id) == 'admin')
def handle_insert_data(message):
    chat_id = message.chat.id
    db = Database(DB_PATH)
    try:
        table_name, *data = message.text.split(',')
        db.insert_data(table_name.strip(), tuple(map(str.strip, data)))
        bot.send_message(chat_id, f"Дані додано до таблиці {table_name.strip()}.")
    except Exception as e:
        bot.send_message(chat_id, f"Помилка: {str(e)}")
    finally:
        db.close()
    reset_user_state(chat_id)
    show_menu(chat_id)

@bot.message_handler(func=lambda message: user_states.get(message.chat.id) == 'awaiting_rename_table' and user_roles.get(message.chat.id) == 'admin')
def handle_rename_table(message):
    chat_id = message.chat.id
    db = Database(DB_PATH)
    try:
        old_name, new_name = message.text.split(',')
        db.rename_table(old_name.strip(), new_name.strip())
        bot.send_message(chat_id, f"Таблицю {old_name.strip()} перейменовано на {new_name.strip()}.")
    except Exception as e:
        bot.send_message(chat_id, f"Помилка: {str(e)}")
    finally:
        db.close()
    reset_user_state(chat_id)
    show_menu(chat_id)


@bot.message_handler(func=lambda message: user_states.get(message.chat.id) == 'awaiting_drop_table' and user_roles.get(message.chat.id) == 'admin')
def handle_drop_table(message):
    chat_id = message.chat.id
    db = Database(DB_PATH)
    try:
        table_name = message.text.strip()
        db.drop_table(table_name)
        bot.send_message(chat_id, f"Таблицю {table_name} видалено.")
    except Exception as e:
        bot.send_message(chat_id, f"Помилка: {str(e)}")
    finally:
        db.close()
    reset_user_state(chat_id)
    show_menu(chat_id)


def show_menu(chat_id):
    role = user_roles.get(chat_id)
    
    markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
    
    if role == 'admin':
        markup.add('Переглянути дані', 'Переглянути таблиці', 'Додати дані', 'Змінити назву таблиці', 'Видалити таблицю')
    else:
        markup.add('Переглянути дані', 'Переглянути таблиці')
    
    bot.send_message(chat_id, "Виберіть опцію з меню:", reply_markup=markup)

def run_bot():
    bot.polling()


def authenticate(username, password):
    if username == "admin" and password == "8888":
        return "admin"
    else:
        return "user"

async def run_streamlit():
    st.set_page_config(page_title="Labten", page_icon=":database:", layout="centered") 

    st.title("Вітаємо на нашому сайті для роботи з базами даних! Увійдіть для початку роботи")

    st.sidebar.title("Вхід в систему")
    username = st.sidebar.text_input("Логін")
    password = st.sidebar.text_input("Пароль", type="password")
    if st.sidebar.button("Увійти"):
        role = authenticate(username, password)
        st.session_state['role'] = role
        st.sidebar.success(f"Вхід як {role}")

    if 'role' in st.session_state:
        role = st.session_state['role']
        if role == "admin":
            st.header("Адміністративний інтерфейс")
            db_choice = st.selectbox("Оберіть базу даних", ["SQL", "MongoDB"])

            if db_choice == "SQL":
                db = Database(role)
                tables = db.get_tables()
                st.write("Таблиці:", tables)

                action = st.selectbox("Оберіть дію", ["Переглянути дані", "Додати дані", "Видалити таблицю", "Перейменувати таблицю"])

                if action == "Додати дані":
                    table_name = st.selectbox("Оберіть таблицю для додавання даних", tables)
                    data = st.text_input("Введіть дані через кому (кількість стовпчиків має відповідати кількості колонок)")
                    if st.button("Додати дані"):
                        data_tuple = tuple(data.split(","))
                        db.insert_data(table_name, data_tuple)
                        st.success(f"Дані додано до таблиці '{table_name}'.")

                elif action == "Видалити таблицю":
                    table_name = st.selectbox("Оберіть таблицю для видалення", tables)
                    if st.button("Видалити таблицю"):
                        db.drop_table(table_name)
                        st.success(f"Таблицю '{table_name}' видалено.")

                elif action == "Перейменувати таблицю":
                    old_name = st.selectbox("Оберіть стару назву", tables)
                    new_name = st.text_input("Нова назва таблиці")
                    if st.button("Перейменувати"):
                        db.rename_table(old_name, new_name)
                        st.success(f"Таблицю '{old_name}' перейменовано на '{new_name}'.")

                elif action == "Переглянути дані":
                    table_name = st.selectbox("Оберіть таблицю для перегляду", tables)
                    if st.button("Показати дані"):
                        data = db.get_data(table_name)
                        st.write(data)
                db.close()

            elif db_choice == "MongoDB":
                db_manager = MongoDBManager("Labtwosixtwo", role)
                collections = db_manager.get_tables()
                st.write("Колекції:", collections)

                action = st.selectbox("Оберіть дію", ["Переглянути дані", "Додати дані", "Видалити колекцію", "Перейменувати колекцію"])

                if action == "Додати дані":
                    collection_name = st.selectbox("Оберіть колекцію для додавання даних", collections)
                    data = st.text_area("Введіть дані (формат JSON)")
                    if st.button("Додати дані"):
                        db_manager.insert_data(collection_name, eval(data))
                        st.success(f"Дані додано до колекції '{collection_name}'.")

                elif action == "Видалити колекцію":
                    collection_name = st.selectbox("Оберіть колекцію для видалення", collections)
                    if st.button("Видалити колекцію"):
                        db_manager.drop_table(collection_name)
                        st.success(f"Колекцію '{collection_name}' видалено.")

                elif action == "Перейменувати колекцію":
                    old_name = st.selectbox("Оберіть стару назву", collections)
                    new_name = st.text_input("Нова назва колекції")
                    if st.button("Перейменувати"):
                        db_manager.rename_table(old_name, new_name)
                        st.success(f"Колекцію '{old_name}' перейменовано на '{new_name}'.")

                elif action == "Переглянути дані":
                    collection_name = st.selectbox("Оберіть колекцію для перегляду", collections)
                    if st.button("Показати дані"):
                        data = db_manager.get_data(collection_name)
                        st.write(data)

        else:
            st.header("Користувацький інтерфейс")
            db_choice = st.selectbox("Оберіть базу даних", ["SQL", "MongoDB"])

            if db_choice == "SQL":
                db = Database(role)
                tables = db.get_tables()
                st.write("Таблиці:", tables)
                table_name = st.selectbox("Оберіть таблицю для перегляду", tables)
                if st.button("Показати дані"):
                    data = db.get_data(table_name)
                    st.write(data)
                db.close()

            elif db_choice == "MongoDB":
                db_manager = MongoDBManager("Labtwosixtwo", role)
                collections = db_manager.get_tables()
                st.write("Колекції:", collections)
                collection_name = st.selectbox("Оберіть колекцію для перегляду", collections)
                if st.button("Показати дані"):
                    data = db_manager.get_data(collection_name)
                    st.write(data)


def main():
    bot_thread = threading.Thread(target=run_bot)
    bot_thread.start()
    asyncio.run(run_streamlit())

if __name__ == "__main__":
    main()
