from datetime import datetime
import secrets
import string

from flask import (
    Blueprint,
    render_template,
    request,
    redirect,
    url_for,
    session,
    jsonify
)

from werkzeug.security import (
    generate_password_hash,
    check_password_hash
)

from database import db
from models import (
    Admin,
    User,
    Message,
    Session as UserSession,
    AuditLog
)


admin_bp = Blueprint(
    "admin",
    __name__,
    url_prefix="/admin"
)


# =========================================================
# HELPERS
# =========================================================

def admin_required():
    return session.get("admin_logged_in") is True


def get_stats():

    return {
        "total_users": User.query.count(),

        "online_users": User.query.filter_by(
            online=True
        ).count(),

        "total_messages": Message.query.count(),

        "unread_messages": Message.query.filter(
            Message.status != "read"
        ).count(),

        "active_sessions": UserSession.query.filter_by(
            session_status="active"
        ).count(),

        "total_audit_logs": AuditLog.query.count()
    }


def serialize_user(user):

    return {
        "id": user.id,
        "phone": user.phone,
        "online": user.online,

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

        "last_ip": user.last_ip
    }


def serialize_log(log):

    return {
        "id": log.id,
        "event_type": log.event_type,
        "phone": log.phone,
        "ip_address": log.ip_address,
        "description": log.description,

        "timestamp": (
            log.timestamp.isoformat()
            if log.timestamp
            else None
        )
    }


def generate_temp_password(length=12):

    alphabet = (
        string.ascii_letters +
        string.digits +
        "!@#$%^&*"
    )

    return "".join(
        secrets.choice(alphabet)
        for _ in range(length)
    )


def emit_admin_activity(
    event_type,
    log=None,
    user=None,
    message=None,
    description=None
):

    """
    Emit live event to Admin Dashboard.

    Importing socketio here avoids circular import
    because app.py imports admin.py.
    """

    try:

        from app import socketio

        payload = {
            "event_type": event_type,
            "description": description
        }

        if log:
            payload["log"] = serialize_log(log)

        if user:
            payload["user"] = serialize_user(user)

        if message:
            payload["message"] = message

        payload["stats"] = get_stats()

        socketio.emit(
            "admin_activity",
            payload,
            room="admin_dashboard"
        )

    except Exception as exc:

        print(
            "[ADMIN SOCKET ERROR]",
            exc
        )


# =========================================================
# ADMIN INITIALIZATION
# =========================================================

def init_admin():

    admin = Admin.query.filter_by(
        username="admin"
    ).first()

    if not admin:

        admin = Admin(
            username="admin",
            password_hash=generate_password_hash("admin")
        )

        db.session.add(admin)
        db.session.commit()

        print()
        print("==========================================")
        print(" ADMIN ACCOUNT CREATED")
        print(" Username : admin")
        print(" Password : admin")
        print("==========================================")
        print()


# =========================================================
# ADMIN LOGIN
# =========================================================

@admin_bp.route(
    "/login",
    methods=["GET", "POST"]
)
def admin_login():

    if admin_required():

        return redirect(
            url_for("admin.dashboard")
        )

    error = None

    if request.method == "POST":

        username = request.form.get(
            "username",
            ""
        ).strip()

        password = request.form.get(
            "password",
            ""
        )

        admin = Admin.query.filter_by(
            username=username
        ).first()

        if admin and check_password_hash(
            admin.password_hash,
            password
        ):

            session["admin_logged_in"] = True
            session["admin_id"] = admin.id
            session["admin_username"] = admin.username

            admin.last_login = datetime.utcnow()
            admin.last_ip = request.remote_addr

            log = AuditLog(
                event_type="ADMIN_LOGIN",
                phone=None,
                ip_address=request.remote_addr,
                description=(
                    f"Admin '{admin.username}' logged in"
                )
            )

            db.session.add(log)
            db.session.commit()

            emit_admin_activity(
                "ADMIN_LOGIN",
                log=log,
                description=log.description
            )

            return redirect(
                url_for("admin.dashboard")
            )

        error = (
            "ACCESS DENIED // Invalid credentials"
        )

        log = AuditLog(
            event_type="ADMIN_LOGIN_FAILED",
            phone=None,
            ip_address=request.remote_addr,
            description=(
                f"Failed admin login attempt "
                f"for username '{username}'"
            )
        )

        db.session.add(log)
        db.session.commit()

    return render_template(
        "admin_login.html",
        error=error
    )


# =========================================================
# ADMIN LOGOUT
# =========================================================

@admin_bp.route("/logout")
def admin_logout():

    username = session.get(
        "admin_username",
        "unknown"
    )

    if admin_required():

        log = AuditLog(
            event_type="ADMIN_LOGOUT",
            phone=None,
            ip_address=request.remote_addr,
            description=(
                f"Admin '{username}' logged out"
            )
        )

        db.session.add(log)
        db.session.commit()

    session.pop(
        "admin_logged_in",
        None
    )

    session.pop(
        "admin_id",
        None
    )

    session.pop(
        "admin_username",
        None
    )

    return redirect(
        url_for("admin.admin_login")
    )


# =========================================================
# ADMIN DASHBOARD
# =========================================================

@admin_bp.route("/")
@admin_bp.route("/dashboard")
def dashboard():

    if not admin_required():

        return redirect(
            url_for("admin.admin_login")
        )

    total_users = User.query.count()

    online_users = User.query.filter_by(
        online=True
    ).count()

    total_messages = Message.query.count()

    unread_messages = Message.query.filter(
        Message.status != "read"
    ).count()

    active_sessions = UserSession.query.filter_by(
        session_status="active"
    ).count()

    total_audit_logs = AuditLog.query.count()

    recent_logs = AuditLog.query.order_by(
        AuditLog.timestamp.desc()
    ).limit(12).all()

    recent_users = User.query.order_by(
        User.created_at.desc()
    ).limit(8).all()

    recent_messages = Message.query.order_by(
        Message.timestamp.desc()
    ).limit(8).all()

    return render_template(
        "dashboard.html",

        admin_username=session.get(
            "admin_username",
            "admin"
        ),

        total_users=total_users,
        online_users=online_users,
        total_messages=total_messages,
        unread_messages=unread_messages,
        active_sessions=active_sessions,
        total_audit_logs=total_audit_logs,

        recent_logs=recent_logs,
        recent_users=recent_users,
        recent_messages=recent_messages
    )


# =========================================================
# USERS API
# =========================================================

@admin_bp.route("/api/users")
def api_users():

    if not admin_required():

        return jsonify({
            "success": False,
            "message": "Unauthorized"
        }), 401

    users = User.query.order_by(
        User.created_at.desc()
    ).all()

    return jsonify({
        "success": True,

        "users": [
            serialize_user(user)
            for user in users
        ]
    })


# =========================================================
# ADMIN RESET USER PASSWORD
# =========================================================

@admin_bp.route(
    "/api/users/<phone>/reset-password",
    methods=["POST"]
)
def reset_user_password(phone):

    if not admin_required():

        return jsonify({
            "success": False,
            "message": "Unauthorized"
        }), 401

    phone = str(phone).strip()

    user = User.query.filter_by(
        phone=phone
    ).first()

    if not user:

        return jsonify({
            "success": False,
            "message": "User not found"
        }), 404

    data = request.get_json(
        silent=True
    ) or {}

    new_password = str(
        data.get(
            "password",
            ""
        )
    )

    generate_password = data.get(
        "generate",
        False
    )

    # -----------------------------------------------------
    # Generate password automatically
    # -----------------------------------------------------

    if generate_password:

        new_password = generate_temp_password(12)

    if not new_password:

        return jsonify({
            "success": False,
            "message": "Password is required"
        }), 400

    if len(new_password) < 6:

        return jsonify({
            "success": False,
            "message": (
                "Password must be at least 6 characters"
            )
        }), 400

    # -----------------------------------------------------
    # Update password HASH
    # -----------------------------------------------------

    user.password_hash = generate_password_hash(
        new_password
    )

    # -----------------------------------------------------
    # Optional: invalidate active sessions
    # -----------------------------------------------------

    active_sessions = UserSession.query.filter_by(
        phone=user.phone,
        session_status="active"
    ).all()

    for user_session in active_sessions:

        user_session.session_status = "terminated"
        user_session.logout_time = datetime.utcnow()

    # User must login again after admin reset

    user.online = False
    user.last_logout = datetime.utcnow()

    # -----------------------------------------------------
    # Audit
    # -----------------------------------------------------

    admin_username = session.get(
        "admin_username",
        "admin"
    )

    log = AuditLog(
        event_type="ADMIN_PASSWORD_RESET",
        phone=user.phone,
        ip_address=request.remote_addr,
        description=(
            f"Admin '{admin_username}' "
            f"reset password for user {user.phone}"
        )
    )

    db.session.add(log)

    db.session.commit()

    # -----------------------------------------------------
    # LIVE ADMIN EVENT
    # -----------------------------------------------------

    emit_admin_activity(
        "ADMIN_PASSWORD_RESET",
        log=log,
        user=user,
        description=log.description
    )

    return jsonify({
        "success": True,
        "message": "Password reset successfully",

        # Returned ONLY once.
        # It is never stored in plaintext.
        "temporary_password": new_password
    })


# =========================================================
# ADMIN DELETE USER
# =========================================================

@admin_bp.route(
    "/api/users/<phone>",
    methods=["DELETE"]
)
def delete_user(phone):

    if not admin_required():

        return jsonify({
            "success": False,
            "message": "Unauthorized"
        }), 401

    phone = str(phone).strip()

    user = User.query.filter_by(
        phone=phone
    ).first()

    if not user:

        return jsonify({
            "success": False,
            "message": "User not found"
        }), 404

    admin_username = session.get(
        "admin_username",
        "admin"
    )

    # -----------------------------------------------------
    # Delete all messages involving this user
    # -----------------------------------------------------

    Message.query.filter(
        (Message.sender == phone) |
        (Message.receiver == phone)
    ).delete(
        synchronize_session=False
    )

    # -----------------------------------------------------
    # Delete all sessions
    # -----------------------------------------------------

    UserSession.query.filter_by(
        phone=phone
    ).delete(
        synchronize_session=False
    )

    # -----------------------------------------------------
    # Delete User
    # -----------------------------------------------------

    db.session.delete(user)

    # -----------------------------------------------------
    # Keep audit record
    # -----------------------------------------------------

    log = AuditLog(
        event_type="ADMIN_USER_DELETED",
        phone=phone,
        ip_address=request.remote_addr,
        description=(
            f"Admin '{admin_username}' "
            f"deleted user {phone}"
        )
    )

    db.session.add(log)

    db.session.commit()

    # -----------------------------------------------------
    # Remove from Socket tracking
    # -----------------------------------------------------

    try:

        from app import socketio, online_sockets

        online_sockets.pop(
            phone,
            None
        )

        socketio.emit(
            "force_logout",
            {
                "phone": phone,
                "reason": "ACCOUNT_DELETED"
            },
            room=f"user_{phone}"
        )

    except Exception as exc:

        print(
            "[ADMIN DELETE SOCKET ERROR]",
            exc
        )

    # -----------------------------------------------------
    # LIVE ADMIN EVENT
    # -----------------------------------------------------

    emit_admin_activity(
        "ADMIN_USER_DELETED",
        log=log,
        description=log.description
    )

    return jsonify({
        "success": True,
        "message": (
            f"User {phone} deleted successfully"
        )
    })


# =========================================================
# MESSAGES API
# =========================================================

@admin_bp.route("/api/messages")
def api_messages():

    if not admin_required():

        return jsonify({
            "success": False,
            "message": "Unauthorized"
        }), 401

    messages = Message.query.order_by(
        Message.timestamp.desc()
    ).limit(500).all()

    return jsonify({
        "success": True,

        "messages": [

            {
                "id": message.id,
                "sender": message.sender,
                "receiver": message.receiver,
                "message": message.message,

                "timestamp": (
                    message.timestamp.isoformat()
                    if message.timestamp
                    else None
                ),

                "status": message.status,

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

            for message in messages
        ]
    })


# =========================================================
# AUDIT LOG API
# =========================================================

@admin_bp.route("/api/audit")
def api_audit():

    if not admin_required():

        return jsonify({
            "success": False,
            "message": "Unauthorized"
        }), 401

    logs = AuditLog.query.order_by(
        AuditLog.timestamp.desc()
    ).limit(500).all()

    return jsonify({
        "success": True,

        "logs": [
            serialize_log(log)
            for log in logs
        ]
    })


# =========================================================
# SESSIONS API
# =========================================================

@admin_bp.route("/api/sessions")
def api_sessions():

    if not admin_required():

        return jsonify({
            "success": False,
            "message": "Unauthorized"
        }), 401

    sessions = UserSession.query.order_by(
        UserSession.login_time.desc()
    ).limit(500).all()

    return jsonify({
        "success": True,

        "sessions": [

            {
                "id": item.id,
                "phone": item.phone,
                "ip_address": item.ip_address,

                "login_time": (
                    item.login_time.isoformat()
                    if item.login_time
                    else None
                ),

                "logout_time": (
                    item.logout_time.isoformat()
                    if item.logout_time
                    else None
                ),

                "session_status":
                    item.session_status
            }

            for item in sessions
        ]
    })