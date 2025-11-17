import tkinter as tk
import threading
import time
import requests
import sqlite3
import urllib3 
from bs4 import BeautifulSoup
from requests.exceptions import RequestException
from datetime import datetime


TARGET_HOURS = [5, 13]

CHECK_INTERVAL_SECONDS = 60

URL_BCV = "https://www.bcv.org.ve/"


class DatabaseManager:

    
    DB_NAME = 'rate_bcv.db'

    def __init__(self):

        self._create_table()

    def _create_table(self):

        try:
            with sqlite3.connect(self.DB_NAME) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS rate_log (
                        id INTEGER PRIMARY KEY,
                        consult_date TEXT NOT NULL,
                        usd_rate REAL NOT NULL,
                        difference_from_previous REAL 
                    )
                ''')
                conn.commit()
        except Exception as e:
            print(f"Error al crear la tabla en la base de datos: {e}")


    def get_last_rate(self):

        try:

            with sqlite3.connect(self.DB_NAME) as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT usd_rate FROM rate_log ORDER BY id DESC LIMIT 1')
                result = cursor.fetchone()
                return result[0] if result else 0.0 
        except Exception as e:
            print(f"Error al obtener la última tasa: {e}")
            return 0.0


    def log_rate(self, usd_rate):

        last_rate = self.get_last_rate()
        

        is_first_entry = (last_rate == 0.0)
        
        if is_first_entry:

            difference = 0.0 
        else:
            difference = usd_rate - last_rate

        if not is_first_entry and abs(usd_rate - last_rate) < 1e-9: 
            consult_date = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            print(f"[{consult_date}] Tasa actual ({usd_rate:.4f}) igual a la última. No se registra en DB.")
            return 0.0 
        consult_date = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        try:
  
            with sqlite3.connect(self.DB_NAME) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO rate_log (consult_date, usd_rate, difference_from_previous)
                    VALUES (?, ?, ?)
                ''', (consult_date, usd_rate, difference))
                conn.commit()
                print(f"[{consult_date}] Tasa registrada en DB: {usd_rate:.4f}. Diferencia: {difference:+.4f}")
                return difference
        except Exception as e:
            print(f"Error al registrar en la base de datos: {e}")
            return None


class RateWidget:
    def __init__(self, root):
        self.root = root

        self.db_manager = DatabaseManager()

        self.last_update_hour = -1 


        self.root.title("Tasa BCV")

        self.root.geometry("520x300+100+100") 
        self.root.configure(bg="#1a1a1a")

        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        

        self._offset_x = 0
        self._offset_y = 0

 
        
    
        FONT_DIGITAL_GRANDE = ("Consolas", 36, "bold") 
        FONT_DIGITAL_MEDIA = ("Consolas", 12)
        FONT_DIGITAL_PEQUENA = ("Consolas", 12)

        self.title_label = tk.Label(
            self.root, 

            text="BCV TASA (USD)", 
            fg="#cccccc", 
            bg="#1a1a1a", 
            font=FONT_DIGITAL_MEDIA,
            padx=10, 
            anchor="w" 
        )
     
        self.title_label.pack(pady=(15, 0), fill="x") 

        self.rate_label = tk.Label(
            self.root, 
            text="00.0000", 
            fg="#00ff99",
            bg="#1a1a1a",
            font=FONT_DIGITAL_GRANDE,
            padx=20,
            pady=10
        )
        self.rate_label.pack(pady=10, padx=20, fill="x")

        self.updated_label = tk.Label(
            self.root, 
            text="cargando...", 
            fg="#888888", 
            bg="#1a1a1a", 
            font=FONT_DIGITAL_PEQUENA
        )
        self.updated_label.pack(pady=(0, 15))

        self.quit_button = tk.Button(
            self.root, 
            text="X", 
            command=self.root.quit,
            bg="#ff3333", 
            fg="#ffffff",
            font=("Arial", 10, "bold"),
            width=3,
            relief="flat"
        )

        self.quit_button.place(x=420, y=10) 

        self.root.bind("<Button-1>", self.on_press)
        self.root.bind("<B1-Motion>", self.on_drag)

        self.start_update_loop()

    def start_update_loop(self):

        thread = threading.Thread(target=self.update_loop, daemon=True)
        thread.start()

    def update_loop(self):

        rate, time_str = self.fetch_current_bcv_rate()
        self.root.after(0, self.update_ui, rate, time_str)

        current_hour = time.localtime().tm_hour
        if "ERROR" not in time_str:
            self.last_update_hour = current_hour
            
        time.sleep(CHECK_INTERVAL_SECONDS)

        while True:
            current_hour = time.localtime().tm_hour
            

            is_target_hour = current_hour in TARGET_HOURS

            has_not_updated_this_hour = current_hour != self.last_update_hour

            if is_target_hour and has_not_updated_this_hour:
                print(f"[{time.strftime('%H:%M:%S')}] Hora objetivo alcanzada ({current_hour}:00). Iniciando scraping.")
                
                rate, time_str = self.fetch_current_bcv_rate()
                self.root.after(0, self.update_ui, rate, time_str)
                
                
                if "ERROR" not in time_str:
                    self.last_update_hour = current_hour
            
            time.sleep(CHECK_INTERVAL_SECONDS)

    def _clean_bcv_value(self, element):

        if not element:
            raise ValueError("Elemento no encontrado.")

        rate_text = element.find('strong').text.strip()

        clean_rate_text = rate_text.replace('.', '') 

        clean_rate_text = clean_rate_text.replace(',', '.') 
        
        return float(clean_rate_text)


    def fetch_current_bcv_rate(self):
        
        usd_rate = None
        try:
           
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }
            
            
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

            
            response = requests.get(URL_BCV, headers=headers, timeout=10, verify=False)
            response.raise_for_status() 


            soup = BeautifulSoup(response.content, 'html.parser')

            dolar_div = soup.find('div', id='dolar')

            if not dolar_div:
                print("Error de Scraping: No se encontró el div con id='dolar'. El HTML del BCV pudo haber cambiado.")
                last_rate = self.db_manager.get_last_rate()
                if last_rate > 0.0:
                    formatted_rate = f"{last_rate:.4f}"
                    return formatted_rate, "FALLO: BCV (Usando última tasa)"
                return "00.0000", "ERROR: #dolar"

            usd_rate = self._clean_bcv_value(dolar_div)

            difference = self.db_manager.log_rate(usd_rate)

            formatted_rate = f"{usd_rate:.4f}"
            

            if difference is not None and difference != 0.0:
                 simbolo = "↑" if difference > 0 else "↓"

                 difference_message = f" ({simbolo} {abs(difference):.4f})"
            else:
                 difference_message = ""
            
            current_time = time.strftime("%H:%M")

            return formatted_rate, f"Act: {current_time}{difference_message}"

        except RequestException as e:

            print(f"Error de Red/HTTP: {e}")
            last_rate = self.db_manager.get_last_rate()
            if last_rate > 0.0:
                formatted_rate = f"{last_rate:.4f}"
                return formatted_rate, "FALLO: RED (Usando última tasa)"
            return "00.0000", "ERROR: RED"
        except ValueError as e:

            print(f"Error de Parseo/Valor: {e}")
            last_rate = self.db_manager.get_last_rate()
            if last_rate > 0.0:
                formatted_rate = f"{last_rate:.4f}"
                return formatted_rate, "FALLO: PARSEO (Usando última tasa)"
            return "00.0000", "ERROR: PARSEO"
        except Exception as e:
            print(f"Error Inesperado: {e}")
            last_rate = self.db_manager.get_last_rate()
            if last_rate > 0.0:
                formatted_rate = f"{last_rate:.4f}"
                return formatted_rate, "FALLO: GEN (Usando última tasa)"
            return "00.0000", "ERROR: GEN"

    def update_ui(self, rate, time_str):

        self.rate_label.config(text=rate)
        self.updated_label.config(text=time_str)

        if rate == "00.0000":
            self.rate_label.config(fg="#ff5555")
        else:
            self.rate_label.config(fg="#00ff99")


    def on_press(self, event):
        self._offset_x = event.x
        self._offset_y = event.y

    def on_drag(self, event):
        x = self.root.winfo_pointerx() - self._offset_x
        y = self.root.winfo_pointery() - self._offset_y
        self.root.geometry(f"+{x}+{y}")


if __name__ == "__main__":
    app_root = tk.Tk()

    widget = RateWidget(app_root) 
    app_root.mainloop()