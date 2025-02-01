from flask import Flask, jsonify
from yandex_music import Client
from pymongo import MongoClient
import os
import logging
import base64
from dotenv import load_dotenv
from flask_cors import CORS
from flask import request


# Загружаем переменные окружения из файла .env
load_dotenv()

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("app.log"),  # Логи в файл
        logging.StreamHandler()  # Логи в консоль
    ]
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

CORS(app)


# Получаем переменные окружения
YANDEX_MUSIC_TOKEN = os.getenv('YANDEX_MUSIC_TOKEN')
MONGO_URI = os.getenv('MONGO_URI', 'mongodb://localhost:27017/')  # URI MongoDB
DB_NAME = os.getenv('DB_NAME', 'music_db')  # Название базы данных

# Подключение к MongoDB
try:
    mongo_client = MongoClient(MONGO_URI)
    db = mongo_client[DB_NAME]
    tracks_collection = db['tracks']
    logger.info("Успешное подключение к MongoDB.")
except Exception as e:
    logger.error(f"Ошибка подключения к MongoDB: {e}")
    raise


@app.before_request
def log_request_info():
    from flask import request
    logger.info(f"Получен запрос: {request.remote_addr} {request.method} {request.url}")

@app.errorhandler(403)
def handle_403_error(e):
    logger.error(f"Ошибка 403: {str(e)}")
    return jsonify({'error': 'Access Forbidden', 'details': str(e)}), 403


@app.route('/')
def index():
    return "Hello, World!"

@app.route('/songs/<string:track_id>', methods=['GET'])
def get_song_by_id(track_id):
    logger.info(f"Получен запрос с IP: {request.remote_addr}")
    logger.info(f"Заголовки запроса: {request.headers}")
    logger.info(f"Путь запроса: {request.path}")
    logger.info(f"Метод запроса: {request.method}")
    logger.info(f"Запрос трека с ID: {track_id}")

    # Проверяем, есть ли трек в базе данных
    track_data = tracks_collection.find_one({'track_id': track_id})

    if track_data:
        logger.info(f"Трек {track_id} найден в базе данных.")
        file_path = track_data['file_path']
    else:
        # Если трека нет в базе, скачиваем его
        logger.info(f"Трек {track_id} не найден в базе данных. Скачивание из Yandex Music...")
        client = Client(YANDEX_MUSIC_TOKEN).init()

        try:
            track = client.tracks([track_id])[0]  # Получаем трек по ID
        except IndexError:
            logger.error(f"Трек с ID {track_id} не найден в Yandex Music.")
            return jsonify({'error': 'Track not found'}), 404

        # Скачиваем трек
        file_path = f"downloads/{track_id}.mp3"
        os.makedirs("downloads", exist_ok=True)  # Создаем папку, если ее нет
        track.download(file_path, 'mp3', 192)
        logger.info(f"Трек {track_id} скачан и сохранен в {file_path}.")

        # Получаем информацию о треке
        title = track.title
        artists = ', '.join(track.artists_name())
        year = track.albums[0].year if track.albums else 2022  # Год выпуска (если доступен)

        # Сохраняем информацию о треке в MongoDB
        track_data = {
            'track_id': track_id,
            'title': title,
            'artists': artists,
            'year': year,
            'file_path': file_path
        }
        tracks_collection.insert_one(track_data)
        logger.info(f"Информация о треке {track_id} сохранена в MongoDB.")

    # Читаем MP3-файл и кодируем его в base64
    with open(file_path, "rb") as audio_file:
        audio_base64 = base64.b64encode(audio_file.read()).decode('utf-8')

    # Возвращаем информацию о треке и base64-кодированный MP3-файл
    return jsonify({
        'title': track_data['title'],
        'artists': track_data['artists'],
        'year': track_data['year'],
        'mp3': audio_base64
    })


if __name__ == '__main__':
    logger.info("Запуск Flask-приложения...")
    # Запуск сервера на всех интерфейсах (0.0.0.0) и порту 4000
    app.run(host='0.0.0.0', port=3000)