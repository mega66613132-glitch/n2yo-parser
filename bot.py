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
    try:
        return driver.find_element(By.ID, el_id).text.strip()
    except:
        return ""

def upload_to_imgur(filepath):
    """Надежная загрузка скриншотов через API Imgur"""
    try:
        # Публичный Client-ID для анонимной загрузки картинок
        headers = {'Authorization': 'Client-ID 546c25a59c58ad7'}
        with open(filepath, 'rb') as f:
            r = requests.post('https://api.imgur.com/3/image', headers=headers, files={'image': f}, timeout=30)
        if r.status_code == 200:
            return r.json()['data']['link'] # Прямая ссылка на картинку
    except Exception as e:
        print(f"Ошибка Imgur: {e}")
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
    options.add_argument("--disable-gpu") # Предотвращает зависания браузера на сервере
    options.add_argument("--disable-software-rasterizer")
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36")

    v_main = get_chrome_version()
    print(f"Запуск браузера (версия Chrome: {v_main})...")
    
    driver = uc.Chrome(options=options, version_main=v_main)
    driver.set_page_load_timeout(60) # Если страница висит больше минуты - идем дальше
    
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
                time.sleep(12) 
                
                # Точки НЕ заменяем, чтобы таблица не ломалась!
                lat = get_text(driver, "satlat")
                lon = get_text(driver, "satlng")
                alt = get_text(driver, "sataltkm")
                speed = get_text(driver, "satspdkm")
                
                az = f"{get_text(driver, 'sataz')} {get_text(driver, 'satazcmp')}".strip()
                el = get_text(driver, "satel")
                
                ra = get_text(driver, "satra").replace('h', 'ч').replace('m', 'м').replace('s', 'с')
                dec = get_text(driver, "satdec")
                lst = get_text(driver, "lmst").replace('h', 'ч').replace('m', 'м').replace('s', 'с')
                period = get_text(driver, "period").replace('m', 'м')
                
                summary_heights[sheet_name] = alt
                
                try:
                    table_element = driver.find_element(By.ID, "tabledata")
                except:
                    table_element = driver.find_element(By.ID, "paneldata")
                    
                timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
                screenshot_name = f"{sheet_name}_{timestamp}.png"
                table_element.screenshot(screenshot_name)
                
                screenshot_link = upload_to_imgur(screenshot_name)
                
                if os.path.exists(screenshot_name):
                    os.remove(screenshot_name)

                # Строгий массив данных (ровно под ваши 14 колонок)
                sheet = workbook.worksheet(sheet_name)
                row_to_append = [
                    "",             # Колонке A (пустая)
                    current_time,   # Колонка B
                    current_date,   # Колонка C
                    lat,            # Колонка D
                    lon,            # Колонка E
                    alt,            # Колонка F
                    speed,          # Колонка G
                    az,             # Колонка H
                    el,             # Колонка I
                    ra,             # Колонка J
                    dec,            # Колонка K
                    lst,            # Колонка L
                    period,         # Колонка M
                    screenshot_link # Колонка N (Скриншот)
                ]
                
                # table_range='A1' заставляет Google Sheets жестко считать с колонки A
                sheet.append_row(row_to_append, value_input_option='USER_ENTERED', table_range='A1')
                print(f"Успешно сохранено! Высота={alt}, Скриншот: {screenshot_link}")
                
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
            
            summary_sheet.append_row(summary_row, value_input_option='USER_ENTERED', table_range='A1')
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
