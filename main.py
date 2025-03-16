import telebot
import requests
import random
from datetime import datetime, timedelta
from googletrans import Translator
from telebot import types
from dotenv import load_dotenv
import os
import json
from flask import Flask, request

load_dotenv()

TOKEN = os.getenv("TOKEN")

translator = Translator()
bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

@app.route('/' + TOKEN, methods=['POST'])
def get_message():
    bot.process_new_updates([telebot.types.Update.de_json(request.stream.read().decode("utf-8"))])
    return "OK", 200

@app.route('/')
def set_webhook():
    bot.remove_webhook()
    bot.set_webhook(url='https://your-app-name.onrender.com/' + TOKEN)
    return "Webhook set!", 200

DAILY_LIMIT = 20
USER_DATA_FILE = "user_data.json"
JOKES_DATA_FILE = "jokes_data.json"

# Завантаження даних
def load_data(file):
    try:
        with open(file, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

# Збереження даних
def save_data(file, data):
    with open(file, "w") as f:
        json.dump(data, f, indent=4)

user_data = load_data(USER_DATA_FILE)
joke_ratings = load_data(JOKES_DATA_FILE)

# Скидання лічильників
def reset_counters(user_id):
    current_time = datetime.now()
    user = user_data.get(str(user_id), {"memes": 0, "jokes": 0, "last_reset": current_time.isoformat(), "language": "uk"})
    
    last_reset = datetime.fromisoformat(user["last_reset"])
    if current_time - last_reset > timedelta(days=1):
        user["memes"] = 0
        user["jokes"] = 0
        user["last_reset"] = current_time.isoformat()

    user_data[str(user_id)] = user
    save_data(USER_DATA_FILE, user_data)

# Команда /start
@bot.message_handler(commands=['start'])
def start(message):
    user_id = message.chat.id
    if str(user_id) not in user_data:
        user_data[str(user_id)] = {"memes": 0, "jokes": 0, "last_reset": datetime.now().isoformat(), "language": "uk"}
        save_data(USER_DATA_FILE, user_data)

    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(types.KeyboardButton("Українська"), types.KeyboardButton("English"))
    bot.send_message(user_id, "Виберіть мову / Choose language", reply_markup=markup)

    help_text = (
        "/joke - Отримати жарт\n"
        "/top_jokes - Топ 10 жартів\n"
        "/check - Перевірити ліміти\n"
        "/help - Допомога"
    )
    bot.send_message(user_id, help_text)
# Обробка вибору мови
@bot.message_handler(func=lambda message: message.text in ["Українська", "English"])
def set_language(message):
    user_id = message.chat.id
    language = "uk" if message.text == "Українська" else "en"
    user_data[str(user_id)]["language"] = language
    save_data(USER_DATA_FILE, user_data)
    bot.send_message(user_id, "Мову змінено!" if language == "uk" else "Language changed!")

# Команда /check – перевірка залишку мемів і жартів
@bot.message_handler(commands=['check'])
def check(message):
    user_id = message.chat.id
    reset_counters(user_id)

    user = user_data[str(user_id)]
    memes_left = DAILY_LIMIT - user["memes"]
    jokes_left = DAILY_LIMIT - user["jokes"]
    
    language = user.get("language", "uk")
    text = (f"📊 *Ваш ліміт на сьогодні:*\nЖарти: {jokes_left}/{DAILY_LIMIT}" 
            if language == "uk" 
            else f"📊 *Your limit today:*\nJokes: {jokes_left}/{DAILY_LIMIT}")

    bot.send_message(user_id, text, parse_mode="Markdown")

# Команда /joke
@bot.message_handler(commands=['joke'])
def send_joke(message):
    user_id = message.chat.id
    reset_counters(user_id)
    
    user = user_data[str(user_id)]
    if user["jokes"] >= DAILY_LIMIT:
        bot.reply_to(message, "Вибачте, ви досягли ліміту жартів на сьогодні!")
        return

    try:
        response = requests.get('https://official-joke-api.appspot.com/random_joke')
        if response.status_code == 200:
            joke = response.json()
            setup, punchline = joke.get('setup', 'Жарт не знайдено.'), joke.get('punchline', 'Фінал жарту не знайдено.')

            language = user.get("language", "uk")
            if language == "uk":
                setup = translator.translate(setup, src='en', dest='uk').text
                punchline = translator.translate(punchline, src='en', dest='uk').text

            joke_id = str(random.randint(100000, 999999))
            joke_ratings[joke_id] = {"setup": setup, "punchline": punchline, "likes": 0, "dislikes": 0}
            save_data(JOKES_DATA_FILE, joke_ratings)

            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("👍", callback_data=f"like_{joke_id}"),
                       types.InlineKeyboardButton("👎", callback_data=f"dislike_{joke_id}"))

            bot.reply_to(message, f"😂 *Жарт:*\n{setup}\n\n🤣 *Фінал:*\n{punchline}", parse_mode='Markdown', reply_markup=markup)

            user["jokes"] += 1
            save_data(USER_DATA_FILE, user_data)
        else:
            bot.reply_to(message, "Не вдалося отримати жарт.")
    except Exception as e:
        bot.reply_to(message, f"Помилка: {e}")

# Обробка оцінок
@bot.callback_query_handler(func=lambda call: call.data.startswith("like_") or call.data.startswith("dislike_"))
def handle_joke_rating(call):
    joke_id = call.data.split("_")[1]
    if joke_id in joke_ratings:
        if call.data.startswith("like_"):
            joke_ratings[joke_id]["likes"] += 1
        else:
            joke_ratings[joke_id]["dislikes"] += 1

        save_data(JOKES_DATA_FILE, joke_ratings)

        bot.answer_callback_query(call.id, "Оцінка врахована!")
        bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)

        joke = joke_ratings[joke_id]
        bot.send_message(call.message.chat.id, f"Жарт оновлено:\n👍 {joke['likes']} | 👎 {joke['dislikes']}")

# Команда /top_jokes
@bot.message_handler(commands=['top_jokes'])
def top_jokes(message):
    if not joke_ratings:
        bot.send_message(message.chat.id, "Ще немає оцінених жартів!")
        return

    sorted_jokes = sorted(joke_ratings.items(), key=lambda x: x[1]["likes"], reverse=True)[:10]
    result = "🏆 *Топ 10 жартів:*\n"
    
    for i, (joke_id, joke) in enumerate(sorted_jokes, 1):
        result += f"{i}. 👍 {joke['likes']} | 👎 {joke['dislikes']}\n{joke['setup']} - {joke['punchline']}\n\n"

    bot.send_message(message.chat.id, result, parse_mode="Markdown")

# Команда /help
@bot.message_handler(commands=['help'])
def help(message):
    bot.send_message(message.chat.id, "/joke - Отримати жарт\n/top_jokes - Топ 10 жартів\n/check - Перевірити ліміти\n/help - Допомога")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
