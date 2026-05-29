import os
import time
import datetime
import re
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
import gspread
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# ================= НАСТРОЙКИ =================
CREDENTIALS_FILE = 'credentials.json' 
SHEET_ID = '1e9SrUlObI--v-clyzLseR-jyAx0mYtPXMcsu9N652Xw' 
DRIVE_FOLDER_ID = '18zb6bD6xDIIm63MfsyWCGswhk77acsSq' 
# =============================================

# Автоматически создаем список спутников: ID от 68360 до 68375 и имена листов
SATELLITES = {68360 + i: f"РАССВЕТ 3-{i+1}" for i in range(16)}

def setup_google_apis():
    scopes = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
    creds = Credentials.from_service_account_file(CREDENTIALS_FILE, scopes=scopes)
    return gspread.authorize(creds), build('drive', 'v3', credentials=creds)

def clean_value(text, marker):
    """
    Ищет нужный маркер (например, ALTITUDE) в тексте, 
    удаляет буквы (km, km/s) и меняет точку на запятую для локали РФ.
    """
    for line in text.split('\n'):
        if marker.upper() in line.upper():
            # Извлекаем часть после двоеточия
            val = line.split(':')[-1].strip()
            # Удаляем буквы и пробелы, оставляя цифры и точки/минусы
            val = re.sub(r'[^\d\.\-]', '', val)
            # Меняем точку на запятую для правильного формата чисел в Excel/Гугл таблицах
            return val.replace('.', ',')
    return ""

def run_bot():
    print(f"[{datetime.datetime.now()}] Начало обхода группировки Рассвет-3...")
    
    chrome_options = Options()
    chrome_options.add_argument("--headless") 
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--window-size=1920,1080")

    driver = webdriver.Chrome(options=chrome_options)
    
    try:
        # Авторизуемся в Google один раз перед циклом
        gc, drive_service = setup_google_apis()
        workbook = gc.open_by_key(SHEET_ID)
        
        current_date = datetime.datetime.now().strftime("%d.%m.%Y")
        current_time = datetime.datetime.now().strftime("%H:%M:%S")
        
        # Список для сбора высот всех КА (чтобы потом обновить сводный лист, если нужно)
        summary_heights = {}

        # Перебираем все 16 спутников
        for sat_id, sheet_name in SATELLITES.items():
            url = f"https://www.n2yo.com/?s={sat_id}"
            print(f"Обработка {sheet_name} (ID: {sat_id})...")
            
            try:
                driver.get(url)
                time.sleep(6) # Ждем загрузки динамических данных (веб-сокетов)
                
                # Находим конкретный блок с обновляемыми данными
                satinfo_element = driver.find_element(By.ID, "satinfo")
                
                # ТОЧЕЧНЫЙ СКРИНШОТ: Selenium умеет снимать только один элемент
                timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
                screenshot_name = f"{sheet_name}_{timestamp}.png"
                satinfo_element.screenshot(screenshot_name)
                
                # Извлекаем текст блока телеметрии
                telemetry_text = satinfo_element.text
                
                # Форматируем значения (Высота и Скорость)
                altitude = clean_value(telemetry_text, "ALTITUDE")
                velocity = clean_value(telemetry_text, "VELOCITY")
                
                summary_heights[sheet_name] = altitude
                
                # Загружаем точечный скриншот на Диск
                file_metadata = {'name': screenshot_name, 'parents': [DRIVE_FOLDER_ID]}
                media = MediaFileUpload(screenshot_name, mimetype='image/png')
                drive_file = drive_service.files().create(body=file_metadata, media_body=media, fields='id, webViewLink').execute()
                screenshot_link = drive_file.get('webViewLink')
                
                # Удаляем локальный файл скриншота, чтобы не занимать место на GitHub
                if os.path.exists(screenshot_name):
                    os.remove(screenshot_name)

                # Запись на индивидуальный лист спутника
                # Структура строки: [Дата, Время, Высота (км), Скорость (км/с), Ссылка на скриншот]
                sheet = workbook.worksheet(sheet_name)
                row_to_append = [current_date, current_time, altitude, velocity, screenshot_link]
                sheet.append_row(row_to_append, value_input_option='USER_ENTERED')
                
                print(f"Успешно сохранено для {sheet_name}: Высота={altitude}, Скорость={velocity}")
                
            except Exception as sat_error:
                print(f"Ошибка при обработке спутника {sheet_name}: {sat_error}")
                continue # Если один спутник выдал ошибку, переходим к следующему
        
        # ОБНОВЛЕНИЕ СВОДНОГО ЛИСТА "Данные по высоте орбит всех КА"
        try:
            summary_sheet = workbook.worksheet("Данные по высоте орбит всех КА")
            # Собираем строку: Дата, Время, и далее высоты от 1 до 16 аппарата
            summary_row = [current_date, current_time]
            for i in range(16):
                name = f"РАССВЕТ 3-{i+1}"
                summary_row.append(summary_heights.get(name, ""))
            
            summary_sheet.append_row(summary_row, value_input_option='USER_ENTERED')
            print("Сводный лист по высоте всех орбит успешно обновлен.")
        except Exception as summary_error:
            print(f"Не удалось обновить сводный лист: {summary_error}")

    except Exception as e:
        print(f"Критическая ошибка бота: {e}")
    finally:
        driver.quit()
        print(f"[{datetime.datetime.now()}] Работа завершена.")

if __name__ == '__main__':
    run_bot()
