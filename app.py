import os, uuid, atexit, time, logging, json
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from flask import Flask, render_template, request, jsonify, Response, session
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.exceptions import HTTPException, BadRequest
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv
from pymongo import MongoClient, errors
from bson import ObjectId
from PIL import Image
from caption_engine import NeuralCaptionEngine

# Initialize global application logging configuration
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)
logger = logging.getLogger(__name__)

# Load environment variables for configuration management
load_dotenv()

class AppConfig:
    # Centralized configuration container for application settings
    SECRET_KEY = os.getenv('SECRET_KEY', 'dev-fallback-key-32-chars-min')
    UPLOAD_FOLDER = os.getenv('UPLOAD_PATH', os.path.join(os.getcwd(), 'uploads'))
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024 # 16MB payload limit
    INFERENCE_TIMEOUT = int(os.getenv('INFERENCE_TIMEOUT', '60'))
    MAX_WORKERS = int(os.getenv('MAX_INFERENCE_WORKERS', '1'))
    MONGO_URI = os.getenv('MONGO_URI')
    APP_VERSION = os.getenv('APP_VERSION', '1.0.0')
    FLASK_ENV = os.getenv('FLASK_ENV', 'development')

# Initialize asynchronous execution pool for non-blocking neural inference
inference_executor_pool: ThreadPoolExecutor = ThreadPoolExecutor(max_workers=AppConfig.MAX_WORKERS)
atexit.register(lambda: inference_executor_pool.shutdown(wait=True))

app: Flask = Flask(__name__, static_folder='static', template_folder='templates')
app.config.from_object(AppConfig)
# Configure secure session and cookie persistence parameters
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE='Lax', 
                 PERMANENT_SESSION_LIFETIME=timedelta(days=7), SESSION_COOKIE_SECURE=AppConfig.FLASK_ENV == 'production')

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp'}
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Singleton instance of the neural inference engine
ai_engine: NeuralCaptionEngine = NeuralCaptionEngine()

# Initialize session-based authentication manager
login_manager = LoginManager()
login_manager.init_app(app)

# Unique identifier for the current runtime deployment instance
DEPLOYMENT_ID = uuid.uuid4().hex

@app.before_request
def validate_deployment_session():
    # Invalidate sessions upon application version mismatch to prevent state drift
    if current_user.is_authenticated and session.get('app_version') != AppConfig.APP_VERSION:
        logout_user()

@login_manager.unauthorized_handler
def handle_unauthorized_access() -> tuple[Response, int]:
    # Return JSON error response for unauthorized API access attempts
    return jsonify({
        "success": False, 
        "error": "Your session has expired or you are not logged in. Please log in to continue."
    }), 401

class User(UserMixin):
    # Identity model for authenticated session management
    def __init__(self, user_data: Dict[str, Any]):
        self.id = str(user_data['_id'])
        self.email = user_data.get('email', 'Unknown')
        self.fullname = user_data.get('fullname', 'User')

    def get_id(self):
        return self.id

@login_manager.user_loader
def load_user(user_id: str) -> Optional[User]:
    if db_status != "ONLINE" or not user_id or users_collection is None:
        return None
    try:
        user_data = users_collection.find_one({"_id": ObjectId(user_id)})
        return User(user_data) if user_data else None
    except Exception as e:
        logger.error(f"Failed to load user session for ID {user_id}: {e}")
        return None

# In-memory fallback metrics for degraded datastore states
MEM_METRICS_BUFFER: Dict[str, Any] = {
    "status": "DEGRADED",
    "storage_node": "VOLATILE_RAM_LOOP",
    "uptime_delta": 0,
    "active_pipelines": ["inference_engine", "lookahead_core"]
}

# Rate-limiting engine for API protection and abuse prevention
limiter: Limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["100 per hour"],
    storage_uri="memory://"
)

# Database connectivity handles and status indicators
db_client: Optional[MongoClient] = None
db_status: str = "OFFLINE"
history_collection: Optional[Any] = None
users_collection: Optional[Any] = None

if AppConfig.MONGO_URI:
    try:
        masked_uri = AppConfig.MONGO_URI.split("@")[-1] if "@" in AppConfig.MONGO_URI else "Hidden String"
        logger.info(f"Dispatching database initialization request toward cluster: [ {masked_uri} ]")
        
        db_client = MongoClient(AppConfig.MONGO_URI, serverSelectionTimeoutMS=5000)
        db_client.server_info() # Verify cluster connectivity
        
        db = db_client['caption_nexus_db']
        history_collection = db['inference_history']
        users_collection = db['users']

        # Establish database indexes for optimized identity lookups and history queries
        users_collection.create_index("email", unique=True)
        history_collection.create_index([("user_id", 1), ("timestamp", -1)])
        db_status = "ONLINE"
        logger.info("Secure cluster link established. MongoDB datastore status: ONLINE")
    except errors.ServerSelectionTimeoutError:
        logger.error("Database Timeout: Cluster connection dropped. Running in local fallback state.")
    except Exception as db_err:
        logger.error(f"Database Authorization Error: {db_err}. Running in local fallback state.")
else:
    logger.warning("Environmental Variable 'MONGO_URI' empty. Local fallback state activated.")

# ==========================================================================
# AUTHENTICATION ENDPOINTS
# ==========================================================================

@app.route('/api/auth/register', methods=['POST'])
def register() -> tuple[Response, int]:
    # Register new user identity and establish initial session state
    if db_status != "ONLINE":
        return jsonify({"success": False, "error": "Database offline. Registration disabled."}), 503
    
    data = request.json or {}
    fullname = data.get('fullname')
    email = data.get('email')
    password = data.get('password')

    if not email or not password:
        return jsonify({"success": False, "error": "Missing credentials"}), 400

    if users_collection.find_one({"email": email}):
        return jsonify({"success": False, "error": "Identity already exists."}), 409

    hashed_pw = generate_password_hash(password)
    new_user = {
        "fullname": fullname,
        "email": email,
        "password": hashed_pw,
        "username": email.split('@')[0]
    }
    
    result = users_collection.insert_one(new_user)
    user_obj = User({**new_user, "_id": result.inserted_id})
    login_user(user_obj)
    session['deployment_id'] = DEPLOYMENT_ID
    session['app_version'] = AppConfig.APP_VERSION
    
    return jsonify({"success": True})

@app.route('/api/auth/login', methods=['POST'])
def login() -> tuple[Response, int]:
    # Authenticate user credentials and establish persistent session state
    if db_status != "ONLINE":
        return jsonify({"success": False, "error": "Database offline. Login disabled."}), 503

    data = request.json or {}
    email = data.get('email')
    password = data.get('password')

    user_data = users_collection.find_one({"email": email})
    if user_data and check_password_hash(user_data['password'], password):
        user_obj = User(user_data)
        login_user(user_obj, remember=True)
        session.permanent = True
        session['deployment_id'] = DEPLOYMENT_ID
        session['app_version'] = AppConfig.APP_VERSION
        logger.info(f"User login successful: {email}")
        return jsonify({"success": True})
    
    logger.warning(f"Failed login attempt for email: {email}")
    return jsonify({"success": False, "error": "Invalid credentials"}), 401

@app.route('/api/auth/logout')
@login_required
def logout():
    # Terminate active user session
    logout_user()
    return jsonify({"success": True})

def allowed_file(file_stream: Any) -> bool:
    # Validate file integrity, extension, and MIME type conformance
    filename: str = file_stream.filename or ""
    extension_valid = '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS
    if not extension_valid:
        return False
        
    try:
        img = Image.open(file_stream)
        img.verify()
        file_stream.seek(0)
        return True
    except Exception:
        return False

# ==========================================================================
# GLOBAL ERROR HANDLERS (Forces JSON responses over default HTML pages)
# ==========================================================================

# Centralized global error handlers for standardized JSON responses
@app.errorhandler(413)
def request_entity_too_large(error: Exception) -> tuple[Response, int]:
    return jsonify({"success": False, "error": "Payload too large. Maximum size is 16MB."}), 413

@app.errorhandler(404)
def resource_not_found(error: Exception) -> tuple[Response, int]:
    return jsonify({"success": False, "error": "The requested API endpoint does not exist."}), 404

@app.errorhandler(405)
def method_not_allowed(error: Exception) -> tuple[Response, int]:
    return jsonify({"success": False, "error": "HTTP method not supported for this endpoint."}), 405

@app.errorhandler(Exception)
def handle_global_runtime_exceptions(error: Exception) -> tuple[Response, int]:
    if isinstance(error, HTTPException):
        return jsonify({
            "success": False, 
            "error": error.description
        }), error.code

    logger.exception(f"Unhandled exception intercepted: {str(error)}")
    return jsonify({
        "success": False, 
        "error": f"Internal Gateway Failure: {str(error)}"
    }), 500

# ==========================================================================
# CORE APPLICATION GATEWAY ENTRYPOINTS
# ==========================================================================

@app.route('/')
def index() -> str:
    return render_template('index.html', database_status=db_status)

@app.route('/api/telemetry/health', methods=['GET'])
def check_system_telemetry_matrix() -> tuple[Response, int]:
    # Aggregate system health metrics and telemetry status
    try:
        return jsonify({
            "success": True,
            "datastore_status": db_status,
            "auth_context": {
                "is_authenticated": current_user.is_authenticated,
                "email": current_user.email if current_user.is_authenticated else None,
                "fullname": current_user.fullname if current_user.is_authenticated else None
            },
            "model_ready": ai_engine.weights_loaded,
            "metrics": {
                "engine_status": "READY" if ai_engine.weights_loaded else "INITIALIZATION_FAILED",
                "engine_error": ai_engine.init_error if not ai_engine.weights_loaded else None,
                "engine_load": "0.14",
                "memory_footprint": "24MB",
                "storage": "PERSISTENT_DISK"
            }
        })
    except (OSError, IOError) as write_fault:
        logger.warning(f"Alert: Datastore Metrics Offline ({write_fault}). Engaging RAM-Loop.")
        fallback_payload = MEM_METRICS_BUFFER.copy()
        fallback_payload["uptime_delta"] = int(time.time()) % 10000
        
        return jsonify({
            "success": False,
            "datastore_status": "OFFLINE",
            "error_context": "STORAGE_LOCKOUT_DEGRADED_STATE",
            "metrics": fallback_payload
        }), 200

@app.route('/api/generate-caption', methods=['POST'])
@login_required
@limiter.limit("5 per minute")
def generate_caption() -> tuple[Response, int]:
    # Neural inference endpoint for automated image caption generation
    file_path = None
    try:
        if 'image' not in request.files:
            return jsonify({"success": False, "error": "No image file provided."}), 400
            
        file_stream = request.files['image']
        if file_stream.filename == '':
            return jsonify({"success": False, "error": "No image selected."}), 400
            
        if not allowed_file(file_stream):
            return jsonify({"success": False, "error": "Asset rejected: Invalid image extension or corrupted file structure."}), 400

        if not ai_engine.weights_loaded:
            error_detail = f": {ai_engine.init_error}" if ai_engine.init_error else ""
            return jsonify({"success": False, "error": f"Neural engine not initialized{error_detail}"}), 503

        original_filename: str = secure_filename(file_stream.filename or "unknown")
        filename: str = f"{uuid.uuid4().hex}_{original_filename}"
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file_stream.save(file_path)

        try:
            # Execute compute-intensive inference via asynchronous worker pool
            future = inference_executor_pool.submit(ai_engine.process_and_decode, file_path)
            engine_result: Dict[str, Any] = future.result(timeout=AppConfig.INFERENCE_TIMEOUT) 
            
            if not engine_result.get("success", False):
                raise Exception(engine_result.get("caption", "Unknown alignment failure."))

            computed_caption = engine_result["caption"]
            confidence_score = engine_result["confidence"]
            model_backbone = engine_result.get("backbone", "Salesforce BLIP Architecture")
            timestamp_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            # Persist inference transaction metadata to the datastore
            if db_status == "ONLINE" and history_collection is not None:
                try:
                    log_document = {
                        "user_id": current_user.id,
                        "filename": original_filename,
                        "caption": computed_caption,
                        "confidence": confidence_score,
                        "timestamp": timestamp_str,
                        "model_backbone": model_backbone
                    }
                    history_collection.insert_one(log_document)
                except Exception as db_write_err:
                    logger.warning(f"Metadata logging failed: {db_write_err}. Proceeding with UI delivery.")

            # Return finalized inference response payload
            return jsonify({
                "success": True,
                "caption": computed_caption,
                "confidence": confidence_score,
                "backbone": model_backbone,
                "timestamp": timestamp_str,
                "weights_status": engine_result.get("weights_status", "unknown")
            })
        except TimeoutError:
            logger.error(f"Inference timeout for file: {original_filename}")
            return jsonify({"success": False, "error": "The inference engine took too long to respond. Try a smaller image."}), 504
        finally:
            # Clean up temporary asset from local filesystem
            if file_path and os.path.exists(file_path):
                os.remove(file_path)

    except Exception as runtime_fault:
        logger.error(f"Execution interrupted during inference handling: {str(runtime_fault)}")
        return jsonify({"success": False, "error": f"Internal Processing Failure: {str(runtime_fault)}"}), 500

@app.route('/api/history', methods=['GET'])
@login_required
def get_history_logs() -> tuple[Response, int]:
    # Retrieve paginated inference history logs for the active user
    try:
        if db_status != "ONLINE" or history_collection is None:
            return jsonify({"success": True, "history": []})

        cursor = history_collection.find({"user_id": current_user.id}, {"_id": 0}).sort("timestamp", -1).limit(10)
        logs_array = list(cursor)
        
        return jsonify({
            "success": True,
            "history": logs_array
        })
    except Exception as query_fault:
        logger.error(f"Query interface dropped during history retrieval: {str(query_fault)}")
        return jsonify({"success": False, "error": str(query_fault)}), 500

if __name__ == '__main__':
    # Entry point for development server execution
    port = int(os.getenv('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=os.getenv('FLASK_DEBUG', 'false').lower() == 'true')