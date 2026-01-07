from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, time
import re
import pytz

app = Flask(__name__)

app.config['SECRET_KEY'] = 'ParkTrack'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

phtime = pytz.timezone("Asia/Manila")

class VehicleEntry(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    plate_number = db.Column(db.String(7), nullable=False)
    slot_number = db.Column(db.String(3), nullable=False)
    entry_time = db.Column(db.DateTime, default = lambda: datetime.now(phtime))
    exit_time = db.Column(db.DateTime)

    def __repr__(self):
        return f"<Vehicle {self.plate_number} in slot {self.slot_number}>"

with app.app_context():
    db.create_all()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/enter', methods=["GET", "POST"])
def enter():
    if request.method == "POST":
        plate = request.form.get("licensePlate").strip().upper()
        slot = request.form.get("slotNumber").strip().upper()

        all_slots = ["P1", "P2", "P3", "P4", "P5", "P6", "P7", "P8", "P9", "P10"]

        if slot not in all_slots:
            flash("Slot unrecognized.", "error")
            return redirect(url_for("enter"))
        
        if not re.fullmatch(r"[A-Z]{3}[0-9]{4}", plate): 
            flash("Invalid license plate format. Use 3 letters + 4 digits (e.g. ABC1234).", "error") 
            return redirect(url_for("enter"))
        existing = VehicleEntry.query.filter_by(plate_number=plate, exit_time = None).first()
        used_slot = VehicleEntry.query.filter_by(slot_number = slot, exit_time = None).first()
        if existing:
            flash("This vehicle is already parked.", "error")
            return redirect(url_for("enter"))
        if used_slot:
            flash("Slot already in use.", "error")
            return redirect(url_for("enter"))
        new_entry = VehicleEntry(
        plate_number=plate,
        slot_number=slot,
        entry_time=datetime.now(phtime)
        )
        
        new_entry = VehicleEntry(plate_number=plate, slot_number=slot)
        db.session.add(new_entry)
        db.session.commit()

        flash("Vehicle parked successfully!", "success")
        return redirect(url_for("enter"))

    return render_template("enter.html")

@app.route("/exit", methods=["GET", "POST"])
def exit():
    if request.method == "POST":
        plate = request.form.get("licensePlate").strip().upper()

        if not re.fullmatch(r"[A-Z]{3}[0-9]{4}", plate):
            flash("Invalid license plate format. Use 3 letters + 4 digits (e.g. ABC1234).", "error")
            return redirect(url_for("exit"))

        existing = VehicleEntry.query.filter_by(plate_number=plate, exit_time=None).first()
        if not existing:
            flash("This vehicle does not exist or has already exited", "error")
            return redirect(url_for("exit"))

        exit_time = datetime.now(phtime)
        entry_time = existing.entry_time

        # Timezone mismatch fix
        if entry_time.tzinfo is None:
            # If entry_time is naive, assume it was saved in Asia/Manila
            entry_time = phtime.localize(entry_time)
        else:
            # If entry_time is aware, convert it to Asia/Manila
            entry_time = entry_time.astimezone(phtime)

        duration_minutes = (exit_time - entry_time).total_seconds() / 60
        hours = int(duration_minutes // 60)
        minutes = int(duration_minutes % 60)
        whl_dur = f"{hours} hours and {minutes} minutes"
        fee = (duration_minutes/60) * 50

        existing.exit_time = exit_time
        db.session.commit()

        flash(f"Vehicle {plate} exited successfully. Duration: {whl_dur}, Fee = {fee} pesos.", "success")
        return redirect(url_for("exit"))

    return render_template("exit.html")

@app.route('/viewcurrent')
def viewcurrent():
    parked_vehicles = VehicleEntry.query.filter_by(exit_time = None).all()

    used_slots = [vehicle.slot_number for vehicle in parked_vehicles]

    all_slots = ["P1", "P2", "P3", "P4", "P5", "P6", "P7", "P8", "P9", "P10"]

    available_slots = [slot for slot in all_slots if slot not in used_slots]

    vehicles = [ 
        {
            "plate":vehicle.plate_number,
            "spot":vehicle.slot_number,
            "time":vehicle.entry_time.strftime("%Y-%m-%d %H:%M:%S")
        }
        for vehicle in parked_vehicles
    ]
    slots = [{"name": s} for s in available_slots]

    return render_template('viewcurrent.html', vehicles=vehicles, slots=slots)

@app.route('/adminlogin', methods=["GET", "POST"])
def adminlogin():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")

        if username == "admin" and password == "password123":
            return redirect(url_for("reports"))
        else:
            return redirect(url_for("adminlogin"))

    return render_template("adminlogin.html")

@app.before_request
def daily_cleanup():
    now = datetime.now(phtime)
    if now.hour == 0 and now.minute == 0:
        VehicleEntry.query.filter(VehicleEntry.exit_time.isnot(None)).delete()
        db.session.commit()

@app.route('/reports')
def reports():
    now = datetime.now(phtime)
    day_start = datetime.combine(now.date(), time.min).replace(tzinfo=phtime)
    day_end = datetime.combine(now.date(), time.max).replace(tzinfo=phtime)

    all_entries_today = VehicleEntry.query.filter(
        VehicleEntry.entry_time >= day_start,
        VehicleEntry.entry_time <= day_end
        ).count()

    vehicle_entries_today = VehicleEntry.query.filter( 
        (VehicleEntry.entry_time >= day_start) & (VehicleEntry.entry_time <= day_end) |
        (VehicleEntry.exit_time == None)
        ).all()

    duration = []
    vehicles = []

    for v in vehicle_entries_today:
        entry_local = v.entry_time.astimezone(phtime)
        exit_local = v.exit_time.astimezone(phtime) if v.exit_time else None

        if exit_local:
            dur = (exit_local - entry_local).total_seconds() / 60
            duration.append(dur)
        else:
            dur = (now - entry_local).total_seconds() / 60

        vehicles.append({
            "plate": v.plate_number,
            "spot": v.slot_number,
            "entry": entry_local.strftime("%Y-%m-%d %H:%M:%S"),
            "exit": exit_local.strftime("%Y-%m-%d %H:%M:%S") if exit_local else "Still Parked",
            "duration": f"{int(dur // 60)} hours and {int(dur % 60)} minutes"
        })

    average_duration = round(sum(duration) / len(duration), 2) if duration else 0

    return render_template("reports.html", vehicles=vehicles, average_duration=average_duration, total_entries=all_entries_today)

if __name__ == "__main__": 
    app.run(debug=True)