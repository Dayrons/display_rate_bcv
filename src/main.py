import tkinter as tk
import threading
import time
import requests
import sqlite3
import urllib3 
from bs4 import BeautifulSoup
from requests.exceptions import RequestException
from datetime import datetime
import json


TARGET_HOURS = [5, 13]

CHECK_INTERVAL_SECONDS = 180 

URL_BCV = "https://www.bcv.org.ve/"

URL_BINANCE_P2P_API = "https://p2p.binance.com/bapi/c2c/v2/friendly/c2c/adv/search"


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
                        bcv_rate REAL NOT NULL,
                        usdt_rate REAL, 
                        bcv_difference_from_previous REAL,
                        usdt_difference_from_previous REAL
                    )
                ''')
                conn.commit()
        except Exception as e:
            print(f"Error al crear la tabla en la base de datos: {e}")


    def get_last_rates(self):
        try:

            with sqlite3.connect(self.DB_NAME) as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT bcv_rate, usdt_rate FROM rate_log ORDER BY id DESC LIMIT 1')
                result = cursor.fetchone()
                return result if result else (0.0, 0.0)
        except Exception as e:
            print(f"Error al obtener las últimas tasas: {e}")
            return (0.0, 0.0)


    def log_rates(self, bcv_rate, usdt_rate):
        last_bcv_rate, last_usdt_rate = self.get_last_rates()
        
        is_first_entry = (last_bcv_rate == 0.0)
        
        bcv_difference = 0.0 if is_first_entry else bcv_rate - last_bcv_rate
        usdt_difference = 0.0 if is_first_entry else usdt_rate - last_usdt_rate

      
        if not is_first_entry and abs(bcv_rate - last_bcv_rate) < 1e-9 and abs(usdt_rate - last_usdt_rate) < 1e-9: 
            consult_date = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            return bcv_difference, usdt_difference 
            
        consult_date = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        try:
  
            with sqlite3.connect(self.DB_NAME) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO rate_log (consult_date, bcv_rate, usdt_rate, bcv_difference_from_previous, usdt_difference_from_previous)
                    VALUES (?, ?, ?, ?, ?)
                ''', (consult_date, bcv_rate, usdt_rate, bcv_difference, usdt_difference))
                conn.commit()
                print(f"[{consult_date}] Tasas registradas: BCV={bcv_rate:.4f}, USDT={usdt_rate:.4f}. Diferencias: BCV={bcv_difference:+.4f}, USDT={usdt_difference:+.4f}.")
                return bcv_difference, usdt_difference
        except Exception as e:
            print(f"Error al registrar en la base de datos: {e}")
            return None, None


class RateWidget:
    def __init__(self, root):
        self.root = root
        
        try:
         
            icono_imagen = tk.PhotoImage(file='/home/user/Documentos/display_rate_bcv/assets/money.png')
            self.root.iconphoto(False, icono_imagen)
            print("Icono cargado con éxito usando PNG.")
            root.tk.call('tk', 'scaling', 1.0)
        except:
            print("No se pudo establecer el escalado de Tkinter.")
            pass

        self.db_manager = DatabaseManager()

        self.last_update_hour = -1 

        self.usdt_rate = self.db_manager.get_last_rates()[1] 
        self.bcv_rate = self.db_manager.get_last_rates()[0] 
   
        self.last_bcv_status = "BCV no cargado" 


        self.root.title("Tasa BCV & USDT")


        self.root.geometry("350x300+100+100") 
        self.root.configure(bg="#1a1a1a")

   
        self.root.pack_propagate(False)


        # self.root.overrideredirect(True)
        # self.root.attributes("-topmost", True)
        
        self._offset_x = 0
        self._offset_y = 0

        FONT_DIGITAL_GRANDE = ("Consolas", 14, "bold") 
        FONT_DIGITAL_MEDIA = ("Consolas", 10)
        FONT_DIGITAL_PEQUENA = ("Consolas", 9)
        FONT_DIFERENCIA = ("Consolas", 12, "bold")


        self.bcv_title_label = tk.Label(
            self.root, 
            text="BCV Oficial (USD)", 
            fg="#cccccc", 
            bg="#1a1a1a", 
            font=FONT_DIGITAL_MEDIA,
            padx=10, 
            anchor="w" 
        )
        self.bcv_title_label.pack(pady=(15, 0), fill="x") 

        self.bcv_rate_label = tk.Label(
            self.root, 
            text="00.0000", 
            fg="#00ff99",
            bg="#1a1a1a",
            font=FONT_DIGITAL_GRANDE,
            padx=10,
            pady=3
        )
        self.bcv_rate_label.pack(pady=3, padx=10, fill="x")


        self.usdt_title_label = tk.Label(
            self.root, 
            text="Binance P2P (USDT)", 
            fg="#cccccc", 
            bg="#1a1a1a", 
            font=FONT_DIGITAL_MEDIA,
            padx=10, 
            anchor="w" 
        )
        self.usdt_title_label.pack(pady=(15, 0), fill="x") 

        self.usdt_rate_label = tk.Label(
            self.root, 
            text="00.0000", 
            fg="#f3ba2f", 
            bg="#1a1a1a",
            font=FONT_DIGITAL_GRANDE,
            padx=10, 
            pady=3
        )
        self.usdt_rate_label.pack(pady=3, padx=10, fill="x")

        self.diff_title_label = tk.Label(
            self.root, 
            text="DIFERENCIA (USDT - BCV)", 
            fg="#cccccc", 
            bg="#1a1a1a", 
            font=FONT_DIGITAL_PEQUENA,
            padx=10, 
            anchor="w" 
        )
        self.diff_title_label.pack(pady=(10, 0), fill="x") 

        self.diff_value_label = tk.Label(
            self.root,
            text="+00.0000", 
            fg="#44ccff", 
            bg="#1a1a1a",
            font=FONT_DIFERENCIA,
            padx=10, 
            pady=3
        )
        self.diff_value_label.pack(pady=3, padx=10, fill="x")


        self.updated_label = tk.Label(
            self.root, 
            text="cargando...", 
            fg="#888888", 
            bg="#1a1a1a", 
            font=FONT_DIGITAL_PEQUENA,
            wraplength=300,
        )
        self.updated_label.pack(pady=(0, 15))

        # self.quit_button = tk.Button(
        #     self.root, 
        #     text="X", 
        #     command=self.root.quit,
        #     bg="#ff3333", 
        #     fg="#ffffff",
        #     font=("Arial", 10, "bold"),
        #     width=3,
        #     relief="flat"
        # )


        # self.quit_button.place(x=300, y=10) 

        self.root.bind("<Button-1>", self.on_press)
        self.root.bind("<B1-Motion>", self.on_drag)

        self.start_update_loop()

    
    def _build_status_string(self, rate_value, time_str_raw, rate_diff, name):
       
        if "FALLO" in time_str_raw:
            return f"{name} FALLO: {time_str_raw}"
        
     
        if rate_diff is not None and abs(rate_diff) > 1e-9:
            simbolo = "↑" if rate_diff > 0 else "↓"
            return f"{name} ACT: {time_str_raw} ({simbolo} {abs(rate_diff):.4f})"
        

        return f"{name} ACT: {time_str_raw} (Estático)"


    def start_update_loop(self):

        thread = threading.Thread(target=self.update_loop, daemon=True)
        thread.start()

    def update_loop(self):

        self.root.after(0, self.updated_label.config, {"text": "ACTUALIZANDO BCV Y USDT (Inicio)..."})
        bcv_rate, usdt_rate, time_str = self.fetch_all_rates()
        self.root.after(0, self.update_ui, bcv_rate, usdt_rate, time_str)

        current_hour = time.localtime().tm_hour

        if "FALLO" not in time_str:
            self.last_update_hour = current_hour
            
        time.sleep(CHECK_INTERVAL_SECONDS)

        while True:
            current_hour = time.localtime().tm_hour
            
            is_target_hour = current_hour in TARGET_HOURS

            has_not_updated_this_hour = current_hour != self.last_update_hour

            if is_target_hour and has_not_updated_this_hour:

                print(f"[{time.strftime('%H:%M:%S')}] Hora objetivo BCV alcanzada ({current_hour}:00). Iniciando actualización completa.")
                self.root.after(0, self.updated_label.config, {"text": "ACTUALIZANDO BCV Y USDT (Hora Objetivo)..."})
                
                bcv_rate, usdt_rate, time_str = self.fetch_all_rates()
                self.root.after(0, self.update_ui, bcv_rate, usdt_rate, time_str)
                
                
                if "FALLO" not in time_str:
                    self.last_update_hour = current_hour
            else:

                print(f"[{time.strftime('%H:%M:%S')}] Actualizando sólo USDT (BCV estático).")
                self.root.after(0, self.updated_label.config, {"text": "ACTUALIZANDO SOLO USDT..."})
                
       
                usdt_rate_value, usdt_time_str_raw = self.fetch_usdt_rate()
                bcv_rate_value = self.bcv_rate 

           
                bcv_diff, usdt_diff = None, None
                if isinstance(bcv_rate_value, (int, float)) and isinstance(usdt_rate_value, (int, float)):
                 
                    bcv_diff, usdt_diff = self.db_manager.log_rates(bcv_rate_value, usdt_rate_value) 
                
             
                usdt_status = self._build_status_string(usdt_rate_value, usdt_time_str_raw, usdt_diff, "USDT")


                full_time_str = f"{self.last_bcv_status} | {usdt_status}"
                

                bcv_formatted = f"{bcv_rate_value:.4f}" if isinstance(bcv_rate_value, (int, float)) else "00.0000"
                usdt_formatted = f"{usdt_rate_value:.4f}" if isinstance(usdt_rate_value, (int, float)) else "00.0000"

     
                self.root.after(0, self.update_ui, bcv_formatted, usdt_formatted, full_time_str) 

            
            time.sleep(CHECK_INTERVAL_SECONDS)

    def _clean_bcv_value(self, element):
        if not element:
            raise ValueError("Elemento BCV no encontrado.")

        rate_text = element.find('strong').text.strip()
        clean_rate_text = rate_text.replace('.', '') 
        clean_rate_text = clean_rate_text.replace(',', '.') 
        
        return float(clean_rate_text)

    def fetch_bcv_rate(self):
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
                print("Error de Scraping BCV: No se encontró el div con id='dolar'.")
                return self.db_manager.get_last_rates()[0], "FALLO: BCV (Elemento no encontrado)"

            bcv_rate = self._clean_bcv_value(dolar_div)
            return bcv_rate, time.strftime("%H:%M")

        except RequestException as e:
            print(f"Error de Red BCV: {e}")
            return self.db_manager.get_last_rates()[0], f"FALLO: RED ({time.strftime('%H:%M')})"
        except ValueError as e:
            print(f"Error de Parseo BCV: {e}")
            return self.db_manager.get_last_rates()[0], f"FALLO: PARSEO ({time.strftime('%H:%M')})"
        except Exception as e:
            print(f"Error Inesperado BCV: {e}")
            return self.db_manager.get_last_rates()[0], f"FALLO: GEN ({time.strftime('%H:%M')})"
            

    def fetch_usdt_rate(self):
        endpoints = [
            URL_BINANCE_P2P_API,
            "https://p2p.binance.com/bapi/c2c/v1/friendly/c2c/adv/search"
        ]

        payload = {
            "asset": "USDT",
            "fiat": "VES",
            "tradeType": "SELL", 
            "page": 1,
            "rows": 20,
            "filterType": "all",
            "payTypes": [],
            "publisherType": None
        }

        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Content-Type': 'application/json'
        }

        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

        last_exception = None
        for url in endpoints:
            try:
                response = requests.post(url, headers=headers, json=payload, timeout=10, verify=False)
                response.raise_for_status()
                data = response.json()

                if 'data' not in data or not data['data']:
                    raise ValueError(f"Respuesta sin 'data' desde {url}")

                prices = []
                for entry in data['data']:
                    try:
                        adv = entry.get('adv') or {}
                        price = adv.get('price')
                        if price is None:
                            continue
                        prices.append(float(price))
                    except Exception:
                        continue

                if not prices:
                    raise ValueError(f"No se encontraron precios válidos en {url}")

                # elegir el precio más bajo (mejor oferta para quien vende USDT)
                usdt_rate = min(prices)
                return usdt_rate, time.strftime("%H:%M")

            except RequestException as e:
                last_exception = e
                print(f"Error de Red USDT (API) en {url}: {e}")
            except ValueError as e:
                last_exception = e
                print(f"Error de Parseo USDT (API) en {url}: {e}")
            except Exception as e:
                last_exception = e
                print(f"Error Inesperado USDT (API) en {url}: {e}")

        # Si fallaron ambos endpoints, como fallback aproximado usar la tasa BCV (1 USDT ≈ 1 USD)
        try:
            bcv_rate = self.db_manager.get_last_rates()[0]
            if isinstance(bcv_rate, (int, float)) and bcv_rate > 0:
                print("Ambos endpoints fallaron. Usando BCV como aproximación para USDT.")
                return bcv_rate, f"FALLO: APROX BCV ({time.strftime('%H:%M')})"
        except Exception:
            pass

        # último recurso: devolver último USDT conocido de la DB
        print(f"Ambos endpoints fallaron y no hay BCV válido. Excepción última: {last_exception}")
        return self.db_manager.get_last_rates()[1], f"FALLO: RED USDT API ({time.strftime('%H:%M')})"
            

    def fetch_all_rates(self):
        
        bcv_rate_value, bcv_time_str_raw = self.fetch_bcv_rate()
        usdt_rate_value, usdt_time_str_raw = self.fetch_usdt_rate()

        self.bcv_rate = bcv_rate_value
        self.usdt_rate = usdt_rate_value


        bcv_diff, usdt_diff = None, None
        if isinstance(bcv_rate_value, (int, float)) and isinstance(usdt_rate_value, (int, float)):
            bcv_diff, usdt_diff = self.db_manager.log_rates(bcv_rate_value, usdt_rate_value)
        

        bcv_status = self._build_status_string(bcv_rate_value, bcv_time_str_raw, bcv_diff, "BCV")
        
        self.last_bcv_status = bcv_status 
        
        usdt_status = self._build_status_string(usdt_rate_value, usdt_time_str_raw, usdt_diff, "USDT")

        bcv_formatted = f"{bcv_rate_value:.4f}" if isinstance(bcv_rate_value, (int, float)) else "00.0000"
        usdt_formatted = f"{usdt_rate_value:.4f}" if isinstance(usdt_rate_value, (int, float)) else "00.0000"
            
        return bcv_formatted, usdt_formatted, f"{bcv_status} | {usdt_status}"


    def update_ui(self, bcv_rate_str, usdt_rate_str, time_str):
        
        try:
            bcv_rate = float(bcv_rate_str)
        except ValueError:
            bcv_rate = 0.0

        try:
            usdt_rate = float(usdt_rate_str)
        except ValueError:
            usdt_rate = 0.0

        self.bcv_rate = bcv_rate
        self.usdt_rate = usdt_rate

        self.bcv_rate_label.config(text=bcv_rate_str)
        self.bcv_rate_label.config(fg="#00ff99" if bcv_rate > 0.0 else "#ff5555") 

        self.usdt_rate_label.config(text=usdt_rate_str)
        self.usdt_rate_label.config(fg="#f3ba2f" if usdt_rate > 0.0 else "#ff5555")

        rate_difference = usdt_rate - bcv_rate
        rate_diff_str = f"{rate_difference:+.4f}"

        self.diff_value_label.config(text=rate_diff_str)
        
        diff_color = "#00ff99" if rate_difference >= 0 else "#ff5555"
        self.diff_value_label.config(fg=diff_color)

        self.updated_label.config(text=time_str)


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