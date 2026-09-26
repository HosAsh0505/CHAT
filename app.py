import json
import os
import re

from datetime import datetime, timezone, timedelta

from flask import (
    Flask,
    request,
    jsonify,
    render_template,
    session,
    make_response
)

from flask_socketio import (
    SocketIO,
    join_room
)

from werkzeug.security import (
    generate_password_hash,
    check_password_hash
)

from database import db
import models

from admin import (
    admin_bp,
    init_admin
)


# ============================================================
# BASE DIRECTORY
# ============================================================

BASE_DIR = os.path.dirname(
    os.path.abspath(__file__)
)


# ============================================================
# LOAD CONFIG
# ============================================================

CONFIG_FILE = os.path.join(
    BASE_DIR,
    "config.json"
)

with open(
    CONFIG_FILE,
    "r",
    encoding="utf-8"
) as f:

    config = json.load(f)


# ============================================================
# FLASK APP
# ============================================================

app = Flask(__name__)

app.config["SECRET_KEY"] = (
    "LAN_CHAT_SECRET_KEY_CHANGE_LATER"
)


# ============================================================
# TIMEZONE
# Egypt = UTC+3
# ============================================================

PROJECT_TIMEZONE = timezone(
    timedelta(hours=3)
)


def now_local():
    """
    Return current project time.

    Stored as naive datetime so it remains
    compatible with the current SQLite schema.
    """

    return datetime.now(
        PROJECT_TIMEZONE
    ).replace(
        tzinfo=None
    )


# ============================================================
# DATABASE
# ============================================================

database_path = os.path.join(
    BASE_DIR,
    config["database"]["path"]
)

app.config["SQLALCHEMY_DATABASE_URI"] = (
    "sqlite:///"
    +
    database_path.replace(
        "\\",
        "/"
    )
)

app.config[
    "SQLALCHEMY_TRACK_MODIFICATIONS"
] = False

db.init_app(app)


# ============================================================
# SOCKET.IO
# ============================================================

socketio = SocketIO(
    app,
    cors_allowed_origins="*"
)


# ============================================================
# ADMIN BLUEPRINT
# ============================================================

app.register_blueprint(
    admin_bp
)


# ============================================================
# SOCKET TRACKING
#
# Example:
#
# {
#     "01011111111": {
#         "socket-id-1",
#         "socket-id-2"
#     }
# }
#
# ============================================================

online_sockets = {}


# ============================================================
# ADMIN LIVE ROOM
# ============================================================

ADMIN_ROOM = "admin_dashboard"


# ============================================================
# HELPER FUNCTIONS
# ============================================================

def valid_phone(phone):

    if not phone:
        return False

    return bool(
        re.fullmatch(
            r"01[0125][0-9]{8}",
            str(phone).strip()
        )
    )


def user_room(phone):

    return f"user_{phone}"


# ============================================================
# MESSAGE SERIALIZER
# ============================================================

def serialize_message(message):

    return {

        "id":
            message.id,

        "sender":
            message.sender,

        "receiver":
            message.receiver,

        "message":
            message.message,

        "timestamp": (
            message.timestamp.isoformat()
            if message.timestamp
            else None
        ),

        "status":
            message.status,

        "delivered_at": (
            message.delivered_at.isoformat()
            if message.delivered_at
            else None
        ),

        "read_at": (
            message.read_at.isoformat()
            if message.read_at
            else None
        )

    }


# ============================================================
# ADMIN SERIALIZERS
# ============================================================

def serialize_user(user):

    return {

        "id":
            user.id,

        "phone":
            user.phone,

        "online":
            bool(user.online),

        "created_at": (
            user.created_at.isoformat()
            if user.created_at
            else None
        ),

        "last_login": (
            user.last_login.isoformat()
            if user.last_login
            else None
        ),

        "last_logout": (
            user.last_logout.isoformat()
            if user.last_logout
            else None
        ),

        "last_ip":
            user.last_ip

    }


def serialize_audit(log):

    return {

        "id":
            log.id,

        "event_type":
            log.event_type,

        "phone":
            log.phone,

        "ip_address":
            log.ip_address,

        "description":
            log.description,

        "timestamp": (
            log.timestamp.isoformat()
            if log.timestamp
            else None
        )

    }


# ============================================================
# ADMIN LIVE STATISTICS
# ============================================================

def get_admin_stats():

    total_users = (
        models.User.query.count()
    )

    online_users = (
        models.User.query
        .filter_by(
            online=True
        )
        .count()
    )

    total_messages = (
        models.Message.query.count()
    )

    unread_messages = (
        models.Message.query
        .filter(
            models.Message.status != "read"
        )
        .count()
    )

    active_sessions = (
        models.Session.query
        .filter_by(
            session_status="active"
        )
        .count()
    )

    total_audit_logs = (
        models.AuditLog.query.count()
    )

    return {

        "total_users":
            total_users,

        "online_users":
            online_users,

        "total_messages":
            total_messages,

        "unread_messages":
            unread_messages,

        "active_sessions":
            active_sessions,

        "total_audit_logs":
            total_audit_logs

    }


# ============================================================
# ADMIN LIVE EVENT EMITTER
#
# dashboard.html listens for:
#
#   admin_activity
#   admin_presence
#
# So we emit exactly these events.
#
# ============================================================

def emit_admin_activity(
    event_type,
    log=None,
    user=None,
    message=None,
    description=None
):

    try:

        payload = {

            "event_type":
                event_type,

            "stats":
                get_admin_stats(),

            "timestamp":
                now_local().isoformat()

        }


        if log is not None:

            payload["log"] = (
                serialize_audit(log)
            )


        if user is not None:

            payload["user"] = (
                serialize_user(user)
            )


        if message is not None:

            payload["message"] = (
                serialize_message(message)
            )


        if description is not None:

            payload["description"] = (
                description
            )


        socketio.emit(

            "admin_activity",

            payload,

            room=ADMIN_ROOM

        )


        print(
            f"[ADMIN LIVE] {event_type}"
        )


    except Exception as e:

        print(
            "[ADMIN LIVE ERROR]"
        )

        print(
            str(e)
        )


# ============================================================
# ADMIN PRESENCE EVENT
# ============================================================

def emit_admin_presence(
    event_type,
    user
):

    try:

        payload = {

            "event_type":
                event_type,

            "user":
                serialize_user(user),

            "stats":
                get_admin_stats(),

            "timestamp":
                now_local().isoformat()

        }


        socketio.emit(

            "admin_presence",

            payload,

            room=ADMIN_ROOM

        )


        print(
            f"[ADMIN PRESENCE] {event_type} "
            f"| {user.phone}"
        )


    except Exception as e:

        print(
            "[ADMIN PRESENCE ERROR]"
        )

        print(
            str(e)
        )


# ============================================================
# BASIC ROUTES
# ============================================================

@app.route(
    "/",
    methods=["GET"]
)
def home():

    if "phone" in session:

        return render_template(
            "chat.html",
            phone=session["phone"]
        )

    return render_template(
        "login.html"
    )


# ============================================================
# HEALTH
# ============================================================

@app.route(
    "/health",
    methods=["GET"]
)
def health():

    return jsonify({

        "success":
            True,

        "status":
            "OK",

        "server":
            config["server"]["host"],

        "port":
            config["server"]["port"]

    })


# ============================================================
# LOGIN PAGE
# ============================================================

@app.route(
    "/login",
    methods=["GET"]
)
def login_page():

    response = make_response(
        render_template(
            "login.html"
        )
    )

    response.headers[
        "Cache-Control"
    ] = (
        "no-store, "
        "no-cache, "
        "must-revalidate, "
        "max-age=0"
    )

    response.headers[
        "Pragma"
    ] = "no-cache"

    return response


# ============================================================
# REGISTER PAGE
# ============================================================

@app.route(
    "/register",
    methods=["GET"]
)
def register_page():

    response = make_response(
        render_template(
            "register.html"
        )
    )

    response.headers[
        "Cache-Control"
    ] = (
        "no-store, "
        "no-cache, "
        "must-revalidate, "
        "max-age=0"
    )

    response.headers[
        "Pragma"
    ] = "no-cache"

    return response


# ============================================================
# REGISTER API
# ============================================================

@app.route(
    "/api/register",
    methods=["POST"]
)
def register():

    data = request.get_json(
        silent=True
    )

    if not data:

        return jsonify({

            "success":
                False,

            "message":
                "Request body must be JSON"

        }), 400


    phone = data.get(
        "phone"
    )

    password = data.get(
        "password"
    )


    if not phone or not password:

        return jsonify({

            "success":
                False,

            "message":
                "Phone and password are required"

        }), 400


    phone = str(
        phone
    ).strip()


    # --------------------------------------------------------
    # VALIDATE PHONE
    # --------------------------------------------------------

    if not valid_phone(phone):

        return jsonify({

            "success":
                False,

            "message":
                "Invalid Egyptian phone number"

        }), 400


    # --------------------------------------------------------
    # VALIDATE PASSWORD
    # --------------------------------------------------------

    if len(password) < 6:

        return jsonify({

            "success":
                False,

            "message":
                "Password must be at least 6 characters"

        }), 400


    # --------------------------------------------------------
    # CHECK EXISTING USER
    # --------------------------------------------------------

    existing_user = (

        models.User.query
        .filter_by(
            phone=phone
        )
        .first()

    )


    if existing_user:

        return jsonify({

            "success":
                False,

            "message":
                "User already exists"

        }), 409


    # --------------------------------------------------------
    # HASH PASSWORD
    # --------------------------------------------------------

    password_hash = (
        generate_password_hash(
            password
        )
    )


    client_ip = request.remote_addr


    # --------------------------------------------------------
    # CREATE USER
    # --------------------------------------------------------

    user = models.User(

        phone=phone,

        password_hash=password_hash,

        last_ip=client_ip,

        online=False

    )


    db.session.add(
        user
    )


    # --------------------------------------------------------
    # AUDIT LOG
    # --------------------------------------------------------

    log = models.AuditLog(

        event_type="USER_CREATED",

        phone=phone,

        ip_address=client_ip,

        description=
            "New user account created"

    )


    db.session.add(
        log
    )

    db.session.commit()


    print(
        "[USER CREATED]"
    )

    print(
        f"Phone : {phone}"
    )

    print(
        f"IP    : {client_ip}"
    )


    # ========================================================
    # ADMIN LIVE
    # ========================================================

    emit_admin_activity(

        event_type="USER_CREATED",

        log=log,

        user=user,

        description=
            "New user account created"

    )


    return jsonify({

        "success":
            True,

        "message":
            "User created successfully",

        "phone":
            phone

    }), 201


# ============================================================
# LOGIN API
# ============================================================

@app.route(
    "/api/login",
    methods=["POST"]
)
def login():

    data = request.get_json(
        silent=True
    )


    if not data:

        return jsonify({

            "success":
                False,

            "message":
                "Request body must be JSON"

        }), 400


    phone = data.get(
        "phone"
    )

    password = data.get(
        "password"
    )


    if not phone or not password:

        return jsonify({

            "success":
                False,

            "message":
                "Phone and password are required"

        }), 400


    phone = str(
        phone
    ).strip()


    # --------------------------------------------------------
    # VALIDATE PHONE
    # --------------------------------------------------------

    if not valid_phone(phone):

        return jsonify({

            "success":
                False,

            "message":
                "Invalid Egyptian phone number"

        }), 400


    # --------------------------------------------------------
    # FIND USER
    # --------------------------------------------------------

    user = (

        models.User.query
        .filter_by(
            phone=phone
        )
        .first()

    )


    if not user:

        return jsonify({

            "success":
                False,

            "message":
                "Invalid phone number or password"

        }), 401


    # --------------------------------------------------------
    # CHECK PASSWORD
    # --------------------------------------------------------

    if not check_password_hash(
        user.password_hash,
        password
    ):

        return jsonify({

            "success":
                False,

            "message":
                "Invalid phone number or password"

        }), 401


    client_ip = request.remote_addr

    now = now_local()


    # --------------------------------------------------------
    # UPDATE USER
    # --------------------------------------------------------

    user.last_login = now

    user.last_ip = client_ip

    user.online = True


    # --------------------------------------------------------
    # CREATE SESSION
    # --------------------------------------------------------

    new_session = models.Session(

        phone=phone,

        ip_address=client_ip,

        login_time=now,

        session_status="active"

    )


    db.session.add(
        new_session
    )


    # --------------------------------------------------------
    # AUDIT LOG
    # --------------------------------------------------------

    log = models.AuditLog(

        event_type="USER_LOGIN",

        phone=phone,

        ip_address=client_ip,

        description=
            "User logged in successfully"

    )


    db.session.add(
        log
    )

    db.session.commit()


    # --------------------------------------------------------
    # FLASK SESSION
    # --------------------------------------------------------

    session.clear()

    session["phone"] = phone


    print(
        "[USER LOGIN]"
    )

    print(
        f"Phone : {phone}"
    )

    print(
        f"IP    : {client_ip}"
    )


    # ========================================================
    # ADMIN LIVE
    # ========================================================

    emit_admin_activity(

        event_type="USER_LOGIN",

        log=log,

        user=user,

        description=
            "User logged in successfully"

    )


    # ========================================================
    # ADMIN PRESENCE
    # ========================================================

    emit_admin_presence(

        event_type="USER_ONLINE",

        user=user

    )


    return jsonify({

        "success":
            True,

        "message":
            "Login successful",

        "phone":
            phone,

        "ip":
            client_ip

    }), 200


# ============================================================
# CHANGE PASSWORD
#
# Authenticated user can change their own password.
#
# Request:
#
# POST /api/change-password
#
# JSON:
#
# {
#     "current_password": "old-password",
#     "new_password": "new-password"
# }
#
# ============================================================

@app.route(
    "/api/change-password",
    methods=["POST"]
)
def change_password():

    # --------------------------------------------------------
    # CHECK LOGIN
    # --------------------------------------------------------

    logged_phone = session.get(
        "phone"
    )


    if not logged_phone:

        return jsonify({

            "success":
                False,

            "message":
                "You are not logged in"

        }), 401


    # --------------------------------------------------------
    # READ JSON
    # --------------------------------------------------------

    data = request.get_json(
        silent=True
    )


    if not data:

        return jsonify({

            "success":
                False,

            "message":
                "Request body must be JSON"

        }), 400


    current_password = data.get(
        "current_password"
    )

    new_password = data.get(
        "new_password"
    )


    # --------------------------------------------------------
    # REQUIRED FIELDS
    # --------------------------------------------------------

    if (
        not current_password
        or
        not new_password
    ):

        return jsonify({

            "success":
                False,

            "message":
                "Current password and new password are required"

        }), 400


    # --------------------------------------------------------
    # NORMALIZE USER PHONE
    # --------------------------------------------------------

    logged_phone = str(
        logged_phone
    ).strip()


    # --------------------------------------------------------
    # FIND USER
    # --------------------------------------------------------

    user = (

        models.User.query
        .filter_by(
            phone=logged_phone
        )
        .first()

    )


    if not user:

        return jsonify({

            "success":
                False,

            "message":
                "User account not found"

        }), 404


    # --------------------------------------------------------
    # VERIFY CURRENT PASSWORD
    # --------------------------------------------------------

    if not check_password_hash(
        user.password_hash,
        current_password
    ):

        # ----------------------------------------------------
        # AUDIT FAILED PASSWORD CHANGE
        # ----------------------------------------------------

        failed_log = models.AuditLog(

            event_type="PASSWORD_CHANGE_FAILED",

            phone=logged_phone,

            ip_address=request.remote_addr,

            description=
                "Password change failed: "
                "current password is incorrect"

        )

        db.session.add(
            failed_log
        )

        db.session.commit()


        emit_admin_activity(

            event_type="PASSWORD_CHANGE_FAILED",

            log=failed_log,

            user=user,

            description=
                "Password change failed: "
                "current password is incorrect"

        )


        return jsonify({

            "success":
                False,

            "message":
                "Current password is incorrect"

        }), 401


    # --------------------------------------------------------
    # VALIDATE NEW PASSWORD
    # --------------------------------------------------------

    if len(new_password) < 8:

        return jsonify({

            "success":
                False,

            "message":
                "New password must be at least 8 characters"

        }), 400


    # --------------------------------------------------------
    # PREVENT SAME PASSWORD
    # --------------------------------------------------------

    if check_password_hash(
        user.password_hash,
        new_password
    ):

        return jsonify({

            "success":
                False,

            "message":
                "New password must be different from the current password"

        }), 400


    # --------------------------------------------------------
    # GENERATE NEW HASH
    # --------------------------------------------------------

    user.password_hash = (
        generate_password_hash(
            new_password
        )
    )


    # --------------------------------------------------------
    # AUDIT LOG
    # --------------------------------------------------------

    log = models.AuditLog(

        event_type="PASSWORD_CHANGED",

        phone=logged_phone,

        ip_address=request.remote_addr,

        description=
            "User changed their password successfully"

    )


    db.session.add(
        log
    )

    db.session.commit()


    # --------------------------------------------------------
    # SERVER LOG
    # --------------------------------------------------------

    print(
        "[PASSWORD CHANGED]"
    )

    print(
        f"Phone : {logged_phone}"
    )

    print(
        f"IP    : {request.remote_addr}"
    )


    # ========================================================
    # ADMIN LIVE ACTIVITY
    # ========================================================

    emit_admin_activity(

        event_type="PASSWORD_CHANGED",

        log=log,

        user=user,

        description=
            "User changed their password successfully"

    )


    # --------------------------------------------------------
    # RESPONSE
    # --------------------------------------------------------

    return jsonify({

        "success":
            True,

        "message":
            "Password changed successfully"

    }), 200


# ============================================================
# CHAT PAGE
# ============================================================

@app.route(
    "/chat",
    methods=["GET"]
)
def chat_page():

    if "phone" not in session:

        return render_template(
            "login.html"
        )


    response = make_response(

        render_template(

            "chat.html",

            phone=session["phone"]

        )

    )


    response.headers[
        "Cache-Control"
    ] = (
        "no-store, "
        "no-cache, "
        "must-revalidate, "
        "max-age=0"
    )

    response.headers[
        "Pragma"
    ] = "no-cache"


    return response


# ============================================================
# CHECK USER
# ============================================================

@app.route(
    "/api/user/<phone>",
    methods=["GET"]
)
def check_user(phone):

    # --------------------------------------------------------
    # USER MUST BE LOGGED IN
    # --------------------------------------------------------

    if "phone" not in session:

        return jsonify({

            "success":
                False,

            "exists":
                False,

            "message":
                "Unauthorized"

        }), 401


    # --------------------------------------------------------
    # CLEAN PHONE
    # --------------------------------------------------------

    phone = str(
        phone
    ).strip()


    # --------------------------------------------------------
    # VALIDATE PHONE
    # --------------------------------------------------------

    if not valid_phone(phone):

        return jsonify({

            "success":
                True,

            "exists":
                False,

            "phone":
                phone,

            "message":
                "Invalid phone number"

        }), 400


    # --------------------------------------------------------
    # SEARCH DATABASE
    # --------------------------------------------------------

    user = (

        models.User.query
        .filter_by(
            phone=phone
        )
        .first()

    )


    # --------------------------------------------------------
    # USER DOES NOT EXIST
    # --------------------------------------------------------

    if user is None:

        print(
            "[USER CHECK] "
            f"{phone} -> NOT FOUND"
        )

        return jsonify({

            "success":
                True,

            "exists":
                False,

            "phone":
                phone,

            "message":
                "User does not exist"

        }), 404


    # --------------------------------------------------------
    # USER EXISTS
    # --------------------------------------------------------

    print(
        "[USER CHECK] "
        f"{phone} -> EXISTS"
    )


    return jsonify({

        "success":
            True,

        "exists":
            True,

        "phone":
            user.phone

    }), 200


# ============================================================
# SOCKET.IO CONNECT
# ============================================================

@socketio.on("connect")
def socket_connect():

    phone = session.get(
        "phone"
    )


    if not phone:

        print(
            "[SOCKET CONNECT REJECTED] "
            "No logged-in user"
        )

        return False


    sid = request.sid

    room = user_room(
        phone
    )


    # --------------------------------------------------------
    # JOIN PRIVATE ROOM
    # --------------------------------------------------------

    join_room(
        room
    )


    # --------------------------------------------------------
    # CREATE SOCKET SET
    # --------------------------------------------------------

    if phone not in online_sockets:

        online_sockets[phone] = set()


    was_already_online = (
        len(
            online_sockets[phone]
        ) > 0
    )


    online_sockets[
        phone
    ].add(
        sid
    )


    # --------------------------------------------------------
    # UPDATE USER ONLINE STATE
    # --------------------------------------------------------

    user = (

        models.User.query
        .filter_by(
            phone=phone
        )
        .first()

    )


    if user:

        user.online = True

        db.session.commit()


    print(
        f"[SOCKET CONNECT] "
        f"{phone} | SID={sid}"
    )


    print(
        "[ONLINE USERS] "
        f"{list(online_sockets.keys())}"
    )


    # ========================================================
    # ADMIN LIVE PRESENCE
    #
    # Only emit when the user actually became online.
    # This prevents multiple browser tabs from generating
    # duplicate USER_ONLINE events.
    # ========================================================

    if user and not was_already_online:

        emit_admin_presence(

            event_type="USER_ONLINE",

            user=user

        )


# ============================================================
# SOCKET.IO DISCONNECT
# ============================================================

@socketio.on("disconnect")
def socket_disconnect():

    phone = session.get(
        "phone"
    )


    if not phone:

        return


    sid = request.sid


    if phone not in online_sockets:

        return


    online_sockets[
        phone
    ].discard(
        sid
    )


    # --------------------------------------------------------
    # IF USER HAS NO OTHER SOCKETS
    # --------------------------------------------------------

    if len(
        online_sockets[phone]
    ) == 0:

        del online_sockets[
            phone
        ]


        user = (

            models.User.query
            .filter_by(
                phone=phone
            )
            .first()

        )


        if user:

            user.online = False

            user.last_logout = (
                now_local()
            )

            db.session.commit()


            # =================================================
            # ADMIN LIVE PRESENCE
            # =================================================

            emit_admin_presence(

                event_type="USER_OFFLINE",

                user=user

            )


            # =================================================
            # ADMIN LIVE ACTIVITY
            # =================================================

            log = models.AuditLog(

                event_type="USER_OFFLINE",

                phone=phone,

                ip_address=user.last_ip,

                description=
                    "User disconnected from LAN-CHAT"

            )

            db.session.add(
                log
            )

            db.session.commit()


            emit_admin_activity(

                event_type="USER_OFFLINE",

                log=log,

                user=user,

                description=
                    "User disconnected from LAN-CHAT"

            )


    print(
        f"[SOCKET DISCONNECT] "
        f"{phone} | SID={sid}"
    )


# ============================================================
# LOGOUT
# ============================================================

@app.route(
    "/api/logout",
    methods=["POST"]
)
def logout():

    phone = session.get(
        "phone"
    )


    if not phone:

        data = request.get_json(
            silent=True
        )


        if data:

            phone = data.get(
                "phone"
            )


    if not phone:

        return jsonify({

            "success":
                False,

            "message":
                "User is not logged in"

        }), 401


    phone = str(
        phone
    ).strip()


    # --------------------------------------------------------
    # FIND USER
    # --------------------------------------------------------

    user = (

        models.User.query
        .filter_by(
            phone=phone
        )
        .first()

    )


    if not user:

        return jsonify({

            "success":
                False,

            "message":
                "User not found"

        }), 404


    now = now_local()

    client_ip = request.remote_addr


    user.online = False

    user.last_logout = now


    # --------------------------------------------------------
    # CLOSE ACTIVE SESSION
    # --------------------------------------------------------

    active_session = (

        models.Session.query

        .filter_by(

            phone=phone,

            session_status="active"

        )

        .order_by(

            models.Session.login_time.desc()

        )

        .first()

    )


    if active_session:

        active_session.logout_time = now

        active_session.session_status = (
            "closed"
        )


    # --------------------------------------------------------
    # AUDIT LOG
    # --------------------------------------------------------

    log = models.AuditLog(

        event_type="USER_LOGOUT",

        phone=phone,

        ip_address=client_ip,

        description=
            "User logged out successfully"

    )


    db.session.add(
        log
    )

    db.session.commit()


    # --------------------------------------------------------
    # REMOVE SOCKET TRACKING
    # --------------------------------------------------------

    if phone in online_sockets:

        del online_sockets[
            phone
        ]


    # --------------------------------------------------------
    # CLEAR FLASK SESSION
    # --------------------------------------------------------

    session.clear()


    print(
        "[USER LOGOUT]"
    )

    print(
        f"Phone : {phone}"
    )


    # ========================================================
    # ADMIN LIVE ACTIVITY
    # ========================================================

    emit_admin_activity(

        event_type="USER_LOGOUT",

        log=log,

        user=user,

        description=
            "User logged out successfully"

    )


    # ========================================================
    # ADMIN LIVE PRESENCE
    # ========================================================

    emit_admin_presence(

        event_type="USER_OFFLINE",

        user=user

    )


    return jsonify({

        "success":
            True,

        "message":
            "Logout successful",

        "phone":
            phone

    }), 200


# ============================================================
# SEND MESSAGE
# ============================================================

@app.route(
    "/api/send-message",
    methods=["POST"]
)
def send_message():

    data = request.get_json(
        silent=True
    )


    if not data:

        return jsonify({

            "success":
                False,

            "message":
                "Request body must be JSON"

        }), 400


    # ========================================================
    # SECURITY
    # ========================================================

    sender = session.get(
        "phone"
    )

    receiver = data.get(
        "receiver"
    )

    message_text = data.get(
        "message"
    )


    if not sender:

        return jsonify({

            "success":
                False,

            "message":
                "You are not logged in"

        }), 401


    if not receiver or not message_text:

        return jsonify({

            "success":
                False,

            "message":
                "Receiver and message are required"

        }), 400


    sender = str(
        sender
    ).strip()

    receiver = str(
        receiver
    ).strip()

    message_text = str(
        message_text
    ).strip()


    # --------------------------------------------------------
    # VALIDATE RECEIVER
    # --------------------------------------------------------

    if not valid_phone(
        receiver
    ):

        return jsonify({

            "success":
                False,

            "message":
                "Invalid receiver phone number"

        }), 400


    # --------------------------------------------------------
    # VALIDATE MESSAGE
    # --------------------------------------------------------

    if not message_text:

        return jsonify({

            "success":
                False,

            "message":
                "Message cannot be empty"

        }), 400


    # --------------------------------------------------------
    # FIND RECEIVER
    # --------------------------------------------------------

    receiver_user = (

        models.User.query
        .filter_by(
            phone=receiver
        )
        .first()

    )


    if not receiver_user:

        return jsonify({

            "success":
                False,

            "message":
                "Receiver does not exist"

        }), 404


    # --------------------------------------------------------
    # CHECK ONLINE STATUS
    # --------------------------------------------------------

    receiver_online = (

        receiver in online_sockets

        and

        len(
            online_sockets[
                receiver
            ]
        ) > 0

    )


    if receiver_online:

        message_status = "delivered"

        delivered_time = (
            now_local()
        )

    else:

        message_status = "pending"

        delivered_time = None


    # --------------------------------------------------------
    # CREATE MESSAGE
    # --------------------------------------------------------

    new_message = models.Message(

        sender=sender,

        receiver=receiver,

        message=message_text,

        timestamp=now_local(),

        status=message_status,

        delivered_at=delivered_time

    )


    db.session.add(
        new_message
    )


    # --------------------------------------------------------
    # AUDIT LOG
    # --------------------------------------------------------

    log = models.AuditLog(

        event_type="MESSAGE_SENT",

        phone=sender,

        ip_address=request.remote_addr,

        description=(

            f"Message sent from "
            f"{sender} to {receiver}"

        )

    )


    db.session.add(
        log
    )

    db.session.commit()


    # ========================================================
    # BUILD MESSAGE OBJECT
    # ========================================================

    message_data = serialize_message(
        new_message
    )


    print(
        "[MESSAGE SENT]"
    )

    print(
        f"From     : {sender}"
    )

    print(
        f"To       : {receiver}"
    )

    print(
        f"Message  : {message_text}"
    )

    print(
        f"Status   : {message_status}"
    )

    print(
        f"Receiver Online : "
        f"{receiver_online}"
    )


    # ========================================================
    # SEND TO RECEIVER
    # ========================================================

    if receiver_online:

        socketio.emit(

            "new_message",

            message_data,

            room=user_room(
                receiver
            )

        )


        print(
            "[SOCKET] "
            f"new_message sent to "
            f"{receiver}"
        )


    # ========================================================
    # SEND TO SENDER
    # ========================================================

    if sender in online_sockets:

        socketio.emit(

            "message_sent",

            message_data,

            room=user_room(
                sender
            )

        )


        print(
            "[SOCKET] "
            f"message_sent sent to "
            f"{sender}"
        )


    # ========================================================
    # ADMIN LIVE MESSAGE
    # ========================================================

    emit_admin_activity(

        event_type="MESSAGE_SENT",

        log=log,

        message=new_message,

        description=(

            f"Message sent from "
            f"{sender} to {receiver}"

        )

    )


    # ========================================================
    # RETURN MESSAGE
    # ========================================================

    return jsonify({

        "success":
            True,

        "message":
            "Message sent successfully",

        "message_id":
            new_message.id,

        "sender":
            sender,

        "receiver":
            receiver,

        "status":
            message_status,

        "message_data":
            message_data

    }), 201


# ============================================================
# GET MESSAGES
# ============================================================

@app.route(
    "/api/messages/<phone>",
    methods=["GET"]
)
def get_messages(phone):

    logged_phone = session.get(
        "phone"
    )


    if not logged_phone:

        return jsonify({

            "success":
                False,

            "message":
                "You are not logged in"

        }), 401


    phone = str(
        phone
    ).strip()


    # ========================================================
    # SECURITY
    # ========================================================

    if phone != logged_phone:

        return jsonify({

            "success":
                False,

            "message":
                "Unauthorized"

        }), 403


    if not valid_phone(phone):

        return jsonify({

            "success":
                False,

            "message":
                "Invalid phone number"

        }), 400


    user = (

        models.User.query
        .filter_by(
            phone=phone
        )
        .first()

    )


    if not user:

        return jsonify({

            "success":
                False,

            "message":
                "User not found"

        }), 404


    # ========================================================
    # GET ALL MESSAGES
    # ========================================================

    messages = (

        models.Message.query

        .filter(

            (models.Message.sender == phone)

            |

            (models.Message.receiver == phone)

        )

        .order_by(

            models.Message.timestamp.asc()

        )

        .all()

    )


    # ========================================================
    # PENDING -> DELIVERED
    # ========================================================

    now = now_local()

    delivered_messages = []


    for msg in messages:

        if (

            msg.receiver == phone

            and

            msg.status == "pending"

        ):

            msg.status = "delivered"

            msg.delivered_at = now

            delivered_messages.append(
                msg
            )


    db.session.commit()


    # ========================================================
    # ADMIN LIVE DELIVERY UPDATE
    # ========================================================

    for msg in delivered_messages:

        delivery_log = models.AuditLog(

            event_type="MESSAGE_DELIVERED",

            phone=phone,

            ip_address=request.remote_addr,

            description=(

                f"Message {msg.id} "
                f"delivered to {phone}"

            )

        )

        db.session.add(
            delivery_log
        )

        db.session.commit()


        emit_admin_activity(

            event_type="MESSAGE_DELIVERED",

            log=delivery_log,

            message=msg,

            description=(

                f"Message {msg.id} "
                f"delivered to {phone}"

            )

        )


    # ========================================================
    # RETURN
    # ========================================================

    result = [

        serialize_message(
            msg
        )

        for msg in messages

    ]


    return jsonify({

        "success":
            True,

        "phone":
            phone,

        "count":
            len(result),

        "messages":
            result

    }), 200


# ============================================================
# MARK MESSAGE AS READ
# ============================================================

@app.route(
    "/api/messages/<int:message_id>/read",
    methods=["POST"]
)
def mark_message_read(
    message_id
):

    logged_phone = session.get(
        "phone"
    )


    if not logged_phone:

        return jsonify({

            "success":
                False,

            "message":
                "You are not logged in"

        }), 401


    message = db.session.get(

        models.Message,

        message_id

    )


    if not message:

        return jsonify({

            "success":
                False,

            "message":
                "Message not found"

        }), 404


    # ========================================================
    # ONLY RECEIVER CAN MARK AS READ
    # ========================================================

    if (
        message.receiver
        !=
        logged_phone
    ):

        return jsonify({

            "success":
                False,

            "message":
                "Unauthorized"

        }), 403


    # ========================================================
    # UPDATE STATUS
    # ========================================================

    if message.status != "read":

        message.status = "read"

        message.read_at = (
            now_local()
        )


        log = models.AuditLog(

            event_type="MESSAGE_READ",

            phone=message.receiver,

            ip_address=request.remote_addr,

            description=(

                f"Message {message.id} "
                f"from {message.sender} "
                f"to {message.receiver} "
                f"was read"

            )

        )


        db.session.add(
            log
        )

        db.session.commit()


        # ====================================================
        # ADMIN LIVE READ EVENT
        # ====================================================

        emit_admin_activity(

            event_type="MESSAGE_READ",

            log=log,

            message=message,

            description=(

                f"Message {message.id} "
                f"from {message.sender} "
                f"to {message.receiver} "
                f"was read"

            )

        )


    # ========================================================
    # NOTIFY SENDER
    # ========================================================

    read_data = {

        "message_id":
            message.id,

        "receiver":
            message.receiver,

        "status":
            "read",

        "read_at": (

            message.read_at.isoformat()

            if message.read_at

            else None

        )

    }


    if message.sender in online_sockets:

        socketio.emit(

            "message_read",

            read_data,

            room=user_room(
                message.sender
            )

        )


    return jsonify({

        "success":
            True,

        "message":
            "Message marked as read",

        "message_id":
            message.id,

        "status":
            message.status

    }), 200


# ============================================================
# ADMIN SOCKET CONNECT
#
# Dashboard sends:
#
#     socket.emit("admin_connect")
#
# ============================================================

@socketio.on("admin_connect")
def admin_socket_connect():

    if session.get(
        "admin_logged_in"
    ) is not True:

        print(
            "[ADMIN SOCKET REJECTED]"
        )

        return False


    join_room(
        ADMIN_ROOM
    )


    print(
        "[ADMIN SOCKET CONNECT]"
        f" SID={request.sid}"
    )


    # ========================================================
    # SEND INITIAL STATE
    # ========================================================

    try:

        stats = get_admin_stats()


        socketio.emit(

            "admin_activity",

            {

                "event_type":
                    "INITIAL_STATE",

                "stats":
                    stats,

                "timestamp":
                    now_local().isoformat()

            },

            room=request.sid

        )


        print(
            "[ADMIN INITIAL STATE SENT]"
        )


    except Exception as e:

        print(
            "[ADMIN INITIAL STATE ERROR]"
        )

        print(
            str(e)
        )


# ============================================================
# DATABASE INITIALIZATION
# ============================================================

with app.app_context():

    db.create_all()

    init_admin()


# ============================================================
# START SERVER
# ============================================================

if __name__ == "__main__":

    host = config[
        "server"
    ][
        "host"
    ]

    port = config[
        "server"
    ][
        "port"
    ]

    debug = config[
        "server"
    ][
        "debug"
    ]


    print("")

    print(
        "=============================================="
    )

    print(
        "              LAN CHAT SERVER"
    )

    print(
        "=============================================="
    )

    print(
        f"Server IP : {host}"
    )

    print(
        f"Port      : {port}"
    )

    print(
        f"Database  : {database_path}"
    )

    print(
        "Socket.IO : ENABLED"
    )

    print(
        "New Chat API : ENABLED"
    )

    print(
        "Password Change API : ENABLED"
    )

    print(
        "Admin Panel : ENABLED"
    )

    print(
        "Admin Live Monitoring : ENABLED"
    )

    print(
        "Admin Login : /admin/login"
    )

    print(
        "=============================================="
    )

    print("")

    print(
        "LAN CHAT SERVER IS RUNNING"
    )

    print("")


    socketio.run(

        app,

        host=host,

        port=port,

        debug=debug,

        allow_unsafe_werkzeug=True,

        use_reloader=False

    )