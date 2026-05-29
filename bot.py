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
    try:
        headers = {'Authorization': 'Client-ID 546c25a59c58ad7'}
        with open(filepath, 'rb') as f:
            r = requests.post('https://api.imgur.com/3/image', headers=headers, files={'image': f}, timeout=30)
        if r.status_code == 200:
            return r.json()['data']['link']
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
    # Настраиваем Московское время (UTC+3)
    msk_tz = datetime.timezone(datetime.timedelta(hours=3))
    start_time_msk = datetime.datetime.now(msk_tz)
    print(f"[{start_time_msk.strftime('%Y-%m-%d %H:%M:%S')}] Начало обхода группировки Рассвет-3...")
    
    display = Display(visible=0, size=(1920, 1080))
    display.start()
    
    options = uc.ChromeOptions()
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-blink-features=AutomationControlled") 
    options.add_argument("--disable-gpu")
    options.add_argument("--disable-software-rasterizer")
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36")

    v_main = get_chrome_version()
    print(f"Запуск браузера (версия Chrome: {v_main})...")
    
    driver = uc.Chrome(options=options, version_main=v_main)
    driver.set_page_load_timeout(60)
    
    try:
        gc = setup_google_sheets()
        workbook = gc.open_by_key(SHEET_ID)

        for sat_id, sheet_name in SATELLITES.items():
            url = f"https://www.n2yo.com/?s={sat_id}"
            print(f"Обработка {sheet_name} (ID: {sat_id})...")
            
            try:
                driver.get(url)
                time.sleep(12) 
                
                # Фиксируем точное Московское время для каждого конкретного спутника!
                now_msk = datetime.datetime.now(msk_tz)
                current_date = now_msk.strftime("%Y-%m-%d")
                current_time = now_msk.strftime("%H:%M:%S")
                
                # Извлечение данных и замена точек на запятые
                lat = get_text(driver, "satlat").replace('.', ',')
                lon = get_text(driver, "satlng").replace('.', ',')
                alt = get_text(driver, "sataltkm").replace('.', ',')
                speed = get_text(driver, "satspdkm").replace('.', ',')
                
                az_val = get_text(driver, 'sataz').replace('.', ',')
                az_cmp = get_text(driver, 'satazcmp')
                az = f"{az_val} {az_cmp}".strip()
                
                el = get_text(driver, "satel").replace('.', ',')
                
                ra = get_text(driver, "satra").replace('h', 'ч').replace('m', 'м').replace('s', 'с')
                dec = get_text(driver, "satdec")
                lst = get_text(driver, "lmst").replace('h', 'ч').replace('m', 'м').replace('s', 'с')
                period = get_text(driver, "period").replace('m', 'м')
                
                try:
                    table_element = driver.find_element(By.ID, "tabledata")
                except:
                    table_element = driver.find_element(By.ID, "paneldata")
                    
                timestamp = now_msk.strftime("%Y-%m-%d_%H-%M-%S")
                screenshot_name = f"{sheet_name}_{timestamp}.png"
                table_element.screenshot(screenshot_name)
                
                screenshot_link = upload_to_imgur(screenshot_name)
                
                if os.path.exists(screenshot_name):
                    os.remove(screenshot_name)

                sheet = workbook.worksheet(sheet_name)
                
                # Массив ровно на 14 колонок (A-N)
                row_to_append = [
                    "",             # Колонке A (пустая)
                    current_time,   # Колонка B: Время (МСК)
                    current_date,   # Колонка C: Дата (МСК)
                    lat,            # Колонка D: Latitude
                    lon,            # Колонка E: Longitude
                    alt,            # Колонка F: Altitude
                    speed,          # Колонка G: Speed
                    az,             # Колонка H: Azimuth
                    el,             # Колонка I: Elevation
                    ra,             # Колонка J: Right ascension
                    dec,            # Колонка K: Declination
                    lst,            # Колонка L: Local Sidereal Time
                    period,         # Колонка M: SATELLITE PERIOD
                    screenshot_link # Колонка N: Скриншот
                ]
                
                col_b = sheet.col_values(2)
                next_row = len(col_b) + 1 
                
                sheet.update(values=[row_to_append], range_name=f"A{next_row}:N{next_row}", value_input_option='USER_ENTERED')
                print(f"Успешно сохранено! Строка {next_row}, Высота={alt}")
                
            except Exception as sat_error:
                print(f"Ошибка при обработке спутника {sheet_name}: {sat_error}")
                continue

    except Exception as e:
        print(f"Критическая ошибка бота: {e}")
    finally:
        driver.quit()
        display.stop()
        end_time_msk = datetime.datetime.now(msk_tz)
        print(f"[{end_time_msk.strftime('%Y-%m-%d %H:%M:%S')}] Работа завершена.")

if __name__ == '__main__':
    run_bot()
