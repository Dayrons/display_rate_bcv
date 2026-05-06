import tkinter as tk
import threading
import time
import requests
import sqlite3
import urllib3 
import os
import sys

# Intentar configurar el backend de pystray para Ubuntu/Linux
# Priorizamos 'appindicator' pero si fallan las dependencias de sistema, usamos 'gtk'
try:
    import gi
    try:
        gi.require_version('AyatanaAppIndicator3', '0.1')
    except (ValueError, ImportError):
        try:
            gi.require_version('AppIndicator3', '0.1')
        except (ValueError, ImportError):
            # Si no hay AppIndicator, forzamos GTK para que pystray no falle al importar
            os.environ['PYSTRAY_BACKEND'] = 'gtk'
except ImportError:
    pass

from bs4 import BeautifulSoup
from requests.exceptions import RequestException
from datetime import datetime
import json
from pystray import Icon, Menu, MenuItem
from PIL import Image, ImageDraw

# Deshabilitar advertencias de SSL una sola vez al inicio
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

TARGET_HOURS = [5, 13]
CHECK_INTERVAL_SECONDS = 180 
URL_BCV = "https://www.bcv.org.ve/"
URL_BINANCE_P2P_API = "https://p2p.binance.com/bapi/c2c/v2/friendly/c2c/adv/search"

def get_resource_path(relative_path):
    """ Obtiene la ruta absoluta para recursos, compatible con PyInstaller y entorno de desarrollo. """
    try:
        base_path = sys._MEIPASS
    except Exception:
        # En desarrollo, el root es el padre de 'src'
        base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    
    return os.path.join(base_path, relative_path)

ASSETS_DIR = get_resource_path('assets')

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
        self.root.protocol("WM_DELETE_WINDOW", self.hide_window)
        
        # Cargar y preparar iconos
        self.icon_path = os.path.join(ASSETS_DIR, 'coin.png')
        self.window_icon_path = os.path.join(ASSETS_DIR, 'money.png')
        
        try:
            # Usar RGBA para soportar transparencias y tamaño estándar para sistemas Linux
            self.icon_image = Image.open(self.icon_path).convert('RGBA')
            self.tray_icon_img = self.icon_image.resize((32, 32), Image.LANCZOS)
        except Exception as e:
            print(f"Error cargando imagen del icono: {e}")
            self.tray_icon_img = Image.new('RGBA', (32, 32), color=(0, 255, 153, 255))
        
        # Intentar poner el icono a la ventana de Tkinter
        try:
            self.tk_icon = tk.PhotoImage(file=self.window_icon_path)
            self.root.iconphoto(False, self.tk_icon)
        except Exception as e:
            print(f"No se pudo establecer el icono de la ventana: {e}")

        self.tray_icon = None
        self.db_manager = DatabaseManager()
        self.last_update_hour = -1 
        self.usdt_rate = self.db_manager.get_last_rates()[1] 
        self.bcv_rate = self.db_manager.get_last_rates()[0] 
        self.last_bcv_status = "BCV no cargado" 

        self.root.title("Tasa BCV & USDT")
        self.root.geometry("350x300+100+100") 
        self.root.configure(bg="#1a1a1a")
        self.root.pack_propagate(False)
        
        self._offset_x = 0
        self._offset_y = 0

        FONT_DIGITAL_GRANDE = ("Consolas", 14, "bold") 
        FONT_DIGITAL_MEDIA = ("Consolas", 10)
        FONT_DIGITAL_PEQUENA = ("Consolas", 9)
        FONT_DIFERENCIA = ("Consolas", 12, "bold")

        self.bcv_title_label = tk.Label(self.root, text="BCV Oficial (USD)", fg="#cccccc", bg="#1a1a1a", font=FONT_DIGITAL_MEDIA, padx=10, anchor="w")
        self.bcv_title_label.pack(pady=(15, 0), fill="x") 

        self.bcv_rate_label = tk.Label(self.root, text="00.0000", fg="#00ff99", bg="#1a1a1a", font=FONT_DIGITAL_GRANDE, padx=10, pady=3, cursor="hand2")
        self.bcv_rate_label.pack(pady=3, padx=10, fill="x")
        self.bcv_rate_label.bind("<Button-1>", self.copy_to_clipboard)

        self.usdt_title_label = tk.Label(self.root, text="Binance P2P (USDT)", fg="#cccccc", bg="#1a1a1a", font=FONT_DIGITAL_MEDIA, padx=10, anchor="w")
        self.usdt_title_label.pack(pady=(15, 0), fill="x") 

        self.usdt_rate_label = tk.Label(self.root, text="00.0000", fg="#f3ba2f", bg="#1a1a1a", font=FONT_DIGITAL_GRANDE, padx=10, pady=3, cursor="hand2")
        self.usdt_rate_label.pack(pady=3, padx=10, fill="x")
        self.usdt_rate_label.bind("<Button-1>", self.copy_to_clipboard)

        self.diff_title_label = tk.Label(self.root, text="DIFERENCIA (USDT - BCV)", fg="#cccccc", bg="#1a1a1a", font=FONT_DIGITAL_PEQUENA, padx=10, anchor="w")
        self.diff_title_label.pack(pady=(10, 0), fill="x") 

        self.diff_value_label = tk.Label(self.root, text="+00.0000", fg="#44ccff", bg="#1a1a1a", font=FONT_DIFERENCIA, padx=10, pady=3)
        self.diff_value_label.pack(pady=3, padx=10, fill="x")

        self.updated_label = tk.Label(self.root, text="cargando...", fg="#888888", bg="#1a1a1a", font=FONT_DIGITAL_PEQUENA, wraplength=300)
        self.updated_label.pack(pady=(0, 15))

        self.root.bind("<Button-1>", self.on_press)
        self.root.bind("<B1-Motion>", self.on_drag)

        self.create_context_menu()
        self.root.bind("<Button-3>", self.show_context_menu)

        self.start_update_loop()

    def create_context_menu(self):
        """Crea el menú contextual con estilo oscuro y los elementos de la captura."""
        self.context_menu = tk.Menu(self.root, tearoff=0, bg="#1e1e1e", fg="#ffffff", 
                                    activebackground="#333333", activeforeground="#00ff99",
                                    font=("Consolas", 10), bd=0)
        
        items = [
            "/home/user/Documentos/itexon/as-app/lib",
            "52228",
            "005923988890",
            "ps_point__of__sale__inherit",
            "github_pat_11BKQIDSA0zHD3fpCVgvJ7__ekjfvd7psyDa7hyq..."
        ]

        for item in items:
            self.context_menu.add_command(label=item, command=lambda v=item: self.copy_string_to_clipboard(v))

    def show_context_menu(self, event):
        """Muestra el menú contextual en la posición del mouse."""
        try:
            self.context_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.context_menu.grab_release()

    def copy_string_to_clipboard(self, value):
        """Copia un string específico al portapapeles."""
        self.root.clipboard_clear()
        self.root.clipboard_append(value)
        print(f"Copiado al portapapeles: {value}")

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
                print(f"[{time.strftime('%H:%M:%S')}] Hora objetivo BCV alcanzada ({current_hour}:00). Actualizando...")
                self.root.after(0, self.updated_label.config, {"text": "ACTUALIZANDO BCV Y USDT..."})
                bcv_rate, usdt_rate, time_str = self.fetch_all_rates()
                self.root.after(0, self.update_ui, bcv_rate, usdt_rate, time_str)
                if "FALLO" not in time_str:
                    self.last_update_hour = current_hour
            else:
                print(f"[{time.strftime('%H:%M:%S')}] Actualizando USDT.")
                self.root.after(0, self.updated_label.config, {"text": "ACTUALIZANDO USDT..."})
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
        clean_rate_text = rate_text.replace('.', '').replace(',', '.') 
        return float(clean_rate_text)

    def fetch_bcv_rate(self):
        try:
            headers = {'User-Agent': 'Mozilla/5.0'}
            response = requests.get(URL_BCV, headers=headers, timeout=10, verify=False)
            response.raise_for_status() 
            soup = BeautifulSoup(response.content, 'html.parser')
            dolar_div = soup.find('div', id='dolar')
            if not dolar_div:
                return self.db_manager.get_last_rates()[0], "FALLO: Scraping"
            bcv_rate = self._clean_bcv_value(dolar_div)
            return bcv_rate, time.strftime("%H:%M")
        except Exception as e:
            print(f"Error BCV: {e}")
            return self.db_manager.get_last_rates()[0], f"FALLO: {time.strftime('%H:%M')}"

    def fetch_usdt_rate(self):
        payload = {"asset": "USDT", "fiat": "VES", "tradeType": "SELL", "page": 1, "rows": 10, "filterType": "all"}
        headers = {'User-Agent': 'Mozilla/5.0', 'Content-Type': 'application/json'}
        try:
            response = requests.post(URL_BINANCE_P2P_API, headers=headers, json=payload, timeout=10, verify=False)
            response.raise_for_status()
            data = response.json()
            prices = [float(entry['adv']['price']) for entry in data.get('data', []) if 'adv' in entry]
            if not prices:
                raise ValueError("No precios")
            return min(prices), time.strftime("%H:%M")
        except Exception as e:
            print(f"Error USDT: {e}")
            return self.db_manager.get_last_rates()[1], f"FALLO: {time.strftime('%H:%M')}"

    def fetch_all_rates(self):
        bcv_v, bcv_t = self.fetch_bcv_rate()
        usdt_v, usdt_t = self.fetch_usdt_rate()
        self.bcv_rate, self.usdt_rate = bcv_v, usdt_v
        bcv_diff, usdt_diff = self.db_manager.log_rates(bcv_v, usdt_v)
        bcv_status = self._build_status_string(bcv_v, bcv_t, bcv_diff, "BCV")
        self.last_bcv_status = bcv_status 
        usdt_status = self._build_status_string(usdt_v, usdt_t, usdt_diff, "USDT")
        bcv_f = f"{bcv_v:.4f}" if isinstance(bcv_v, (int, float)) else "00.0000"
        usdt_f = f"{usdt_v:.4f}" if isinstance(usdt_v, (int, float)) else "00.0000"
        return bcv_f, usdt_f, f"{bcv_status} | {usdt_status}"

    def update_ui(self, bcv_rate_str, usdt_rate_str, time_str):
        self.bcv_rate_label.config(text=bcv_rate_str)
        self.usdt_rate_label.config(text=usdt_rate_str)
        try:
            rate_difference = float(usdt_rate_str) - float(bcv_rate_str)
            self.diff_value_label.config(text=f"{rate_difference:+.4f}", fg="#00ff99" if rate_difference >= 0 else "#ff5555")
        except: pass
        self.updated_label.config(text=time_str)

    def on_press(self, event):
        self._offset_x, self._offset_y = event.x, event.y

    def on_drag(self, event):
        x = self.root.winfo_pointerx() - self._offset_x
        y = self.root.winfo_pointery() - self._offset_y
        self.root.geometry(f"+{x}+{y}")

    def hide_window(self):
        """Oculta la ventana y activa el icono en el área de notificación."""
        self.root.withdraw()
        
        # En Ubuntu/GNOME, reconstruir el icono asegura que el menú se registre correctamente
        if self.tray_icon is not None:
            try:
                self.tray_icon.stop()
            except:
                pass

        # Obtener valores actuales para el menú informativo
        bcv_text = f"BCV: {self.bcv_rate:.4f}" if isinstance(self.bcv_rate, (int, float)) else "BCV: --"
        usdt_text = f"USDT: {self.usdt_rate:.4f}" if isinstance(self.usdt_rate, (int, float)) else "USDT: --"

        # Definir opciones del menú con información útil (ítems desactivados para información)
        menu_options = Menu(
            MenuItem(bcv_text, lambda: None, enabled=False),
            MenuItem(usdt_text, lambda: None, enabled=False),
            Menu.SEPARATOR,
            MenuItem('Abrir Ventana', self.show_window, default=True),
            MenuItem('Salir', self.quit_app)
        )
        
        # Título simple y nombre de ID único para DBus
        self.tray_icon = Icon(
            "tasa_bcv_usdt_app", 
            self.tray_icon_img, 
            title="Tasa BCV y USDT", 
            menu=menu_options
        )
        
        # Ejecutar en un hilo separado
        threading.Thread(target=self.tray_icon.run, daemon=True).start()

    def show_window(self, icon=None, item=None):
        """Restaura la ventana y detiene el icono de la bandeja."""
        if icon:
            icon.stop()
        elif self.tray_icon:
            try:
                self.tray_icon.stop()
            except:
                pass
            
        self.tray_icon = None
        
        # Restaurar ventana con prioridad y asegurar el foco
        self.root.after(0, self.root.deiconify)
        self.root.after(10, self.root.lift)
        self.root.after(50, lambda: self.root.attributes('-topmost', True))
        self.root.after(100, lambda: self.root.attributes('-topmost', False))
        self.root.after(150, self.root.focus_force)

    def quit_app(self, icon=None, item=None):
        """Cierra la aplicación de forma definitiva."""
        print("Cerrando aplicación...")
        try:
            if icon:
                icon.stop()
            if self.tray_icon:
                self.tray_icon.stop()
        except Exception as e:
            print(f"Error al detener tray icon: {e}")
            
        # Intentar cerrar Tkinter de forma limpia
        try:
            self.root.quit()
            self.root.destroy()
        except:
            pass
            
        # Forzar la terminación del proceso para evitar iconos fantasma en Ubuntu
        time.sleep(0.2)
        os._exit(0)
    
    def copy_to_clipboard(self, event):
        label = event.widget
        monto = label.cget("text")
        self.root.clipboard_clear()
        self.root.clipboard_append(monto)
        original_color = label.cget("fg")
        label.config(fg="#ffffff")
        self.root.after(200, lambda: label.config(fg=original_color))


if __name__ == "__main__":
    app_root = tk.Tk()
    widget = RateWidget(app_root) 
    app_root.mainloop()
