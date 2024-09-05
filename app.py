import os

from flask import Flask, render_template, request, jsonify
import random
import datetime
import requests
import serial
import sqlite3
import threading
import csv
import io
import google.generativeai as genai
from google.generativeai.types import HarmCategory, HarmBlockThreshold

from dotenv import load_dotenv

app = Flask(__name__)

# Load environment variables from .env file
load_dotenv()

# OpenWeatherMap API configuration
OPENWEATHERMAP_API_KEY = os.getenv("OPENWEATHERMAP_API_KEY")
CITY = "Kanpur,IN"

# Database files
MOISTURE_DB = "moisture_data.db"
PUMP_DB = "pump_data.db"

# Serial port configuration
SERIAL_PORT = "COM6"
BAUD_RATE = 9600

# Global variable to track Arduino connection status
ard_status = "Connected"

# Gemini API configuration
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
genai.configure(api_key=GOOGLE_API_KEY)

# Configure the model
generation_config = {
    "temperature": 0.9,
    "top_p": 1,
    "top_k": 1,
    "max_output_tokens": 2048,
}

safety_settings = [
    {
        "category": HarmCategory.HARM_CATEGORY_HARASSMENT,
        "threshold": HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
    },
    {
        "category": HarmCategory.HARM_CATEGORY_HATE_SPEECH,
        "threshold": HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
    },
    {
        "category": HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT,
        "threshold": HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
    },
    {
        "category": HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT,
        "threshold": HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
    },
]

model = genai.GenerativeModel(
    model_name="gemini-1.0-pro",
    generation_config=generation_config,
    safety_settings=safety_settings,
)


def init_databases():
    conn_moisture = sqlite3.connect(MOISTURE_DB)
    c_moisture = conn_moisture.cursor()
    c_moisture.execute(
        """CREATE TABLE IF NOT EXISTS moisture_data
                          (timestamp TEXT, moisture_level INTEGER)"""
    )
    conn_moisture.commit()
    conn_moisture.close()

    conn_pump = sqlite3.connect(PUMP_DB)
    c_pump = conn_pump.cursor()
    c_pump.execute(
        """CREATE TABLE IF NOT EXISTS pump_data
                      (timestamp TEXT, water_used REAL, temperature REAL, humidity REAL)"""
    )
    conn_pump.commit()
    conn_pump.close()


def get_weather_data():
    base_url = "http://api.openweathermap.org/data/2.5/weather"
    params = {
        "q": CITY,
        "appid": OPENWEATHERMAP_API_KEY,
        "units": "metric",  # For Celsius
    }
    try:
        response = requests.get(base_url, params=params)
        if response.status_code == 200:
            data = response.json()
            return {
                "temperature": round(data["main"]["temp"], 1),
                "humidity": round(data["main"]["humidity"], 1),
            }
    except:
        return {
            "temperature": "N/A",
            "humidity": "N/A",
        }


def generate_data():
    # Connect to the moisture database to get the last soil moisture level
    conn_moisture = sqlite3.connect(MOISTURE_DB)
    c_moisture = conn_moisture.cursor()
    c_moisture.execute(
        "SELECT moisture_level FROM moisture_data ORDER BY timestamp DESC LIMIT 1"
    )
    result = c_moisture.fetchone()
    soil_moisture_level = (
        result[0] if result else random.randint(0, 100)
    )  # Fallback to random if no data
    conn_moisture.close()

    # Connect to the pump database to get the sum of water used and the last watering event timestamp
    conn_pump = sqlite3.connect(PUMP_DB)
    c_pump = conn_pump.cursor()

    # Sum of water used
    c_pump.execute("SELECT SUM(water_used) FROM pump_data")
    result = c_pump.fetchone()
    water_usage = (
        round(result[0], 2)
        if result[0] is not None
        else round(random.uniform(0.5, 2.0), 2)
    )  # Fallback to random if no data

    # Last watering event timestamp
    c_pump.execute("SELECT timestamp FROM pump_data ORDER BY timestamp DESC LIMIT 1")
    result = c_pump.fetchone()
    last_watering_event = (
        result[0]
        if result
        else (
            datetime.datetime.now() - datetime.timedelta(minutes=random.randint(5, 120))
        ).strftime("%Y-%m-%d %H:%M:%S")
    )
    conn_pump.close()

    # Get weather data
    weather_data = get_weather_data()
    if weather_data:
        temperature = weather_data["temperature"]
        humidity = weather_data["humidity"]
    else:
        temperature = round(random.uniform(15.0, 30.0), 1)
        humidity = round(random.uniform(40.0, 80.0), 1)

    return {
        "soil_moisture_level": soil_moisture_level,
        "ard_status": ard_status,
        "water_usage": water_usage,
        "last_watering_event": last_watering_event,
        "temperature": temperature,
        "humidity": humidity,
        "CITY": CITY,
    }


def fetch_moisture_data():
    conn = sqlite3.connect(MOISTURE_DB)
    c = conn.cursor()
    now = datetime.datetime.now()
    twenty_four_hours_ago = now - datetime.timedelta(hours=24)
    c.execute(
        """SELECT timestamp, moisture_level 
           FROM moisture_data 
           WHERE timestamp >= ?
           ORDER BY timestamp ASC""",
        (twenty_four_hours_ago.strftime("%Y-%m-%d %H:%M:%S"),),
    )
    data = c.fetchall()
    conn.close()
    return data


def fetch_pump_data():
    conn = sqlite3.connect(PUMP_DB)
    c = conn.cursor()
    now = datetime.datetime.now()
    twenty_four_hours_ago = now - datetime.timedelta(hours=24)
    c.execute(
        """SELECT timestamp, water_used, temperature, humidity 
           FROM pump_data 
           WHERE timestamp >= ?
           ORDER BY timestamp ASC""",
        (twenty_four_hours_ago.strftime("%Y-%m-%d %H:%M:%S"),),
    )
    data = c.fetchall()
    conn.close()
    return data


def generate_csv_data():
    moisture_data = fetch_moisture_data()
    pump_data = fetch_pump_data()

    csv_buffer = io.StringIO()
    csv_writer = csv.writer(csv_buffer)

    csv_writer.writerow(
        ["Timestamp", "Moisture Level", "Water Used", "Temperature", "Humidity"]
    )

    # Create dictionaries for quick lookup
    moisture_dict = {row[0]: row[1] for row in moisture_data}
    pump_dict = {row[0]: row[1:] for row in pump_data}

    # Combine all timestamps
    all_timestamps = sorted(set(moisture_dict.keys()) | set(pump_dict.keys()))

    # Write rows
    for timestamp in all_timestamps:
        moisture_level = moisture_dict.get(timestamp, "")
        pump_data = pump_dict.get(timestamp, ["", "", ""])
        csv_writer.writerow([timestamp, moisture_level] + list(pump_data))

    return csv_buffer.getvalue()


def get_ai_insights(csv_data):
    prompt = f"""
    Analyze the following CSV data for a plant watering system:

    {csv_data}

    Provide insights on the following aspects:
    1. Overall moisture level trends
    2. Watering frequency and amount
    3. Temperature and humidity effects on watering
    4. Any unusual patterns or anomalies
    5. Recommendations for improving plant care based on the data

    Format your response using Markdown for better readability.
    """

    response = model.generate_content(prompt)
    return response.text


def save_moisture_data(moisture_level):
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    moisture_level = round(moisture_level)
    conn = sqlite3.connect(MOISTURE_DB)
    c = conn.cursor()
    c.execute(
        "INSERT INTO moisture_data (timestamp, moisture_level) VALUES (?, ?)",
        (timestamp, moisture_level),
    )
    conn.commit()
    conn.close()


def save_pump_data(water_used):
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    weather_data = get_weather_data()
    if weather_data:
        conn = sqlite3.connect(PUMP_DB)
        c = conn.cursor()
        c.execute(
            "INSERT INTO pump_data (timestamp, water_used, temperature, humidity) VALUES (?, ?, ?, ?)",
            (
                timestamp,
                round(water_used, 2),
                weather_data["temperature"],
                weather_data["humidity"],
            ),
        )
        conn.commit()
        conn.close()


def serial_communication():
    global ard_status
    try:
        ser = serial.Serial(SERIAL_PORT, BAUD_RATE)
        print("Arduino connected.")
        while True:
            if ser.in_waiting > 0:
                line = ser.readline().decode("utf-8").strip()

                # Process moisture level data
                if "Moisture Level:" in line:
                    moisture_level = int(line.split(":")[1].strip())
                    moisture_percent = (moisture_level / 500.0) * 100
                    save_moisture_data(moisture_percent)

                # Process water usage data
                elif "Water Used:" in line:
                    water_used = float(line.split(":")[1].strip())
                    save_pump_data(water_used)

    except serial.SerialException as e:
        if "ClearCommError" in str(e) or "FileNotFoundError" in str(e) or "No such file or directory" in str(e):
            ard_status = "Disconnected"

        print("Arduino disconnected:", e)

    except Exception as e:
        print("Error:", e)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/dashboard")
def dashboard():
    data = generate_data()
    return render_template("dashboard.html", data=data)


@app.route("/graphs")
def graphs():
    moisture_data = fetch_moisture_data()
    pump_data = fetch_pump_data()

    # Prepare data for the charts
    moisture_time = [item[0] for item in moisture_data]
    moisture_level = [item[1] for item in moisture_data]

    pump_time = [item[0] for item in pump_data]
    water_used = [item[1] for item in pump_data]
    temperature = [item[2] for item in pump_data]
    humidity = [item[3] for item in pump_data]

    return render_template(
        "graphs.html",
        moisture_time=moisture_time,
        moisture_level=moisture_level,
        pump_time=pump_time,
        water_used=water_used,
        temperature=temperature,
        humidity=humidity,
    )


@app.route("/ai")
def ai():
    csv_data = generate_csv_data()
    insights = get_ai_insights(csv_data)
    return render_template("ai.html", insights=insights)


@app.route("/chat", methods=["POST"])
def chat():
    user_message = request.json["message"]

    # Check if the message is related to plants or the watering system
    plant_related = (
        model.generate_content(
            f"Please determine if the following message is related to plants or a plant watering system. Answer with 'Yes' if it is related, or 'No' if it is not. Message: {user_message}"
        )
        .text.strip()
        .lower()
    )

    if plant_related == "yes":
        context = """
        You are an AI assistant for a plant watering system. Your role is to provide information and answer questions 
        about plants, plant care, watering systems, and related topics. Use the data from the plant watering system 
        if relevant to the question.
        """
        prompt = f"{context}\n\nHuman: {user_message}\nAI:"
        response = model.generate_content(prompt)
        return jsonify({"response": response.text})
    else:
        return jsonify(
            {
                "response": "I'm sorry, but I can only answer questions related to plants and the watering system."
            }
        )


if __name__ == "__main__":
    # Start the serial communication thread
    serial_thread = threading.Thread(target=serial_communication)
    serial_thread.start()
    app.run(debug=True)
