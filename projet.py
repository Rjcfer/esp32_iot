from microdot import Microdot, Response
import network
import time
import _thread
from neopixel import NeoPixel
from machine import Pin, I2C, SoftI2C
import ssd1306
import dht
import urequests
import config  # Importer le fichier config

# === CONFIGURATION ===
WIFI_SSID = config.WIFI_SSID
WIFI_PASSWORD = config.WIFI_PASSWORD
AP_SSID = config.AP_SSID
AP_PASSWORD = config.AP_PASSWORD
THINGSPEAK_WRITE_API_KEY = config.THINGSPEAK_WRITE_API_KEY
THINGSPEAK_READ_API_KEY = config.THINGSPEAK_READ_API_KEY
CHANNEL_ID = config.CHANNEL_ID
SEND_INTERVAL = config.SEND_INTERVAL

# === INIT HARDWARE ===
NUM_LEDS = 12
np = NeoPixel(Pin(23), NUM_LEDS)
dht_sensor = dht.DHT11(Pin(27))
button = Pin(0, Pin.IN, Pin.PULL_UP)
i2c = SoftI2C(scl=Pin(22), sda=Pin(21))
oled = ssd1306.SSD1306_I2C(128, 32, i2c)
led_strip=NeoPixel(Pin(23),12)

# === GLOBAL VARIABLES ===
r = 0
g = 0
b = 0
current = 12
history = []  # Liste des mesures

# === Led control ==
def trun_on_LEDs():
    global current,r,g,b
    for i in range(12):
        if i < current:
            led_strip[i] = (r,g,b)
        else:
            led_strip[i] = (0,0,0)
    led_strip.write()
    
# === WiFi setup (STA + AP) ===
def setup_network():
    sta = network.WLAN(network.STA_IF)
    sta.active(True)
    sta.connect(WIFI_SSID, WIFI_PASSWORD)
    for _ in range(10):
        if sta.isconnected():
            break
        print("Connecting to WiFi...")
        time.sleep(1)
    if sta.isconnected():
        print("Connected:", sta.ifconfig())
    else:
        print("WiFi STA failed")

    ap = network.WLAN(network.AP_IF)
    ap.active(True)
    ap.config(essid=AP_SSID, password=AP_PASSWORD, authmode=3)
    while not ap.active():
        time.sleep(0.5)
    print("AP active:", ap.ifconfig())

# === Capteur DHT ===
def read_sensor():
    try:
        dht_sensor.measure()
        temp = dht_sensor.temperature()
        hum = dht_sensor.humidity()
        return temp, hum
    except:
        return None, None

def send_to_thingspeak(temp, hum):
    try:
        url = f"http://api.thingspeak.com/update?api_key={THINGSPEAK_WRITE_API_KEY}&field1={temp}&field2={hum}"
        urequests.get(url)
        print(f"Sent: {temp}°C, {hum}%")
        history.append((time.localtime(), temp, hum))
        if len(history) > 20:
            history.pop(0)
    except Exception as e:
        print(f"Error sending to ThingSpeak: {e}")

# === Webserver ===
app = Microdot()
Response.default_content_type = 'text/html'

html_site = """<html>
<head>
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>ESP32 Control</title>
</head>
<body>
<h1>ESP32 Control</h1>
<p>Status: {status}</p>
<h3>LED Control</h3>
<form action="/color">
  <label for="r" style="color: red;">RED:</label>
  <input type="range" name="r" min="0" max="255" value="0"><br>
  <label for="g" style="color: green;">GREEN:</label>
  <input type="range" name="g" min="0" max="255" value="0"><br>
  <label for="b" style="color: blue;">BLUE:</label>
  <input type="range" name="b" min="0" max="255" value="0"><br>
  <input type="submit" value="Choose">
</form>

<h3>LED Count</h3>
<form action="/count">
  <input type="number" name="n" min="0" max="12" value="12">
  <input type="submit" value="Update">
</form>

<h3>Text Display</h3>
<form action="/text">
  <input type="text" name="t">
  <input type="submit" value="Show">
</form>

<h3><a href="/data">View Last 20 Measurements</a></h3>

</body>
</html>"""

@app.route('/')
def start(request):
    return html_site.format(status='Hello'), 200, {'Content-Type': 'text/html'}

@app.route('/button1')
def button_pressed(request):
    print('Button Pressed!')
    return html_site.format(status='Button Pressed'), 200, {'Content-Type': 'text/html'}

@app.route('/color')
def set_color(request):
    global r, g, b
    r = int(request.args.get('r'))
    g = int(request.args.get('g'))
    b = int(request.args.get('b'))
    trun_on_LEDs()
    return html_site.format(status=f'Color set to ({r}, {g}, {b})'), 200, {'Content-Type': 'text/html'}

@app.route('/count')
def set_count(request):
    global current
    current = int(request.args.get('n'))
    trun_on_LEDs()
    return html_site.format(status=f'LED count set to {current}'), 200, {'Content-Type': 'text/html'}

@app.route('/text')
def show_text(request):
    text_on_display = request.args.get('t')
    oled.fill(0)
    oled.text(text_on_display, 0, 0)
    oled.show()
    return html_site.format(status='Text displayed on OLED'), 200, {'Content-Type': 'text/html'}

@app.route('/data')
def data_page(request):
    try:
        url = f"http://api.thingspeak.com/channels/{CHANNEL_ID}/feeds.json?api_key={THINGSPEAK_READ_API_KEY}&results=20"
        response = urequests.get(url)
        data = response.json()
        response.close()

        feeds = data.get("feeds", [])
        rows = ""
        for feed in reversed(feeds):
            timestamp = feed["created_at"].replace("T", " ").replace("Z", "")
            temp = feed.get("field1", "N/A")
            hum = feed.get("field2", "N/A")
            rows += f"<tr><td>{timestamp}</td><td>{temp}°C</td><td>{hum}%</td></tr>\n"

        html = f"""
        <html>
        <head>
        <title>Measurements</title>
        <style>
            body {{ font-family: sans-serif; background: #f0f0f0; padding: 20px; }}
            table {{ border-collapse: collapse; width: 100%; background: white; box-shadow: 2px 2px 10px #ccc; }}
            th, td {{ border: 1px solid #ddd; padding: 8px; text-align: center; }}
            th {{ background: #4CAF50; color: white; }}
        </style>
        </head>
        <body>
        <h2>Last 20 Measurements</h2>
        <table>
            <tr><th>Timestamp</th><th>Temperature</th><th>Humidity</th></tr>
            {rows}
        </table>
        <h3><a href="/">Back to Home</a></h3>
        </body>
        </html>
        """
        return html
    except Exception as e:
        print(f"Error fetching data: {e}")
        return f"<html><body><h2>Error retrieving data: {e}</h2></body></html>"

# === Web server thread ===
def start_webserver():
    _thread.start_new_thread(lambda: app.run(port=80), ())

# === Main logic ===
def main_loop():
    last_send = time.time()
    while True:
        now = time.time()
        if now - last_send >= SEND_INTERVAL:
            temp, hum = read_sensor()
            if temp is not None:
                send_to_thingspeak(temp, hum)
            last_send = now
        time.sleep(0.1)

def start_sensor_loop():
    _thread.start_new_thread(main_loop, ())

# === MAIN ===
setup_network()
start_sensor_loop()  
app.run(port=80) 