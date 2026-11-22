from flask import Flask, jsonify

app = Flask(__name__)

CLASSES = [
    {"id": 1, "name": "Morning Yoga", "time": "07:00", "trainer": "Asha", "capacity": 15},
    {"id": 2, "name": "HIIT", "time": "18:00", "trainer": "Rahul", "capacity": 20},
    {"id": 3, "name": "Strength Training", "time": "19:30", "trainer": "Vikram", "capacity": 12},
]


@app.get("/health")
def health():
    return jsonify(status="ok")


@app.get("/classes")
def list_classes():
    return jsonify(CLASSES)