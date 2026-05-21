import os
from datetime import date
from functools import wraps

from dotenv import load_dotenv
from flask import (Flask, flash, redirect, render_template,
                   request, session, url_for)

import database as db

load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-change-me")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "changeme")

db.init_db()

@app.template_filter("strptime_weekday")
def strptime_weekday(date_str):
    return date.fromisoformat(date_str).weekday()


# ---------------------------------------------------------------------------
# Auth helper
# ---------------------------------------------------------------------------

def admin_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get("admin"):
            return redirect(url_for("admin_login"))
        return f(*args, **kwargs)
    return wrapper


# ---------------------------------------------------------------------------
# Student routes
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    today = date.today().isoformat()
    cameras = db.get_cameras_with_status(today)
    calendar_rows, calendar_dates = db.get_calendar_data(14)
    return render_template("index.html", cameras=cameras, today=today,
                           calendar_rows=calendar_rows, calendar_dates=calendar_dates)


@app.route("/reserve", methods=["GET", "POST"])
def reserve():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        netid = request.form.get("netid", "").strip().lower()
        camera_id = request.form.get("camera_id", type=int)
        pickup = request.form.get("pickup_date", "")

        if not all([name, netid, camera_id, pickup]):
            flash("Please fill in all fields.", "error")
            return redirect(url_for("reserve"))

        from datetime import timedelta
        if pickup < (date.today() - timedelta(days=1)).isoformat():
            flash("Pickup date cannot be in the past.", "error")
            return redirect(url_for("reserve"))

        if db.student_has_active(netid):
            flash("You already have an active reservation or checked-out camera. "
                  "You cannot make another until it is returned.", "error")
            return redirect(url_for("reserve"))

        if not db.camera_available(camera_id, pickup,
                                   (date.fromisoformat(pickup).__add__(
                                       __import__("datetime").timedelta(days=2)
                                   )).isoformat()):
            flash("That camera is not available on the selected date. "
                  "Please choose another camera or date.", "error")
            return redirect(url_for("reserve"))

        db.create_reservation(camera_id, name, netid, pickup)
        flash("Reservation confirmed!", "success")
        return redirect(url_for("my_reservation", netid=netid))

    today = date.today().isoformat()
    cameras = db.get_cameras_with_status(today)
    return render_template("reserve.html", cameras=cameras, today=today)


@app.route("/my-reservation")
def my_reservation():
    netid = request.args.get("netid", "").strip().lower()
    reservation = db.get_reservation_by_netid(netid) if netid else None
    return render_template("my_reservation.html", reservation=reservation, netid=netid,
                           today=date.today().isoformat())


@app.route("/checkin", methods=["GET", "POST"])
def checkin():
    reservation = None
    netid = ""
    if request.method == "POST":
        netid = request.form.get("netid", "").strip().lower()
        if netid and request.form.get("action") == "return":
            res = db.get_reservation_by_netid(netid)
            if res and res["status"] == "checked_out":
                db.set_status(res["id"], "returned")
                flash(f"Camera {res['camera_number']} checked in. Thanks!", "success")
                return redirect(url_for("index"))
        if netid:
            reservation = db.get_reservation_by_netid(netid)
    return render_template("checkin.html", reservation=reservation, netid=netid,
                           today=date.today().isoformat())


@app.route("/cancel/<int:res_id>", methods=["POST"])
def cancel(res_id):
    netid = request.form.get("netid", "").strip().lower()
    db.cancel_reservation(res_id, netid=netid)
    flash("Reservation cancelled.", "info")
    return redirect(url_for("index"))


# ---------------------------------------------------------------------------
# Admin routes
# ---------------------------------------------------------------------------

@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        if request.form.get("password") == ADMIN_PASSWORD:
            session["admin"] = True
            return redirect(url_for("admin_dashboard"))
        flash("Incorrect password.", "error")
    return render_template("admin_login.html")


@app.route("/admin/logout")
def admin_logout():
    session.pop("admin", None)
    return redirect(url_for("index"))


@app.route("/admin")
@admin_required
def admin_dashboard():
    today = date.today().isoformat()
    reservations = db.get_all_reservations()
    cameras = db.get_cameras_with_status(today)
    return render_template("admin_dashboard.html",
                           reservations=reservations,
                           cameras=cameras,
                           today=today)


@app.route("/admin/checkout/<int:res_id>", methods=["POST"])
@admin_required
def admin_checkout(res_id):
    db.set_status(res_id, "checked_out")
    flash("Marked as checked out.", "success")
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/return/<int:res_id>", methods=["POST"])
@admin_required
def admin_return(res_id):
    db.set_status(res_id, "returned")
    flash("Marked as returned.", "success")
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/cancel/<int:res_id>", methods=["POST"])
@admin_required
def admin_cancel(res_id):
    db.cancel_reservation(res_id)
    flash("Reservation cancelled.", "info")
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/extend/<int:res_id>", methods=["POST"])
@admin_required
def admin_extend(res_id):
    new_return = request.form.get("new_return_date", "")
    if new_return:
        db.extend_reservation(res_id, new_return)
        flash("Return date updated.", "success")
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/add-camera", methods=["POST"])
@admin_required
def admin_add_camera():
    num = db.add_camera()
    flash(f"Camera {num} added.", "success")
    return redirect(url_for("admin_dashboard"))


if __name__ == "__main__":
    app.run(debug=True)
