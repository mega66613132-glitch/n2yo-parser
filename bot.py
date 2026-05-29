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

def get_text(driver, el_id):
    """Идеальное извлечение данных по их уникальным ID на сайте"""
    try:
        return driver.find_element(By.ID, el_id).text.strip()
    except:
        return ""

def upload_image_to_host(filepath):
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        with open(filepath, 'rb') as f:
            r = requests.post('https://catbox.moe/user/api.php', 
                              data={'reqtype': 'fileupload'}, 
                              files={'fileToUpload': f},
                              headers=headers, timeout=15)
        if r.status_code == 200 and 'http' in r.text:
            return r.text.strip()
    except Exception as e:
        pass
    return "Скриншот не загружен"

def get_chrome_version():
    try:
        output = subprocess.check_output(['google-chrome', '--version']).decode('utf-8')
        return int(re.search(r'\d+', output).group())
    except:
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
        
        current_date = datetime.datetime.now().strftime("%Y-%m-%d")
        current_time = datetime.datetime.now().strftime("%H:%M:%S")
        
        summary_heights = {}

        for sat_id, sheet_name in SATELLITES.items():
            url = f"https://www.n2yo.com/?s={sat_id}"
            print(f"Обработка {sheet_name} (ID: {sat_id})...")
            
            try:
                driver.get(url)
                time.sleep(15) 
                
                # 1. Извлекаем данные точно по ID из вашего HTML кода!
                lat = get_text(driver, "satlat").replace('.', ',')
                lon = get_text(driver, "satlng").replace('.', ',')
                alt = get_text(driver, "sataltkm").replace('.', ',')
                speed = get_text(driver, "satspdkm").replace('.', ',')
                
                # Собираем Азимут (цифры + направление)
                az_val = get_text(driver, "sataz").replace('.', ',')
                az_cmp = get_text(driver, "satazcmp")
                az = f"{az_val} {az_cmp}".strip()
                
                el = get_text(driver, "satel").replace('.', ',')
                
                # Заменяем английские буквы на русские (h -> ч, m -> м, s -> с)
                ra = get_text(driver, "satra").replace('h', 'ч').replace('m', 'м').replace('s', 'с')
                dec = get_text(driver, "satdec")
                lst = get_text(driver, "lmst").replace('h', 'ч').replace('m', 'м').replace('s', 'с')
                period = get_text(driver, "period").replace('m', 'м')
                
                summary_heights[sheet_name] = alt
                
                # 2. Делаем скриншот ТОЛЬКО нужной таблицы
                try:
                    table_element = driver.find_element(By.ID, "tabledata")
                except:
                    table_element = driver.find_element(By.ID, "paneldata")
                    
                timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
                screenshot_name = f"{sheet_name}_{timestamp}.png"
                table_element.screenshot(screenshot_name)
                
                screenshot_link = upload_image_to_host(screenshot_name)
                
                if os.path.exists(screenshot_name):
                    os.remove(screenshot_name)

                # 3. Записываем в Google Таблицу (идеальное попадание в колонки)
                sheet = workbook.worksheet(sheet_name)
                row_to_append = [
                    "",             # A: (пустая)
                    current_time,   # B: Время снятия данных
                    current_date,   # C: Дата 
                    lat,            # D: Latitude
                    lon,            # E: Longitude
                    alt,            # F: Altitude, км
                    speed,          # G: Speed, км/с
                    az,             # H: Azimuth
                    el,             # I: Elevation
                    ra,             # J: Right ascension
                    dec,            # K: Declination
                    lst,            # L: Local Sidereal Time
                    period,         # M: SATELLITE PERIOD
                    screenshot_link # N: Ссылка на картинку
                ]
                sheet.append_row(row_to_append, value_input_option='USER_ENTERED')
                print(f"Успешно сохранено! Высота={alt}, Скорость={speed}, Ссылка: {screenshot_link[:30]}...")
                
            except Exception as sat_error:
                print(f"Ошибка при обработке спутника {sheet_name}: {sat_error}")
                continue
        
        # Обновление сводного листа
        try:
            summary_sheet = workbook.worksheet("Данные по высоте орбит всех КА")
            summary_row = ["", "", current_date]
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
