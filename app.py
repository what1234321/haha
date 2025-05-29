from flask import Flask, render_template, request, jsonify
import requests
import json
from datetime import datetime, timedelta, timezone
import os

KST = timezone(timedelta(hours=9))

app = Flask(__name__)
API_KEY = '9777155c8a3cc183254aee7ad5ebbafe'
NEWS_API_KEY = 'a726dddf2e3bff7b3b0aaa2067c63c13'

city_map = {
    '서울': 'Seoul', '부산': 'Busan', '대구': 'Daegu', '인천': 'Incheon', '광주': 'Gwangju', '대전': 'Daejeon',
    '울산': 'Ulsan', '세종': 'Sejong', '수원': 'Suwon', '춘천': 'Chuncheon', '청주': 'Cheongju', '전주': 'Jeonju',
    '목포': 'Mokpo', '창원': 'Changwon', '진주': 'Jinju', '안동': 'Andong', '포항': 'Pohang', '강릉': 'Gangneung',
    '속초': 'Sokcho', '평택': 'Pyeongtaek', '김해': 'Gimhae', '양산': 'Yangsan', '구미': 'Gumi', '여수': 'Yeosu',
    '순천': 'Suncheon', '군산': 'Gunsan', '김천': 'Gimcheon', '제주': 'Jeju'
}

autocomplete_list = list(city_map.keys()) + list(city_map.values())

WEEKDAY_MAP = {
    "월요일": 0, "화요일": 1, "수요일": 2, "목요일": 3,
    "금요일": 4, "토요일": 5, "일요일": 6
}

FAV_FILE = 'favorites.json'
if not os.path.exists(FAV_FILE):
    with open(FAV_FILE, 'w', encoding='utf-8') as f:
        json.dump([], f)

@app.route('/', methods=['GET', 'POST'])
def home():
    city_input = request.args.get('city', default='Seoul')

    # ✅ 검색 기록 저장
    save_search_history(city_input)

    if city_input in city_map:
        city = city_map[city_input]
    else:
        city = city_input

    # ✅ 날씨 기록 저장 (그래프용)
    weather = get_weather(city)

    news_articles = []
    news_error = None
    if request.method == 'POST':
        query = request.form.get('query')
        news_url = f'https://gnews.io/api/v4/search?q={query}&token={NEWS_API_KEY}&lang=ko&max=5'
        response = requests.get(news_url)
        if response.status_code == 200:
            news_articles = response.json().get('articles', [])
            if not news_articles:
                news_error = "검색 결과가 없습니다."
        else:
            news_error = "뉴스 정보를 가져오는데 실패했습니다."

    return render_template(
        'index.html',
        weather=weather,
        news_articles=news_articles,
        news_error=news_error
    )

@app.route('/autocomplete')
def autocomplete():
    query = request.args.get('q', '')
    suggestions = [c for c in autocomplete_list if query.lower() in c.lower()]
    return jsonify(suggestions)

@app.route('/weather-data')
def weather_data():
    city = request.args.get('city', default='Seoul')
    weather = get_weather(city)
    return jsonify(weather)

@app.route('/add-group', methods=['POST'])
def add_group():
    data = request.get_json()
    name = data.get('name') or data.get('group_name')
    entries = data.get('entries', [])
    groups = load_groups()
    groups = [g for g in groups if g['group_name'] != name]
    groups.append({'group_name': name, 'entries': entries})
    save_groups(groups)
    return jsonify({'message': '저장 완료', 'groups': groups})

@app.route('/groups')
def get_groups():
    return jsonify(load_groups())

@app.route('/delete-group', methods=['POST'])
def delete_group():
    name = request.get_json().get('name') or request.get_json().get('group_name')
    groups = load_groups()
    groups = [g for g in groups if g['group_name'] != name]
    save_groups(groups)
    return '', 204

@app.route('/get-group-weather')
def get_group_weather():
    name = request.args.get('group')
    groups = load_groups()
    group = next((g for g in groups if g['group_name'] == name), None)
    if not group:
        return jsonify({'error': 'Group not found'}), 404
    results = []
    for entry in group['entries']:
        city = entry['city']
        weekday = entry['weekday']
        time = entry['time']
        forecast = get_forecast(city, weekday, time)
        result = {
            'weekday': weekday,
            'time': time,
            'city': city
        }
        if forecast.get("info"):
            result['info'] = forecast['info']
            result['forecast_time'] = None
            result['temperature'] = None
            result['description'] = None
            result['humidity'] = None
            result['rain'] = None
        else:
            result['forecast_time'] = forecast.get('forecast_time')
            result['temperature'] = forecast.get('temperature')
            result['description'] = forecast.get('description')
            result['humidity'] = forecast.get('humidity')
            result['rain'] = forecast.get('rain')
            result['info'] = None
        results.append(result)
    return jsonify({'results': results})

@app.route('/get_hourly_forecast', methods=['POST'])
def get_hourly_forecast():
    data = request.get_json()
    city = data['city']
    city_eng = city_map.get(city, city)

    url = f'https://api.openweathermap.org/data/2.5/forecast?q={city_eng}&appid={API_KEY}&units=metric&lang=kr'
    res = requests.get(url)
    forecast_data = res.json()

    hourly_labels = []
    hourly_temps = []
    hourly_humids = []

    for item in forecast_data['list'][:8]:
        time = datetime.strptime(item['dt_txt'], "%Y-%m-%d %H:%M:%S").strftime("%H시")
        temp = item['main']['temp']
        humid = item['main']['humidity']  # 습도 가져오기
        hourly_labels.append(time)
        hourly_temps.append(round(temp, 1))
        hourly_humids.append(round(humid, 1))  # 습도 리스트에 저장

    return jsonify({
        'labels': hourly_labels,
        'temps': hourly_temps,
        'humids': hourly_humids,
    })

def get_weather(city):
    url = f'https://api.openweathermap.org/data/2.5/weather?q={city}&appid={API_KEY}&units=metric&lang=kr'
    response = requests.get(url)
    data = response.json()
    if data.get('cod') != 200:
        return {
            'city': city,
            'error': f"'{city}'의 날씨를 찾을 수 없습니다. (영문 도시명은 첫 글자를 대문자로 입력하세요. 예: Busan)"
        }
    else:
        return {
            'city': city,
            'temperature': data['main']['temp'],
            'description': data['weather'][0]['description'],
            'humidity': data['main']['humidity'],
            'rain': data.get('rain', {}).get('1h', 0),
            'error': None
        }

def get_forecast(city, target_weekday, target_time):
    url = f'https://api.openweathermap.org/data/2.5/forecast?q={city}&appid={API_KEY}&units=metric&lang=kr'
    response = requests.get(url)
    data = response.json()
    if 'list' not in data:
        return {"info": "예보를 불러올 수 없습니다."}

    now = datetime.now()
    now_weekday = now.weekday()
    target_weekday_num = WEEKDAY_MAP.get(target_weekday)
    days_ahead = (target_weekday_num - now_weekday + 7) % 7
    target_date = now + timedelta(days=days_ahead)

    hour, minute = map(int, target_time.split(":"))
    target_dt = target_date.replace(hour=hour, minute=minute, second=0, microsecond=0)

    if abs((target_dt - now).total_seconds()) > 120 * 3600:
        return {"info": "예보 없음"}

    min_diff = float('inf')
    best_match = None
    for entry in data['list']:
        entry_dt = datetime.strptime(entry['dt_txt'], "%Y-%m-%d %H:%M:%S")
        diff = abs((entry_dt - target_dt).total_seconds())
        if diff < min_diff:
            min_diff = diff
            best_match = entry

    if best_match:
        return {
            "temperature": best_match['main']['temp'],
            "description": best_match['weather'][0]['description'],
            "humidity": best_match['main']['humidity'],
            "rain": best_match.get('rain', {}).get('3h', 0),
            "forecast_time": best_match['dt_txt']
        }
    return {"info": "예보 없음"}

def load_groups():
    with open(FAV_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)

def save_groups(groups):
    with open(FAV_FILE, 'w', encoding='utf-8') as f:
        json.dump(groups, f, ensure_ascii=False, indent=2)

HISTORY_FILE = 'history.json'

def save_search_history(city):
    if city in city_map:
        kor = city
        eng = city_map[city]
    elif city in city_map.values():
        eng = city
        kor = next(k for k, v in city_map.items() if v == city)
    else:
        kor = city
        eng = city
    display_city = f"{kor} ({eng})"
    try:
        with open(HISTORY_FILE, 'r') as f:
            history = json.load(f)
    except FileNotFoundError:
        history = []
    history_entry = {
        'city': display_city,
        'timestamp': datetime.now(KST).strftime('%Y-%m-%d %H:%M:%S')
    }
    history.append(history_entry)
    with open(HISTORY_FILE, 'w') as f:
        json.dump(history, f, indent=4)

@app.route('/history')
def view_history():
    try:
        with open(HISTORY_FILE, 'r') as f:
            history = json.load(f)
    except FileNotFoundError:
        history = []
    return render_template('history.html', history=history)
    
