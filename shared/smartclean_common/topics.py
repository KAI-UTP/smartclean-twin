"""MQTT topic constants for SmartClean Twin."""


class Topics:
    PREFIX = "smartclean"
    ROBOT_ID = "SCR01"
    _BASE = f"{PREFIX}/{ROBOT_ID}"

    TELEMETRY_RAW = f"{_BASE}/telemetry/raw"
    TELEMETRY_VALIDATED = f"{_BASE}/telemetry/validated"
    TELEMETRY_POSE = f"{_BASE}/telemetry/pose"
    TELEMETRY_BATTERY = f"{_BASE}/telemetry/battery"
    TELEMETRY_MOTOR = f"{_BASE}/telemetry/motor"
    TELEMETRY_ENVIRONMENT = f"{_BASE}/telemetry/environment"

    STATE = f"{_BASE}/state"
    PREDICTION = f"{_BASE}/prediction"
    ALERT = f"{_BASE}/alert"
    MISSION = f"{_BASE}/mission"

    COMMAND_MOTION = f"{_BASE}/command/motion"
    COMMAND_CLEANING = f"{_BASE}/command/cleaning"
    COMMAND_ALL = f"{_BASE}/command/#"

    ACK = f"{_BASE}/ack"
    SERVICE_HEALTH = f"{_BASE}/service/health"
