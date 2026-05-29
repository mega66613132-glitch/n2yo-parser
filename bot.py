import os
import time
import datetime
import re
import subprocess
import requests
from pyvirtualdisplay import Display
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
import gspread
from google.oauth2.service_account import Credentials

# ================= НАСТРОЙКИ =================
CREDENTIALS_FILE = 'credentials.json' 
SHEET_ID = '1e9SrUlObI--v-clyzLseR-jyAx0mYtPXMcsu9N652Xw' 
# =============================================

SATELLITES = {68360 + i: f"РАССВЕТ 3-{i+1}" for i in range(16)}

def setup_google_sheets():
    scopes = ['https://www.googleapis.com/auth/spreadsheets']
    creds = Credentials.from_service_account_file(CREDENTIALS_FILE, scopes=scopes)
    return gspread.authorize(creds)

def clean_value(text, marker):
    for line in text.split('\n'):
        if marker.upper() in line.upper():
            val = line.split(':')[-1].strip()
            val = re.sub(r'[^\d\.\-]', '', val)
            return val.replace('.', ',')
    return ""

def upload_image_to_host(filepath):
    """Загружает скриншот на бесплатный сервер и возвращает прямую ссылку"""
    try:
        with open(filepath, 'rb') as f:
            response = requests.post('https://catbox.moe/user/api.php', 
                                     data={'reqtype': 'fileupload'}, 
                                     files={'fileToUpload': f})
        if response.status_code == 200:
            return response.text # Готовая ссылка на картинку
    except Exception as e:
        print(f"Ошибка загрузки картинки: {e}")
    return "Не удалось сохранить скриншот"

def get_chrome_version():
    try:
        output = subprocess.check_output(['google-chrome', '--version']).decode('utf-8')
        version = re.search(r'\d+', output).group()
        return int(version)
    except Exception as e:
        print(f"Не удалось определить версию Chrome: {e}")
        return None

def run_bot():
    print(f"[{datetime.datetime.now()}] Начало обхода группировки Рассвет-3...")
    
    display = Display(visible=0, size=(1920, 1080))
    display.start()
    
    options = uc.ChromeOptions()
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-blink-features=AutomationControlled") 
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36")

    v_main = get_chrome_version()
    print(f"Запуск браузера (версия Chrome: {v_main})...")
    
    driver = uc.Chrome(options=options, version_main=v_main)
    
    try:
        gc = setup_google_sheets()
        workbook = gc.open_by_key(SHEET_ID)
        
        current_date = datetime.datetime.now().strftime("%d.%m.%Y")
        current_time = datetime.datetime.now().strftime("%H:%M:%S")
        
        summary_heights = {}

        for sat_id, sheet_name in SATELLITES.items():
            url = f"https://www.n2yo.com/?s={sat_id}"
            print(f"Обработка {sheet_name} (ID: {sat_id})...")
            
            try:
                driver.get(url)
                time.sleep(15) 
                
                # УМНЫЙ ПОИСК: Ищем таблицу по содержанию текста, а не по ID
                try:
                    satinfo_element = driver.find_element(By.XPATH, "//*[contains(text(), 'NORAD ID')]/ancestor::table[1]")
                except:
                    satinfo_element = driver.find_element(By.XPATH, "//*[contains(text(), 'ALTITUDE')]/ancestor::table[1]")
                
                timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
                screenshot_name = f"{sheet_name}_{timestamp}.png"
                satinfo_element.screenshot(screenshot_name)
                
                telemetry_text = satinfo_element.text
                altitude = clean_value(telemetry_text, "ALTITUDE")
                velocity = clean_value(telemetry_text, "SPEED") 
                
                summary_heights[sheet_name] = altitude
                
                # Загружаем скриншот и получаем ссылку
                screenshot_link = upload_image_to_host(screenshot_name)
                
                # Удаляем картинку с сервера GitHub, чтобы не мусорить
                if os.path.exists(screenshot_name):
                    os.remove(screenshot_name)

                # Запись в Гугл Таблицу
                sheet = workbook.worksheet(sheet_name)
                row_to_append = [current_date, current_time, altitude, velocity, screenshot_link]
                sheet.append_row(row_to_append, value_input_option='USER_ENTERED')
                
                print(f"Успешно сохранено для {sheet_name}: Высота={altitude}, Скорость={velocity}")
                
            except Exception as sat_error:
                print(f"Ошибка при обработке спутника {sheet_name}: {sat_error}")
                continue
        
        # Обновление сводного листа
        try:
            summary_sheet = workbook.worksheet("Данные по высоте орбит всех КА")
            summary_row = [current_date, current_time]
            for i in range(16):
                name = f"РАССВЕТ 3-{i+1}"
                summary_row.append(summary_heights.get(name, ""))
            
            summary_sheet.append_row(summary_row, value_input_option='USER_ENTERED')
            print("Сводный лист успешно обновлен.")
        except Exception as summary_error:
            print(f"Не удалось обновить сводный лист: {summary_error}")

    except Exception as e:
        print(f"Критическая ошибка бота: {e}")
    finally:
        driver.quit()
        display.stop()
        print(f"[{datetime.datetime.now()}] Работа завершена.")

if __name__ == '__main__':
    run_bot()
