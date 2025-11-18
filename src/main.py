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

CHECK_INTERVAL_SECONDS = 180 

URL_BCV = "https://www.bcv.org.ve/"
URL_BINANCE_P2P = "https://p2p.binance.com/es/trade/all-payments/USDT?fiat=VES"
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
        """Obtiene la última tasa BCV y USDT registrada."""
        try:

            with sqlite3.connect(self.DB_NAME) as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT bcv_rate, usdt_rate FROM rate_log ORDER BY id DESC LIMIT 1')
                result = cursor.fetchone()
                # Devuelve (BCV, USDT) o (0.0, 0.0) si no hay registros.
                return result if result else (0.0, 0.0)
        except Exception as e:
            print(f"Error al obtener las últimas tasas: {e}")
            return (0.0, 0.0)


    def log_rates(self, bcv_rate, usdt_rate):
        """Registra las nuevas tasas BCV y USDT si hay cambios."""
        last_bcv_rate, last_usdt_rate = self.get_last_rates()
        
        is_first_entry = (last_bcv_rate == 0.0)
        
        # Calcular diferencias
        bcv_difference = 0.0 if is_first_entry else bcv_rate - last_bcv_rate
        usdt_difference = 0.0 if is_first_entry else usdt_rate - last_usdt_rate

        # Verificar si ambas tasas son idénticas a las últimas para evitar spam de DB
        if not is_first_entry and abs(bcv_rate - last_bcv_rate) < 1e-9 and abs(usdt_rate - last_usdt_rate) < 1e-9: 
            consult_date = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            print(f"[{consult_date}] Ambas tasas iguales a las últimas. No se registra en DB.")
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
                print(f"[{consult_date}] Tasas registradas: BCV={bcv_rate:.4f}, USDT={usdt_rate:.4f}.")
                return bcv_difference, usdt_difference
        except Exception as e:
            print(f"Error al registrar en la base de datos: {e}")
            return None, None


class RateWidget:
    def __init__(self, root):
        self.root = root

        self.db_manager = DatabaseManager()

        self.last_update_hour = -1 
        self.usdt_rate = self.db_manager.get_last_rates()[1] # Inicializa con última tasa USDT
        self.bcv_rate = self.db_manager.get_last_rates()[0] # Inicializa con última tasa BCV


        self.root.title("Tasa BCV & USDT")

        # Nuevo tamaño para acomodar ambas tasas
        self.root.geometry("600x630+100+100") 
        self.root.configure(bg="#1a1a1a")

        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        

        self._offset_x = 0
        self._offset_y = 0

 
        
    
        FONT_DIGITAL_GRANDE = ("Consolas", 32, "bold") 
        FONT_DIGITAL_MEDIA = ("Consolas", 14)
        FONT_DIGITAL_PEQUENA = ("Consolas", 10)
        FONT_DIFERENCIA = ("Consolas", 14, "bold")


        # --- BCV Section ---
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
            padx=20,
            pady=5
        )
        self.bcv_rate_label.pack(pady=5, padx=20, fill="x")


        # --- USDT Section ---
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
            fg="#f3ba2f", # Color Binance
            bg="#1a1a1a",
            font=FONT_DIGITAL_GRANDE,
            padx=20,
            pady=5
        )
        self.usdt_rate_label.pack(pady=5, padx=20, fill="x")

        # --- Diferencia Section ---
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
            padx=20,
            pady=5
        )
        self.diff_value_label.pack(pady=5, padx=20, fill="x")


        # --- Updated Label ---
        self.updated_label = tk.Label(
            self.root, 
            text="cargando...", 
            fg="#888888", 
            bg="#1a1a1a", 
            font=FONT_DIGITAL_PEQUENA,
            wraplength=620,
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

        self.quit_button.place(x=510, y=10) 

        self.root.bind("<Button-1>", self.on_press)
        self.root.bind("<B1-Motion>", self.on_drag)

        self.start_update_loop()

    def start_update_loop(self):

        thread = threading.Thread(target=self.update_loop, daemon=True)
        thread.start()

    def update_loop(self):
        # Primer arranque
        bcv_rate, usdt_rate, time_str = self.fetch_all_rates()
        self.root.after(0, self.update_ui, bcv_rate, usdt_rate, time_str)

        current_hour = time.localtime().tm_hour
        if "ERROR" not in time_str and "FALLO" not in time_str:
            self.last_update_hour = current_hour
            
        time.sleep(CHECK_INTERVAL_SECONDS)

        while True:
            current_hour = time.localtime().tm_hour
            
            # Verificación de hora objetivo (para BCV)
            is_target_hour = current_hour in TARGET_HOURS

            has_not_updated_this_hour = current_hour != self.last_update_hour

            # La tasa USDT se refresca cada CHECK_INTERVAL_SECONDS. 
            # La tasa BCV sólo se refresca en las horas objetivo O en la carga inicial.

            if is_target_hour and has_not_updated_this_hour:
                print(f"[{time.strftime('%H:%M:%S')}] Hora objetivo BCV alcanzada ({current_hour}:00). Iniciando scraping.")
                
                bcv_rate, usdt_rate, time_str = self.fetch_all_rates()
                self.root.after(0, self.update_ui, bcv_rate, usdt_rate, time_str)
                
                
                if "ERROR" not in time_str and "FALLO" not in time_str:
                    self.last_update_hour = current_hour
            else:
                # Actualización de USDT cada 3 minutos, independientemente de la hora BCV
                print(f"[{time.strftime('%H:%M:%S')}] Actualizando sólo USDT (BCV estático).")
                usdt_rate, time_str_usdt = self.fetch_usdt_rate()
                
                # Usar la BCV rate previamente cargada o de la última consulta exitosa.
                bcv_rate = self.bcv_rate 

                # Solo actualiza la UI y log si la USDT cambió (la BCV se mantiene)
                self.root.after(0, self.update_ui, bcv_rate, usdt_rate, time_str_usdt) 

            
            time.sleep(CHECK_INTERVAL_SECONDS)

    def _clean_bcv_value(self, element):
        """Limpia y convierte el valor BCV de un elemento HTML."""
        if not element:
            raise ValueError("Elemento BCV no encontrado.")

        rate_text = element.find('strong').text.strip()
        clean_rate_text = rate_text.replace('.', '') 
        clean_rate_text = clean_rate_text.replace(',', '.') 
        
        return float(clean_rate_text)

    def _clean_usdt_value(self, element):
        """Limpia y convierte el valor USDT de un elemento HTML de Binance."""
        if not element:
            raise ValueError("Elemento USDT no encontrado.")

        # Binance P2P usa una clase específica para el precio
        # Buscamos un span con el texto que parece un precio (contiene punto o coma y al menos 4 dígitos)
        price_span = element.find('div', class_='css-1m1f8yj')

        if not price_span:
             raise ValueError("No se encontró el precio USDT en el HTML de Binance.")
             
        rate_text = price_span.text.strip().split('VES')[0] # Obtener solo el número antes de "VES"
        
        # Eliminar comas de miles y reemplazar coma decimal por punto
        clean_rate_text = rate_text.replace(',', '').replace('.', '') # Eliminar todos los separadores

        # Asumir que los últimos 4 dígitos son decimales, o usar la lógica si es que Binance P2P usa el punto como separador decimal.
        # Basado en la estructura de Binance P2P, a menudo el precio aparece sin separador de miles y con punto decimal.
        try:
             # Intenta convertir directamente
             return float(rate_text.replace(',', ''))
        except ValueError:
             # Si falla, aplica lógica de reemplazo para compatibilidad con la estructura común de Venezuela (punto de miles, coma decimal)
             clean_rate_text = rate_text.replace('.', '').replace(',', '.')
             return float(clean_rate_text)


    def fetch_bcv_rate(self):
        """Obtiene solo la tasa BCV."""
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
                return self.db_manager.get_last_rates()[0], "FALLO: BCV (Usando última tasa)"

            bcv_rate = self._clean_bcv_value(dolar_div)
            return bcv_rate, time.strftime("%H:%M")

        except RequestException as e:
            print(f"Error de Red BCV: {e}")
            return self.db_manager.get_last_rates()[0], "FALLO: RED"
        except ValueError as e:
            print(f"Error de Parseo BCV: {e}")
            return self.db_manager.get_last_rates()[0], "FALLO: PARSEO"
        except Exception as e:
            print(f"Error Inesperado BCV: {e}")
            return self.db_manager.get_last_rates()[0], "FALLO: GEN"
            

    def fetch_usdt_rate(self):
        
        payload = {
            "asset": "USDT",
            "fiat": "VES",
            "tradeType": "SELL", 
            "page": 1,
            "rows": 10,
            "filterType": "all" 
        }

        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                'Content-Type': 'application/json'
            }
            
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

            # Usar POST para la API
            response = requests.post(
                URL_BINANCE_P2P_API, 
                headers=headers, 
                json=payload, 
                timeout=10, 
                verify=False
            )
            response.raise_for_status() 
            
            data = response.json()
            
            if 'data' not in data or not data['data']:
                raise ValueError("Respuesta de la API de Binance P2P no tiene datos ('data' vacío).")
            
            # Buscamos el precio del primer anuncio (que suele ser el más bajo/competitivo para la venta)
            first_ad = data['data'][0]
            
            if 'adv' not in first_ad or 'price' not in first_ad['adv']:
                raise ValueError("Estructura de la respuesta de Binance P2P inesperada (falta 'adv' o 'price').")
                
            usdt_rate = float(first_ad['adv']['price'])
            
            return usdt_rate, time.strftime("%H:%M")


        except RequestException as e:
            print(f"Error de Red USDT (API): {e}")
            return self.db_manager.get_last_rates()[1], "FALLO: RED USDT API"
        except ValueError as e:
            print(f"Error de Parseo USDT (API): {e}")
            return self.db_manager.get_last_rates()[1], "FALLO: PARSEO USDT API"
        except Exception as e:
            print(f"Error Inesperado USDT (API): {e}")
            return self.db_manager.get_last_rates()[1], "FALLO: GEN USDT API"


        except RequestException as e:
            print(f"Error de Red USDT: {e}")
            return self.db_manager.get_last_rates()[1], "FALLO: RED USDT"
        except ValueError as e:
            print(f"Error de Parseo USDT: {e}")
            return self.db_manager.get_last_rates()[1], "FALLO: PARSEO USDT"
        except Exception as e:
            print(f"Error Inesperado USDT: {e}")
            return self.db_manager.get_last_rates()[1], "FALLO: GEN USDT"
            


        except RequestException as e:
            print(f"Error de Red USDT: {e}")
            return self.db_manager.get_last_rates()[1], "FALLO: RED USDT"
        except ValueError as e:
            print(f"Error de Parseo USDT: {e}")
            return self.db_manager.get_last_rates()[1], "FALLO: PARSEO USDT"
        except Exception as e:
            print(f"Error Inesperado USDT: {e}")
            return self.db_manager.get_last_rates()[1], "FALLO: GEN USDT"


    def fetch_all_rates(self):
        """Obtiene ambas tasas y actualiza la base de datos si es necesario."""
        
        # Obtener BCV
        bcv_rate_value, bcv_time_str = self.fetch_bcv_rate()
        
        # Obtener USDT
        usdt_rate_value, usdt_time_str = self.fetch_usdt_rate()

        # Almacenar en atributos para usar en actualizaciones solo USDT
        self.bcv_rate = bcv_rate_value
        self.usdt_rate = usdt_rate_value


        # --- Manejo de la base de datos ---
        # Solo loguea si ambas son números y al menos una cambió
        if isinstance(bcv_rate_value, (int, float)) and isinstance(usdt_rate_value, (int, float)):
            bcv_diff, usdt_diff = self.db_manager.log_rates(bcv_rate_value, usdt_rate_value)
        else:
            bcv_diff, usdt_diff = None, None

        
        # --- Formato y mensajes de diferencia BCV ---
        bcv_formatted = f"{bcv_rate_value:.4f}" if isinstance(bcv_rate_value, (int, float)) else "00.0000"
        
        if bcv_diff is not None and bcv_diff != 0.0:
            simbolo_bcv = "↑" if bcv_diff > 0 else "↓"
            bcv_time_str = f"Act: {bcv_time_str} ({simbolo_bcv} {abs(bcv_diff):.4f})"
        else:
             bcv_time_str = f"Act: {bcv_time_str}"
        
        # --- Formato y mensajes de diferencia USDT ---
        usdt_formatted = f"{usdt_rate_value:.4f}" if isinstance(usdt_rate_value, (int, float)) else "00.0000"

        if usdt_diff is not None and usdt_diff != 0.0:
            simbolo_usdt = "↑" if usdt_diff > 0 else "↓"
            usdt_time_str = f"USDT Act: {usdt_time_str} ({simbolo_usdt} {abs(usdt_diff):.4f})"
        else:
            usdt_time_str = f"USDT Act: {usdt_time_str}"
            
        # Devolver las tasas formateadas y el mensaje combinado de última actualización
        return bcv_formatted, usdt_formatted, f"{bcv_time_str} | {usdt_time_str}"


    def update_ui(self, bcv_rate_str, usdt_rate_str, time_str):
        """Actualiza la interfaz con ambas tasas y la diferencia."""
        
        # Conversión segura de string a float para el cálculo de diferencia
        try:
            bcv_rate = float(bcv_rate_str)
        except ValueError:
            bcv_rate = 0.0

        try:
            usdt_rate = float(usdt_rate_str)
        except ValueError:
            usdt_rate = 0.0

        # Almacena los valores como float para el próximo ciclo
        self.bcv_rate = bcv_rate
        self.usdt_rate = usdt_rate

        # --- BCV UI ---
        self.bcv_rate_label.config(text=bcv_rate_str)
        self.bcv_rate_label.config(fg="#00ff99" if bcv_rate > 0.0 else "#ff5555")

        # --- USDT UI ---
        self.usdt_rate_label.config(text=usdt_rate_str)
        self.usdt_rate_label.config(fg="#f3ba2f" if usdt_rate > 0.0 else "#ff5555")

        # --- Diferencia UI ---
        rate_difference = usdt_rate - bcv_rate
        rate_diff_str = f"{rate_difference:+.4f}"

        self.diff_value_label.config(text=rate_diff_str)
        
        # Color para la diferencia: verde si USDT es más alto, rojo si es más bajo (no debería pasar)
        diff_color = "#00ff99" if rate_difference >= 0 else "#ff5555"
        self.diff_value_label.config(fg=diff_color)

        # --- Última actualización UI ---
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